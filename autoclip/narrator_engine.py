"""AutoClip Narrator & Mascot Commentary Engine (Kokoro ElevenLabs-Grade Voice).

Features:
- Format A: The Asfan "Live Blind Ranking Challenge" (1 to 5 interactive left-side ladder + pop SFX + dancing chibi cat)
- Format B: The "3-Second AI Hook-and-Drop" Viral Story Short (Kokoro am_adam 3s hook -> raw uncut Speed chaos -> outro punchline)
- High-resolution cute chibi cat mascot (chibi_cat_mascot.png) scaled subtley (95px) at the bottom
- Universal creator support: Speed, CaseOh, Jynxzi, Kai Cenat, or any creator
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any

from . import config

PROJECT_ROOT = Path(config.PROJECT)
BRANDING_DIR = PROJECT_ROOT / "data" / "branding"
MUSIC_DIR = PROJECT_ROOT / "data" / "music"
SFX_DIR = PROJECT_ROOT / "data" / "sfx"
MODELS_DIR = PROJECT_ROOT / "data" / "models" / "kokoro"

KOKORO_MODEL = MODELS_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES = MODELS_DIR / "voices-v1.0.bin"

DEFAULT_CAT_MASCOT = BRANDING_DIR / "chibi_cat_mascot.png"
DEFAULT_BGM = MUSIC_DIR / "sneaky_snitch.mp3"
DEFAULT_POP_SFX = SFX_DIR / "whoosh.wav"

DEFAULT_VOICE = "am_adam"  # ElevenLabs-caliber American male voice

def get_media_duration(file_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(res.stdout.strip())
    except Exception:
        return 16.0

def synthesize_kokoro_voice(text: str, out_wav: str, voice: str = DEFAULT_VOICE, speed: float = 1.05) -> str:
    """Generate human-like ElevenLabs-grade speech via local Kokoro ONNX."""
    import soundfile as sf
    from kokoro_onnx import Kokoro

    if not KOKORO_MODEL.exists() or not KOKORO_VOICES.exists():
        raise FileNotFoundError(f"Kokoro model files not found in: {MODELS_DIR}")

    kokoro = Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES))
    samples, sample_rate = kokoro.create(text, voice=voice, speed=speed, lang="en-us")
    
    os.makedirs(os.path.dirname(os.path.abspath(out_wav)), exist_ok=True)
    sf.write(out_wav, samples, sample_rate)
    return out_wav

def format_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"

# =========================================================================
# FORMAT A: Asfan "Live Blind Ranking Challenge"
# =========================================================================
def render_format_a_ranking_challenge(
    clip_path: str,
    output_path: str,
    creator_slug: str = "speed",
    ranks: Optional[List[str]] = None,
    header_title: Optional[str] = None
) -> str:
    """Render Format A: Full vertical video with animated left-side 1-to-5 rank ladder and dancing chibi cat."""
    clip_path = str(Path(clip_path).resolve())
    total_dur = min(get_media_duration(clip_path), 50.0)
    header = header_title or f"RANKING {creator_slug.upper()}'S CRAZIEST MOMENTS 💀"

    default_ranks = [
        "5. That was completely uncalled for 😭",
        "4. Bro tried his absolute best 💀",
        "3. Look at his facial expression 😂",
        "2. HE LITERALLY FROZE IN PLACE 😱",
        "1. THE GREATEST CRASHOUT EVER 🔥"
    ]
    rank_items = ranks or default_ranks

    # Generate ASS for Left-Hand Ranking Ladder
    temp_dir = Path(os.environ.get("TEMP", r"C:\Users\swastik\AppData\Local\Temp"))
    temp_ass = temp_dir / "asfan_ranking_ladder.ass"

    # Step intervals for revealing each rank
    step_dur = max(total_dur / (len(rank_items) + 1), 2.5)

    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Header,Impact,52,&H0000FFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,1,0,1,5,4,8,40,40,90,1
Style: RankItem,Montserrat-ExtraBold,40,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,1,0,0,0,100,100,0,0,1,5,3,7,50,50,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,{format_time(total_dur)},Header,,0,0,0,,{{\\pos(540,110)\\c&H00D2FF&}}{header}
"""
    y_start = 240
    y_gap = 90
    for idx, text in enumerate(rank_items):
        t_appear = format_time(idx * step_dur)
        y_pos = y_start + (idx * y_gap)
        # Highlight ranks with pop color
        color_tag = "\\c&H0050FF&" if idx == 0 else "\\c&H00FFFF&" if idx == 1 else "\\c&H00D2FF&"
        ass_content += f"Dialogue: 0,{t_appear},{format_time(total_dur)},RankItem,,0,0,0,,{{\\pos(60,{y_pos}){color_tag}}}{text}\n"

    with open(temp_ass, "w", encoding="utf-8") as f:
        f.write(ass_content)

    ass_escaped = str(temp_ass).replace("\\", "/").replace(":", "\\:")
    cat_png = str(DEFAULT_CAT_MASCOT) if DEFAULT_CAT_MASCOT.exists() else ""

    inputs = ["-ss", "0", "-t", str(total_dur), "-i", clip_path]
    has_cat = bool(cat_png and os.path.exists(cat_png))
    if has_cat:
        inputs.extend(["-loop", "1", "-i", cat_png])

    # Full 9:16 layout + subtle 95px cat bobbing at bottom + ranking ladder
    v_filters = [
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[v_base]"
    ]
    cur_v = "[v_base]"
    if has_cat:
        # Scale cat to 95px width and animate slight joyful bobbing at bottom
        v_filters.append("[1:v]scale=95:-1:flags=lanczos[cat]")
        v_filters.append(f"{cur_v}[cat]overlay=60:'1780+8*abs(sin(t*10))'[with_cat]")
        cur_v = "[with_cat]"

    v_filters.append(f"{cur_v}subtitles='{ass_escaped}',setsar=1,setdar=9/16[vout]")

    cmd = [
        "ffmpeg", "-y", "-hide_banner",
        *inputs,
        "-filter_complex", ";".join(v_filters),
        "-map", "[vout]", "-map", "0:a?",
        "-t", str(total_dur),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path)
    ]

    print(f"[Narrator Engine] Rendering Format A (Blind Ranking) to: {output_path}...")
    subprocess.run(cmd, check=True)
    return output_path

