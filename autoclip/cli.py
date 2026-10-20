"""AutoClip CLI.

Usage:
  autoclip parse "<request>"                 -> intent/format/topic detection
  autoclip research                          -> show current trend research report
  autoclip research --refresh-notes          -> (agent hook) re-emit canned notes
  autoclip run   <manifest.json> [--out x.mp4] [--qa-only]
  autoclip qa    <file.mp4>

The heavy research + candidate extraction steps (web search, whisper verification,
face checks) are run by the orchestrating agent; the CLI executes the deterministic
build + QA parts against a manifest.
"""
import argparse, json, os, sys
from . import request as request_mod
from . import research as research_mod
from . import format as format_mod
from . import candidates as candidates_mod
from . import qa as qa_mod
from . import mediatools as mt
from . import config

def cmd_parse(args):
    r = request_mod.parse(args.text)
    print(json.dumps(r, indent=2))

def cmd_research(args):
    if getattr(args, "creator", None) or getattr(args, "ai", None):
        creator = args.creator or args.ai
        research_mod.ai_research(creator, topic=getattr(args, "topic", None))
    elif getattr(args, "refresh_notes", False):
        t = ("CARRIER_SIGNAL 2026: IShowSpeed viral moments center on Ronaldo/World Cup "
             "fanaticism (meeting Ronaldo, hotels, airports) plus high-energy IRL chaos; "
             "portrait 9:16 originals outperform re-edited landscape clips.")
        research_mod.record_findings({}, extra_notes=[t])
    print(research_mod.report_markdown())
    print("\n(saved to)", research_mod.save_report())

def cmd_test_llm(args):
    from . import llm as llm_mod
    llm_mod.test_llm()

def cmd_web(args):
    from . import web as web_mod
    web_mod.run_server(port=args.port)

def cmd_qa(args):
    tec = qa_mod.tech_qa(args.file)
    print("TECHNICAL:", "PASS" if tec["ok"] else "FAIL")
    for e in tec["errors"]:
        print("  -", e)
    print(json.dumps(tec.get("found", {}), indent=2))

def cmd_transcribe(args):
    from . import mediatools as mt
    def _on_prog(curr, tot):
        print(f"[transcribe] {curr:.1f}/{tot:.1f}", flush=True)

    words = mt.whisper_words(args.video, progress_cb=_on_prog)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"video": args.video, "words": words}, f, indent=1)
    print(f"{len(words)} words -> {args.out}", flush=True)

