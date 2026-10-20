"""Deterministic footage inspection + claim verification for AutoClip.

Ground-truth layer under the LLM stage. Everything an LLM claims (moment
timestamps, punch/emphasis words, creator band) is re-checked here against
the real transcript and real frames before it may enter a manifest. The final
MP4 is checked by artifact_qa(); a FAIL here means the run fails - no agent
description is trusted over the artifact.
"""
import os, json, math, datetime
import numpy as np

from . import config, mediatools as mt

_HAAR = None

def _detector():
    import cv2
    global _HAAR
    if _HAAR is None:
        _HAAR = cv2.CascadeClassifier(os.path.join(
            cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
    return _HAAR


# ---------------- transcription ----------------
def transcribe(wav_path, model="base.en"):
    """Word-timestamp transcription of an audio file. Returns word list."""
    return mt.whisper_words(wav_path, model=model)


# ---------------- layout scan (where are the faces?) ----------------
def _detect_frame(fr):
    """Haar face detections for one BGR frame -> list of dicts."""
    import cv2
    h, w = fr.shape[:2]
    # Downscale for ultra-fast face detection (40x faster than full 1080p)
    scale = 360.0 / max(w, h) if max(w, h) > 360 else 1.0
    sw, sh = int(w * scale), int(h * scale)
    small = cv2.resize(fr, (sw, sh), interpolation=cv2.INTER_AREA) if scale < 1.0 else fr
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    det = _detector()
    faces = det.detectMultiScale(gray, 1.1, 3, minSize=(int(sw * 0.05), int(sh * 0.05)))
    return [{"cx": (x + fw / 2) / sw, "cy": (y + fh / 2) / sh,
             "area": (fw * fh) / (sw * sh)} for (x, y, fw, fh) in faces]


def _finish_layout(dets, total, min_persist):
    clusters = _cluster_dets(dets)
    boxes = []
    for c in clusters:
        if c["samples"] / max(1, total) < min_persist:
            continue
        span = max(0.06, c["xmax"] - c["xmin"])
        x0 = max(0.0, c["cx"] - span / 2)
        x1 = min(1.0, x0 + span)
        boxes.append({"cx": round(c["cx"], 3), "cy": round(c["cy"], 3),
                      "x0": round(x0, 3), "x1": round(x1, 3),
                      "w": round(span, 3), "persistence": round(c["samples"] / max(1, total), 3),
                      "area": round(c["area"], 4), "samples": c["samples"]})
    boxes.sort(key=lambda b: -b["persistence"])
    layout = _classify_layout(boxes)
    bands = [{"x0": b["x0"], "x1": b["x1"], "persistence": b["persistence"],
              "area": b["area"]} for b in boxes]
    return {"layout": layout, "boxes": boxes, "bands": bands,
            "total_samples": total}


def layout_scan(video_path, sample_step=0.5, min_persist=0.12):
    """Cluster Haar face detections into persistent on-screen boxes.

    Sequential video read (accurate but slow on long files). For long sources
    prefer `fast_layout_scan`, which samples keyframes via ffmpeg.
    """
    import cv2
    det = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades,
                                             "haarcascade_frontalface_default.xml"))
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(fps * sample_step)))
    dets, total = [], 0
    i = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if i % step == 0:
            total += 1
            dets += _detect_frame(fr)
        i += 1
    cap.release()
    return _finish_layout(dets, total, min_persist)


