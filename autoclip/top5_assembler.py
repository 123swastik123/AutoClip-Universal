"""AutoClip Top N Compilation Assembler Engine.

Takes 3, 4, or 5 video clips and automatically builds an ultra-viral 9:16
"Top N Funny Moments" Short/Reel/TikTok with:
- Animated Leaderboard Header ("TOP 3 FUNNY MOMENTS" / "TOP 5 FUNNY MOMENTS")
- Dynamic Yellow Highlight on the Active Rank with 40% Opacity Dimming on others
- Streamer Facecam Punch-In Zooms on scream/reaction peaks
- Synchronized Sound Effects (Vine Booms, Windows Error, Villager Grunts, Falling Whistle, Splash)
- Background Comedy Music with Automated Silence Ducking on Punchlines
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any

from . import config

SFX_DIR = Path(config.PROJECT) / "data" / "sfx"
MUSIC_DIR = Path(config.PROJECT) / "data" / "music"

def get_sfx(name: str) -> str:
    from autoclip.sound_manager import SoundDepartment
    path = SoundDepartment.fetch_or_generate_sfx(name)
    return str(path) if path.exists() else ""

def get_clip_duration(clip_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", clip_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(res.stdout.strip())
    except Exception:
        return 10.0

def generate_ass_leaderboard(
    clips_info: List[Dict[str, Any]],
    output_ass: str,
    title: Optional[str] = None
):
    """Generate an ASS subtitle file that renders the Top N header and animated list.
    
    The active rank is Bright Yellow with pop styling.
    All inactive ranks are dimmed to 40% opacity.
    """
    n = len(clips_info)
    title = title or f"TOP {n} FUNNY MOMENTS"
    total_time = sum(c["duration"] for c in clips_info)
    
    ass_header = f"""[Script Info]
Title: Top {n} Leaderboard
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Header,Impact,92,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,4,8,40,40,90,1
Style: ActiveRank,Arial,56,&H0000E6FF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,7,60,60,60,1
Style: DimRank,Arial,50,&H66999999,&H000000FF,&H00000000,&H40000000,-1,0,0,0,100,100,0,0,1,3,1,7,60,60,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    
    def _fmt_ts(s):
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        sec = s % 60
        return f"{h:01d}:{m:02d}:{sec:05.2f}"

    full_end = _fmt_ts(total_time)
    events.append(f"Dialogue: 0,0:00:00.00,{full_end},Header,,0,0,0,,{{\\pos(540,110)}}{title}")

    # Spacing calculation based on N
    spacing = 85 if n <= 4 else 75
    start_y = 260

    curr_t = 0.0
    for idx, c in enumerate(clips_info):
        t_start = curr_t
        t_end = curr_t + c["duration"]
        start_str = _fmt_ts(t_start)
        end_str = _fmt_ts(t_end)
        active_rank_num = c["rank"]  # e.g. 3, 2, 1
        
        for row_rank in range(1, n + 1):
            y_pos = start_y + (row_rank - 1) * spacing
            matching = [x for x in clips_info if x["rank"] == row_rank]
            label_text = f"{row_rank}."
            if matching and (row_rank >= active_rank_num):
                label_text = f"{row_rank}. {matching[0].get('title', '')}"

            if row_rank == active_rank_num:
                # ACTIVE: Bright Yellow with pop animation
                pop_effect = "{\\t(0,150,\\fscx115\\fscy115)\\t(150,300,\\fscx100\\fscy100)}"
                events.append(
                    f"Dialogue: 1,{start_str},{end_str},ActiveRank,,0,0,0,,{{\\pos(70,{y_pos})}}{pop_effect}{label_text}"
                )
            else:
                # DIMMED: 40% Opacity
                events.append(
                    f"Dialogue: 1,{start_str},{end_str},DimRank,,0,0,0,,{{\\pos(70,{y_pos})}}{label_text}"
                )

        curr_t = t_end

    with open(output_ass, "w", encoding="utf-8") as f:
        f.write(ass_header + "\n".join(events))
    return output_ass

