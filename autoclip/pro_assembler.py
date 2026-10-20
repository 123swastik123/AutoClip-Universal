"""AutoClip Pro Top-Tier Compilation Assembler Engine (Master Sound Design).

Builds high-retention 9:16 Top 5 / Top 3 Shorts with:
- Visual Camera Flash / Whip Transitions (fade from white + shutter + whoosh)
- Frame-Accurate Millisecond Synchronized Sound Effects (clean, minimal, non-intrusive)
- No unnecessary sirens, robotic pings, or loud clutter
- Bouncing Active Yellow Leaderboard Ranks with 35% Dimmed Background
- Ducked Upbeat Comedy Music (-22dB)
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
    for ext in [".wav", ".mp3"]:
        p = SFX_DIR / f"{name}{ext}"
        if p.exists():
            return str(p)
        dl_p = Path("C:/Users/swastik/Downloads") / f"{name}{ext}"
        if dl_p.exists():
            return str(dl_p)
    return ""

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

def generate_pro_leaderboard(
    clips_info: List[Dict[str, Any]],
    output_ass: str,
    title: str = "TOP 5 FUNNIEST SPEED MOMENTS"
):
    n = len(clips_info)
    total_time = sum(c["duration"] for c in clips_info)
    
    ass_header = f"""[Script Info]
Title: Pro Top {n} Leaderboard
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Header,Impact,92,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,4,8,40,40,90,1
Style: ActiveRank,Arial,56,&H0000E6FF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,6,3,7,60,60,60,1
Style: DimRank,Arial,48,&H80777777,&H000000FF,&H00000000,&H40000000,-1,0,0,0,100,100,0,0,1,3,1,7,60,60,60,1

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

    spacing = 82 if n <= 4 else 75
    start_y = 260

    curr_t = 0.0
    for idx, c in enumerate(clips_info):
        t_start = curr_t
        t_end = curr_t + c["duration"]
        start_str = _fmt_ts(t_start)
        end_str = _fmt_ts(t_end)
        active_rank_num = c["rank"]
        
        for row_rank in range(1, n + 1):
            y_pos = start_y + (row_rank - 1) * spacing
            matching = [x for x in clips_info if x["rank"] == row_rank]
            label_text = f"{row_rank}."
            if matching and (row_rank >= active_rank_num):
                label_text = f"{row_rank}. {matching[0].get('title', '')}"

            if row_rank == active_rank_num:
                pop_effect = "{\\t(0,180,\\fscx125\\fscy125)\\t(180,320,\\fscx100\\fscy100)}"
                events.append(
                    f"Dialogue: 1,{start_str},{end_str},ActiveRank,,0,0,0,,{{\\pos(70,{y_pos})}}{pop_effect}{label_text}"
                )
            else:
                events.append(
                    f"Dialogue: 1,{start_str},{end_str},DimRank,,0,0,0,,{{\\pos(70,{y_pos})}}{label_text}"
                )

        curr_t = t_end

    with open(output_ass, "w", encoding="utf-8") as f:
        f.write(ass_header + "\n".join(events))
    return output_ass