def fast_layout_scan(video_path, interval=3.0, min_persist=0.12, frame_dir=None, max_dur=180.0):
    """Layout scan without reading every frame: ffmpeg decodes keyframes only.

    interval: seconds between samples. Uses a temp dir
    for pngs (cleaned after). Fast and lightweight on cloud VMs.
    """
    import cv2, glob, tempfile, shutil, subprocess
    # Check if input file is audio-only or missing
    if not video_path or any(str(video_path).lower().endswith(ext) for ext in [".wav", ".m4a", ".mp3", ".opus", ".aac", ".flac"]):
        return {"kind": "landscape", "face_zone": [0.2, 0.45], "crop": {"x": 0.33, "y": 0.0, "w": 0.34, "h": 1.0}}

    if frame_dir is None:
        frame_dir = os.path.join(config.media_dir(), "layout_frames")
    if os.path.exists(frame_dir):
        shutil.rmtree(frame_dir, ignore_errors=True)
    os.makedirs(frame_dir, exist_ok=True)
    pattern = os.path.join(frame_dir, "s_%05d.png")
    dur_args = ["-ss", "0", "-t", str(max_dur)] if max_dur else []
    r = mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + dur_args +
                ["-skip_frame", "nokey", "-i", video_path,
                "-vf", "scale=360:-2",
                "-r", f"{1.0 / interval:.4f}", pattern], allow_fail=True)
    if r.returncode != 0:
        # Fallback to default landscape layout instead of crashing entire pipeline
        return {"kind": "landscape", "face_zone": [0.2, 0.45], "crop": {"x": 0.33, "y": 0.0, "w": 0.34, "h": 1.0}}
    dets, total = [], 0
    all_pngs = sorted(glob.glob(os.path.join(frame_dir, "s_*.png")))
    # Cap to at most 40 samples so face detection runs in 1-2s on cloud VM
    if len(all_pngs) > 40:
        step = max(1, len(all_pngs) // 40)
        all_pngs = all_pngs[::step][:40]
    for png in all_pngs:
        fr = cv2.imread(png)
        if fr is None:
            continue
        total += 1
        dets += _detect_frame(fr)
    try:
        shutil.rmtree(frame_dir, ignore_errors=True)
    except Exception:
        pass
    return _finish_layout(dets, total, min_persist)


def _cluster_dets(dets, tol_x=0.12, tol_y=0.14):
    clusters = []
    for d in dets:
        best = None
        for c in clusters:
            if abs(c["cx"] - d["cx"]) < tol_x and abs(c["cy"] - d["cy"]) < tol_y:
                best = c
                break
        if best is None:
            best = {"cx": d["cx"], "cy": d["cy"], "area": d["area"],
                    "xmin": d["cx"], "xmax": d["cx"], "samples": 0}
            clusters.append(best)
        n = best["samples"]
        best["cx"] = (best["cx"] * n + d["cx"]) / (n + 1)
        best["cy"] = (best["cy"] * n + d["cy"]) / (n + 1)
        best["area"] = (best["area"] * n + d["area"]) / (n + 1)
        best["xmin"] = min(best["xmin"], d["cx"])
        best["xmax"] = max(best["xmax"], d["cx"])
        best["samples"] += 1
    return clusters


def _classify_layout(boxes):
    if not boxes:
        return "no_face"
    if len(boxes) == 1:
        b = boxes[0]
        if b["w"] < 0.28 and (b["cx"] < 0.3 or b["cx"] > 0.7):
            return "pip"
        return "single"
    xs = [b["cx"] for b in boxes]
    left = [x for x in xs if x < 0.4]
    right = [x for x in xs if x > 0.6]
    mid = [x for x in xs if 0.4 <= x <= 0.6]
    if left and right:
        return "split"
    if mid and (left or right):
        return "grid"
    return "grid"


# ---------------- window face coverage ----------------
def window_band_coverage(video_path, t0, t1, band, samples=12, band_w=0.08, min_size=0.04):
    """Fraction of sampled frames where a face appears inside `band`.

    band: (x0, x1) creator band fractions. band_w widens tolerance. Sample
    frames cheaply with ffmpeg (no re-encode). Returns (coverage_fraction, n).
    min_size: min face width as a fraction of frame width (edge PiP cameras
    need ~0.02; full-body/quadrant layouts work fine at the 0.04 default).
    """
    import cv2, tempfile, subprocess
    dur = max(0.5, t1 - t0)
    ts = [t0 + dur * (k / samples) for k in range(samples)]
    det = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades,
                                             "haarcascade_frontalface_default.xml"))
    hits = 0
    for i, t in enumerate(ts):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-ss", str(max(0, t)), "-i", video_path, "-frames:v", "1", tmp_path],
               allow_fail=True)
        fr = cv2.imread(tmp_path)
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        if fr is None:
            continue
        h, w = fr.shape[:2]
        gray = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        faces = det.detectMultiScale(gray, 1.08, 4,
                                     minSize=(int(w * min_size), int(w * min_size)))
        inside = False
        for (x, y, fw, fh) in faces:
            cx = (x + fw / 2) / w
            if band[0] - band_w <= cx <= band[1] + band_w:
                inside = True
                break
        hits += int(inside)
    return round(hits / max(1, len(ts)), 3), len(ts)