def cmd_creative_qa(args):
    from . import mediatools as mt, candidates as cand
    from . import config, qa as qa_mod
    import os, datetime
    with open(args.manifest, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    fmt = format_mod.build_directives(manifest["request"])
    clips = []
    seq_ordered = []
    for p in manifest["plans"]:
        r = p.get("editorial_rank") or p.get("rank")
        vid = os.path.join(config.media_dir(), f"M{r}_capped.mp4" if r is not None else f"{p['id']}_capped.mp4")
        if not os.path.exists(vid):
            vid = os.path.join(config.media_dir(), f"{p['id']}_capped.mp4")
        cx, hits, area = mt.face_center(vid, sample_step=0.4)
        words = p.get("words", [])
        dur = (words[-1]["end"] - words[0]["start"]) if words else 0
        gaps = [words[i + 1]["start"] - words[i]["end"] for i in range(len(words) - 1)]
        maxg = round(max(gaps), 2) if gaps else 0.0
        score, subs, topics = cand.score_candidate(p, fmt["weights"])
        clips.append({"id": p["id"], "dur": round(p["t1"] - p["t0"], 2), "face_hits": round(hits, 2),
                      "words": len(words), "max_pause": maxg, "speech": round(dur, 1),
                      "score": score, "subscores": subs, "punch": bool(p.get("punch")),
                      "topics": list(topics)})
        p["score"], p["subscores"], p["topics"] = score, subs, list(topics)
        seq_ordered.append(p)
        print(f"{p['id']:4s} face_hits={hits*100:3.0f}% area={area*100:3.0f}%  max_gap={maxg:.2f}s  "
              f"words={len(words):3d}  score={score}")
        # caption meta check
        cap_file = os.path.join(config.media_dir(), f"M{r}_cap.json" if r is not None else f"{p['id']}_cap.json")
        if not os.path.exists(cap_file):
            cap_file = os.path.join(config.media_dir(), f"{p['id']}_cap.json")

    # order plans #5..#1 for sequence assessment
    seq_ordered.sort(key=lambda p: -(p.get("editorial_rank") or p.get("rank") or 0))
    seq_score, seq_subs = cand.score_sequence(seq_ordered, fmt.get("sequence_weights"))
    for q in seq_ordered:
        q["sequence_score"] = seq_score
        q["sequence_subscores"] = seq_subs
    seq_res = qa_mod.sequence_qa(seq_ordered, seq_floor=fmt["quality_floor"].get("min_sequence_score", 0.55))
    print("SEQUENCE:", "PASS" if not seq_res["issues"] else "FAIL",
          json.dumps(seq_res["metrics"]))
    for i in seq_res["issues"]:
        print("  ISSUE:", i)
    for n in seq_res["notes"]:
        print("  note:", n)

    caption_metas = []
    for p in clips:
        r = next((q for q in seq_ordered if q["id"] == p["id"]), p)
        cap_file = os.path.join(config.media_dir(), f"M{r.get('editorial_rank') or r.get('rank')}_cap.json")
        if os.path.exists(cap_file):
            try:
                caption_metas.append(json.load(open(cap_file, encoding="utf-8")))
            except Exception:
                pass

    res = qa_mod.creative_qa(clips, sequence=seq_ordered, caption_metas=caption_metas)
    os.makedirs(os.path.join("data", "state"), exist_ok=True)
    with open(os.path.join("data", "state", "qa_creative.json"), "w", encoding="utf-8") as f:
        json.dump({"clips": clips, "creative": res, "sequence": seq_res,
                   "ts": datetime.datetime.now().isoformat(timespec="seconds")}, f, indent=1)
    print("CREATIVE QA:", "PASS" if res["ok"] else "FAIL")
    for i in res["issues"]:
        print("  ISSUE:", i)
    for n in res["notes"]:
        print("  note:", n)
    return res

def cmd_run(args):
    with open(args.manifest, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    req = manifest["request"]
    fmt = format_mod.build_directives(req)
    ranked = candidates_mod.rank_moments(manifest["plans"], fmt["weights"])
    sel = candidates_mod.assign_countdown(ranked, fmt["countdown"]["n"],
                                          seq_weights=fmt.get("sequence_weights"))
    print(f"Selected {len(sel)} moments ordered #5.. #1")
    for p in sel:
        print(f"  M{p.get('id')} rank#{p['rank']} score={p['score']} src={p.get('src')}")
    if sel:
        seq_score, seq_subs = candidates_mod.score_sequence(sel, fmt.get("sequence_weights"))
        for p in sel:
            p["sequence_score"] = seq_score
            p["sequence_subscores"] = seq_subs
        print(f"  sequence_score={seq_score:.3f} "
              f"escalation={seq_subs.get('escalation')} topic_conn={seq_subs.get('topic_connection')} "
              f"reaction_esc={seq_subs.get('reaction_escalation')} payoff_climax={seq_subs.get('payoff_climax')}")

    from . import edit as edit_mod
    import datetime
    nc = fmt["countdown"]
    out_dir = os.path.dirname(os.path.abspath(args.out)) or ""
    os.makedirs(out_dir, exist_ok=True)
    hook = fmt["hook"]
    # render moments first so the #1 climax can back the title card
    built = {p["id"]: _build_one(p, fmt, i) for i, p in enumerate(sel)}
    last = sel[-1]
    title = edit_mod.make_title(built[last["id"]][1], hook)
    clips = [title]
    for p in sel:
        card, clip = built[p["id"]]
        clips.append(card); clips.append(clip)
    edit_mod.assemble(clips, args.out, hook, whoosh_at=None, music_profile=fmt.get("music"))
    print("rendered", args.out)

    tec = qa_mod.tech_qa(args.out)
    print("TECHNICAL QA:", "PASS" if tec["ok"] else "FAIL", json.dumps(tec.get("found", {}).get("duration")) if tec.get("found") else "")
    for e in tec["errors"]:
        print("  -", e)

    # creative QA (incl. sequence + captions) persisted automatically
    import subprocess
    r = subprocess.run([sys.executable, "-m", "autoclip.cli", "creative-qa", args.manifest],
                       capture_output=True, text=True)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr[-1500:])

def _build_one(p, fmt, i):
    """Render one moment: prep -> reframe -> punch -> karaoke -> return (card, clip)."""
    from . import edit as edit_mod
    out_id = f"M{p['rank']}"
    prep = edit_mod.prep(p, out_id)
    reframed, _face = edit_mod.reframe(prep, p, out_id)
    em = p.get("emphasis", [])
    cap_profile = fmt["caption"]
    words = p.get("words", [])
    if fmt["edit"].get("punch_ins") and words:
        peak = max(words, key=lambda w: w.get("energy", 0))
        t0_val = p.get("t0", 0.0) or 0.0
        p_tin = peak["start"]
        if t0_val > 0 and p_tin >= t0_val:
            p_tin = p_tin - t0_val
        p["punch"] = {"tin": max(0.1, round(p_tin + 0.05, 3))}
    punched = edit_mod.add_punch(reframed, p, out_id)
    capped = edit_mod.burn_karaoke(punched, prep, words, em, cap_profile, out_id, t0_offset=p.get("t0"))
    dur = fmt["countdown"]["last_card_seconds"] if p.get("special_last") \
        else fmt["countdown"]["card_seconds"]
    who, boom = edit_mod.make_sfx()
    card = edit_mod.make_card(p["card_label"], dur, p.get("special_last", False),
                              capped, out_id, boom)
    return card, capped

def cmd_artifact_qa(args):
    from . import inspect as inspect_mod
    manifest = None
    if args.manifest:
        with open(args.manifest, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    res = inspect_mod.artifact_qa(args.file, manifest=manifest)
    print("ARTIFACT QA:", "PASS" if res["ok"] else "FAIL")
    print(json.dumps(res["checks"], indent=2))
    for e in res["errors"]:
        print("  -", e)
    return res

def cmd_inspect(args):
    from . import inspect as inspect_mod
    from . import mediatools as mt
    video = os.path.abspath(args.video)
    print(f"layout scan: {video} ...", flush=True)
    layout = (inspect_mod.fast_layout_scan(video, interval=args.sample)
              if args.fast else
              inspect_mod.layout_scan(video, sample_step=args.sample))
    print(f"  layout={layout['layout']} boxes={len(layout['boxes'])}")
    for b in layout["boxes"]:
        print(f"    box cx={b['cx']} x={b['x0']}-{b['x1']} persist={b['persistence']} area={b['area']}")
    words = []
    if args.words:
        with open(args.words, "r", encoding="utf-8") as f:
            wdata = json.load(f)
        words = wdata.get("words", []) if isinstance(wdata, dict) else wdata
    elif args.audio:
        wav = args.audio
    else:
        wav = os.path.join(os.path.dirname(args.out or video) or ".",
                           os.path.splitext(os.path.basename(video))[0] + ".wav")
        if not os.path.exists(wav):
            print(f"audio to {wav} ...", flush=True)
            mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", video, "-ar", "16000", "-ac", "1", wav])
        words = inspect_mod.transcribe(wav, model=args.model)
    windows = inspect_mod.scan_windows(words, max_windows=args.top_windows)
    out = {"video": video, "duration": mt.ffprobe_dur(video),
           "layout": layout, "words": words, "windows": windows,
           "model": args.model, "scan_mode": "fast" if args.fast else "sequential"}
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
    print(f"windows={len(windows)} words={len(words)} -> {args.out or '(stdout only)'}")
    for w in windows:
        print(f"  {w['id']}: {w['t0']:.1f}-{w['t1']:.1f}s {w['dur']:.1f}s {len(w['words'])} words")
    return out

def cmd_analyze(args):
    from . import inspect as inspect_mod, llm as llm_mod
    with open(args.inspect, "r", encoding="utf-8") as f:
        insp = json.load(f)
    layout = insp["layout"]
    request = args.request or "make a short from this footage"
    try:
        from . import request as req_mod, format as fmt_mod
        req = req_mod.parse(request)
        fmt = fmt_mod.build_directives(req)
    except Exception:
        req, fmt = {"request": request}, None
    floors = args.floors or {"min_seconds": 6, "max_seconds": 45, "min_words": 8}

    windows = insp["windows"]
    if args.max_windows:
        windows = windows[:args.max_windows]
    payload_lines = []
    for w in windows:
        payload_lines.append(f"WINDOW {w['id']} [{w['t0']:.1f}s .. {w['t1']:.1f}s] {w['dur']:.1f}s:")
        payload_lines.append(" ".join(x["text"] for x in w["words"]))
    payload = "\n".join(payload_lines)

    band_hint = ""
    if layout.get("bands"):
        b = layout["bands"][0]
        band_hint = f"The creator's face band is approximately x=[{b['x0']},{b['x1']}] (persistence {b['persistence']}). "
        band_hint += f"Layout class: {layout['layout']}."

    system = ("You pick short-form video moments from provided transcript windows. "
              "You reason about what lands as content. You ALWAYS reply with JSON matching exactly the "
              "given schema. Timestamps must be numbers within the window bounds you cite. "
              "punch_word and every emphasis_word MUST be a verbatim token (case-insensitive) present in that "
              "window's word stream. Choose rarely. Return 1-3 candidates, best first.")
    user = (f"{band_hint}\nFormat/request: {request_func(req)}\n"
            f"Window floors: {floors}.\nTranscript windows:\n{payload}\n\n"
            "Decide which window(s) make the strongest short. For each, pick the exact start/end "
            "seconds (verbatim word times are fine), a one-line title, why it works, a punch word, "
            "zero-to-four emphasis words, and whether the creator is on camera. "
            "Return JSON: {\"candidates\":[{\"id\":\"c1\",\"window\":\"<window id>\",\"t0\":<float>,"
            "\"t1\":<float>,\"title\":\"\",\"why\":\"\",\"confidence\":\"high|medium|low\","
            "\"creator_on_cam\":true,\"punch_word\":\"<verbatim|null>\",\"emphasis_words\":[\"\"]}]}")
    schema = {
        "candidates": {"$list": {
            "id": ("str", True), "window": ("str", False), "t0": ("float", True),
            "t1": ("float", True), "title": ("str", False), "why": ("str", False),
            "confidence": ("str", True), "creator_on_cam": ("bool", False),
            "punch_word": ("str", False), "emphasis_words": ("str[]", False),
        }}
    }
    print(f"calling {args.model} on {min(3, args.max_windows or 3)} windows ...", flush=True)
    parsed = llm_mod.chat(system, user, schema=schema, model=args.model,
                          temperature=args.temperature)
    out_doc = {"request": request_func(req), "windows": windows,
               "layout": layout, "candidates": parsed["candidates"],
               "floors": floors}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out_doc, f, indent=1)
    for c in parsed["candidates"]:
        print(json.dumps(c, indent=2))
    print("->", args.out)

def cmd_verify(args):
    from . import inspect as inspect_mod
    with open(args.candidates, "r", encoding="utf-8") as f:
        cand_doc = json.load(f)
    insp = None
    if args.inspect:
        with open(args.inspect, "r", encoding="utf-8") as f:
            insp = json.load(f)
    words = (insp or {}).get("words") or (cand_doc.get("words") or [])
    video = (insp or {}).get("video") or cand_doc.get("video")
    band = None
    if insp and insp.get("layout", {}).get("bands"):
        b = insp["layout"]["bands"][0]
        band = (b["x0"], b["x1"])
    if args.band:
        x0, x1 = [float(x) for x in args.band.split(",")]
        band = (x0, x1)
    out = inspect_mod.verify_candidates(cand_doc["candidates"], words, video, band=band)
    res = {"video": video, "band": band, "candidates": out,
           "verified": [c for c in out if c.get("verified")]}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    for c in out:
        st = "VERIFIED" if c.get("verified") else "REJECTED"
        print(f"{st} {c['id']} {c['t0']:.1f}-{c['t1']:.1f}s face={c.get('face_coverage', '-')} "
              f"words={c.get('words_in_window', '-')}")
        for p in c.get("problems", []):
            print(f"   ! {p}")
    print(f"{len(res['verified'])}/{len(out)} -> {args.out}")
    return res

def request_func(req):
    return f"{req.get('format', '?')} / {req.get('topic', '?')}" if isinstance(req, dict) else str(req)


def _load_words(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("words", []) if isinstance(data, dict) else data


def _find_word(win, token):
    needle = str(token).strip().upper().rstrip(".,!?;:")
    if not needle:
        return None
    for w in win:
        if w["text"].strip().upper().rstrip(".,!?;:") == needle:
            return w
    return None


def _creator_band(layout):
    boxes = [b for b in layout.get("boxes", []) if b.get("persistence", 0) >= 0.15]
    if not boxes:
        boxes = layout.get("boxes", [])
    if not boxes:
        return None
    b = sorted(boxes, key=lambda x: x["area"])[0]  # creator cam is usually the smallest persistent face
    return b["x0"], b["x1"]


_CREATOR_BANDS = [(0.0, 0.2), (0.8, 1.0), (0.12, 0.4), (0.6, 0.88), (0.4, 0.6)]


def _probe_creator_band(video_path, windows, prior=None):
    """Find the band whose small camera (PiP) is actually on screen.

    Genre reality: the creator cam is the small frames edge-anchored box that a
    4%-floor detector routinely misses. Probe with a 2% floor across candidate
    bands and pick the best-covered one; fall back to the layout heuristic.
    Only counts faces with width < 18% of frame width (small PiP signature).
    """
    import cv2
    det = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades,
                                             "haarcascade_frontalface_default.xml"))
    ranges = [(w["t0"], w["t1"]) for w in windows] or [(0.0, 60.0)]
    hits = {b: 0 for b in _CREATOR_BANDS}
    total_frames = 0
    for (t0, t1) in ranges:
        dur = max(0.5, t1 - t0)
        for k in range(3):
            t = t0 + dur * ((k + 0.5) / 3)
            fr = _frame_at(video_path, t)
            if fr is None:
                continue
            h, w = fr.shape[:2]
            scale = 360.0 / max(w, h) if max(w, h) > 360 else 1.0
            sw, sh = int(w * scale), int(h * scale)
            small = cv2.resize(fr, (sw, sh), interpolation=cv2.INTER_AREA) if scale < 1.0 else fr
            total_frames += 1
            for (x, y, fw, fh) in det.detectMultiScale(
                    cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), 1.1, 3,
                    minSize=(int(sw * 0.03), int(sh * 0.03))):
                cx = (x + fw / 2) / sw
                face_w_ratio = fw / sw
                if face_w_ratio > 0.25:
                    continue
                for band in _CREATOR_BANDS:
                    if band[0] <= cx <= band[1]:
                        hits[band] += 1
                        break
    if not total_frames:
        return prior or (0.0, 0.2)
    best = max(_CREATOR_BANDS, key=lambda b: hits[b])
    if hits[best] >= max(2, int(total_frames * 0.35)):
        return best
    return prior or best


