"""High-CTR Viral Shorts Thumbnail Generator.

Matches high-performing YouTube Shorts / TikTok thumbnail standards:
1. 9:16 vertical high-res canvas (1080x1920)
2. Climax keyframe capture with saturation & contrast pop
3. Top streamer pill badge (e.g., [SPEED x REAL MADRID], [CASEOH HORROR])
4. Multi-color bold Impact typography (Yellow / White / Red hierarchy)
5. Thick black outline (stroke) + drop-shadow for maximum readability
6. Optional red focus circle on action subjects
"""

import os
import sys
import re
import math
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(r"C:\Users\swastik\Desktop\AutoClip")
THUMBNAILS_DIR = PROJECT_ROOT / "data" / "thumbnails"
THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)

FONT_PATH = r"C:\Windows\Fonts\impact.ttf"
if not os.path.exists(FONT_PATH):
    FONT_PATH = "arial.ttf"

def extract_climax_frame(video_path: str, out_img: str, target_timestamp: float = None) -> bool:
    """Extract a sharp keyframe from the video climax (around 75% or specified timestamp)."""
    if not os.path.exists(video_path):
        return False
    
    # Probe duration
    dur = 10.0
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", video_path
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            dur = float(r.stdout.strip())
    except Exception:
        pass

    if target_timestamp is None:
        # Climax usually happens 70-85% into the clip or 2.5s before end
        target_timestamp = max(1.0, min(dur - 2.5, dur * 0.75))

    extract_cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", str(round(target_timestamp, 2)),
        "-i", video_path,
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        "-vframes", "1",
        "-q:v", "2",
        out_img
    ]
    try:
        subprocess.run(extract_cmd, timeout=15)
        return os.path.exists(out_img) and os.path.getsize(out_img) > 1000
    except Exception as e:
        print(f"[Thumbnail] FFmpeg extract error: {e}")
        return False

def parse_thumbnail_copy(title: str, hook: str, creator: str, theme: str = None):
    """Generate 2-3 short, explosive words/lines for high CTR thumbnail."""
    c_norm = (creator or "speed").lower()
    t_clean = (title or "").upper()
    h_clean = (hook or "").upper()

    # Priority 1: Check title/hook keywords
    if any(k in t_clean or k in h_clean for k in ["MESSI", "MESSY", "GIF", "GIFT OF MESSI"]):
        return {
            "badge": "JYNXZI x MESSI GIF",
            "lines": [("CHAT DO THE", "#FFFFFF"), ("GIF OF MESSI?!", "#FFE600")]
        }
    if "MBAPPE" in t_clean or "REAL MADRID" in t_clean:
        return {
            "badge": "SPEED x REAL MADRID",
            "lines": [("NO WAY", "#FFE600"), ("BRO?!", "#FFFFFF")]
        }
    if "ELEVATOR" in t_clean:
        return {
            "badge": "CASEOH HORROR",
            "lines": [("CASEOH", "#FFE600"), ("THIS ELEVATOR", "#FFFFFF"), ("NEVER STOPS?!", "#FF2A2A")]
        }
    if "HEAR" in t_clean or "GHOST" in t_clean or "JUMPSCARE" in t_clean:
        return {
            "badge": "CASEOH HORROR" if "case" in c_norm else "JUMPSCARE",
            "lines": [("DID I JUST HEAR", "#FFFFFF"), ("SOMETHING?!", "#FFE600")]
        }
    if "HEADSHOT" in t_clean or "SNIPE" in t_clean:
        return {
            "badge": "JYNXZI x R6",
            "lines": [("CLEANEST", "#FFE600"), ("HEADSHOT?!", "#FFFFFF")]
        }
    if "CLUTCH" in t_clean or "1V4" in t_clean or "1V3" in t_clean or "1V5" in t_clean:
        return {
            "badge": "JYNXZI CLUTCH",
            "lines": [("1V4 CLUTCH", "#FFE600"), ("NO WAY?!", "#FF2A2A")]
        }
    if "FOOD" in t_clean or "EATING" in t_clean or (theme and "food" in theme.lower()):
        return {
            "badge": "SPEED x TASTE TEST",
            "lines": [("SPEED REACTS", "#FFE600"), ("TO THIS FOOD 😭", "#FFFFFF")]
        }
    if "RAGE" in t_clean or "DESK" in t_clean or "SLAM" in t_clean:
        return {
            "badge": "RAGE MOMENT",
            "lines": [("HE BROKE IT?!", "#FF2A2A"), ("UNHINGED 💀", "#FFE600")]
        }
    if "CRINGE" in t_clean or "RIZZ" in t_clean:
        return {
            "badge": "CRINGE MOMENT",
            "lines": [("SECONDHAND", "#FFE600"), ("EMBARRASSMENT 💀", "#FFFFFF")]
        }

    # Streamer default explosive hooks
    if "speed" in c_norm:
        badge = "SPEED x VIRAL"
        lines = [("NO WAY", "#FFE600"), ("HE DID THIS?!", "#FFFFFF")]
    elif "case" in c_norm:
        badge = "CASEOH MOMENTS"
        lines = [("CASEOH", "#FFE600"), ("CANNOT BELIEVE THIS", "#FFFFFF"), ("WHAT IS THIS?!", "#FF2A2A")]
    elif "jynx" in c_norm:
        badge = "JYNXZI HIGHLIGHTS"
        lines = [("HE ACTUALLY", "#FFFFFF"), ("PULLED IT OFF?!", "#FFE600")]
    elif "kai" in c_norm:
        badge = "KAI CENAT LIVE"
        lines = [("ROOM CHAOS", "#FF2A2A"), ("UNFILTERED ⚡", "#FFE600")]
    else:
        badge = "VIRAL MOMENT"
        lines = [("NO WAY", "#FFE600"), ("BRO?!", "#FFFFFF")]

    return {"badge": badge, "lines": lines}