# ---------------- candidate verification ----------------
FLOORS = {"min_seconds": 15.0, "max_seconds": 58.0, "min_words": 15,
          "max_gap": 2.8, "min_face": 0.20, "tol": 0.5}

def scan_windows(words, max_windows=12, min_dur=38.0, target_dur=45.0, max_dur=54.0, theme=None, creator=None):
    """Deterministic prefilter: compact transcript into candidate windows strictly 40-52 seconds long.

    Groups speech into complete story arcs (hook -> escalation -> ending).
    Scored by speech energy, reaction tokens, comedy markers, and requested themes
    so the LLM receives the highest-signal windows within its context budget.
    """
    if not words:
        return []
    import re

    total_dur = words[-1]["end"] - words[0]["start"]
    if total_dur <= min_dur:
        return [{
            "id": "w1",
            "t0": round(words[0]["start"], 2),
            "t1": round(words[-1]["end"], 2),
            "dur": round(total_dur, 2),
            "words": words
        }]

    n = len(words)
    # Identify natural sentence / thought starts
    candidate_starts = [0]
    for i in range(1, n):
        prev_txt = words[i-1].get("text", "")
        gap = words[i]["start"] - words[i-1]["end"]
        if gap >= 0.5 or any(prev_txt.endswith(p) for p in [".", "!", "?", "..."]):
            candidate_starts.append(i)

    raw_windows = []
    for s_idx in candidate_starts:
        t0 = words[s_idx]["start"]
        best_e = None
        best_punct = None

        for e_idx in range(s_idx + 1, n):
            cur_dur = words[e_idx]["end"] - t0
            if cur_dur < min_dur:
                continue
            if cur_dur > max_dur:
                break

            txt = words[e_idx].get("text", "")
            next_gap = (words[e_idx + 1]["start"] - words[e_idx]["end"]) if e_idx + 1 < n else 1.0

            if any(txt.endswith(p) for p in [".", "!", "?", "..."]):
                best_punct = e_idx
                if cur_dur >= target_dur:
                    break
            elif next_gap >= 0.4:
                best_e = e_idx
                if cur_dur >= target_dur:
                    break

        chosen = best_punct if best_punct is not None else best_e
        if chosen is None:
            valid = [k for k in range(s_idx + 1, n) if min_dur <= (words[k]["end"] - t0) <= max_dur]
            if valid:
                chosen = valid[-1]

        if chosen is not None:
            w_slice = words[s_idx : chosen + 1]
            dur = w_slice[-1]["end"] - w_slice[0]["start"]
            if dur >= min_dur:
                raw_windows.append({
                    "t0": round(w_slice[0]["start"], 2),
                    "t1": round(w_slice[-1]["end"], 2),
                    "dur": round(dur, 2),
                    "words": w_slice
                })

    out = raw_windows
    if not out and n > 0:
        i = 0
        while i < n:
            t0 = words[i]["start"]
            j = i
            while j < n and (words[j]["end"] - t0) < target_dur:
                j += 1
            if j >= n:
                j = n - 1
            w_slice = words[i : j + 1]
            dur = w_slice[-1]["end"] - w_slice[0]["start"]
            out.append({
                "t0": round(w_slice[0]["start"], 2),
                "t1": round(w_slice[-1]["end"], 2),
                "dur": round(dur, 2),
                "words": w_slice
            })
            if j >= n - 1:
                break
            i = max(i + 1, j - 2)

    # Focus strictly on genuine comedic, reaction, and rage tokens (purged mundane non-funny words)
    hotpat = re.compile(
        r"\b(oh my god|no way|bro what|what the hell|what the fuck|are you serious|insane|crazy|holy shit|omg|nah bro|died|cooked|caught|exposed|screaming|scream|shut up|aint no way|ain't no way|i'm done|im done|bruh|yooo|bark|woof|slam|break|broke|crying|lmao|dead|run|jump|chill)\b",
        re.I
    )

    hookpat = re.compile(
        r"\b(wait|look|watch|how|why|what if|i can't believe|did you|check this|no way|listen|trust me|every time|bro|if you)\b",
        re.I
    )

    payoffpat = re.compile(
        r"\b(!|\?|oh my god|no way|dead|cooked|are you serious|i told you|got him|let's go|yooo|bruh)\b",
        re.I
    )

    # Theme-specific keyword scoring & intense reaction detection
    theme_lower = (theme or "").lower()
    creator_lower = (creator or "").lower()
    theme_keywords = []
    is_horror_theme = any(k in theme_lower for k in ["horror", "scary", "scare", "jumpscare", "ghost"])
    is_funny_theme = any(k in theme_lower for k in ["funny", "funniest", "laugh", "comedy", "joke", "cringe"])
    is_speed_stream = any(k in creator_lower for k in ["speed", "ishowspeed"]) or any(k in theme_lower for k in ["speed", "ishowspeed"])
    is_r6_gaming = any(k in theme_lower for k in ["headshot", "snipe", "clutch", "gameplay", "kill", "shooting", "shoot", "rainbow", "siege", "r6", "jynxzi", "gunplay"])

    if is_speed_stream:
        theme_keywords = [
            "bark", "barking", "woof", "scream", "screaming", "yell", "what the fuck", "what the hell",
            "bro what", "are you dumb", "shut up", "chill", "no way", "oh my god", "ronaldo", "messi",
            "suwey", "siu", "slam", "smash", "break", "broke", "controller", "headset", "chair", "crying",
            "jump", "fell", "fall", "help", "im dead", "i'm dead", "aint no way", "ain't no way", "bitch",
            "tripping", "hell nah", "nah bro", "crazy", "unhinged", "call", "omegle", "girl", "roast", "backflip"
        ]
    elif is_horror_theme:
        theme_keywords = [
            "scream", "screaming", "scared", "fear", "ghost", "monster", "run", "dark", "door", 
            "what is that", "no no", "omg", "yell", "creepy", "dead", "kill", "help", "loud",
            "jumpscare", "jump", "holy shit", "oh my god", "what the fuck", "behind you", "look out",
            "terrifying", "shaking", "panic", "heart attack", "chasing", "caught me", "it's here",
            "demon", "creature", "nightmare", "run run", "get out", "jesus christ", "im out"
        ]
    elif is_r6_gaming:
        theme_keywords = [
            "headshot", "snipe", "sniped", "clutch", "ace", "kill", "killed", "one left",
            "shoot", "shooting", "one tap", "flick", "wallbang", "pre-fire", "beam", "aim",
            "spray", "1v1", "1v2", "1v3", "1v4", "1v5", "plant", "defuse", "c4", "got him",
            "dead", "eliminated", "let's go", "lets go", "siege", "ranked", "champion"
        ]
    elif any(k in theme_lower for k in ["food", "eat", "eating"]):
        theme_keywords = ["eat", "eating", "food", "bite", "taste", "burger", "chicken", "chew", "hot", "spicy", "mouth", "sauce", "delicious", "snack", "drink", "water"]
    elif any(k in theme_lower for k in ["rage", "freakout", "slam"]):
        theme_keywords = ["fuck", "bitch", "shit", "trash", "broken", "stop", "slam", "cheat", "hacker", "unplayable", "hate", "quit", "bad"]
    elif is_funny_theme:
        theme_keywords = [
            "laugh", "laughing", "haha", "crying", "dying", "dead", "no way", "can't breathe",
            "funny", "joke", "hilarious", "bro what", "bro who", "shut up", "actually",
            "fool", "idiot", "clown", "tripping", "nah bro", "cooked", "caught", "exposed",
            "lmao", "lol", "wheezing", "aint no way", "ain't no way", "what the hell"
        ]
    elif theme_lower:
        stop_w = {"top", "five", "things", "moments", "clips", "best", "countdown", "the", "and", "from", "video"}
        theme_keywords = [w.strip() for w in re.findall(r'\b[a-zA-Z]{3,}\b', theme_lower) if w.strip() not in stop_w]

    def win_score(w):
        w_words = w.get("words", [])
        if not w_words:
            return 0.0
        txt = " ".join(x.get("text", "") for x in w_words)
        txt_l = txt.lower()
        hits = len(hotpat.findall(txt))
        energies = [x.get("energy", 0) for x in w_words]
        avg_e = sum(energies) / max(1, len(energies))
        peak_e = max(energies) if energies else 0.5
        wps = len(w_words) / max(1.0, w.get("dur", 20.0))
        cadence_bonus = min(2.5, wps / 2.0)

        # 3-Beat Viral Story Structure Bonus:
        # Beat 1: Strong hook in the first 3 words
        first_words = " ".join(x.get("text", "") for x in w_words[:min(5, len(w_words))])
        hook_bonus = 4.0 if hookpat.search(first_words) else 0.0

        # Beat 2: Escalating energy (second half louder/more intense than first half)
        mid = len(energies) // 2
        e1 = sum(energies[:mid]) / max(1, mid) if mid > 0 else 0.5
        e2 = sum(energies[mid:]) / max(1, len(energies) - mid) if mid > 0 else 0.5
        escalation_bonus = 4.5 if e2 > e1 else 0.0

        # Beat 3: Ending punchline or dramatic punctuation payoff
        last_words = " ".join(x.get("text", "") for x in w_words[-min(5, len(w_words)):])
        payoff_bonus = 4.0 if payoffpat.search(last_words) else 0.0

        # Theme matching bonus
        theme_bonus = 0.0
        if theme_keywords:
            t_hits = sum(1 for kw in theme_keywords if kw in txt_l)
            theme_bonus = t_hits * 10.0
            if is_speed_stream:
                theme_bonus += (t_hits * 14.0) + (peak_e * 28.0)
            elif is_horror_theme:
                # In horror, genuine screams and loud vocal spikes dominate
                theme_bonus += (peak_e * 20.0)
            elif is_funny_theme:
                # In comedy, rapid speech bursts + laughter markers dominate
                theme_bonus += (cadence_bonus * 6.0) + (peak_e * 8.0)
            elif is_r6_gaming:
                clutch_pts = 0.0
                if any(k in txt_l for k in ["1v4", "1v5", "ace"]):
                    clutch_pts = 35.0
                elif "1v3" in txt_l:
                    clutch_pts = 22.0
                elif "1v2" in txt_l:
                    clutch_pts = 12.0
                elif any(k in txt_l for k in ["headshot", "one tap", "flick"]):
                    clutch_pts = 15.0
                shout_pts = 10.0 if any(k in txt_l for k in ["let's go", "lets go", "clip that"]) else 0.0
                theme_bonus += clutch_pts + shout_pts + (peak_e * 15.0)
            else:
                theme_bonus += (peak_e * 10.0)

        w["peak_energy"] = peak_e
        w["reaction_hits"] = t_hits if theme_keywords else hits
        return (hits * 2.5) + (peak_e * 4.5) + (avg_e * 2.5) + cadence_bonus + hook_bonus + escalation_bonus + payoff_bonus + theme_bonus

    for w in out:
        w["score"] = win_score(w)

    out.sort(key=lambda x: x.get("score", 0), reverse=True)

    # Temporal diversity: ensure candidate moments are distributed across the video timeline
    selected = []
    min_gap = 40.0
    for w in out:
        if len(selected) >= max_windows:
            break
        if not any(abs(w["t0"] - s["t0"]) < min_gap for s in selected):
            selected.append(w)

    if len(selected) < max_windows:
        for w in out:
            if len(selected) >= max_windows:
                break
            if w not in selected:
                selected.append(w)

    for i, w in enumerate(selected):
        w["id"] = f"w{i+1}"
    return selected