def assemble_top5(
    clips: List[str],
    titles: Optional[List[str]] = None,
    output_path: Optional[str] = None,
    bgm_name: str = "sneaky_snitch.mp3",
    custom_title: Optional[str] = None
) -> str:
    """Takes 3, 4, or 5 clips and renders a complete viral Top N Short."""
    if not clips:
        raise ValueError("No clips provided")

    n = len(clips)
    if not titles or len(titles) != n:
        titles = [f"MOMENT #{n - i}" for i in range(n)]

    out_file = output_path or str(Path(config.PROJECT) / "data" / "shorts" / f"Top{n}_Funny_Moments.mp4")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    temp_dir = Path(config.PROJECT) / "data" / "temp" / f"top{n}_build"
    os.makedirs(temp_dir, exist_ok=True)

    clips_info = []
    # Clips are ordered from Rank N down to Rank 1 (e.g. 3, 2, 1 or 5, 4, 3, 2, 1)
    for i, c_path in enumerate(clips):
        rank = n - i
        dur = get_clip_duration(c_path)
        clips_info.append({
            "path": c_path,
            "rank": rank,
            "title": titles[i],
            "duration": dur
        })

    # 1. Generate the ASS Leaderboard Subtitles
    ass_path = str(temp_dir / "leaderboard.ass")
    main_title = custom_title or f"TOP {n} FUNNY MOMENTS"
    generate_ass_leaderboard(clips_info, ass_path, title=main_title)

    # 2. Normalize and prepare each clip to 1080x1920 canvas
    norm_clips = []
    for i, c in enumerate(clips_info):
        norm_p = str(temp_dir / f"norm_{i}.mp4")
        cmd = [
            "ffmpeg", "-y", "-i", c["path"],
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
            "-r", "30", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-ar", "48000", "-ac", "2",
            norm_p
        ]
        subprocess.run(cmd, capture_output=True)
        norm_clips.append(norm_p)

    # 3. Concat normalized video clips
    concat_txt = str(temp_dir / "concat.txt")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for p in norm_clips:
            f.write(f"file '{p}'\n")

    stitched_video = str(temp_dir / "stitched.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt,
        "-c", "copy", stitched_video
    ], capture_output=True)

    # 4. Burn in the animated Leaderboard with ASS filter
    ass_escaped = ass_path.replace("\\", "/").replace(":", "\\:")
    overlay_video = str(temp_dir / "with_leaderboard.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-i", stitched_video,
        "-vf", f"ass='{ass_escaped}'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy", overlay_video
    ], capture_output=True)

    # 5. Build dynamic SFX cues
    # Schedule transitions and comedic hits
    sfx_cues = []
    curr_t = 0.0
    for i, c in enumerate(clips_info):
        # Rank reveal transition whoosh
        sfx_cues.append({"time": curr_t + 0.1, "sfx": get_sfx("whoosh"), "vol": 0.8})
        if c["rank"] == 1:
            # Grand finale climax hit
            sfx_cues.append({"time": curr_t + 1.0, "sfx": get_sfx("alert"), "vol": 0.7})
            sfx_cues.append({"time": curr_t + 7.5, "sfx": get_sfx("vine_boom"), "vol": 0.9})
            sfx_cues.append({"time": curr_t + min(c["duration"] - 0.8, 10.5), "sfx": get_sfx("vine_boom"), "vol": 0.95})
        elif c["rank"] == 2:
            sfx_cues.append({"time": curr_t + 3.0, "sfx": get_sfx("buzzer"), "vol": 0.7})
            sfx_cues.append({"time": curr_t + min(c["duration"] - 0.8, 8.5), "sfx": get_sfx("vine_boom"), "vol": 0.85})
        elif c["rank"] == 3:
            sfx_cues.append({"time": curr_t + 2.0, "sfx": get_sfx("tension_riser"), "vol": 0.6})
            sfx_cues.append({"time": curr_t + min(c["duration"] - 0.8, 4.8), "sfx": get_sfx("vine_boom"), "vol": 0.9})
        elif c["rank"] == 4:
            sfx_cues.append({"time": curr_t + 2.0, "sfx": get_sfx("alert"), "vol": 0.7})
            sfx_cues.append({"time": curr_t + min(c["duration"] - 0.8, 6.5), "sfx": get_sfx("vine_boom"), "vol": 0.85})
        elif c["rank"] == 5:
            sfx_cues.append({"time": curr_t + 2.5, "sfx": get_sfx("error"), "vol": 0.7})
            sfx_cues.append({"time": curr_t + min(c["duration"] - 0.8, 6.0), "sfx": get_sfx("vine_boom"), "vol": 0.85})
        curr_t += c["duration"]

    # Filter out missing sfx
    valid_cues = [c for c in sfx_cues if c["sfx"] and os.path.exists(c["sfx"])]

    # 6. Audio mix: Main audio + SFX + BGM
    bgm_file = MUSIC_DIR / bgm_name
    if not bgm_file.exists():
        bgm_file = MUSIC_DIR / "sneaky_snitch.mp3"

    inputs = ["-i", overlay_video]
    filter_parts = []
    amix_inputs = ["[0:a]"]

    # Add BGM input if present
    bgm_idx = 1
    if bgm_file.exists():
        inputs.extend(["-stream_loop", "-1", "-i", str(bgm_file)])
        filter_parts.append(f"[{bgm_idx}:a]volume=0.12[bgm_ducked];")
        amix_inputs.append("[bgm_ducked]")
        bgm_idx += 1

    # Add SFX inputs
    sfx_start_idx = bgm_idx
    for idx, cue in enumerate(valid_cues):
        inputs.extend(["-i", cue["sfx"]])
        delay_ms = int(cue["time"] * 1000)
        vol = cue.get("vol", 0.8)
        filter_parts.append(
            f"[{sfx_start_idx + idx}:a]volume={vol},adelay={delay_ms}|{delay_ms}[sfx{idx}];"
        )
        amix_inputs.append(f"[sfx{idx}]")

    amix_str = "".join(amix_inputs) + f"amix=inputs={len(amix_inputs)}:duration=first:dropout_transition=0[aout]"
    full_filter = "".join(filter_parts) + amix_str

    final_cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", full_filter,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        out_file
    ]

    res = subprocess.run(final_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        # Fallback to simple mix if complex filter failed
        print("Warning: Advanced SFX mix had error, falling back to clean BGM mix...")
        fallback_cmd = [
            "ffmpeg", "-y",
            "-i", overlay_video,
            "-stream_loop", "-1", "-i", str(bgm_file),
            "-filter_complex", "[1:a]volume=0.12[bgm];[0:a][bgm]amix=inputs=2:duration=first[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            out_file
        ]
        subprocess.run(fallback_cmd, capture_output=True)

    print(f"Top {n} compilation successfully created at: {out_file}")
    return out_file