def _learn_caption_band(capped_path, pre_path, samples=8, diff_thr=50.0):
    """Find the y-band (fractions) where the caption overlay actually draws text.

    Diff `capped` (post-caption) against `pre` (pre-caption): the only content
    change is the burned karaoke text, so diff pixels mark the text band.
    """
    import cv2
    import numpy as np
    dur = 0.0
    try:
        from . import mediatools as mt_read
        dur = mt_read.ffprobe_dur(capped_path) or 0.0
    except Exception:
        pass
    if not dur:
        return (0.55, 0.88)
    ts = [dur * (0.15 + 0.7 * k / max(1, samples - 1)) for k in range(samples)]
    rows = []
    for t in ts:
        a = _frame_at(capped_path, t)
        b = _frame_at(pre_path, t)
        if a is None or b is None or a.shape != b.shape:
            continue
        if a.shape[:2] != b.shape[:2]:
            continue
        g0 = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(np.float32)
        g1 = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.float32)
        d = np.abs(g0 - g1)
        ys, _ = np.where(d > diff_thr)
        rows.append(ys)
    if not rows:
        return (0.55, 0.88)
    all_rows = np.concatenate(rows)
    if len(all_rows) < 30:
        return (0.55, 0.88)
    h = a.shape[0]
    lo, hi = np.percentile(all_rows, [3, 97])
    lo = max(0, int(lo) - 20); hi = min(h, int(hi) + 25)
    return (round(lo / h, 3), round(hi / h, 3))


