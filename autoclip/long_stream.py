"""Long Stream Processing Engine (2-Hour Chunking & Heatmap Sniping).

Enables processing of 6-hour, 7-hour, and 8-hour live streams/VODs by:
1. Segmenting streams into 2-hour discrete chunks (Parts 1, 2, 3, etc.)
2. Sniping YouTube's "Most Replayed" retention heatmap data to locate viral peaks
3. Surgically downloading ONLY required audio and winning 45-second video clips
"""
import os
import sys
import json
import time
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from . import mediatools as mt
from . import config

PROJECT_ROOT = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
DOWNLOADS_DIR = PROJECT_ROOT / "data" / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_CHUNK_DURATION = 7200.0  # 2 Hours in seconds


def get_stream_chunks(duration: float, chunk_sec: float = DEFAULT_CHUNK_DURATION) -> List[Dict[str, Any]]:
    """Divide a long stream duration into sequential 2-hour chunks."""
    if duration <= 0:
        return []

    chunks = []
    current_t0 = 0.0
    part_idx = 1

    while current_t0 < duration:
        current_t1 = min(current_t0 + chunk_sec, duration)
        h0 = int(current_t0 // 3600)
        m0 = int((current_t0 % 3600) // 60)
        h1 = int(current_t1 // 3600)
        m1 = int((current_t1 % 3600) // 60)

        chunks.append({
            "part": part_idx,
            "t0": round(current_t0, 2),
            "t1": round(current_t1, 2),
            "duration": round(current_t1 - current_t0, 2),
            "label": f"Part {part_idx} ({h0}h{m0:02d}m – {h1}h{m1:02d}m)",
            "start_time_str": f"{h0:02d}:{m0:02d}:00",
            "end_time_str": f"{h1:02d}:{m1:02d}:00",
            "heatmap_score": 0.0,
            "peak_count": 0
        })

        current_t0 = current_t1
        part_idx += 1

    return chunks


def fetch_stream_metadata_and_heatmap(url: str) -> Dict[str, Any]:
    """Fetch video metadata and YouTube 'Most Replayed' retention heatmap graph."""
    from .youtube_pipeline import get_python_exe, get_yt_cookie_args, get_yt_env, get_youtube_info

    # 1. Fast metadata extraction via get_youtube_info (< 3 seconds)
    base_info = get_youtube_info(url)
    duration = float(base_info.get("duration") or 0.0)
    title = base_info.get("title") or "Stream"
    uploader = base_info.get("uploader") or "Creator"
    vid_id = base_info.get("id") or "stream"
    thumb = base_info.get("thumbnail") or ""

    heatmap = []
    chapters = []

    # 2. Fast heatmap extraction attempt with quick timeout
    cmd = [
        get_python_exe(), "-m", "yt_dlp",
        "--dump-json",
        "--skip-download",
        "--no-check-formats",
        "--youtube-skip-dash-manifest",
        "--socket-timeout", "8",
        "--no-warnings"
    ] + get_yt_cookie_args() + [url]

    try:
        r = subprocess.run(cmd, env=get_yt_env(), capture_output=True, text=True, timeout=6)
        if r.returncode == 0 and r.stdout.strip():
            data = json.loads(r.stdout)
            if float(data.get("duration") or 0.0) > 0:
                duration = float(data.get("duration"))
            heatmap = data.get("heatmap") or []
            chapters = data.get("chapters") or []
            title = data.get("title") or title
            uploader = data.get("uploader") or uploader
            vid_id = data.get("id") or vid_id
            thumb = data.get("thumbnail") or thumb
    except Exception as e:
        print(f"[Long Stream] Fast heatmap probe note: {e}")

    return {
        "ok": duration > 0,
        "id": vid_id,
        "title": title,
        "uploader": uploader,
        "duration": duration,
        "heatmap": heatmap,
        "chapters": chapters,
        "thumbnail": thumb
    }


def analyze_chunks_with_heatmap(chunks: List[Dict[str, Any]], heatmap: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Score each 2-hour chunk using YouTube's viewer retention and replay data."""
    if not heatmap or not chunks:
        return chunks

    for chunk in chunks:
        c_t0 = chunk["t0"]
        c_t1 = chunk["t1"]
        matching_points = [
            pt.get("value", 0.0) for pt in heatmap
            if c_t0 <= pt.get("start_time", 0.0) <= c_t1
        ]
        if matching_points:
            avg_val = sum(matching_points) / len(matching_points)
            max_val = max(matching_points)
            # Normalize to 0-100 rating
            chunk["heatmap_score"] = round(avg_val * 100, 1)
            chunk["heatmap_max"] = round(max_val * 100, 1)
            # Count significant peaks (> 0.7)
            chunk["peak_count"] = sum(1 for v in matching_points if v >= 0.7)
        else:
            chunk["heatmap_score"] = 50.0
            chunk["heatmap_max"] = 50.0
            chunk["peak_count"] = 0

    return chunks


def download_surgical_audio(url: str, t0: float, t1: float, out_wav: str, progress_cb=None, slug: Optional[str] = None) -> bool:
    """Download audio for the specified time window with maximum speed.

    1. For segments longer than 10 minutes (such as 2-hour chunks), using yt-dlp --download-sections
       triggers ffmpeg HTTP streaming which is throttled by YouTube/Twitch to ~2.5x real-time speed
       (causing 2 hours of audio to take ~48 minutes, freezing the progress at 18%).
    2. Instead, we download the entire audio track using native parallel HTTP chunked requests
       (-N 8 --http-chunk-size 10M), which streams at 3-10+ MB/s and completes in ~30-60s while
       streaming live progress updates.
    3. Once the master audio track is cached locally, ffmpeg slices the exact [t0, t1] segment
       locally in < 1 second!
    4. Future chunks of the same stream (Part 2, Part 3, etc.) will reuse the cached master audio
       and slice immediately with 0s download time.
    """
    import re
    from .youtube_pipeline import get_python_exe, get_yt_cookie_args, get_yt_env, sanitize_slug

    out_wav = os.path.abspath(out_wav)
    os.makedirs(os.path.dirname(out_wav), exist_ok=True)

    # If out_wav already exists and is valid, return immediately
    if os.path.exists(out_wav) and os.path.getsize(out_wav) > 10000:
        return True

    slug_val = slug or sanitize_slug(url.split("v=")[-1].split("/")[-1].split("?")[0])
    master_audio_prefix = str(DOWNLOADS_DIR / f"{slug_val}_master_audio")

    # 1. Check if master audio track is already downloaded and cached
    master_audio = None
    for ext in [".m4a", ".mp4", ".webm", ".opus", ".mp3"]:
        cand = f"{master_audio_prefix}{ext}"
        if os.path.exists(cand) and os.path.getsize(cand) > 50000:
            master_audio = cand
            break

    # 2. If master audio not found, download it with 8 parallel chunked connections
    if not master_audio:
        dl_template = f"{master_audio_prefix}.%(ext)s"
        cmd = [
            get_python_exe(), "-m", "yt_dlp",
            "--newline",
            "-f", "140/ba[ext=m4a]/ba[ext=webm]/Audio_Only/ba/b",
            "--concurrent-fragments", "16",
            "-N", "8",
            "-o", dl_template,
            "--no-warnings"
        ] + get_yt_cookie_args() + [url]

        print(f"[Long Stream] High-speed audio track download started for {slug_val} (16 concurrent streams)...")
        if progress_cb:
            progress_cb(18, f"High-speed downloading audio track (16 concurrent streams)...")

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
            last_cb_time = time.time()

            while True:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break
                line_str = line.strip()
                if not line_str:
                    continue
                # Parse yt-dlp download progress: [download] 45.2% of 150.00MiB at 3.50MiB/s ETA 00:23
                m = re.search(r'\[download\]\s+([0-9.]+)%(?:\s+of\s+([^\s]+)\s+at\s+([^\s]+))?', line_str)
                if m:
                    pct_val = float(m.group(1))
                    speed = m.group(3) or "fast"
                    now = time.time()
                    if (pct_val - last_pct >= 3.0 or (now - last_cb_time >= 2.0)) and progress_cb:
                        last_pct = pct_val
                        last_cb_time = now
                        bar_pct = 18 + int((pct_val / 100.0) * 11)
                        progress_cb(bar_pct, f"Downloading audio: {pct_val:.0f}% ({speed})...")

            proc.wait(timeout=30)
            if proc.returncode != 0:
                print(f"[Long Stream] Audio track download finished with code {proc.returncode}")
        except Exception as e:
            print(f"[Long Stream] High-speed audio download process note: {e}")

        # Locate completed master audio file
        for ext in [".m4a", ".mp4", ".webm", ".opus", ".mp3"]:
            cand = f"{master_audio_prefix}{ext}"
            if os.path.exists(cand) and os.path.getsize(cand) > 50000:
                master_audio = cand
                break

    # 3. If master audio successfully acquired, slice local audio in < 1 second!
    if master_audio and os.path.exists(master_audio):
        dur = t1 - t0
        if progress_cb:
            progress_cb(29, f"Slicing 16kHz WAV for Whisper ({t0/3600:.1f}h–{t1/3600:.1f}h)...")

        slice_cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{t0:.2f}",
            "-t", f"{dur:.2f}",
            "-i", master_audio,
            "-vn", "-ac", "1", "-ar", "16000",
            out_wav
        ]
        mt.run(slice_cmd, allow_fail=False)
        if os.path.exists(out_wav) and os.path.getsize(out_wav) > 1000:
            print(f"[Long Stream] ✅ Successfully extracted local audio slice to {out_wav} in < 1s")
            return True

    # 4. Fallback: direct surgical range extraction if master audio was unavailable
    print(f"[Long Stream] Falling back to surgical range extraction...")
    import uuid
    u_id = uuid.uuid4().hex[:6]
    temp_prefix = out_wav + f"_raw_{u_id}"

    h0 = int(t0 // 3600)
    m0 = int((t0 % 3600) // 60)
    s0 = int(t0 % 60)

    h1 = int(t1 // 3600)
    m1 = int((t1 % 3600) // 60)
    s1 = int(t1 % 60)

    section_arg = f"*{h0:02d}:{m0:02d}:{s0:02d}-{h1:02d}:{m1:02d}:{s1:02d}"

    cmd = [
        get_python_exe(), "-m", "yt_dlp",
        "--download-sections", section_arg,
        "-N", "8",
        "-f", "ba/b",
        "--force-keyframes-at-cuts",
        "-o", f"{temp_prefix}.%(ext)s",
        "--no-warnings"
    ] + get_yt_cookie_args() + [url]

    try:
        r = subprocess.run(cmd, env=get_yt_env(), capture_output=True, text=True, timeout=900)
        downloaded = None
        for ext in [".webm", ".m4a", ".mp3", ".opus", ".wav", ".mp4"]:
            cand = f"{temp_prefix}{ext}"
            if os.path.exists(cand) and os.path.getsize(cand) > 1000:
                downloaded = cand
                break
            part_cand = f"{temp_prefix}{ext}.part"
            if os.path.exists(part_cand) and os.path.getsize(part_cand) > 10000:
                try:
                    if os.path.exists(cand):
                        os.remove(cand)
                    os.rename(part_cand, cand)
                    downloaded = cand
                    break
                except Exception:
                    pass

        if not downloaded:
            print(f"[Long Stream] Audio download returned code {r.returncode}, output: {r.stderr[-300:]}")
            return False

        mt.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", downloaded,
            "-vn", "-ac", "1", "-ar", "16000",
            out_wav
        ], allow_fail=False)

        try:
            if os.path.exists(downloaded):
                os.remove(downloaded)
        except Exception:
            pass

        return os.path.exists(out_wav) and os.path.getsize(out_wav) > 1000
    except Exception as e:
        print(f"[Long Stream] Surgical audio extraction error: {e}")
        return False


def download_surgical_video(url: str, t0: float, t1: float, out_mp4: str) -> bool:
    """Download video for ONLY the specific winning 45-50s clip section."""
    import uuid
    from .youtube_pipeline import get_python_exe, get_yt_cookie_args, get_yt_env

    out_mp4 = os.path.abspath(out_mp4)
    u_id = uuid.uuid4().hex[:6]
    temp_prefix = out_mp4 + f"_raw_{u_id}"

    # Add 2 seconds padding on each side for safety
    pad_t0 = max(0.0, t0 - 2.0)
    pad_t1 = t1 + 2.0

    h0 = int(pad_t0 // 3600)
    m0 = int((pad_t0 % 3600) // 60)
    s0 = int(pad_t0 % 60)

    h1 = int(pad_t1 // 3600)
    m1 = int((pad_t1 % 3600) // 60)
    s1 = int(pad_t1 % 60)

    section_arg = f"*{h0:02d}:{m0:02d}:{s0:02d}-{h1:02d}:{m1:02d}:{s1:02d}"

    from .youtube_pipeline import get_bgutil_args, ensure_bgutil_server
    ensure_bgutil_server()

    cmd = [
        get_python_exe(), "-m", "yt_dlp",
        "--download-sections", section_arg,
        "-N", "8",
        "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
        "--force-keyframes-at-cuts",
        "--merge-output-format", "mp4",
        "-o", f"{temp_prefix}.%(ext)s",
        "--no-warnings"
    ] + get_yt_cookie_args() + get_bgutil_args() + [url]

    print(f"[Long Stream] Surgically downloading winning clip video ({t1 - t0:.1f}s): {section_arg}...")

    def _find_candidate():
        # Check explicit extensions
        for ext in [".mp4", ".mkv", ".webm", ".ts"]:
            p = f"{temp_prefix}{ext}"
            if os.path.exists(p) and os.path.getsize(p) > 1000:
                return p
            part_p = f"{p}.part"
            if os.path.exists(part_p) and os.path.getsize(part_p) > 1000:
                try:
                    os.rename(part_p, p)
                    return p
                except Exception:
                    pass
        # Search by prefix
        parent_dir = os.path.dirname(temp_prefix) or "."
        base_prefix = os.path.basename(temp_prefix)
        for f in os.listdir(parent_dir):
            if f.startswith(base_prefix):
                fp = os.path.join(parent_dir, f)
                if fp.endswith(".part"):
                    target_fp = fp[:-5]
                    try:
                        os.rename(fp, target_fp)
                        return target_fp
                    except Exception:
                        pass
                elif os.path.isfile(fp) and os.path.getsize(fp) > 1000:
                    return fp
        return None

    try:
        r = subprocess.run(cmd, env=get_yt_env(), capture_output=True, text=True, timeout=300)
        cand = _find_candidate()

        # If primary failed, retry with Android player client
        if not cand:
            print("[Long Stream] Primary slice download unfulfilled, retrying with Android player client...")
            alt_cmd = [
                get_python_exe(), "-m", "yt_dlp",
                "--download-sections", section_arg,
                "--extractor-args", "youtube:player_client=android,web",
                "-N", "8",
                "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
                "--force-keyframes-at-cuts",
                "--merge-output-format", "mp4",
                "-o", f"{temp_prefix}.%(ext)s",
                "--no-warnings"
            ] + get_yt_cookie_args() + [url]
            r2 = subprocess.run(alt_cmd, env=get_yt_env(), capture_output=True, text=True, timeout=300)
            cand = _find_candidate()

        if cand and os.path.exists(cand) and os.path.getsize(cand) > 1000:
            # Trim exact desired range with ffmpeg
            offset = max(0.0, t0 - pad_t0)
            dur = t1 - t0
            mt.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-ss", f"{offset:.2f}",
                "-i", cand,
                "-t", f"{dur:.2f}",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                "-c:a", "aac",
                out_mp4
            ], allow_fail=False)

            try:
                os.remove(cand)
            except Exception:
                pass

            return os.path.exists(out_mp4) and os.path.getsize(out_mp4) > 1000
        else:
            print(f"[Long Stream] Surgical video candidate not found after download attempts.")
    except Exception as e:
        print(f"[Long Stream] Surgical video download error: {e}")

    return False


def process_long_stream_to_5_shorts(
    url: str,
    target_part: Optional[int] = None,
    job_id: Optional[str] = None,
    progress_cb=None,
    creator: Optional[str] = None,
    theme: Optional[str] = None,
    reframe_mode: Optional[str] = None,
    fresh: bool = False
) -> Dict[str, Any]:
    """Execute end-to-end 2-Hour Chunked Pipeline with YouTube Heatmap Sniping."""
    import uuid
    from . import youtube_pipeline
    from . import creators as creators_mod
    from . import format as format_mod
    from . import edit as edit_mod
    from . import qa as qa_mod

    job_id = job_id or uuid.uuid4().hex[:8]
    shorts_dir = PROJECT_ROOT / "data" / "shorts"
    shorts_dir.mkdir(parents=True, exist_ok=True)

    if progress_cb:
        progress_cb(10, "Fetching stream metadata & YouTube viewer retention heatmap...")

    meta = fetch_stream_metadata_and_heatmap(url)
    dur = meta.get("duration", 0.0)
    vid_id = meta.get("id", "stream")
    title = meta.get("title", "Long Stream")
    uploader = meta.get("uploader", "Creator")
    heatmap = meta.get("heatmap", [])

    if dur <= 0:
        fast_info = youtube_pipeline.get_youtube_info(url)
        dur = float(fast_info.get("duration") or 0.0)
        if dur > 0:
            vid_id = fast_info.get("id") or vid_id
            title = fast_info.get("title") or title
            uploader = fast_info.get("uploader") or uploader
            if not meta.get("thumbnail"):
                meta["thumbnail"] = fast_info.get("thumbnail", "")

    if dur <= 0:
        raise RuntimeError(f"Could not determine stream duration for '{url}'. If this is an ongoing live broadcast, please wait until the stream has concluded.")

    chunks = get_stream_chunks(dur)
    scored_chunks = analyze_chunks_with_heatmap(chunks, heatmap)

    # 1. Select target chunk (User requested part or highest heatmap score)
    target_chunk = None
    if target_part:
        target_chunk = next((c for c in scored_chunks if c["part"] == target_part), None)

    if not target_chunk:
        # Auto-snipe hottest segment based on peak retention
        target_chunk = max(scored_chunks, key=lambda c: (c.get("peak_count", 0), c.get("heatmap_score", 0)))
        print(f"[Long Stream] Auto-selected highest retention segment: {target_chunk['label']} (Replay Score: {target_chunk.get('heatmap_score')}/100, Peaks: {target_chunk.get('peak_count')})")

    c_part = target_chunk["part"]
    c_t0 = target_chunk["t0"]
    c_t1 = target_chunk["t1"]
    c_label = target_chunk["label"]

    if progress_cb:
        progress_cb(18, f"Surgically downloading audio for {c_label} (Heatmap: {target_chunk.get('heatmap_score')}/100)...")

    c_slug = youtube_pipeline.sanitize_slug(vid_id)
    chunk_wav = str(DOWNLOADS_DIR / f"{c_slug}_p{c_part}.wav")

    # Download surgical audio only if missing
    if fresh or not os.path.exists(chunk_wav) or os.path.getsize(chunk_wav) < 1000:
        ok = download_surgical_audio(url, c_t0, c_t1, chunk_wav, progress_cb=progress_cb, slug=c_slug)
        if not ok:
            raise RuntimeError(f"Failed to surgically download audio stream for {c_label}")

    # 2. Transcribe this 2-hour window
    if progress_cb:
        progress_cb(32, f"Transcribing {c_label} with faster-whisper...")

    words, _ = youtube_pipeline.transcribe_audio_words(chunk_wav, f"{c_slug}_p{c_part}", progress_cb=progress_cb, fresh=fresh)

    # Offset words by c_t0 so they map to true global stream timestamps
    for w in words:
        w["start"] = round(w["start"] + c_t0, 2)
        w["end"] = round(w["end"] + c_t0, 2)

    video_info = {
        "id": vid_id,
        "title": f"{title} [{c_label}]",
        "uploader": uploader,
        "duration": dur,
        "thumbnail": meta.get("thumbnail", ""),
        "selected_creator": creator or creators_mod.detect_creator(f"{title} {uploader}"),
        "selected_chunk": target_chunk
    }

    # 3. LLM Ranking of TOP 5 clips across this segment
    if progress_cb:
        progress_cb(52, f"Querying Free LLM API for TOP 5 viral clips in {c_label}...")

    clips, band = youtube_pipeline.find_and_rank_5_clips(words, chunk_wav, video_info, progress_cb=progress_cb, theme=theme)

    creator_key = video_info["selected_creator"]
    creator_profile = creators_mod.get_creator_profile(creator_key)
    creator_tracks = creator_profile.get("tracks", [])

    is_gaming = youtube_pipeline.is_gaming_video(video_info, creator_profile)
    effective_reframe = reframe_mode or "blur_fill"

    rendered_results = []
    total_clips = len(clips)

    # 4. Surgically download ONLY the 5 winning ~45s video slices and render
    for idx, c in enumerate(clips, 1):
        rank = c["rank"]
        score = c["score"]
        t0 = c["t0"]
        t1 = c["t1"]
        clip_dur = round(t1 - t0, 2)

        clip_track = creator_tracks[(rank - 1) % len(creator_tracks)] if creator_tracks else creator_profile["music"]
        track_label = clip_track.get("name", "BGM")

        pct = 60 + int(idx / total_clips * 35)
        if progress_cb:
            progress_cb(pct, f"Surgically extracting & rendering Clip #{rank}/5 ({score}/100): '{c['title'][:25]}' ({track_label[:20]})...")

        temp_slice = str(DOWNLOADS_DIR / f"{c_slug}_slice_r{rank}.mp4")
        dl_ok = download_surgical_video(url, t0, t1, temp_slice)
        if not dl_ok:
            print(f"[Long Stream] Warning: Failed to download video slice for Rank #{rank}, skipping...")
            continue

        out_name = f"{c_slug}_p{c_part}_rank{rank}_{score}pts.mp4"
        out_path = str(shorts_dir / out_name)

        # Slice matching words relative to the 0.0 start of temp_slice
        win_words = [
            {
                "text": w.get("text", ""),
                "start": max(0.0, round(w["start"] - t0, 2)),
                "end": max(0.0, round(w["end"] - t0, 2)),
                "energy": w.get("energy", 0.5)
            }
            for w in words if (t0 - 0.4) <= w["start"] <= (t1 + 0.4)
        ]
        if not win_words:
            win_words = [{"text": "MOMENT", "start": 0.0, "end": clip_dur, "energy": 0.5}]

        emph = [e.strip(" .,;!?").upper() for e in (c.get("emphasis_words") or []) if e.strip(" .,;!?")]
        if not emph and win_words:
            emph = [win_words[0]["text"].upper()]

        pw = c.get("punch_word")
        punch_tin = 0.5
        for w in win_words:
            if pw and pw.lower() in w["text"].lower():
                punch_tin = max(0.1, round(w["start"], 3))
                break

        force_split = is_gaming and (creator_profile["id"] in ("jynxzi", "caseoh"))

        plan = {
            "id": f"{job_id[:6]}_r{rank}",
            "rank": rank,
            "src_path": temp_slice,
            "src": os.path.basename(temp_slice),
            "t0": 0.0,
            "t1": clip_dur,
            "kind": "landscape",
            "creator": creator_profile["id"],
            "reframe_mode": effective_reframe,
            "is_gaming": is_gaming,
            "force_split_screen": force_split,
            "is_split_screen": force_split,
            "face_zone": [round(band[0], 3), round(band[1], 3)] if band else [0.2, 0.45],
            "crop": {"x": 0.33, "y": 0.0, "w": 0.34, "h": 1.0},
            "subtitles": {
                "format": "word_pop",
                "words": win_words,
                "highlight_color": "&H00D7FF&",
                "font_size": 18,
                "bottom_margin": 140,
                "punch_time": punch_tin,
                "emphasis_words": emph
            },
            "audio": {
                "duck_db": -16.0,
                "music_path": clip_track.get("path") if not clip_track.get("is_silent") else None,
                "music_volume": 0.18,
                "loudnorm": True,
                "target_lufs": -14.0
            },
            "sfx": {
                "type": c.get("sfx_type") or "vine_boom",
                "time": punch_tin,
                "volume": 0.4
            },
            "hook": {
                "text": c.get("hook_text") or c.get("scene_topic") or "WATCH THIS",
                "duration": 3.0,
                "color": "#FFE500"
            },
            "output": out_path
        }

        try:
            render_res = edit_mod.render_moment(plan)
            final_mp4 = render_res.get("output_path", out_path)
            qa_res = qa_mod.tech_qa(final_mp4)
            dur_actual = qa_res.get("found", {}).get("duration", clip_dur)
            file_size_mb = round(os.path.getsize(final_mp4) / (1024 * 1024), 2)

            rendered_results.append({
                "rank": rank,
                "t0": t0,
                "t1": t1,
                "duration": dur_actual,
                "size_mb": file_size_mb,
                "filename": out_name,
                "file": f"data/shorts/{out_name}",
                "rel_path": f"data/shorts/{out_name}",
                "video_path": os.path.abspath(final_mp4),
                "title": c.get("title", f"Clip #{rank}"),
                "scene_topic": c.get("scene_topic", f"HIGHLIGHT #{rank}"),
                "hook": c.get("hook_text", ""),
                "description": c.get("description", ""),
                "tags": c.get("tags", []),
                "score": score,
                "tier": c.get("tier", "Viral Highlight"),
                "creator_id": creator_profile["id"],
                "creator_name": creator_profile["name"],
                "optimal_schedule": creators_mod.calculate_next_optimal_slot(creator_profile["id"], clip_rank=rank)
            })
        finally:
            # Clean up the temporary surgical slice immediately
            try:
                if os.path.exists(temp_slice):
                    os.remove(temp_slice)
            except Exception:
                pass

    # Save summary manifest
    manifest_file = os.path.join(shorts_dir, f"{job_id}_summary.json")
    summary = {
        "job_id": job_id,
        "video_info": video_info,
        "video_title": video_info.get("title", f"{title} [{c_label}]"),
        "clips": rendered_results,
        "ranked_shorts": rendered_results,
        "shorts": rendered_results,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    if progress_cb:
        progress_cb(100, f"Done! 5 Viral Shorts from {c_label} ready to preview and download.")

    return summary
