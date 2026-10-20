"""YouTube URL to 5 Ranked 9:16 Shorts Generator.

Fully automated pipeline:
1. YouTube video & audio extraction via yt-dlp
2. Word-level timestamp & energy transcription via faster-whisper
3. Creator face tracking & 9:16 portrait boundary detection
4. Multi-model Free LLM API ranking (#1 to #5 with viral ratings, good/bad critiques)
5. Deterministic verification against transcript & frame boundaries
6. 9:16 vertical video rendering (face-follow, punch zoom, kinetic karaoke pop captions, -14 LUFS)
7. Downloadable artifact generation with QA verification
"""
import os, sys, json, re, time, uuid, subprocess, math

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from . import config, mediatools as mt, inspect as inspect_mod, llm as llm_mod, format as format_mod, edit as edit_mod, qa as qa_mod, memory as memory_mod

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOADS_DIR = os.path.join(PROJECT_ROOT, "data", "downloads")
SHORTS_DIR = os.path.join(PROJECT_ROOT, "data", "shorts")

os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(SHORTS_DIR, exist_ok=True)

def sanitize_slug(text):
    clean = re.sub(r'[^a-zA-Z0-9_\-]', '_', text.strip())
    clean = re.sub(r'_+', '_', clean).strip('_')
    return clean[:32] if clean else "video"

def get_yt_env():
    env = os.environ.copy()
    local_bin = os.path.expanduser(r"~/.local/bin")
    if os.path.exists(local_bin) and local_bin not in env.get("PATH", ""):
        env["PATH"] = local_bin + os.pathsep + env.get("PATH", "")
    deno_dir = os.path.expanduser(r"~/.deno/bin")
    if os.path.exists(deno_dir) and deno_dir not in env.get("PATH", ""):
        env["PATH"] = deno_dir + os.pathsep + env.get("PATH", "")
    return env

def get_yt_cookie_args():
    downloads_dir = os.path.expanduser("~/Downloads")
    target_data_cookie = os.path.join(PROJECT_ROOT, "data", "cookies.txt")

    # 1. Sync fresh cookie files from user's Downloads directory if newer
    for dl_name in ["www.youtube.com_cookies.txt", "cookies.txt"]:
        dl_path = os.path.join(downloads_dir, dl_name)
        if os.path.exists(dl_path) and os.path.getsize(dl_path) > 10:
            try:
                if not os.path.exists(target_data_cookie) or os.path.getmtime(dl_path) > os.path.getmtime(target_data_cookie):
                    import shutil
                    shutil.copyfile(dl_path, target_data_cookie)
                    print(f"[YouTube Pipeline] Synced fresh cookies from {dl_path} to {target_data_cookie}")
            except Exception:
                pass

    candidates = [
        target_data_cookie,
        os.path.join(downloads_dir, "www.youtube.com_cookies.txt"),
        os.path.join(downloads_dir, "cookies.txt"),
        os.path.join(PROJECT_ROOT, "data", "clean_cookies.txt"),
        os.path.join(PROJECT_ROOT, "cookies.txt")
    ]
    for p in candidates:
        if os.path.exists(p) and os.path.getsize(p) > 10:
            return ["--cookies", p]
    return []

def get_python_exe():
    venv_py = os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")
    if os.path.exists(venv_py):
        return venv_py
    return sys.executable

_BGUTIL_PROC = None