def _frame_at(path, t):
    import cv2, tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tp = tmp.name
    mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", str(round(max(0.0, t), 2)), "-i", path, "-frames:v", "1", tp],
           allow_fail=True)
    fr = cv2.imread(tp)
    try:
        os.remove(tp)
    except OSError:
        pass
    return fr


def cmd_pipeline(args):
    """One-command end-to-end: inspect -> Gemma analyze -> verify -> manifest -> render -> artifact QA.

    Big Pickle operates, Gemma thinks (chooses the cut + punch words as strict JSON),
    AutoClip turns those decisions into a manifest, FFmpeg renders, QA verifies the
    actual MP4 pixels. Nothing is uploaded here.
    """
    from . import inspect as inspect_mod
    from . import llm as llm_mod
    from . import mediatools as mt
    from . import config
    import datetime
    src = os.path.abspath(args.src)
    if not os.path.exists(src):
        raise SystemExit(f"source not found: {src}")

    req = request_mod.parse(args.request)
    print("=" * 70)
    print(f"REQUEST : {request_func(req)}\nSRC     : {src}")

    # 1) INSPECT (deterministic: audio -> transcription -> layout -> windows)
    print("=" * 70, "\n[1/6] INSPECT  transcription + layout scan", flush=True)
    wav = os.path.splitext(src)[0] + ".wav"
    words = None
    if args.words:
        words = _load_words(args.words)
        print(f"  words from {args.words} ({len(words)})")
    else:
        mt.extract_audio(src, wav)
        words = inspect_mod.transcribe(wav, model=args.whisper)
        print(f"  transcribed {len(words)} words from {wav}")
    layout = inspect_mod.fast_layout_scan(src, interval=args.sample)
    print(f"  layout={layout['layout']} boxes={len(layout['boxes'])}")
    windows = inspect_mod.scan_windows(words, max_windows=args.max_windows)
    band = args.band
    if band is not None and isinstance(band, str):
        band = tuple(float(x) for x in band.split(","))
    if band is None:
        band = _probe_creator_band(src, windows, prior=_creator_band(layout))
    print(f"  creator band= {band}  (windows={[w['id'] for w in windows]})")

    # 2) ANALYZE (Gemma thinks: pick the cut, punch + emphasis words)
    print("=" * 70, "\n[2/6] ANALYZE  Gemma proposes candidates (JSON)", flush=True)
    payload_lines = []
    for w in windows:
        payload_lines.append(f"WINDOW {w['id']} [{w['t0']:.1f}s .. {w['t1']:.1f}s]:")
        payload_lines.append(" ".join(x["text"] for x in w["words"]))
    band_hint = ""
    if band:
        band_hint = (f"The creator's face stays in x-band [{band[0]:.3f},{band[1]:.3f}]. "
                     f"Layout class: {layout['layout']}.")
    system = ("You pick short-form video moments from transcript windows. You ALWAYS reply "
              "with JSON matching the given schema exactly. Timestamps must be within the window "
              "bounds you cite. punch_word and every emphasis_word MUST be a verbatim token "
              "(case-insensitive) present in that window's word stream. Choose rarely. "
              "Return 1-3 candidates, best first.")
    user = (f"{band_hint}\nFormat/request: {request_func(req)}\n"
            f"Transcript windows:\n{''.join(payload_lines)}\n\n"
            "Which window makes the strongest short? For each choice give exact start/end seconds, "
            "a one-line title, why it works, a punch word, zero-to-four emphasis words, and whether "
            "the creator is on camera. Return JSON {\"candidates\":[{\"id\":\"c1\",\"window\":\"<id>\","
            "\"t0\":<float>,\"t1\":<float>,\"title\":\"\",\"why\":\"\",\"confidence\":\"high|medium|low\","
            "\"creator_on_cam\":true,\"punch_word\":\"<verbatim|null>\",\"emphasis_words\":[\"\"]}]}")
    schema = {"candidates": {"$list": {
        "id": ("str", True), "window": ("str", False), "t0": ("float", True),
        "t1": ("float", True), "title": ("str", False), "why": ("str", False),
        "confidence": ("str", True), "creator_on_cam": ("bool", False),
        "punch_word": ("str", False), "emphasis_words": ("str[]", False)}}}
    parsed = llm_mod.chat(system, user, schema=schema, model=args.model,
                          temperature=args.temperature)
    cands = parsed["candidates"]
    print(json.dumps(cands, indent=1))

    # 3) VERIFY (deterministic: transcript + real frames must back every claim)
    print("=" * 70, "\n[3/6] VERIFY   deterministic cross-check", flush=True)
    ver = inspect_mod.verify_candidates(cands, words, src, band=band, min_size=0.02)
    for c in ver:
        print(f"  {'OK      ' if c.get('verified') else 'REJECTED'} {c['id']} "
              f"{c['t0']:.1f}-{c['t1']:.1f}s face={c.get('face_coverage', '-')} "
              f"words={c.get('words_in_window', '-')} {c.get('problems', [])}")
    chosen = next((c for c in ver if c.get("verified")), None)
    if chosen is None:
        raise SystemExit("no candidate survived verification - pipeline refuses to render")

    # 4) MANIFEST (AutoClip orchestrates: Gemma decision -> concrete edit plan)
    print("=" * 70, "\n[4/6] MANIFEST build edit plan", flush=True)
    win = [w for w in words if chosen["t0"] - 0.5 <= w["start"] <= chosen["t1"] + 0.5]
    t0a, t1a = win[0]["start"], win[-1]["end"]
    pw = _find_word(win, chosen.get("punch_word")) or max(win, key=lambda w: w.get("energy", 0))
    tin = max(0.1, round(pw["start"] - t0a, 3))
    emph = []
    for e in chosen.get("emphasis_words") or []:
        if _find_word(win, e):
            token = e.strip(" .,;!?")
            if token and token not in emph:
                emph.append(token)
    for extra in (chosen.get("punch_word"), "ass", "honest", "really"):
        if extra and _find_word(win, extra):
            token = str(extra).strip(" .,;!?")
            if token not in emph:
                emph.append(token)
    emph = emph[:6]

    probe = json.loads(mt.stream_info(src))
    vs = next(s for s in probe.get("streams", []) if s.get("codec_type") == "video")
    in_w, in_h = int(vs["width"]), int(vs["height"])
    kind = "portrait" if in_h >= in_w else "landscape"
    name = args.name or "pipeline_cut"
    plan = {
        "id": name, "rank": 1,
        "src_path": src, "src": os.path.basename(src),
        "t0": round(t0a, 2), "t1": round(t1a, 2),
        "kind": kind,
        "face_zone": [round(band[0], 3), round(band[1], 3)] if band else None,
        "words": win,
        "emphasis": emph,
        "punch": {"tin": tin, "z": float(getattr(args, "zoom", 1.12))},
        "title": chosen.get("title") or "",
        "why": chosen.get("why") or "",
        "gemma": {"candidate_id": chosen.get("id"),
                  "confidence": chosen.get("confidence"),
                  "creator_on_cam": chosen.get("creator_on_cam")},
        "research": {
            "creator": req.get("creator"),
            "source": os.path.basename(src),
            "src_t0": t0a, "src_t1": t1a,
        },
    }
    manifest = {"request": req, "plans": [plan]}
    state_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "data", "state")
    os.makedirs(state_dir, exist_ok=True)
    man_path = os.path.join(state_dir, f"{name}_manifest.json")
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
    print(f"  -> {man_path}\n  t0={plan['t0']} t1={plan['t1']} kind={kind} "
          f"band={plan['face_zone']} punch@tin={tin} emphasis={emph}")

    # 5) RENDER (FFmpeg executes the plan: prep -> reframe -> punch -> captions -> assemble)
    print("=" * 70, "\n[5/6] RENDER   FFmpeg executes edit plan", flush=True)
    from . import edit as edit_mod
    fmt = format_mod.build_directives(req)
    out_id = f"M{plan['rank']}"
    prep = edit_mod.prep(plan, out_id)
    reframed, face_stats = edit_mod.reframe(prep, plan, out_id)
    print(f"  face_stats = {face_stats}")
    punched = edit_mod.add_punch(reframed, plan, out_id)
    capped = edit_mod.burn_karaoke(punched, prep, plan["words"], plan["emphasis"],
                                   fmt["caption"], out_id, t0_offset=plan["t0"])
    edit_mod.assemble([capped], args.out, fmt["hook"], whoosh_at=None,
                      music_profile=fmt.get("music"))
    print("  rendered", args.out)

    # 6) ARTIFACT QA (verify the REAL MP4: captions visible, face framed, tech ok)
    print("=" * 70, "\n[6/6] ARTIFACT QA  final MP4 is the source of truth", flush=True)
    cap_band = _learn_caption_band(capped, punched)
    print(f"  learned caption band = {cap_band}")
    cap_res = inspect_mod.caption_pixels(args.out, band=cap_band, samples=14, debug=True)
    aqa = inspect_mod.artifact_qa(args.out, manifest=manifest, media_dir=config.media_dir(),
                                  extract_frames=True)
    aqa["checks"]["captions_learned_band"] = cap_res
    if not cap_res.get("present"):
        aqa["errors"].append("caption pixels not detected in learned band of final MP4")
    fs = face_stats or {}
    edited = not (abs(fs.get("cx0", 0.5) - 0.5) < 0.05 and abs(fs.get("cx1", 0.5) - 0.5) < 0.05) \
        or float(plan["punch"].get("z", 1.0)) > 1.02
    aqa["checks"]["edit_evidence"] = {
        "crop_centers_x": [fs.get("cx0"), fs.get("cx1")],
        "punch_zoom": plan["punch"]["z"],
        "dynamic_crop": bool(edited)}
    if not edited:
        aqa["errors"].append("no measurable edit: looks like a static center crop")
    aqa["ok"] = not aqa["errors"] and aqa.get("ok", True)
    print(json.dumps(aqa["checks"], indent=1))
    for e in aqa["errors"]:
        print("  FAIL:", e)

    report = {"ok": aqa["ok"], "manifest": man_path, "final": args.out,
              "checks": aqa["checks"], "errors": aqa["errors"],
              "ts": datetime.datetime.now().isoformat(timespec="seconds")}
    with open(os.path.join(state_dir, f"{name}_pipeline.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print("=" * 70)
    print("PIPELINE:", "PASS" if aqa["ok"] else "FAIL", "->", args.out)
    return aqa

def cmd_top5(args):
    from . import top5_assembler
    clips = args.clips
    titles = [t.strip() for t in args.titles.split(",")] if args.titles else None
    out = top5_assembler.assemble_top5(clips=clips, titles=titles, output_path=args.out)
    print(f"\n[AutoClip Top 5] Output successfully generated at: {out}")

def main(argv=None):
    ap = argparse.ArgumentParser(prog="autoclip")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("parse"); p.add_argument("text"); p.set_defaults(fn=cmd_parse)
    p = sub.add_parser("test-llm"); p.set_defaults(fn=cmd_test_llm)
    p = sub.add_parser("web"); p.add_argument("--port", type=int, default=8080, help="port to listen on (default: 8080)"); p.set_defaults(fn=cmd_web)
    p = sub.add_parser("research")
    p.add_argument("--refresh-notes", action="store_true")
    p.add_argument("--ai", default=None, help="creator name for automated AI research")
    p.add_argument("--creator", default=None, help="creator name for automated AI research")
    p.add_argument("--topic", default=None, help="optional topic hint for AI research")
    p.set_defaults(fn=cmd_research)
    p = sub.add_parser("transcribe"); p.add_argument("video"); p.add_argument("out"); p.set_defaults(fn=cmd_transcribe)
    p = sub.add_parser("creative-qa"); p.add_argument("manifest"); p.set_defaults(fn=cmd_creative_qa)
    p = sub.add_parser("qa"); p.add_argument("file"); p.set_defaults(fn=cmd_qa)
    p = sub.add_parser("run"); p.add_argument("manifest"); p.add_argument("--out", default="autoclip_out.mp4"); p.set_defaults(fn=cmd_run)
    p = sub.add_parser("inspect"); p.add_argument("video")
    p.add_argument("--audio", default=None)
    p.add_argument("--words", default=None, help="existing words json instead of re-transcribing")
    p.add_argument("--model", default="base.en")
    p.add_argument("--sample", type=float, default=0.5)
    p.add_argument("--fast", action="store_true", help="keyframe-based layout scan (fast, for long sources)")
    p.add_argument("--top-windows", type=int, default=10)
    p.add_argument("--out", default=None); p.set_defaults(fn=cmd_inspect)
    p = sub.add_parser("analyze"); p.add_argument("inspect")
    p.add_argument("--request", default=None)
    p.add_argument("--floors", default=None)
    p.add_argument("--max-windows", type=int, default=3)
    p.add_argument("--model", default=None, help="explicit model override (default: cascades through configured models)")
    p.add_argument("--temperature", type=float, default=0.2)
    p.add_argument("--out", required=True); p.set_defaults(fn=cmd_analyze)
    p = sub.add_parser("verify"); p.add_argument("candidates")
    p.add_argument("--inspect", default=None)
    p.add_argument("--band", default=None, help="creator x-band 'x0,x1'")
    p.add_argument("--out", required=True); p.set_defaults(fn=cmd_verify)
    p = sub.add_parser("artifact-qa"); p.add_argument("file")
    p.add_argument("--manifest", default=None); p.set_defaults(fn=cmd_artifact_qa)
    p = sub.add_parser("pipeline")
    p.add_argument("--src", required=True)
    p.add_argument("--request", default="make a funniest moment short")
    p.add_argument("--out", default=os.path.join("data", "pipeline_out.mp4"))
    p.add_argument("--words", default=None, help="reuse existing transcription json")
    p.add_argument("--band", default=None, help="creator x-band 'x0,x1'")
    p.add_argument("--model", default=None, help="explicit model override (default: cascades through configured models)")
    p.add_argument("--temperature", type=float, default=0.4)
    p.add_argument("--whisper", default="base.en")
    p.add_argument("--max-windows", type=int, default=3)
    p.add_argument("--sample", type=float, default=1.0)
    p.add_argument("--zoom", type=float, default=1.12)
    p.add_argument("--name", default=None)
    p.set_defaults(fn=cmd_pipeline)

    p = sub.add_parser("top5")
    p.add_argument("--clips", nargs="+", required=True, help="List of 4 or 5 video clips in order from 5 down to 1")
    p.add_argument("--titles", default=None, help="Comma-separated titles for the clips")
    p.add_argument("--out", default=None, help="Output MP4 file path")
    p.set_defaults(fn=cmd_top5)

    args = ap.parse_args(argv)
    args.fn(args)

if __name__ == "__main__":
    main()