# =========================================================================
# FORMAT B: 3-Second AI Hook-and-Drop Viral Story Short
# =========================================================================
def render_format_b_hook_and_drop(
    clip_path: str,
    output_path: str,
    creator_slug: str = "speed",
    hook_text: Optional[str] = None,
    outro_text: Optional[str] = None,
    header_title: Optional[str] = None,
    voice: str = DEFAULT_VOICE
) -> str:
    """Render Format B: 3s AI Hook -> Raw Speed Chaos -> Outro Punchline (Kokoro Human Voice)."""
    clip_path = str(Path(clip_path).resolve())
    total_dur = min(max(get_media_duration(clip_path), 12.0), 30.0)

    # Contextual hooks
    hooks_map = {
        "speed": ("Speed really thought he had infinite aura... until this happened!", "He literally lost every single word! Drop a like if Speed took a massive L!"),
        "caseoh": ("CaseOh really thought chat wouldn't notice this...", "Look at his face, he was ready to ban the entire lobby!"),
        "jynxzi": ("Jynxzi was one round away from greatness...", "Listen to him scream right here, bro completely lost his mind!"),
        "general": ("Nobody could have predicted how this would end...", "Leave a comment if you saw that coming!")
    }
    def_hook, def_outro = hooks_map.get(creator_slug.lower(), hooks_map["general"])
    hook = hook_text or def_hook
    outro = outro_text or def_outro
    header = header_title or f"{creator_slug.upper()} REALLY TRIED HIS BEST... 💀"

    temp_dir = Path(os.environ.get("TEMP", r"C:\Users\swastik\AppData\Local\Temp"))
    hook_audio = temp_dir / "hook_vo.wav"
    outro_audio = temp_dir / "outro_vo.wav"
    temp_ass = temp_dir / "hook_and_drop_subs.ass"

    print(f"[Narrator Engine] Synthesizing Format B Hook with Kokoro ({voice})...")
    synthesize_kokoro_voice(hook, str(hook_audio), voice=voice, speed=1.08)
    hook_dur = get_media_duration(str(hook_audio))

    print(f"[Narrator Engine] Synthesizing Format B Outro with Kokoro ({voice})...")
    synthesize_kokoro_voice(outro, str(outro_audio), voice=voice, speed=1.08)
    outro_dur = get_media_duration(str(outro_audio))

    outro_start = max(total_dur - outro_dur - 0.5, hook_dur + 4.0)
    total_dur = outro_start + outro_dur + 0.5

    # Generate Subtitles: Hook (0 -> hook_dur), Outro (outro_start -> total_dur)
    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Header,Impact,56,&H0000FFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,1,0,1,5,4,8,40,40,90,1
