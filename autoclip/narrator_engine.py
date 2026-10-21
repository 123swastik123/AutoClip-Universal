"""AutoClip Narrator & Mascot Commentary Engine.

Generates 9:16 viral Speed commentary Shorts/Reels/TikToks styled after
top creator animation formats (like @Asfan.Animation):
- AI Host mascot character in the bottom corner holding a mic and bouncing dynamically
- Charismatic English neural voiceover (ElevenLabs / Edge-TTS high quality)
- Comedic breakdown commentary specifically tailored to IShowSpeed's wildest moments
- Centered 9:16 layout with blurred backdrop and bold top headline banner
- 3-track audio balance: Narrator VO (1.4x), ducked Speed stream audio (0.2x), and comedic BGM (0.08x)
"""

import os
import sys
import json
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any

from . import config

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

PROJECT_ROOT = Path(config.PROJECT)
SFX_DIR = PROJECT_ROOT / "data" / "sfx"
MUSIC_DIR = PROJECT_ROOT / "data" / "music"
BRANDING_DIR = PROJECT_ROOT / "data" / "branding"

DEFAULT_MASCOT = BRANDING_DIR / "mascot_host.png"
DEFAULT_BGM = MUSIC_DIR / "sneaky_snitch.mp3"

DEFAULT_VOICE = "en-US-ChristopherNeural"

VIRAL_SPEED_SCRIPTS = [
    {
        "header": "SPEED REALLY TRIED HIS BEST... 💀",
        "lines": [
            (0.0, 3.5, "Speed really thought he had the ULTIMATE RIZZ..."),
            (3.5, 6.8, "Until THIS HAPPENED! 😱"),
            (6.8, 10.5, "Bro tried using his craziest facial expressions!"),
            (10.5, 13.8, "He literally FROZE with ZERO words left! 💀"),
            (13.8, 16.9, "Drop a LIKE if Speed took a MASSIVE L! 😂"),
        ]
    },
    {
        "header": "SPEED'S MOST UNHINGED MOMENT 😭",
        "lines": [
            (0.0, 3.2, "Bro nobody can prepare you for what Speed just did!"),
            (3.2, 6.5, "Look at his reaction right here..."),
            (6.5, 9.8, "He genuinely thought he was winning this interaction! 💀"),
            (9.8, 13.0, "The second things went wrong, he completely lost his mind! 😭"),
            (13.0, 16.0, "Subscribe if you would've crashed out too! 🔥"),
        ]
    },
    {
        "header": "SPEED TOOK THE BIGGEST L EVER 💀",
        "lines": [
            (0.0, 3.0, "Speed really thought he was the main character..."),
            (3.0, 6.2, "Watch how confident he looks right now! 😂"),
            (6.2, 9.5, "And in three... two... one... ABSOLUTE DISASTER! 😱"),
            (9.5, 12.8, "Look at his face, bro didn't know whether to bark or cry! 💀"),
            (12.8, 15.5, "Hit that subscribe button for more crazy Speed moments!"),
        ]
    }
]

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

async def _synthesize_tts_async(text: str, out_file: str, voice: str = DEFAULT_VOICE, rate: str = "+0%"):
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(out_file)

def synthesize_narrator_speech(text: str, out_file: str, voice: str = DEFAULT_VOICE, rate: str = "+0%") -> str:
    """Synthesize high-quality neural English voiceover using edge-tts."""
    if not HAS_EDGE_TTS:
        raise RuntimeError("edge-tts is required for narrator speech synthesis. Install with: pip install edge-tts")
    os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
    asyncio.run(_synthesize_tts_async(text, out_file, voice, rate))
    return out_file

def generate_ass_narrator_subtitles(
    lines: List[tuple],
    header_title: str,
    output_ass: str,
    total_duration: float
):
    """Generate vibrant animated ASS subtitles for the narrator monologue."""
    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Header,Impact,56,&H0000FFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,1,0,1,5,4,8,40,40,90,1