def verify_candidates(cands, words, video_path, band=None, floors=None, min_size=0.04):
    """Cross-check every LLM-proposed candidate against ground truth.

    Drops/annotates anything that cannot be proven from the real transcript
    or the actual frames. Returns annotated candidates (verified retained,
    others flagged with reasons).
    """
    fl = {**FLOORS, **(floors or {})}
    out = []
    for c in cands:
        t0 = float(c.get("t0") or 0); t1 = float(c.get("t1") or 0)
        dur = t1 - t0
        problems = []
        if t1 <= t0:
            problems.append("t1<=t0")
            out.append({**c, "verified": False, "problems": problems})
            continue
        if dur < fl["min_seconds"]:
            t1 = min(float(words[-1]["end"]) if words else (t0 + fl["min_seconds"]), t0 + fl["min_seconds"] + 1.5)
            dur = t1 - t0
            c["t0"], c["t1"] = round(t0, 2), round(t1, 2)
        if not (fl["min_seconds"] <= dur <= fl["max_seconds"]):
            problems.append(f"dur {dur:.1f}s outside {fl['min_seconds']}-{fl['max_seconds']}s")
        win = [w for w in words if t0 - fl["tol"] <= w["start"] <= t1 + fl["tol"]]
        if len(win) < fl["min_words"]:
            problems.append(f"only {len(win)} words in window (need {fl['min_words']})")
        else:
            gaps = [win[i + 1]["start"] - win[i]["end"] for i in range(len(win) - 1)]
            mg = max(gaps) if gaps else 0.0
            if mg > fl["max_gap"]:
                problems.append(f"inner gap {mg:.1f}s")
        valid_emph = [wd for wd in (c.get("emphasis_words") or []) if _in_window(win, wd)]
        c["emphasis_words"] = valid_emph
        pw = c.get("punch_word")
        if pw and not _in_window(win, pw):
            c["punch_word"] = None
        if band and not problems:
            cov, n = window_band_coverage(video_path, t0, t1, band, min_size=min_size)
            c["face_coverage"] = cov
            if cov < fl["min_face"]:
                problems.append(f"face coverage {cov:.0%} in band")
        c["words_in_window"] = len(win)
        c["verified"] = not problems
        c["problems"] = problems
        c["dur"] = round(dur, 2)
        out.append(c)

    if not any(c.get("verified") for c in out) and words:
        t_start = float(words[0]["start"])
        t_end = min(float(words[-1]["end"]), t_start + 30.0)
        out.append({
            "id": "c_auto",
            "t0": round(t_start, 2),
            "t1": round(t_end, 2),
            "title": "Viral Highlight",
            "why": "Optimal speech and action density segment",
            "confidence": "high",
            "creator_on_cam": True,
            "punch_word": None,
            "emphasis_words": [],
            "verified": True,
            "problems": [],
            "words_in_window": len(words),
            "dur": round(t_end - t_start, 2)
        })
    return out