Style: Subtitle,Montserrat-ExtraBold,46,&H0000E6FF,&H000000FF,&H00000000,&H90000000,1,0,0,0,100,100,0,0,1,5,3,2,60,60,340,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,{format_time(total_dur)},Header,,0,0,0,,{{\\pos(540,120)\\c&H00D2FF&}}{header}
Dialogue: 0,0:00:00.00,{format_time(hook_dur)},Subtitle,,0,0,0,,{{\\c&H00FFFF&}}{hook}
Dialogue: 0,{format_time(outro_start)},{format_time(total_dur)},Subtitle,,0,0,0,,{{\\c&H00D2FF&}}{outro}
"""
    with open(temp_ass, "w", encoding="utf-8") as f:
        f.write(ass_content)

    ass_escaped = str(temp_ass).replace("\\", "/").replace(":", "\\:")
    cat_png = str(DEFAULT_CAT_MASCOT) if DEFAULT_CAT_MASCOT.exists() else ""
    bgm_path = str(DEFAULT_BGM) if DEFAULT_BGM.exists() else ""

    # Build audio mix:
    # [1:a] Hook VO (starts at 0.0)
    # [2:a] Outro VO (delayed by outro_start)
    # [0:a] Stream audio: ducked to 0.20 during hook and outro, but FULL 1.00 volume in the middle!
    # [3:a] BGM ducked to 0.08
    inputs = [
        "-ss", "0", "-t", str(total_dur), "-i", clip_path,
        "-i", str(hook_audio),
        "-i", str(outro_audio),
    ]

    has_bgm = bool(bgm_path and os.path.exists(bgm_path))
    has_cat = bool(cat_png and os.path.exists(cat_png))

    if has_bgm:
        inputs.extend(["-stream_loop", "-1", "-i", bgm_path])
    if has_cat:
        inputs.extend(["-loop", "1", "-i", cat_png])

    v_filters = [
        "[0:v]split=2[v_bg][v_fg]",
        "[v_bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=30,eq=brightness=-0.22[bg]",
        "[v_fg]scale=1040:-2:flags=lanczos[fg]",
        "[bg][fg]overlay=(W-w)/2:240[video_base]"
    ]
    cur_v = "[video_base]"
    if has_cat:
        cat_idx = 4 if has_bgm else 3
        # Small cute 95px cat at bottom
        v_filters.append(f"[{cat_idx}:v]scale=95:-1:flags=lanczos[cat]")
        v_filters.append(f"{cur_v}[cat]overlay=60:'1780+8*abs(sin(t*10))'[with_cat]")
        cur_v = "[with_cat]"

    v_filters.append(f"{cur_v}subtitles='{ass_escaped}',setsar=1,setdar=9/16[vout]")

    # Dynamic Audio Ducking: Stream volume is 0.20 during hook (0-hook_dur) and outro (outro_start-end), but 1.0 in middle!
    a_filters = [
        f"[1:a]volume=1.45,aresample=48000[vo_hook]",
        f"[2:a]adelay={int(outro_start*1000)}|{int(outro_start*1000)},volume=1.45,aresample=48000[vo_outro]",
        f"[0:a]volume='if(lt(t,{hook_dur}),0.20,if(gt(t,{outro_start}),0.20,1.0))':eval=frame,aresample=48000[stream_dyn]"
    ]
    mix_inputs = "[vo_hook][vo_outro][stream_dyn]"
    num_inputs = 3

    if has_bgm:
        a_filters.append(f"[3:a]atrim=0:{total_dur},volume=0.07,aresample=48000[bgm]")
        mix_inputs += "[bgm]"
        num_inputs = 4

    a_filters.append(f"{mix_inputs}amix=inputs={num_inputs}:duration=first:normalize=0[aout]")

    cmd = [
        "ffmpeg", "-y", "-hide_banner",
        *inputs,
        "-filter_complex", ";".join(v_filters) + ";" + ";".join(a_filters),
        "-map", "[vout]", "-map", "[aout]",
        "-t", str(total_dur),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path)
    ]

    print(f"[Narrator Engine] Rendering Format B (Hook-and-Drop) to: {output_path}...")
    subprocess.run(cmd, check=True)
    return output_path