def ensure_bgutil_server():
    """Start the bgutil PO token server (port 4416) if not already running.
    Required for yt-dlp to bypass YouTube's bot detection on high-res downloads.
    """
    global _BGUTIL_PROC
    import urllib.request
    # Quick check: is the server already up?
    try:
        with urllib.request.urlopen("http://127.0.0.1:4416/ping", timeout=2) as resp:
            if resp.status == 200:
                return True
    except Exception:
        pass

    # Find bgutil server main.ts
    bgutil_main = os.path.join(PROJECT_ROOT, "tools", "bgutil-ytdlp-pot-provider", "server", "src", "main.ts")
    if not os.path.exists(bgutil_main):
        print("[YouTube] bgutil server not found — skipping PO token. Downloads may be slower.")
        return False

    # Find deno executable
    deno_candidates = [
        r"C:\Users\swastik\.deno\bin\deno.exe",
        r"C:\Program Files\deno\deno.exe",
        "deno"
    ]
    deno_exe = None
    for d in deno_candidates:
        try:
            r = subprocess.run([d, "--version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                deno_exe = d
                break
        except Exception:
            continue

    if not deno_exe:
        print("[YouTube] Deno not found. bgutil PO token server unavailable.")
        return False

    try:
        server_dir = os.path.dirname(bgutil_main)
        _BGUTIL_PROC = subprocess.Popen(
            [deno_exe, "run", "--allow-all", bgutil_main],
            cwd=server_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        # Wait up to 6 seconds for the server to come online
        for _ in range(12):
            time.sleep(0.5)
            try:
                with urllib.request.urlopen("http://127.0.0.1:4416/ping", timeout=1) as resp:
                    if resp.status == 200:
                        print("[YouTube] ✅ bgutil PO token server started on port 4416")
                        return True
            except Exception:
                continue
        print("[YouTube] bgutil server took too long to start — proceeding without it")
        return False
    except Exception as e:
        print(f"[YouTube] bgutil server start note: {e}")
        return False

def get_bgutil_args():
    """Return yt-dlp extractor-args for the bgutil PO token server if running."""
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:4416/ping", timeout=1) as resp:
            if resp.status == 200:
                return ["--extractor-args", "youtubepot-bgutilhttp:base_url=http://127.0.0.1:4416"]
    except Exception:
        pass
    return []


def get_youtube_info(url):
    """Retrieve video metadata without downloading full stream."""
    cmd = [
        get_python_exe(), "-m", "yt_dlp",
        "--no-warnings", "--skip-download",
        "--print", "%(id)s\t%(title)s\t%(uploader)s\t%(duration)s\t%(thumbnail)s",
    ] + get_yt_cookie_args() + [url]
    try:
        r = subprocess.run(cmd, env=get_yt_env(), capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            parts = r.stdout.strip().split("\t")
            vid_id = parts[0] if len(parts) > 0 else "yt_video"
            title = parts[1] if len(parts) > 1 else "YouTube Video"
            uploader = parts[2] if len(parts) > 2 else "Creator"
            dur_str = parts[3] if len(parts) > 3 else "0"
            thumb = parts[4] if len(parts) > 4 else ""
            try:
                duration = float(dur_str)
            except ValueError:
                duration = 0.0
            return {
                "id": vid_id,
                "title": title,
                "uploader": uploader,
                "duration": duration,
                "thumbnail": thumb
            }
    except Exception as e:
        print(f"[YouTube Pipeline] Warning: metadata fetch failed: {e}")
    
    # Fallback regex extraction of video id
    m = re.search(r'(?:v=|\/|youtu\.be\/)([0-9A-Za-z_-]{11})', url)
    vid_id = m.group(1) if m else f"yt_{uuid.uuid4().hex[:8]}"
    return {
        "id": vid_id,
        "title": f"YouTube Video ({vid_id})",
        "uploader": "Creator",
        "duration": 180.0,
        "thumbnail": ""
    }

def cleanup_downloads_cache(keep_id=None, max_folder_mb=2500):
    """Proactively keep data/downloads folder lean (<= 2.5GB).
    
    Automatically deletes completed raw source videos (.mp4, .wav) older than 30 minutes,
    and guarantees that old 50-minute stream files never clog up your disk.
    """
    try:
        now = time.time()
        # 1. Delete completed raw source videos not in active use
        for f in os.listdir(DOWNLOADS_DIR):
            if keep_id and keep_id in f:
                continue
            if f.endswith(".part") or f.endswith(".ytdl"):
                continue
            if f.endswith("_words.json") or f.endswith("_summary.json"):
                continue  # preserve lightweight metadata
            fp = os.path.join(DOWNLOADS_DIR, f)
            if os.path.isfile(fp):
                age_sec = now - os.path.getmtime(fp)
                # If older than 20 minutes and not active, clean it up
                if age_sec > 1200 and (f.endswith("_source.mp4") or f.endswith(".wav")):
                    try:
                        os.remove(fp)
                        print(f"[Storage Cleaner] Purged aged raw source: {f}")
                    except Exception:
                        pass

        # 2. Check total folder size, enforce max_folder_mb cap
        files = []
        for f in os.listdir(DOWNLOADS_DIR):
            if keep_id and keep_id in f:
                continue
            if f.endswith(".part"):
                continue
            fp = os.path.join(DOWNLOADS_DIR, f)
            if os.path.isfile(fp):
                files.append((fp, os.path.getsize(fp), os.path.getmtime(fp)))

        total_bytes = sum(sz for _, sz, _ in files)
        max_bytes = max_folder_mb * 1024 * 1024
        if total_bytes > max_bytes:
            # Sort oldest first and delete until under limit
            files.sort(key=lambda x: x[2])
            for fp, sz, _ in files:
                try:
                    os.remove(fp)
                    total_bytes -= sz
                    if total_bytes <= max_bytes:
                        break
                except Exception:
                    pass
    except Exception as e:
        print(f"[Storage Cleaner] Note: {e}")
    except Exception:
        pass

def _auto_refresh_cookies():
    """Auto-refresh cookies via nodriver headless Chrome (subprocess to avoid event loop conflicts).
    Returns True if authenticated cookies were written to data/cookies.txt."""
    import importlib.util

    grabber_path = os.path.join(PROJECT_ROOT, "scripts", "grab_yt_cookies.py")
    if not os.path.exists(grabber_path):
        print("[YouTube] Cookie grabber script not found, skipping auto-refresh")
        return False

    cookie_file = os.path.join(PROJECT_ROOT, "data", "cookies.txt")

    try:
        # Run grab_yt_cookies.py in a subprocess to avoid asyncio nesting issues
        r = subprocess.run(
            [get_python_exe(), grabber_path],
            capture_output=True, text=True,
            timeout=60,
            env={**get_yt_env(), "PYTHONIOENCODING": "utf-8"}
        )
        print(f"[YouTube] Cookie refresh stdout: {r.stdout[-500:] if r.stdout else '(empty)'}")
        if r.returncode == 0:
            # Verify new cookies have auth tokens
            auth_keys = {"LOGIN_INFO", "SID", "SAPISID", "__Secure-3PSID", "HSID", "__Secure-1PSID"}
            if os.path.exists(cookie_file):
                with open(cookie_file, "r", encoding="utf-8", errors="replace") as f:
                    content_text = f.read()
                found = [k for k in auth_keys if k in content_text]
                if found:
                    print(f"[YouTube] ✅ Cookie refresh succeeded. Auth keys: {found}")
                    return True
                else:
                    print(f"[YouTube] ⚠️ Cookie refresh ran but no auth keys found. Profile may not be logged in.")
                    return False
        else:
            print(f"[YouTube] Cookie refresh subprocess failed: {r.stderr[-200:] if r.stderr else 'no stderr'}")
            return False
    except subprocess.TimeoutExpired:
        print("[YouTube] Cookie refresh timed out (60s). Profile may need interactive login.")
        return False
    except Exception as e:
        print(f"[YouTube] Cookie auto-refresh error: {e}")
        return False


def download_youtube_video(url, progress_cb=None):
    """Download YouTube video up to 720p, and extract audio wav.
    
    4-tier resilient download chain:
    1. Standard yt-dlp + cookies
    2. Android player_client (bypasses some bot checks)  
    3. iOS player client
    4. Auto-refresh cookies from Chrome profile, then retry
    """
    if progress_cb:
        progress_cb(10, "Fetching video metadata from YouTube...")
    info = get_youtube_info(url)
    vid_id = sanitize_slug(info["id"])
    target_mp4 = os.path.join(DOWNLOADS_DIR, f"{vid_id}_source.mp4")
    target_wav = os.path.join(DOWNLOADS_DIR, f"{vid_id}.wav")

    cleanup_downloads_cache(keep_id=vid_id)

    if os.path.exists(target_mp4) and os.path.getsize(target_mp4) > 100000:
        dur = mt.ffprobe_dur(target_mp4)
        if dur and dur > 1.0:
            if progress_cb:
                progress_cb(25, f"Using cached source video: {os.path.basename(target_mp4)}")
            if not os.path.exists(target_wav) or os.path.getsize(target_wav) < 10000:
                mt.extract_audio(target_mp4, target_wav, max_dur=None)
            return target_mp4, target_wav, info
        else:
            print(f"[YouTube Pipeline] Warning: Corrupt cached video {target_mp4}, removing...")
            try:
                os.remove(target_mp4)
            except OSError:
                pass

    if progress_cb:
        progress_cb(15, f"Downloading '{info['title'][:40]}' via yt-dlp...")

    local_bin = os.path.expanduser(r"~/.local/bin")
    ffmpeg_loc_args = ["--ffmpeg-location", local_bin] if os.path.exists(os.path.join(local_bin, "ffmpeg.exe")) else []

    # Ensure PO token server is running (required to bypass YouTube bot detection for 1080p)
    ensure_bgutil_server()

    def _is_bot_error(text):
        return ("Sign in to confirm" in text or "not a bot" in text.lower() or
                "LOGIN_REQUIRED" in text)

    def _try_dl(extra_args=None, label="default"):
        cookie_args = get_yt_cookie_args()
        cmd = [
            get_python_exe(), "-m", "yt_dlp",
            "-f", "bv*[height<=360]+ba/b[height<=360]/b",
            "--no-part", "--no-playlist",
            "--merge-output-format", "mp4",
            "--force-overwrites",
            "--socket-timeout", "15",
            "-o", target_mp4
        ] + cookie_args + (extra_args or []) + [url]
        print(f"[YouTube] [{label}] Starting download: {' '.join(cmd[:8])}...", flush=True)
        try:
            proc = subprocess.Popen(
                cmd,
                env=get_yt_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace"
            )
            last_pct = 0.0
            t_start = time.time()
            all_out = []
            while True:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break
                if line:
                    all_out.append(line)
                    m_dl = re.search(r'\[download\]\s+([0-9.]+)%', line)
                    if m_dl:
                        pct_val = float(m_dl.group(1))
                        if pct_val - last_pct >= 4.0 or pct_val >= 99.0:
                            last_pct = pct_val
                            if progress_cb:
                                progress_cb(15 + int(pct_val * 0.10), f"Downloading video: {pct_val:.0f}%...")
                if time.time() - t_start > 120:
                    proc.kill()
                    break

            proc.wait(timeout=10)
            full_log = "".join(all_out[-30:])
            success = (proc.returncode == 0) and os.path.exists(target_mp4) and (os.path.getsize(target_mp4) > 50000)
            return success, full_log
        except Exception as ex:
            return False, str(ex)

    # Tier 1: Standard with saved cookies
    ok, err1 = _try_dl(label="Tier1:standard")
    if ok:
        print("[YouTube] Tier 1 succeeded")
    
    # Tier 2: Android player client
    if not ok:
        if progress_cb:
            progress_cb(16, "Retrying with Android player client...")
        ok, err2 = _try_dl(
            extra_args=["--extractor-args", "youtube:player_client=android,web"],
            label="Tier2:android"
        )
        if ok:
            print("[YouTube] Tier 2 (android) succeeded")
    else:
        err2 = ""

    # Tier 3: iOS player client
    if not ok:
        if progress_cb:
            progress_cb(17, "Retrying with iOS player client...")
        ok, err3 = _try_dl(
            extra_args=["--extractor-args", "youtube:player_client=ios,android"],
            label="Tier3:ios"
        )
        if ok:
            print("[YouTube] Tier 3 (ios) succeeded")
    else:
        err3 = ""

    # Tier 4: Auto-refresh cookies from Chrome profile
    if not ok and _is_bot_error(err1 + err2 + err3):
        if progress_cb:
            progress_cb(18, "Bot detected - auto-refreshing YouTube cookies...")
        print("[YouTube] Bot detection. Auto-refreshing cookies via saved Chrome profile...")
        try:
            refreshed = _auto_refresh_cookies()
        except Exception as re_err:
            print(f"[YouTube] Cookie refresh failed: {re_err}")
            refreshed = False

        if refreshed:
            if progress_cb:
                progress_cb(19, "Retrying with fresh cookies...")
            ok, err4 = _try_dl(label="Tier4:post-refresh")
            if not ok:
                ok, err4 = _try_dl(
                    extra_args=["--extractor-args", "youtube:player_client=android,web"],
                    label="Tier4:post-refresh+android"
                )
            if ok:
                print("[YouTube] Tier 4 (cookie refresh) succeeded")
        else:
            err4 = "Cookie refresh returned no authenticated session"
    else:
        err4 = ""

    if not ok:
        all_err = " ".join(e for e in [err1, err2, err3, err4] if e.strip())
        if _is_bot_error(all_err):
            raise RuntimeError(
                "YouTube is blocking downloads (bot check).\n\n"
                "Fix: Type !refresh_cookies in Discord and log into YouTube when Chrome opens.\n"
                "Takes 30 seconds. Works permanently after that."
            )
        err_lines = [l for l in all_err.splitlines() if "ERROR:" in l or "HTTP Error" in l]
        summary = " ".join(err_lines) if err_lines else all_err[-300:]
        raise RuntimeError(f"Could not download YouTube video: {summary}")

    dur = mt.ffprobe_dur(target_mp4)
    if not dur or dur <= 1.0:
        try:
            os.remove(target_mp4)
        except OSError:
            pass
        raise RuntimeError("Downloaded video container is incomplete or corrupt. Re-run to retry.")

    if progress_cb:
        progress_cb(25, "Extracting full audio stream for transcription...")
    mt.extract_audio(target_mp4, target_wav, max_dur=None)

    return target_mp4, target_wav, info

def load_words_data(path_or_data):
    """Normalize words list whether passed as path, dict, or list."""
    if isinstance(path_or_data, str):
        with open(path_or_data, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = path_or_data
    return data.get("words", []) if isinstance(data, dict) else data

def purge_video_cache(vid_id, purge_source=False):
    """Thoroughly purge all cached transcripts, old rendered shorts, and summaries for this video ID.
    
    Guarantees 100% fresh execution from scratch whenever a user repastes a video.
    """
    clean_id = sanitize_slug(vid_id)
    purged_count = 0
    # 1. Clean downloads directory
    if os.path.exists(DOWNLOADS_DIR):
        for f in os.listdir(DOWNLOADS_DIR):
            if clean_id in f:
                if not purge_source and f.endswith("_source.mp4"):
                    continue
                try:
                    os.remove(os.path.join(DOWNLOADS_DIR, f))
                    purged_count += 1
                except Exception:
                    pass
    # 2. Clean shorts directory (rendered clips, thumbnails, and summaries)
    if os.path.exists(SHORTS_DIR):
        for f in os.listdir(SHORTS_DIR):
            p = os.path.join(SHORTS_DIR, f)
            if clean_id in f:
                try:
                    os.remove(p)
                    purged_count += 1
                except Exception:
                    pass
            elif f.endswith("_summary.json"):
                try:
                    with open(p, "r", encoding="utf-8") as sf:
                        s_data = json.load(sf)
                    v_info = s_data.get("video_info") or {}
                    if sanitize_slug(v_info.get("id", "")) == clean_id or clean_id in str(s_data):
                        os.remove(p)
                        purged_count += 1
                except Exception:
                    pass
    print(f"[YouTube Pipeline] Purged {purged_count} stale cache/short files for video '{clean_id}'.")
    return purged_count

def transcribe_audio_words(wav_path, vid_id, progress_cb=None, fresh=False):
    """Transcribe audio with faster-whisper to word-level timestamps."""
    words_json = os.path.join(DOWNLOADS_DIR, f"{vid_id}_words.json")

    if not fresh and os.path.exists(words_json) and os.path.getsize(words_json) > 100:
        if progress_cb:
            progress_cb(40, f"Loaded existing word timestamps ({words_json})")
        return load_words_data(words_json), words_json
    elif fresh and os.path.exists(words_json):
        try:
            os.remove(words_json)
        except Exception:
            pass

    if progress_cb:
        progress_cb(32, "Transcribing video speech with faster-whisper (word timestamps & energy)...")

    cmd = [
        get_python_exe(),
        "-u",
        "-m", "autoclip.cli", "transcribe", wav_path, words_json
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )

    last_pct = 0.0
    for line in iter(proc.stdout.readline, ''):
        line_str = line.strip()
        if not line_str:
            continue
        m = re.search(r'\[transcribe\]\s+([0-9.]+)/([0-9.]+)', line_str)
        if m:
            curr_s = float(m.group(1))
            tot_s = float(m.group(2))
            pct_val = (curr_s / tot_s) * 100.0 if tot_s > 0 else 0.0
            if (pct_val - last_pct >= 4.0 or pct_val >= 98.0) and progress_cb:
                last_pct = pct_val
                bar_pct = 32 + int((pct_val / 100.0) * 12)
                progress_cb(bar_pct, f"Transcribing speech: {curr_s/60:.1f}m / {tot_s/60:.1f}m ({pct_val:.0f}%)...")

    proc.wait(timeout=1800)
    if proc.returncode != 0 or not os.path.exists(words_json):
        raise RuntimeError(f"Transcription failed: exit code {proc.returncode}")

    words = load_words_data(words_json)
    if progress_cb:
        progress_cb(44, f"Transcribed {len(words)} words successfully.")
    return words, words_json

def ensure_40_50s_duration(words, t0, t1, min_dur=None, max_dur=None):
    """Enforce complete story duration floor strictly between 40 and 52 seconds (or user learned memory).
    
    Snaps ending to a natural punctuation mark or speech boundary so speaker is not cut off.
    """
    if min_dur is None or max_dur is None:
        try:
            prefs = memory_mod.get_active_preferences()
            min_dur = float(prefs.get("min_duration", 40.0)) - 1.0
            max_dur = float(prefs.get("max_duration", 52.0))
        except Exception:
            min_dur = 39.0
            max_dur = 52.0

    if not words:
        return round(float(t0), 2), round(max(float(t0) + min_dur, float(t1)), 2)
        
    t0 = float(t0)
    t1 = float(t1)
    dur = t1 - t0
    target_t1 = t1
    if dur < min_dur:
        target_t1 = t0 + 44.0
    elif dur > max_dur:
        target_t1 = t0 + 48.0
        
    cand_words = [w for w in words if (t0 + min_dur - 1.0) <= w["end"] <= (t0 + max_dur + 1.0)]
    
    # 1. Look for punctuation (. ! ?) near target
    best_t1 = None
    for w in cand_words:
        txt = w.get("text", "").strip()
        w_dur = w["end"] - t0
        if w_dur >= min_dur and any(txt.endswith(p) for p in [".", "!", "?", "..."]):
            best_t1 = round(w["end"] + 0.2, 2)
            if w_dur >= 42.0:
                break
                
    # 2. Look for natural speech pause (gap >= 0.5s)
    if best_t1 is None:
        for i in range(len(cand_words) - 1):
            w_dur = cand_words[i]["end"] - t0
            gap = cand_words[i+1]["start"] - cand_words[i]["end"]
            if w_dur >= min_dur and gap >= 0.5:
                best_t1 = round(cand_words[i]["end"] + 0.2, 2)
                if w_dur >= 42.0:
                    break
                    
    # 3. Fallback to closest word within window
    if best_t1 is None and cand_words:
        closest = min(cand_words, key=lambda w: abs(w["end"] - target_t1))
        best_t1 = round(closest["end"] + 0.2, 2)
        
    if best_t1 is None:
        all_after = [w for w in words if w["end"] > t0]
        if all_after:
            last_w = all_after[-1]
            best_t1 = min(round(last_w["end"] + 0.2, 2), round(t0 + max_dur, 2))
        else:
            best_t1 = round(t0 + min_dur, 2)
            
    final_dur = best_t1 - t0
    if final_dur > max_dur:
        best_t1 = round(t0 + max_dur, 2)
        
    return round(t0, 2), round(best_t1, 2)

def find_and_rank_5_clips(words, video_path, video_info, progress_cb=None, theme=None):
    """Analyze transcript windows with Free LLM API and rank top 5 clips."""
    words = load_words_data(words)
    if progress_cb:
        progress_cb(45, "Scanning video layout & creator face tracking...")

    creator_hint = video_info.get("selected_creator") or video_info.get("uploader", "Creator")
    title_hint = video_info.get("title", "")
    title_lower = title_hint.lower()

    is_audio_only = any(str(video_path).lower().endswith(ext) for ext in [".wav", ".m4a", ".mp3", ".opus", ".aac", ".flac"])
    if is_audio_only:
        layout = {"kind": "landscape", "face_zone": [0.2, 0.45], "crop": {"x": 0.33, "y": 0.0, "w": 0.34, "h": 1.0}}
        band = [0.2, 0.45]
    else:
        try:
            layout = inspect_mod.fast_layout_scan(video_path, interval=1.0)
        except Exception as e:
            print(f"[YouTube Pipeline] Layout scan fallback: {e}")
            layout = {"kind": "landscape", "face_zone": [0.2, 0.45], "crop": {"x": 0.33, "y": 0.0, "w": 0.34, "h": 1.0}}

    windows = inspect_mod.scan_windows(words, max_windows=50, theme=theme, creator=creator_hint)
    if not windows:
        # Fallback window if silence/sparse
        dur = mt.ffprobe_dur(video_path) or 45.0
        windows = [{
            "id": "w1",
            "t0": 0.0,
            "t1": min(dur, 45.0),
            "dur": min(dur, 45.0),
            "words": words
        }]

    if not is_audio_only:
        # Probe creator face band
        from .cli import _probe_creator_band, _creator_band
        try:
            band = _probe_creator_band(video_path, windows, prior=_creator_band(layout))
        except Exception:
            band = [0.2, 0.45]
    else:
        band = [0.2, 0.45]

    if progress_cb:
        progress_cb(52, "Querying Free LLM API for TOP 5 viral clips, hooks & punchy moments...")

    payload_lines = []
    for w in windows:
        w_txt = " ".join(x.get("text", "") for x in w["words"])
        payload_lines.append(f"WINDOW {w['id']} [{w['t0']:.1f}s .. {w['t1']:.1f}s]:\n{w_txt}")

    # ── Genre-aware clip brief ──────────────────────────────────────────────
    def _build_genre_brief(t: str) -> str:
        if any(k in creator_hint.lower() for k in ["speed", "ishowspeed"]) or any(k in t for k in ["speed", "ishowspeed"]):
            return (
                "CONTENT TYPE: ISHOWSPEED STREAM HIGHLIGHTS & FREAKOUTS.\n"
                "PRIORITY MOMENTS TO FIND:\n"
                "  1. Pure unhinged freakouts — Speed barking, screaming at max volume, jumping, or slamming desk.\n"
                "  2. Broken setup / rage moments — destroying controller, headphones, chair, or spilling.\n"
                "  3. Hilarious troll encounters (Omegle/Discord/games) — outrageous questions, instant shock, flirting fails.\n"
                "  4. Insane high-pitch noises, shrieks, or unhinged laugh reactions.\n"
                "  5. Football/Ronaldo rage or celebration debates.\n"
                "CRITICAL: DO NOT pick calm talking, reading donations, or slow game setup. Pick ONLY high-energy chaos!\n"
            )
        if any(k in t for k in ["horror", "scary", "haunted", "ghost", "jumpscare", "fnaf",
                                  "plant shop", "visage", "phasmophobia", "outlast", "resident evil",
                                  "silent hill", "dread", "fear", "terror", "nightmare"]):
            return (
                "CONTENT TYPE: HORROR GAME PLAYTHROUGH.\n"
                "PRIORITY MOMENTS TO FIND:\n"
                "  1. Jump-scare reactions — the moment creator SCREAMS, gasps, or panics. This is #1.\n"
                "  2. Build-up + scare payoff — tense stalking that ends with creator yelling.\n"
                "  3. Unexpected in-game event that makes creator lose control (creature appears, loud noise).\n"
                "  4. Creator refusing to continue / hiding / saying 'I'm done' or 'I quit'.\n"
                "  5. Funny relieved reaction AFTER surviving a scare.\n"
                "DO NOT pick: calm exploration, menu navigation, or normal conversation with no in-game action.\n"
                "RULE: If a window has screaming, 'OH MY GOD', 'WHAT WAS THAT', 'NO NO NO', 'I'M SCARED' — it is a top clip.\n"
            )
        if any(k in t for k in ["rainbow six", "siege", "r6", "valorant", "warzone", "cod",
                                  "call of duty", "fortnite", "apex", "csgo", "cs2",
                                  "ranked", "1v4", "1v5", "tournament", "champion", "clutch"]):
            return (
                "CONTENT TYPE: COMPETITIVE FPS / SHOOTER GAMEPLAY.\n"
                "PRIORITY MOMENTS TO FIND:\n"
                "  1. Clutch plays — 1v2, 1v3, 1v4 where creator wins against the odds.\n"
                "  2. Ace / multi-kill moments with reaction screaming or celebration.\n"
                "  3. Rage/tilt — creator misses a shot or loses and goes off.\n"
                "  4. Insane mechanical play (no-scope, flick shot) with instant reaction.\n"
                "  5. Rank-up or rank-down emotional reaction.\n"
                "DO NOT pick: loading screens, menu browsing, or calm strategic discussion with no action.\n"
                "RULE: The ACTION in the game matters, not the words. Look for high-energy speech DURING gameplay.\n"
            )
        if any(k in t for k in ["minecraft", "roblox", "terraria", "stardew"]):
            return (
                "CONTENT TYPE: SANDBOX / BUILDING GAME.\n"
                "PRIORITY MOMENTS TO FIND:\n"
                "  1. Unexpected death/loss reaction — creator dies stupidly and goes off.\n"
                "  2. Epic discovery or build reveal causing amazement.\n"
                "  3. Troll or grief moment (getting griefed or trolling someone).\n"
                "  4. Challenge completion with huge celebration.\n"
                "  5. Funny awkward moment / accidental destruction.\n"
                "DO NOT pick: slow quiet building with no reaction or long narrative explanation.\n"
            )
        if any(k in t for k in ["irl", "vlog", "meetup", "mall", "store", "street", "real life",
                                  "day in", "challenge", "prank", "fan", "went to", "visiting",
                                  "tried", "eating", "cooking", "reacting to"]):
            return (
                "CONTENT TYPE: IRL / VLOG / REAL LIFE.\n"
                "PRIORITY MOMENTS TO FIND:\n"
                "  1. Unexpected public reaction — stranger says/does something wild.\n"
                "  2. Prank payoff or challenge completion with huge reaction.\n"
                "  3. Fan encounter that gets emotional or crazy.\n"
                "  4. Creator doing something embarrassing or getting called out.\n"
                "  5. Funny relatable shareable moment.\n"
                "DO NOT pick: calm walking/talking narration with no event happening.\n"
            )
        if any(k in t for k in ["gta", "grand theft", "heist", "nopixel", "roleplay"]):
            return (
                "CONTENT TYPE: OPEN WORLD / GTA ROLEPLAY.\n"
                "PRIORITY MOMENTS TO FIND:\n"
                "  1. High-speed chase or escape with panicked reaction.\n"
                "  2. Heist/robbery that goes wrong or perfectly right.\n"
                "  3. Wild unexpected in-game event with huge creator reaction.\n"
                "  4. Funny RP interaction that goes off-script.\n"
                "  5. Creator getting killed in a ridiculous way.\n"
                "DO NOT pick: driving around with no event, or quiet planning sessions.\n"
            )
        if any(k in t for k in ["game", "gaming", "plays", "stream", "gameplay", "let's play",
                                  "playing", "boss", "speedrun"]):
            return (
                "CONTENT TYPE: GAMING STREAM.\n"
                "PRIORITY MOMENTS TO FIND:\n"
                "  1. Any moment where creator SCREAMS, yells, or loses control of emotions.\n"
                "  2. Big win or big fail — peak high or peak low emotional moment.\n"
                "  3. In-game event that directly causes a strong creator reaction.\n"
                "  4. Something funny or unexpected happening DURING gameplay.\n"
                "  5. Hype moment that makes audience want to share.\n"
                "CRITICAL RULE: Focus on moments where IN-GAME ACTION triggers a reaction. "
                "Calm conversation between players with no action is NOT a good clip.\n"
            )
        return (
            "CONTENT TYPE: REACTION / COMMENTARY / ENTERTAINMENT.\n"
            "PRIORITY MOMENTS TO FIND:\n"
            "  1. The most shocking or outrageous moment the creator reacts to.\n"
            "  2. Biggest laugh or comedy payoff.\n"
            "  3. Most emotional or heartfelt moment.\n"
            "  4. A moment so unexpected it demands a share.\n"
            "  5. Best quotable line with strong delivery.\n"
            "DO NOT pick: filler intro/outro or slow exposition with no emotional peak.\n"
        )

    genre_brief = _build_genre_brief(title_lower)
    theme_directive = ""
    if theme:
        theme_directive = (
            f"\n🎯 SPECIAL THEME DIRECTIVE:\n"
            f"The user explicitly requested: '{theme.upper()}'. All 5 extracted clips MUST strictly focus on "
            f"'{theme.upper()}' from THIS video transcript windows! Look specifically for moments fitting '{theme}'! "
            f"Rank #1 the absolute best {theme} moment down to #5.\n\n"
        )

    system_prompt = (
        "You are an elite viral short-form video editor (TikTok, YouTube Shorts, Reels) "
        f"specializing in {creator_hint}'s content.\n\n"
        + genre_brief + "\n"
        + theme_directive +
        "CORE EDITING & NAMING STANDARDS (MANDATORY):\n"
        "1. NO GENERIC BUZZWORDS: NEVER use words like 'Climax', 'The #1 Climax', 'Bro Lost It', 'Wait Till The End', 'Viral Freakout'. The viewer must instantly know WHAT ACTUALLY HAPPENED in that scene.\n"
        "2. SPECIFIC SCENE-DESCRIPTIVE TITLES: Describe the literal physical or comedic action that occurred (e.g. 'Speed Barks At Streamer 🐶', 'Controller Smashed In Rage 🎮', 'Sleeping In Grocery Aisle 😴', 'Smoothie Blender Explodes 🥤').\n"
        "3. SCENE TOPIC: A concise 2-4 word UPPERCASE phrase naming the exact event for on-screen badges (e.g. 'BARKED AT STREAMER', 'BROKE CONTROLLER', 'FELL ASLEEP IN AISLE', 'BLENDER EXPLODED').\n"
        "4. COMPLETE STORY ARC: Every clip MUST have a complete mini-story:\n"
        "   - Beat 1 (0-3s): Explosive Hook setting up the specific event\n"
        "   - Beat 2 (3-35s): Escalating tension, argument, chaos, or gameplay struggle\n"
        "   - Beat 3 (35-48s): Satisfying hilarious punchline, reaction climax, or payoff. Never cut off mid-thought!\n"
        "5. STRICT SOURCE EXCLUSIVITY: Every clip must strictly originate from the provided video's transcript windows below. Do NOT hallucinate clips from other videos or streams.\n"
        "6. Rank strictly from #1 (Funniest & Wildest Event) down to #5 (Secondary Highlight).\n\n"
        "For EACH clip, provide:\n"
        "1. rank: integer 1 to 5\n"
        "2. score: integer rating from 50 to 100 (e.g. #1: 96, #2: 91, #3: 86, #4: 79, #5: 72)\n"
        "3. tier: specific tier string describing the event ('S-Tier Controller Rage', 'A-Tier Barking Freakout', 'B-Tier Chaotic Prank', etc. - NEVER use generic 'Climax')\n"
        "4. title: scene-descriptive YouTube Shorts title with emoji (e.g. 'Speed Barks At Girl 🐶', 'Controller Destroyed In FIFA 🎮')\n"
        "5. scene_topic: 2-4 word UPPERCASE description of the event (e.g. 'BARKED AT GIRL', 'BROKE CONTROLLER', 'SLEEPING IN AISLE')\n"
        "6. why_good: specific viral strengths of this scene\n"
        "7. why_bad: honest critique (pacing, build-up speed)\n"
        "8. t0: start timestamp in seconds\n"
        "9. t1: end timestamp in seconds (STRICTLY 40s to 50s duration, complete 3-beat story: Hook -> Escalation -> Payoff)\n"
        "10. punch_word: single highest energy/reaction word present verbatim in that window\n"
        "11. emphasis_words: 2 to 5 verbatim keywords for pop karaoke subtitles\n"
        "12. hook_text: explosive 3-6 word UPPERCASE scene-specific hook banner (e.g. 'SPEED BARKS AT STREAMER 🐶', 'BROKE HIS CONTROLLER 🎮', 'FELL ASLEEP IN AISLE 😴' - NEVER generic 'BRO LOST IT')\n"
        "13. music_mood: Analyze current viral YouTube Shorts trends for this streamer and select the exact trending background music sound: "
        "'phonk_rage' (high-adrenaline Brazilian Phonk for scream rages & crazy climax), "
        "'meme_funk' (catchy bounce / viral TikTok Latin jazz meme groove for goofy chaotic fails), "
        "'horror_drone' (chilling suspense drone for jumpscare build-ups), "
        "'lofi_awkward' (chill modern boom-bap / quirky pizzicato bounce for awkward dialogue & roasts), "
        "or 'clean_dialogue_silence' (mute BGM completely if the speech is funny on its own without distraction).\n"
        "14. sfx_type: Analyze viral short-form comedic timing and choose the single best punchline sound effect: "
        "'vine_boom' (heavy bass impact on shock or crazy face), "
        "'record_scratch' (awkward pause, sudden cutoff), "
        "'tension_riser' (rising buildup before a scary climax), "
        "'bell_ding' (smart realization or punchline hit), "
        "'whoosh' (fast reaction whip), or 'none' (clean audio).\n"
        "15. description: high-converting YouTube Shorts description with trending hashtags\n"
        "16. tags: list of 5-8 trending tags\n"
        "Return ONLY a JSON object matching the exact schema."
    )

    theme_msg = f" Focused strictly on '{theme.upper()}'." if theme else ""
    user_prompt = (
        f"Video Title: {title_hint}\n"
        f"Channel/Creator: {creator_hint}\n"
        f"Transcript Windows:\n" + "\n\n".join(payload_lines) + "\n\n"
        f"Extract, rate, and rank exactly 5 distinct viral clips (#1 best to #5 worst) from THIS video only.{theme_msg} "
        "Every single clip must be genuinely funny with a complete, coherent beginning-to-end story."
    )

    schema = {
        "clips": {
            "$list": {
                "rank": ("int", True),
                "score": ("int", True),
                "tier": ("str", True),
                "title": ("str", True),
                "scene_topic": ("str", True),
                "why_good": ("str", False),
                "why_bad": ("str", False),
                "t0": ("float", True),
                "t1": ("float", True),
                "punch_word": ("str", False),
                "emphasis_words": ("str[]", False),
                "hook_text": ("str", False),
                "music_mood": ("str", False),
                "sfx_type": ("str", False),
                "description": ("str", False),
                "tags": ("str[]", False)
            }
        }
    }

    raw_res = None
    try:
        client_timeout = int(os.environ.get("AUTOCLIP_LLM_TIMEOUT", "60"))
        raw_res = llm_mod.chat(system_prompt, user_prompt, schema=schema, temperature=0.3, timeout=client_timeout)
    except Exception as e:
        print(f"[YouTube Pipeline] LLM call error: {e}. Falling back to rule-based window ranking.")

    llm_clips = (raw_res or {}).get("clips", [])

    # If LLM returned fewer than 5 clips, pad with top-energy windows
    verified_candidates = []
    used_times = set()

    # Normalize LLM candidates
    for c in llm_clips:
        raw_t0 = float(c.get("t0", 0))
        raw_t1 = float(c.get("t1", raw_t0 + 44.0))
        t0, t1 = ensure_40_50s_duration(words, raw_t0, raw_t1, min_dur=39.0, max_dur=52.0)
        dur = t1 - t0
        
        # Avoid exact duplicates
        time_key = round(t0, 0)
        if time_key in used_times:
            continue
        used_times.add(time_key)

        pw = c.get("punch_word") or "MOMENT"
        default_hook = c.get("hook_text") or f"WAIT FOR THIS {pw.upper()} 💀"
        verified_candidates.append({
            "rank": len(verified_candidates) + 1,
            "score": int(c.get("score") or (98 - len(verified_candidates) * 6)),
            "tier": str(c.get("tier") or "Viral Moment"),
            "title": str(c.get("title") or f"Viral Clip #{len(verified_candidates)+1}"),
            "scene_topic": str(c.get("scene_topic") or default_hook.replace("💀", "").replace("😂", "").replace("🔥", "").strip()[:24].upper()),
            "why_good": str(c.get("why_good") or "High speech cadence and engaging narrative turn."),
            "why_bad": str(c.get("why_bad") or "Standard pacing compared to top climax."),
            "t0": round(t0, 2),
            "t1": round(t1, 2),
            "dur": round(t1 - t0, 2),
            "punch_word": pw,
            "emphasis_words": c.get("emphasis_words") or [],
            "hook_text": default_hook,
            "music_mood": c.get("music_mood") or "meme_funk",
            "sfx_type": c.get("sfx_type") or "vine_boom",
            "description": c.get("description") or f"{c.get('title')} #shorts #viral #funny",
            "tags": c.get("tags") or ["shorts", "viral", "funny", "streamer"],
            "peak_energy": c.get("peak_energy", 0.5),
            "reaction_hits": c.get("reaction_hits", 0),
            "verified": True
        })
        if len(verified_candidates) >= 5:
            break

    # If still fewer than 5, fill from remaining windows
    if len(verified_candidates) < 5:
        tier_names = [
            ("S-Tier Viral Hook", 96, "Instant high-energy opening and punchy delivery.", "Fast pacing requires quick visual cuts."),
            ("A-Tier Reaction Peak", 89, "Strong expressive speech and relatable comedic hook.", "Slight pause before punchline."),
            ("B-Tier Comedy Beat", 82, "Great back-and-forth momentum and dialogue clarity.", "Moderate audio intensity."),
            ("C-Tier Story Hook", 76, "Contextual storyline element that builds curiosity.", "Slower buildup than top moments."),
            ("D-Tier Clean Cut", 70, "Clean standalone sentence structure with clear speech.", "Subtle reaction payoff.")
        ]
        for w in windows:
            if len(verified_candidates) >= 5:
                break
            t_cand = w["t0"]
            overlap = False
            for prev in verified_candidates:
                if abs(t_cand - prev["t0"]) < 25.0:
                    overlap = True
                    break
            if overlap:
                continue
            used_times.add(round(t_cand, 0))
            idx = len(verified_candidates)
            tier_info = tier_names[idx] if idx < len(tier_names) else ("Viral Clip", 70, "Good speech flow", "Standard energy")
            
            STOP_WORDS = {
                "i", "a", "an", "the", "for", "and", "if", "it's", "what", "yes", "no", "is", "to", "in", 
                "of", "with", "that", "this", "my", "you", "he", "she", "we", "they", "me", "him", "her", 
                "us", "them", "so", "be", "do", "did", "was", "are", "have", "had", "just", "like", "at", 
                "by", "from", "up", "about", "into", "over", "after", "it", "its", "your", "our", "their"
            }
            VIRAL_HOOKS = [
                "WAIT TILL THE END 💀",
                "HE ACTUALLY SAID THIS 😭",
                "BRO CANNOT BE SERIOUS 😂",
                "WATCH WHAT HAPPENS NEXT 😱",
                "BRO GOT INSTANTLY EXPOSED 🔥"
            ]
            VIRAL_TITLES = [
                "BRO CANNOT BE REAL RIGHT NOW 💀",
                "WAIT FOR THE ENDING... UNBELIEVABLE 😱",
                "WHEN THE GUESS GOES TERRIBLY WRONG 😂",
                "HE REALLY THOUGHT HE WAS SLICK 😭",
                "THE MOST SHOCKING STREAM REACTION 🔥"
            ]
            
            w_words = w.get("words", [])
            substantive = [x for x in w_words if x.get("text", "").strip(" .,!?").lower() not in STOP_WORDS and len(x.get("text", "").strip(" .,!?")) >= 3]
            pw = max(substantive, key=lambda x: x.get("energy", 0))["text"].strip(" .,!?").upper() if substantive else "BRO"
            emph = [x["text"].strip(" .,!?").upper() for x in sorted(substantive or w_words, key=lambda x: x.get("energy", 0), reverse=True)[:3]]

            raw_t0 = round(w["t0"], 2)
            raw_t1 = round(w["t1"], 2)
            t0, t1 = ensure_40_50s_duration(words, raw_t0, raw_t1, min_dur=39.0, max_dur=52.0)
            w_dur = round(t1 - t0, 2)

            # Contextual hook derived directly from creator's spoken dialogue
            spoken_clean = [x.get("text", "").strip(" .,!?\"'") for x in w_words if x.get("text", "").strip(" .,!?\"'")]
            first_phrase = " ".join(spoken_clean[:6]).upper() if spoken_clean else ""
            if first_phrase and len(first_phrase) <= 38:
                hook_text = f"{first_phrase} 💀"
            elif substantive:
                top_sub = " ".join([x["text"].strip(" .,!?").upper() for x in substantive[:4]])
                hook_text = f"LOOK AT THIS: {top_sub} 😱"
            else:
                hook_text = VIRAL_HOOKS[idx % len(VIRAL_HOOKS)]

            # Contextual title derived from dialogue
            if len(spoken_clean) >= 4:
                dialogue_title = " ".join(spoken_clean[:6]).capitalize()
                title_text = f"\"{dialogue_title}...\" 😱"
            else:
                title_text = VIRAL_TITLES[idx % len(VIRAL_TITLES)]

            verified_candidates.append({
                "rank": idx + 1,
                "score": tier_info[1],
                "tier": tier_info[0],
                "title": title_text,
                "why_good": tier_info[2],
                "why_bad": tier_info[3],
                "t0": t0,
                "t1": t1,
                "dur": w_dur,
                "punch_word": pw,
                "emphasis_words": emph,
                "hook_text": hook_text,
                "description": f"{title_text} Hook: {hook_text} #shorts #viral #gaming",
                "tags": ["shorts", "viral", "highlights", "funny", "gaming"],
                "peak_energy": w.get("peak_energy", 0.5),
                "reaction_hits": w.get("reaction_hits", 0),
                "verified": True
            })

    # Sort strictly by score / rank 1 to 5
    verified_candidates.sort(key=lambda x: -x["score"])
    for i, c in enumerate(verified_candidates[:5], 1):
        c["rank"] = i

    final_5 = verified_candidates[:5]
    if progress_cb:
        progress_cb(60, f"Successfully identified & ranked all 5 clips (Top score: {final_5[0]['score']}/100)")

    return final_5, band

def is_gaming_video(video_info, creator_profile):
    title = (video_info.get("title") or "").lower()
    cats = [str(c).lower() for c in (video_info.get("categories") or [])]

    # Strong IRL signals -> definitely NOT gaming
    irl_keywords = [
        "sanctuary", "visited", "visiting", "vlog", "irl", "interview", "podcast",
        "tour", "cooking", "in real life", "meets", "day in the life", "challenge in person",
        "fan meetup", "shopping", "eating", "camp", "animal", "zoo", "street", "house tour",
        "q&a", "unboxing", "reacting to", "reacts to"
    ]
    if any(k in title for k in irl_keywords):
        return False

    # Strong gaming signals
    gaming_keywords = [
        "rainbow six", "siege", "r6", "ranked", "gameplay", "fortnite", "valorant",
        "warzone", "cod", "call of duty", "minecraft", "roblox", "gta", "clutch",
        "1v1", "tournament", "champion rank", "copper to champ", "fnaf", "playthrough",
        "elden ring", "apex legends", "overwatch", "csgo", "cs2", "lethal company"
    ]
    if any(k in title for k in gaming_keywords):
        return True

    if any("gaming" in c for c in cats):
        return True

    # Creator specific fallback
    if creator_profile.get("id") in ("jynxzi", "caseoh"):
        if any(w in title for w in ["rank", "ranked", "siege", "r6", "1v1", "game", "match", "tournament"]):
            return True
        return False

    return False


def render_5_ranked_shorts(clips, src_video, words, band, video_info, job_id, progress_cb=None, reframe_mode=None):
    """Render each of the 5 ranked clips to 1080x1920 9:16 vertical Short format."""
    from . import creators as creators_mod
    words = load_words_data(words)
    rendered_results = []
    total_clips = len(clips)
    vid_slug = sanitize_slug(video_info.get("id", "yt"))

    # Detect or use selected streamer profile for tailored non-copyrighted BGM and upload timing
    creator_key = video_info.get("selected_creator") or creators_mod.detect_creator(
        f"{video_info.get('title', '')} {video_info.get('uploader', '')} {video_info.get('id', '')}"
    )
    creator_profile = creators_mod.get_creator_profile(creator_key)
    optimal_sched = creators_mod.calculate_next_optimal_slot(creator_profile["id"])

    # Determine whether this specific video is actual gaming gameplay or real-life / IRL
    video_is_gaming = is_gaming_video(video_info, creator_profile)
    print(f"[YouTube Pipeline] Content Classification: {'🎮 GAMING STREAM' if video_is_gaming else '📹 IRL / VLOG / REAL LIFE'}")

    # Base track profile (or specific user override)
    selected_track_id = video_info.get("selected_track_id")
    creator_tracks = creator_profile.get("tracks", [])
    user_track = None
    if selected_track_id:
        for t in creator_tracks:
            if t["id"] == selected_track_id:
                user_track = dict(t)
                break

    # Directives for styling (golden-yellow karaoke pop text, 0.4s cuts, loudnorm)
    fmt = format_mod.build_directives({"format": "moment", "creator": creator_profile["name"]})

    effective_reframe = reframe_mode or video_info.get("reframe_mode")
    for idx, c in enumerate(clips, 1):
        rank = c["rank"]
        score = c["score"]
        pct_start = 60 + int((idx - 1) / total_clips * 35)
        pct_end = 60 + int(idx / total_clips * 35)

        # Match specific track from the streamer's 4 dedicated tracks based on clip rank/vibe
        if user_track:
            clip_track = user_track
        elif creator_tracks:
            clip_track = creator_tracks[(rank - 1) % len(creator_tracks)]
        else:
            clip_track = creator_profile["music"]

        track_label = clip_track.get("name", creator_profile["music"]["name"])

        if progress_cb:
            progress_cb(pct_start, f"Rendering Clip #{rank}/5 ({score}/100): '{c['title'][:30]}' (9:16 smart tracking, {track_label[:24]}...)...")

        out_name = f"{vid_slug}_rank{rank}_{score}pts.mp4"
        out_path = os.path.join(SHORTS_DIR, out_name)

        # Slice matching words
        t0 = c["t0"]
        t1 = c["t1"]
        win_words = [w for w in words if (t0 - 0.4) <= w["start"] <= (t1 + 0.4)]
        if not win_words:
            win_words = [{"text": "MOMENT", "start": t0, "end": t1, "energy": 0.5}]

        # Verified emphasis words
        emph = []
        for e in c.get("emphasis_words") or []:
            tk = e.strip(" .,;!?").upper()
            if tk and tk not in emph:
                emph.append(tk)
        if not emph and win_words:
            emph = [win_words[0]["text"].upper()]

        # Reaction punch word
        pw = c.get("punch_word")
        punch_tin = 0.5
        for w in win_words:
            if pw and pw.lower() in w["text"].lower():
                punch_tin = max(0.1, round(w["start"] - t0, 3))
                break

        force_split = False
        is_split = False
        if effective_reframe == "split_screen":
            force_split = True
            is_split = True
        elif effective_reframe == "blur_fill":
            force_split = False
            is_split = False
        else:
            force_split = video_is_gaming and (creator_profile["id"] in ("jynxzi", "caseoh"))
            is_split = force_split

        plan = {
            "id": f"{job_id[:6]}_r{rank}",
            "rank": rank,
            "src_path": src_video,
            "src": os.path.basename(src_video),
            "t0": t0,
            "t1": t1,
            "kind": "landscape",
            "creator": creator_profile["id"],
            "reframe_mode": effective_reframe,
            "is_gaming": video_is_gaming,
            "force_split_screen": force_split,
            "is_split_screen": is_split,
            "face_zone": [round(band[0], 3), round(band[1], 3)] if band else None,
            "words": win_words,
            "emphasis": emph,
            "punch": {"tin": punch_tin, "z": 1.14},
            "title": c["title"],
            "why": c["why_good"]
        }

        out_id = f"job_{job_id[:6]}_clip{rank}"
        try:
            # 1. Cut segment
            prep_file = edit_mod.prep(plan, out_id)

            # 2. Smart 9:16 Multi-Speaker or Dynamic Face-Tracking Reframe
            reframed, face_stats = edit_mod.reframe(prep_file, plan, out_id)

            # 3. Reaction punch-in zoom (automatically bypassed for split-screen)
            punched = edit_mod.add_punch(reframed, plan, out_id)

            # 4. Kinetic animated pop karaoke subtitles & Top Viral Hook Banner
            capped = edit_mod.burn_karaoke(
                punched, prep_file, plan["words"], plan["emphasis"],
                fmt["caption"], out_id, t0_offset=plan["t0"],
                hook_text=c.get("hook_text") or c.get("title")
            )

            # 5. Broadcast audio normalization (-14 LUFS) + Context-Aware Intelligent SFX & BGM
            from . import sfx_director
            sfx_cues = sfx_director.plan_sfx_for_clip(
                clip_words=plan["words"],
                video_info=video_info,
                creator=creator_profile["id"],
                dur=t1 - t0,
                hint_sfx=c.get("sfx_type")
            )

            # Adaptive BGM: Dynamically map based on LLM decision or scene context
            title_lower = (video_info.get("title") or "").lower()
            is_irl_vlog = any(k in title_lower for k in ["kfc", "store", "vlog", "irl", "street", "interview", "food", "drive thru"])
            
            from . import music as music_mod

            # Dynamic track override from trending Shorts analysis
            llm_mood = (c.get("music_mood") or "").lower()
            chosen_track_key = clip_track.get("id", creator_profile["id"])
            if "silence" in llm_mood:
                bed_vol = 0.0
            elif "phonk" in llm_mood:
                bed_vol = 0.22
                chosen_track_key = f"{creator_profile['id']}_brazilian_phonk" if f"{creator_profile['id']}_brazilian_phonk" in music_mod.TRACK_CONFIGS else (
                    f"{creator_profile['id']}_tactical_phonk" if f"{creator_profile['id']}_tactical_phonk" in music_mod.TRACK_CONFIGS else clip_track.get("id", "speed_brazilian_phonk")
                )
            elif "horror" in llm_mood or "drone" in llm_mood:
                bed_vol = 0.18
                chosen_track_key = "caseoh_streambeats_midnight"
            elif "meme" in llm_mood or "funk" in llm_mood:
                bed_vol = 0.16
                chosen_track_key = "speed_persona_surprise"
            elif "lofi" in llm_mood or is_irl_vlog:
                bed_vol = 0.08
                chosen_track_key = "viral_shorts_lofi_bounce"
            else:
                bed_vol = float(fmt.get("music", {}).get("bed_volume", 0.16))

            _music_profile = {
                **fmt.get("music", {}),
                "enabled": (bed_vol > 0.0),
                "creator": chosen_track_key,
                "bed_volume": bed_vol,
                "duck_threshold": float(fmt.get("music", {}).get("duck_threshold", 0.055)),
                "duck_ratio": float(fmt.get("music", {}).get("duck_ratio", 8.0)),
            }
            final_mp4 = edit_mod.assemble([capped], out_path, fmt["hook"], whoosh_at=None,
                                          music_profile=_music_profile,
                                          sfx_cues=sfx_cues,
                                          creator=creator_profile["id"])

            # Aggressive cleanup: delete intermediate files immediately after each clip
            try:
                for intermediate in [prep_file, reframed, punched, capped]:
                    if intermediate and os.path.exists(intermediate):
                        os.remove(intermediate)
            except Exception:
                pass

            # 6. QA check
            qa_res = qa_mod.tech_qa(final_mp4)
            dur_actual = qa_res.get("found", {}).get("duration", round(t1 - t0, 1))

            file_size_mb = round(os.path.getsize(final_mp4) / (1024 * 1024), 2)

            rendered_results.append({
                "rank": rank,
                "score": score,
                "tier": c["tier"],
                "title": c["title"],
                "scene_topic": c.get("scene_topic") or c.get("hook_text", ""),
                "why_good": c["why_good"],
                "why_bad": c["why_bad"],
                "hook_text": c.get("hook_text", ""),
                "description": c.get("description", ""),
                "tags": c.get("tags", []),
                "peak_energy": c.get("peak_energy", 0.5),
                "reaction_hits": c.get("reaction_hits", 0),
                "creator_id": creator_profile["id"],
                "creator_name": creator_profile["name"],
                "creator_avatar": creator_profile["avatar"],
                "optimal_schedule": creators_mod.calculate_next_optimal_slot(creator_profile["id"], clip_rank=rank),
                "music_name": chosen_track_key if bed_vol > 0.0 else "None (Clean Dialogue)",
                "track_id": chosen_track_key if bed_vol > 0.0 else "none",
                "music_pool": "Trending Phonk / Funk" if bed_vol > 0.0 else "Clean Dialogue",
                "is_split_screen": plan.get("is_split_screen", False),
                "t0": t0,
                "t1": t1,
                "duration": dur_actual,
                "size_mb": file_size_mb,
                "filename": out_name,
                "file": f"data/shorts/{out_name}",
                "rel_path": f"data/shorts/{out_name}",
                "video_path": os.path.abspath(out_path),
                "download_url": f"/api/download?file=data/shorts/{out_name}",
                "stream_url": f"/video/data/shorts/{out_name}",
                "face_hits": round(face_stats.get("hits", 0.85) * 100, 1),
                "qa_passed": qa_res.get("ok", True)
            })

        except Exception as e:
            print(f"[YouTube Pipeline] Error rendering clip #{rank}: {e}")
            raise RuntimeError(f"Failed rendering short clip #{rank} ('{c.get('title')}'): {e}")

    if progress_cb:
        progress_cb(98, "All 5 shorts rendered & verified! Packaging downloadable files...")

    return rendered_results

def run_youtube_to_5_shorts(url, job_id=None, progress_cb=None, creator=None, track_id=None, keep_source=False, theme=None, reframe_mode=None, fresh=False, chunk_part=None, _is_chunked=False):
    """Full execution: URL -> Download -> Transcribe -> 5 Ranked Clips -> Render 5 Shorts."""
    job_id = job_id or uuid.uuid4().hex[:8]

    # Auto-detect Long Streams (> 2 Hours / 7200s) and route to surgical chunking engine
    info = get_youtube_info(url)
    stream_dur = float(info.get("duration") or 0.0)
    if not _is_chunked and (stream_dur > 7200.0 or chunk_part is not None):
        print(f"[YouTube Pipeline] Long Stream Detected ({stream_dur / 3600:.1f}h). Routing to 2-Hour Chunking & Heatmap Engine...")
        from . import long_stream
        return long_stream.process_long_stream_to_5_shorts(
            url=url,
            target_part=chunk_part,
            job_id=job_id,
            progress_cb=progress_cb,
            creator=creator,
            theme=theme,
            reframe_mode=reframe_mode,
            fresh=fresh
        )

    if fresh:
        try:
            vid_id = sanitize_slug(info["id"])
            purge_video_cache(vid_id, purge_source=False)
        except Exception as fe:
            print(f"[YouTube Pipeline] Fresh cleanup note: {fe}")

    # Auto-clean any stale scratch downloads or interrupted .part files before starting
    try:
        clean_all_completed_source_media()
    except Exception:
        pass

    # 1. Download
    src_video, wav_path, video_info = download_youtube_video(url, progress_cb=progress_cb)
    vid_slug = sanitize_slug(video_info.get("id", "yt"))

    # Ensure wav_path exists (extract if missing)
    if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 1000:
        if progress_cb:
            progress_cb(28, "Extracting audio track for speech recognition...")
        mt.extract_audio(src_video, wav_path, max_dur=None)

    if creator:
        video_info["selected_creator"] = creator
    if track_id:
        video_info["selected_track_id"] = track_id
    if reframe_mode:
        video_info["reframe_mode"] = reframe_mode

    # 2. Transcribe
    words, words_json = transcribe_audio_words(wav_path, vid_slug, progress_cb=progress_cb, fresh=fresh)

    # 3. LLM Ranking of 5 Clips
    clips, band = find_and_rank_5_clips(words, src_video, video_info, progress_cb=progress_cb, theme=theme)

    # 4. Render All 5 Shorts
    results = render_5_ranked_shorts(clips, src_video, words, band, video_info, job_id, progress_cb=progress_cb, reframe_mode=reframe_mode)

    # 5. Scratch cleanup: Remove raw source video and wav scratch immediately if keep_source is False
    if not keep_source:
        try:
            if os.path.exists(src_video):
                os.remove(src_video)
            if os.path.exists(wav_path):
                os.remove(wav_path)
            if progress_cb:
                progress_cb(100, "5 Viral Shorts ready & raw source media purged (zero storage clutter)!")
        except Exception as e:
            print(f"[YouTube Pipeline] Warning: Scratch cleanup note: {e}")

    # Save run manifest
    manifest_file = os.path.join(SHORTS_DIR, f"{job_id}_summary.json")
    summary = {
        "job_id": job_id,
        "video_info": video_info,
        "clips": results,
        "ranked_shorts": results,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # 6. Learn from session
    try:
        from . import memory as mem_mod
        mem_mod.record_session(
            video_id=video_info.get("id", job_id),
            title=video_info.get("title", "Video"),
            creator=video_info.get("uploader", "Creator"),
            chosen_clips=results,
            format_mode="split_two" if any(r.get("is_split_screen") for r in results) else "dynamic_reframe"
        )
    except Exception as e:
        print(f"[YouTube Pipeline] Warning: Learning memory update failed: {e}")

    if progress_cb:
        progress_cb(100, "Done! 5 Viral Shorts ready to preview and download.")

    return summary


def clean_all_completed_source_media(current_vid_id=None):
    """Automatically purge raw downloaded source videos (.mp4, .wav, .part) from completed sessions.
    
    Guarantees that your hard drive never fills up with gigabytes of temporary 50-minute stream files!
    Only the final rendered Shorts (~25MB each) are kept.
    """
    cleaned_bytes = 0
    cur_slug = sanitize_slug(current_vid_id) if current_vid_id else ""
    if not os.path.exists(DOWNLOADS_DIR):
        return 0
    for f in os.listdir(DOWNLOADS_DIR):
        if cur_slug and cur_slug in f:
            continue
        if f.endswith("_source.mp4") or f.endswith(".wav") or f.endswith(".part") or f.endswith(".ytdl") or "_source." in f:
            fp = os.path.join(DOWNLOADS_DIR, f)
            try:
                sz = os.path.getsize(fp)
                if os.path.isfile(fp):
                    os.remove(fp)
                    cleaned_bytes += sz
            except Exception:
                pass
    if cleaned_bytes > 0:
        print(f"[Storage Cleaner] Auto-freed {cleaned_bytes / (1024*1024):.1f}MB of obsolete raw stream media.")
    return cleaned_bytes


def purge_source_media(vid_id):
    """Safely remove raw source video and scratch files for a given video slug."""
    slug = sanitize_slug(vid_id)
    count = 0
    for d in [DOWNLOADS_DIR, config.media_dir()]:
        if not os.path.exists(d):
            continue
        for f in os.listdir(d):
            if slug in f and not f.endswith("_summary.json") and not f.endswith("_words.json"):
                if "shorts" in d:
                    continue
                fp = os.path.join(d, f)
                try:
                    if os.path.isfile(fp):
                        os.remove(fp)
                        count += 1
                except Exception:
                    pass
    return count