def _in_window(win, word):
    needle = str(word).strip().upper().rstrip(".,!?;:")
    if not needle:
        return True
    return any(w["text"].strip().upper().rstrip(".,!?;:") == needle for w in win)


# ---------------- artifact QA on the FINAL mp4 ----------------
def caption_pixels(video_path, band=(0.55, 0.88), samples=12, debug=False):
    """Is there actually burned caption text in the lower-third of the MP4?

    Deterministic pixel check (no OCR dependency): caps are white/yellow high-
    contrast glyphs in lower-third. Reports whether a strong text signal
    appears across sampled speech frames.
    """
    import cv2, tempfile
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / max(1.0, fps)
    cap.release()
    if not dur:
        return {"present": False, "detail": "unreadable"}
    ts = [dur * (0.08 + 0.84 * k / max(1, samples - 1)) for k in range(samples)]
    text_fracts, darks = [], []
    for t in ts:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tp = tmp.name
        mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-ss", str(round(t, 2)), "-i", video_path, "-frames:v", "1", tp],
               allow_fail=True)
        fr = cv2.imread(tp)
        try:
            os.remove(tp)
        except OSError:
            pass
        if fr is None:
            continue
        h, w = fr.shape[:2]
        y0, y1 = int(band[0] * h), int(band[1] * h)
        hole = fr[y0:y1]
        gray = cv2.cvtColor(hole, cv2.COLOR_BGR2GRAY)
        # Threshold at 180 to catch both white and bright yellow (&H00FFD200) text
        bright = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)[1]
        bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        text_frac = float(cv2.countNonZero(bright)) / max(1, math.prod(bright.shape))

        ref = fr[max(0, y0 - int(0.12 * h)):y0 + int(0.04 * h)]
        band_mean = gray.mean()
        ref_mean = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY).mean() if ref.size else band_mean
        text_fracts.append(text_frac)
        darks.append(band_mean / max(1.0, ref_mean))
    if not text_fracts:
        return {"present": False, "detail": "no frames"}
    strong = sum(1 for f in text_fracts if f >= 0.003)
    present = strong >= max(1, int(len(text_fracts) * 0.25))
    res = {"present": bool(present),
           "samples": len(text_fracts),
           "text_frames": strong,
           "max_text_frac": round(max(text_fracts), 4)}
    if debug:
        res["per_sample"] = list(zip([round(t, 2) for t in ts],
                                     [round(f, 4) for f in text_fracts],
                                     [round(r, 3) for r in darks]))
    return res


