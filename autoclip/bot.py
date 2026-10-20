"""AutoClip Hermes / VM Autonomous Bot Engine.

Designed for complete hands-free execution:
1. Receives YouTube URL from bot/chat
2. Extracts source & audio
3. Word-level transcription via faster-whisper
4. Free LLM API multi-model ranking of top 5 moments
5. 9:16 portrait reframe with face-tracking & golden subtitles
6. Royalty-free streamer background music (-14 LUFS, 0 SFX)
7. Dual-gate QA verification
8. Auto-upload to YouTube with title, description, tags & optimal scheduled audience slot.
"""

import os, sys, json, argparse, time
from . import config, youtube_pipeline, composio_client, creators

def process_youtube_url(url, creator=None, auto_upload=False, upload_rank=1, privacy="public", progress_cb=None, theme=None, reframe_mode=None, fresh=False, chunk_part=None):
    """Full hands-free execution for bot integrations.

    Args:
        url: Full YouTube video URL
        creator: Creator profile slug ('speed', 'kai', 'jynxzi', 'caseoh', or None for auto)
        auto_upload: If True, automatically upload the top short(s) to YouTube
        upload_rank: Which rank to upload (default 1 = highest ranked short)
        privacy: 'public', 'private', or 'unlisted'
        progress_cb: Optional callback(pct, msg) for UI progress updates
        theme: Explicit theme focus (e.g. 'horror', 'foods eating', 'headshots', 'rage')
        reframe_mode: 'blur_fill' or 'split_screen' or None
        fresh: If True, purge any prior partial downloads/transcripts and run 100% fresh from start
        chunk_part: Optional 2-hour chunk segment number for long streams (e.g. 1, 2, 3...)

    Returns:
        dict with all generated shorts metadata and upload receipts
    """
    print(f"\n[AutoClip Bot] Starting autonomous pipeline for: {url}")
    print(f"[AutoClip Bot] Creator profile: {creator or 'Auto-Detect'} | Theme: {theme or 'Viral Highlights'} | Layout: {reframe_mode or 'Auto'} | Fresh: {fresh} | Chunk: {chunk_part or 'Auto/Whole'}")

    def progress(pct, msg):
        print(f"[{pct:3d}%] {msg}", flush=True)
        if progress_cb:
            try:
                progress_cb(pct, msg)
            except Exception:
                pass

    # Step 1: Run complete 5-Shorts generation pipeline
    t0 = time.time()
    result = youtube_pipeline.run_youtube_to_5_shorts(url, progress_cb=progress, creator=creator, theme=theme, reframe_mode=reframe_mode, fresh=fresh, chunk_part=chunk_part)
    elapsed = time.time() - t0

    video_info = result.get("video_info", {})
    ranked_shorts = result.get("ranked_shorts") or result.get("clips", [])
    for s in ranked_shorts:
        if not s.get("video_path"):
            f_rel = s.get("file") or s.get("rel_path") or ""
            if f_rel:
                abs_f = os.path.abspath(f_rel)
                if os.path.exists(abs_f):
                    s["video_path"] = abs_f

    print(f"\n[AutoClip Bot] Generation complete in {elapsed:.1f}s! {len(ranked_shorts)} Shorts created.")

    # Step 2: Auto-upload if requested
    upload_results = []
    if auto_upload and ranked_shorts:
        for short in ranked_shorts:
            r_num = short.get("rank", 0)
            if upload_rank and r_num != upload_rank:
                continue

            v_path = short.get("video_path")
            if not v_path or not os.path.exists(v_path):
                continue

            from . import viral_metadata, thumbnail_generator
            raw_title = short.get("title", f"{video_info.get('title', 'Creator')} Best Moment")
            hook_text = short.get("hook", "")
            c_slug = creator or video_info.get("selected_creator")
            if not c_slug:
                detected = creators.detect_creator(
                    f"{video_info.get('title', '')} {video_info.get('uploader', '')} {video_info.get('id', '')}"
                )
                c_slug = detected if detected in ("speed", "caseoh", "jynxzi") else "jynxzi"

            meta = viral_metadata.build_viral_metadata(raw_title, hook=hook_text, creator=c_slug, theme=theme)
            title = meta["title"]
            desc = meta["description"]
            tags = meta["tags"]
            pinned_comment = meta.get("pinned_comment")

            # Generate High-CTR Thumbnail
            thumb_path = thumbnail_generator.generate_short_thumbnail(
                v_path,
                title=title,
                creator=c_slug,
                hook=hook_text,
                theme=theme
            )
            short["thumbnail_path"] = thumb_path

            # Calculate dynamic nearest optimal audience upload slot (with rank staggering)
            slot = creators.calculate_next_optimal_slot(c_slug, clip_rank=r_num)
            pub_at = slot.get("target_iso")

            print(f"[AutoClip Bot] Uploading Rank #{r_num} ('{title}') to YouTube channel for creator '{c_slug}'...")
            u_res = composio_client.upload_video_to_youtube(
                v_path,
                title=title,
                description=desc,
                tags=tags,
                privacy=privacy,
                publish_at=pub_at,
                creator=c_slug,
                thumbnail_path=thumb_path,
                pinned_comment=pinned_comment
            )
            short["upload_receipt"] = u_res
            upload_results.append({
                "rank": r_num,
                "title": title,
                "receipt": u_res
            })
            print(f"[AutoClip Bot] Upload result for Rank #{r_num}: {u_res.get('ok')}")

    output_payload = {
        "ok": True,
        "source_url": url,
        "video_title": video_info.get("title", ""),
        "uploader": video_info.get("uploader", ""),
        "total_time_seconds": round(elapsed, 1),
        "shorts": ranked_shorts,
        "uploads": upload_results
    }
    return output_payload

def main():
    parser = argparse.ArgumentParser(description="AutoClip Hands-Free Bot Engine")
    parser.add_argument("url", help="YouTube video URL to clip")
    parser.add_argument("--creator", choices=["speed", "kai", "jynxzi", "caseoh"], default=None, help="Target streamer profile")
    parser.add_argument("--upload", action="store_true", help="Automatically upload top short to YouTube")
    parser.add_argument("--upload-rank", type=int, default=1, help="Which ranked short to upload (1-5)")
    parser.add_argument("--privacy", choices=["public", "private", "unlisted"], default="public", help="Upload privacy status")
    parser.add_argument("--json", action="store_true", help="Print only JSON output for machine parsing")
    args = parser.parse_args()

    res = process_youtube_url(
        args.url,
        creator=args.creator,
        auto_upload=args.upload,
        upload_rank=args.upload_rank,
        privacy=args.privacy
    )

    if args.json:
        print("\n===AUTOCLIP_JSON_START===")
        print(json.dumps(res, indent=2))
        print("===AUTOCLIP_JSON_END===")

if __name__ == "__main__":
    main()