Style: MascotLabel,Montserrat-ExtraBold,34,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4,3,1,40,40,40,1
Style: NarratorSub,Montserrat-ExtraBold,48,&H0000E6FF,&H000000FF,&H00000000,&H90000000,1,0,0,0,100,100,0,0,1,5,3,2,60,60,420,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,{format_time(total_duration)},Header,,0,0,0,,{{\\pos(540,120)\\c&H00D2FF&}}{header_title}
"""
    for start_t, end_t, text in lines:
        t_start = format_time(start_t)
        t_end = format_time(end_t)
        # Format text with vibrant emphasis
        highlighted = text.replace("RIZZ", "{\\c&H00FFFF&}RIZZ{\\c&H0000E6FF&}") \
                          .replace("THIS HAPPENED", "{\\c&H0000FF&}THIS HAPPENED{\\c&H00FFFFFF&}") \
                          .replace("FROZE", "{\\c&H0000FF&}FROZE{\\c&H0000E6FF&}") \
                          .replace("DISASTER", "{\\c&H0000FF&}DISASTER{\\c&H0000E6FF&}") \
                          .replace("MASSIVE L", "{\\c&H0000FF&}MASSIVE L{\\c&H00D2FF&}")
        ass_content += f"Dialogue: 0,{t_start},{t_end},NarratorSub,,0,0,0,,{{\\c&H00E6FF&}}{highlighted}\n"

    with open(output_ass, "w", encoding="utf-8") as f:
        f.write(ass_content)

def format_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"

def render_mascot_commentary_short(
    clip_path: str,
    output_path: str,
    script_preset_idx: int = 0,
    custom_script: Optional[Dict[str, Any]] = None,
    mascot_img: Optional[str] = None,
    bgm_file: Optional[str] = None,
    voice: str = DEFAULT_VOICE,
    custom_title: Optional[str] = None
) -> str:
    """Render a complete, polished 9:16 Short with animated mascot host and narrator VO."""
    clip_path = str(Path(clip_path).resolve())
    if not os.path.exists(clip_path):
        raise FileNotFoundError(f"Source clip not found: {clip_path}")

    # Determine script & timing
    script = custom_script or VIRAL_SPEED_SCRIPTS[script_preset_idx % len(VIRAL_SPEED_SCRIPTS)]
    header_title = custom_title or script.get("header", "SPEED REALLY TRIED HIS BEST... 💀")
    lines = script.get("lines", [])

    # Concatenate full spoken text for TTS
    full_speech = " ".join([line[2] for line in lines])
    
    # Temp files
    temp_dir = Path(os.environ.get("TEMP", r"C:\Users\swastik\AppData\Local\Temp"))
    temp_audio = temp_dir / "narrator_vo_temp.mp3"
    temp_ass = temp_dir / "narrator_subs_temp.ass"

    print(f"[Narrator Engine] Synthesizing voiceover with {voice}...")
    synthesize_narrator_speech(full_speech, str(temp_audio), voice=voice)

    vo_duration = get_media_duration(str(temp_audio))
    # Give 0.5s padding at end for natural breathing room
    total_dur = max(vo_duration + 0.5, 14.0)
    print(f"[Narrator Engine] Voiceover duration: {vo_duration:.2f}s | Short duration: {total_dur:.2f}s")

    # Rescale lines if total duration differs slightly
    last_end = lines[-1][1] if lines else 16.0
    time_scale = vo_duration / max(last_end, 1.0)
    scaled_lines = [(s * time_scale, e * time_scale, txt) for (s, e, txt) in lines]

    # Generate ASS
    generate_ass_narrator_subtitles(scaled_lines, header_title, str(temp_ass), total_dur)

    # Assets
    mascot_path = mascot_img or (str(DEFAULT_MASCOT) if DEFAULT_MASCOT.exists() else "")
    bgm_path = bgm_file or (str(DEFAULT_BGM) if DEFAULT_BGM.exists() else "")

    ass_escaped = str(temp_ass).replace("\\", "/").replace(":", "\\:")

    # Build FFmpeg command
    # Inputs:
    # 0:v - Source Video
    # 1:a - Narrator VO
    # 2:a - BGM Track (looped)
    # 3:v - Mascot PNG (looped)
    
    inputs = [
        "-ss", "0", "-t", str(total_dur), "-i", clip_path,
        "-i", str(temp_audio),
    ]

    has_bgm = bool(bgm_path and os.path.exists(bgm_path))
    has_mascot = bool(mascot_path and os.path.exists(mascot_path))

    if has_bgm:
        inputs.extend(["-stream_loop", "-1", "-i", bgm_path])
    if has_mascot:
        inputs.extend(["-loop", "1", "-i", mascot_path])

    # Filter graph construction
    v_filters = [
        "[0:v]split=2[v_bg][v_fg]",
        "[v_bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=30,eq=brightness=-0.22[bg]",
        "[v_fg]scale=1040:-2:flags=lanczos[fg]",
        "[bg][fg]overlay=(W-w)/2:240[video_base]"
    ]

    current_v = "[video_base]"
    if has_mascot:
        mascot_idx = 3 if has_bgm else 2
        # Animated mascot talking bounce: y = 1480 + 14*abs(sin(t*12))
        v_filters.append(f"[{mascot_idx}:v]scale=320:-1:flags=lanczos[mascot]")
        v_filters.append(f"{current_v}[mascot]overlay=40:'1480+14*abs(sin(t*12))'[with_mascot]")
        current_v = "[with_mascot]"

    v_filters.append(f"{current_v}subtitles='{ass_escaped}',setsar=1,setdar=9/16[vout]")

    # Audio filters
    # VO: 1.4x volume, 48kHz
    # Stream: 0.20x volume ducked
    # BGM: 0.08x volume ducked
    a_filters = [
        "[1:a]volume=1.40,aresample=48000[vo]",
        "[0:a]volume=0.20,aresample=48000[stream]"
    ]
    mix_inputs = "[vo][stream]"
    num_a_inputs = 2

    if has_bgm:
        a_filters.append(f"[2:a]atrim=0:{total_dur},volume=0.08,aresample=48000[bgm]")
        mix_inputs += "[bgm]"
        num_a_inputs = 3

    a_filters.append(f"{mix_inputs}amix=inputs={num_a_inputs}:duration=first:normalize=0[aout]")

    filter_complex = ";".join(v_filters) + ";" + ";".join(a_filters)

    cmd = [
        "ffmpeg", "-y", "-hide_banner",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-t", str(total_dur),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path)
    ]

    print(f"[Narrator Engine] Rendering final video to: {output_path}...")
    subprocess.run(cmd, check=True)
    print(f"[Narrator Engine] Video render successful -> {output_path}")
    return output_path