def generate_short_thumbnail(
    video_path: str,
    title: str = "",
    creator: str = "speed",
    hook: str = "",
    theme: str = None,
    out_path: str = None,
    timestamp: float = None,
    add_focus_circle: bool = False
) -> str:
    """Generate a high-quality 9:16 viral Short thumbnail matching streamer reference templates."""
    video_path = os.path.abspath(video_path)
    if not os.path.exists(video_path):
        return ""

    stem = Path(video_path).stem
    if not out_path:
        out_path = str(THUMBNAILS_DIR / f"{stem}_thumbnail.jpg")

    temp_frame = str(THUMBNAILS_DIR / f"temp_{stem}.jpg")

    target_ts = timestamp
    t_clean = (title or "").upper()
    h_clean = (hook or "").upper()
    if target_ts is None:
        if any(k in t_clean or k in h_clean for k in ["MESSI", "MESSY", "GIF", "GIFT OF MESSI"]):
            target_ts = 2.45

    ok = extract_climax_frame(video_path, temp_frame, target_timestamp=target_ts)
    if not ok or not os.path.exists(temp_frame):
        return ""

    try:
        base_img = Image.open(temp_frame).convert("RGBA")
        if base_img.size != (1080, 1920):
            base_img = base_img.resize((1080, 1920), Image.Resampling.LANCZOS)

        # 1. Color Enhancement (pop saturation +18%, contrast +12%)
        enhancer = ImageEnhance.Color(base_img)
        base_img = enhancer.enhance(1.18)
        enhancer = ImageEnhance.Contrast(base_img)
        base_img = enhancer.enhance(1.12)

        draw = ImageDraw.Draw(base_img)

        # 2. Get Hook Text and Badge
        copy_data = parse_thumbnail_copy(title, hook, creator, theme)
        badge_text = copy_data.get("badge")
        lines = copy_data.get("lines", [])

        # 3. Draw Top Pill Badge (e.g. [SPEED x REAL MADRID])
        if badge_text:
            badge_font_size = 46
            try:
                badge_font = ImageFont.truetype(FONT_PATH, badge_font_size)
            except Exception:
                badge_font = ImageFont.load_default()

            # Measure text size
            bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
            bw = bbox[2] - bbox[0]
            bh = bbox[3] - bbox[1]

            pill_x1 = 55
            pill_y1 = 60
            pill_pad_x = 35
            pill_pad_y = 18
            pill_x2 = pill_x1 + bw + (pill_pad_x * 2)
            pill_y2 = pill_y1 + bh + (pill_pad_y * 2)

            # Red rounded rectangle badge with smooth corners
            pill_color = (245, 34, 45, 240)  # Bright YouTube Red
            draw.rounded_rectangle([pill_x1, pill_y1, pill_x2, pill_y2], radius=16, fill=pill_color)
            # Subtle white inner stroke
            draw.rounded_rectangle([pill_x1, pill_y1, pill_x2, pill_y2], radius=16, outline=(255, 255, 255, 180), width=2)
            # Text inside badge
            draw.text((pill_x1 + pill_pad_x, pill_y1 + pill_pad_y - 4), badge_text, font=badge_font, fill=(255, 255, 255, 255))

        # 4. Draw Attention Red Focus Circle if requested or for specific clips
        if add_focus_circle or "mbappe" in (title or "").lower() or "circle" in (title or "").lower():
            # Draw glowing red oval / circle in upper half (action area)
            circle_box = [340, 160, 800, 620]
            draw.ellipse(circle_box, outline=(255, 30, 30, 245), width=16)

        # 5. Draw Giant Bold Text Hierarchy
        # Position text in the upper-mid region or top depending on lines count
        text_y = 620 if len(lines) <= 2 else 140
        line_spacing = 22

        for text_str, hex_color in lines:
            # Auto-size font so text fits width comfortably
            font_size = 135
            while font_size > 70:
                try:
                    font = ImageFont.truetype(FONT_PATH, font_size)
                except Exception:
                    font = ImageFont.load_default()
                    break
                t_box = draw.textbbox((0, 0), text_str, font=font)
                t_w = t_box[2] - t_box[0]
                if t_w <= 980:
                    break
                font_size -= 6

            t_box = draw.textbbox((0, 0), text_str, font=font)
            t_w = t_box[2] - t_box[0]
            t_h = t_box[3] - t_box[1]
            t_x = int((1080 - t_w) / 2)  # Centered horizontally

            # Parse hex color
            c_clean = hex_color.lstrip("#")
            rgb_color = tuple(int(c_clean[i:i+2], 16) for i in (0, 2, 4))

            # Thick Black Outline (8 directions + diagonals for heavy pop)
            stroke_width = 10
            for dx in range(-stroke_width, stroke_width + 1):
                for dy in range(-stroke_width, stroke_width + 1):
                    if dx*dx + dy*dy <= stroke_width*stroke_width:
                        draw.text((t_x + dx, text_y + dy), text_str, font=font, fill=(0, 0, 0, 255))

            # Drop shadow
            draw.text((t_x + 6, text_y + 8), text_str, font=font, fill=(0, 0, 0, 180))

            # Main text
            draw.text((t_x, text_y), text_str, font=font, fill=rgb_color)

            text_y += t_h + stroke_width*2 + line_spacing

        # Save output JPEG with maximum quality
        final_rgb = base_img.convert("RGB")
        final_rgb.save(out_path, format="JPEG", quality=95, optimize=True)

        try:
            if os.path.exists(temp_frame):
                os.remove(temp_frame)
        except Exception:
            pass

        print(f"[Thumbnail] High-CTR thumbnail created successfully: {out_path}")
        return out_path

    except Exception as e:
        print(f"[Thumbnail] Error rendering thumbnail: {e}")
        return temp_frame