def build_pro_compilation(
    clips: List[str],
    titles: List[str],
    output_path: str,
    custom_title: str = "TOP 5 FUNNIEST SPEED MOMENTS"
) -> str:
    n = len(clips)
    temp_dir = Path(config.PROJECT) / "data" / "temp" / f"pro_top{n}_build"
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    clips_info = []
    for i, c_path in enumerate(clips):
        rank = n - i
        dur = get_clip_duration(c_path)
        clips_info.append({
            "path": c_path,
            "rank": rank,
            "title": titles[i],
            "duration": dur
        })

    # 1. Leaderboard subtitles
    ass_path = str(temp_dir / "leaderboard.ass")
    generate_pro_leaderboard(clips_info, ass_path, title=custom_title)

    # 2. Prepare normalized clips with visual flash transition at start
    norm_clips = []
    for i, c in enumerate(clips_info):
        norm_p = str(temp_dir / f"norm_{i}.mp4")
        vf = (
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
            "fade=t=in:st=0:d=0.16:c=white,"
            "format=yuv420p"
        )
        cmd = [
            "ffmpeg", "-y", "-i", c["path"],
            "-vf", vf,
            "-r", "30", "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac", "-ar", "48000", "-ac", "2",
            norm_p
        ]
        subprocess.run(cmd, capture_output=True)
        norm_clips.append(norm_p)

    # 3. Concat video clips
    concat_txt = str(temp_dir / "concat.txt")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for p in norm_clips:
            f.write(f"file '{p}'\n")

    stitched_video = str(temp_dir / "stitched.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt,
        "-c", "copy", stitched_video
    ], capture_output=True)

    # 4. Burn in the animated Leaderboard
    ass_escaped = ass_path.replace("\\", "/").replace(":", "\\:")
    overlay_video = str(temp_dir / "with_leaderboard.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-i", stitched_video,
        "-vf", f"ass='{ass_escaped}'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy", overlay_video
    ], capture_output=True)

    # 5. Clean, Minimal, Frame-Accurate Sound Effects
    # Golden rule: Only purposeful sound effects. No clutter. Controlled volumes.
    sfx_cues = []
    curr_t = 0.0
    for i, c in enumerate(clips_info):
        rank = c["rank"]
        
        # Crisp camera shutter + whoosh on every rank transition
        sfx_cues.append({"time": curr_t, "sfx": get_sfx("whip_whoosh"), "vol": 0.65})
        sfx_cues.append({"time": curr_t + 0.02, "sfx": get_sfx("camera_shutter"), "vol": 0.60})

        if rank == 5:
            # Troll donation & TNT explosion: squeak on pressure plate, bruh on explosion
            sfx_cues.append({"time": curr_t + 13.80, "sfx": get_sfx("squeak"), "vol": 0.65})
            sfx_cues.append({"time": curr_t + 14.60, "sfx": get_sfx("bruh"), "vol": 0.60})
        elif rank == 4:
            # First Day Teaching: error sound on "8 - 4 is 8", bruh on shouting/police
            sfx_cues.append({"time": curr_t + 8.30, "sfx": get_sfx("error"), "vol": 0.55})
            sfx_cues.append({"time": curr_t + 15.50, "sfx": get_sfx("bruh"), "vol": 0.60})
        elif rank == 3:
            # My Name Is Speed: punchy Vine Boom on "My name is SPEED!", buzzer on repeat
            sfx_cues.append({"time": curr_t + 15.80, "sfx": get_sfx("vine_boom"), "vol": 0.60})
            sfx_cues.append({"time": curr_t + 21.00, "sfx": get_sfx("buzzer"), "vol": 0.50})
        elif rank == 2:
            # Talking Ben: error on "stinky ass couch", Vine Boom when Ben shushes Speed
            sfx_cues.append({"time": curr_t + 4.60, "sfx": get_sfx("error"), "vol": 0.50})
            sfx_cues.append({"time": curr_t + 18.30, "sfx": get_sfx("vine_boom"), "vol": 0.65})
        elif rank == 1:
            # VR Herbert:
            # Cinematic bass boom on #1 reveal
            sfx_cues.append({"time": curr_t + 0.05, "sfx": get_sfx("cinematic_boom"), "vol": 0.70})
            # Punchy Vine Boom on "touched me in a bathroom four years ago!"
            sfx_cues.append({"time": curr_t + 16.40, "sfx": get_sfx("vine_boom"), "vol": 0.60})
            # Quick comic police blip (0.3s) on "Call the cops!"
            sfx_cues.append({"time": curr_t + 25.30, "sfx": get_sfx("whoop_whoop"), "vol": 0.55})

        curr_t += c["duration"]

    # Filter existing cues
    valid_cues = [q for q in sfx_cues if q["sfx"] and os.path.exists(q["sfx"])]

    # 6. Audio mix with ducked background music (-22dB)
    bgm_file = MUSIC_DIR / "sneaky_snitch.mp3"
    if not bgm_file.exists():
        bgm_file = Path("C:/Users/swastik/Downloads") / "Sneaky_Snitch.mp3"

    inputs = ["-i", overlay_video]
    filter_parts = []
    amix_inputs = ["[0:a]"]

    bgm_idx = 1
    if bgm_file.exists():
        inputs.extend(["-stream_loop", "-1", "-i", str(bgm_file)])
        # volume=0.08 is clean background bed (-22 dB)
        filter_parts.append(f"[{bgm_idx}:a]volume=0.08[bgm_ducked];")
        amix_inputs.append("[bgm_ducked]")
        bgm_idx += 1

    sfx_start_idx = bgm_idx
    for idx, cue in enumerate(valid_cues):
        inputs.extend(["-i", cue["sfx"]])
        delay_ms = int(cue["time"] * 1000)
        vol = cue.get("vol", 0.6)
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
        output_path
    ]

    subprocess.run(final_cmd, capture_output=True)
    print(f"Top 5 compilation successfully created at: {output_path}")
    return output_path