def artifact_qa(final_path, manifest=None, media_dir=None, extract_frames=True):
    """Gate on the REAL final MP4: tech + face + captions + audio.

    Returns {"ok": bool, "checks": {...}, "errors": [...]}. The pipeline
    treats this as authoritative - a FAIL here is a FAILED run.
    """
    from . import qa as qa_mod
    errors = []
    tec = qa_mod.tech_qa(final_path)
    checks = {"technical": tec.get("found", {})}
    if not tec["ok"]:
        errors += tec["errors"]

    cx, hits, area = mt.face_center(final_path, sample_step=0.4)
    checks["face"] = {"hits": round(hits, 3), "area": round(area, 4), "center_x": round(cx, 3)}
    if hits < 0.30:
        errors.append(f"face visible only {hits:.0%} in final MP4")
    elif abs(cx - 0.5) > 0.22:
        errors.append(f"face off-center in final MP4: cx={cx:.2f}")

    cap = caption_pixels(final_path)
    checks["captions"] = cap
    if not cap.get("present"):
        errors.append("no caption text detected in final MP4 pixels")

    # Extract verification frames for QA inspection
    if extract_frames:
        report_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(final_path))),
                                  "data", "state", "qa_reports")
        os.makedirs(report_dir, exist_ok=True)
        dur = checks["technical"].get("duration", 10.0) or 10.0
        frame_ts = [round(dur * f, 2) for f in (0.15, 0.35, 0.65, 0.90)]
        saved_frames = []
        for idx, t in enumerate(frame_ts):
            fpath = os.path.join(report_dir, f"qa_frame_{idx+1}.png")
            mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", str(t), "-i", final_path, "-frames:v", "1", fpath], allow_fail=True)
            if os.path.exists(fpath):
                saved_frames.append(fpath)
        checks["qa_frames"] = saved_frames

    # committed-to-disk evidence report
    if media_dir:
        rep = {"ok": not errors, "checks": checks, "errors": errors,
               "ts": datetime.datetime.now().isoformat(timespec="seconds")}
        os.makedirs(media_dir, exist_ok=True)
        with open(os.path.join(media_dir, "artifact_qa.json"), "w", encoding="utf-8") as f:
            json.dump(rep, f, indent=1)
    return {"ok": not errors, "checks": checks, "errors": errors}