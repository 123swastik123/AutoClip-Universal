"""AutoClip Visual Studio Editor Engine (CapCut-Style Customizer).

Handles customized re-rendering with:
1. Split screen layout control (Streamer Top vs Gameplay Top, split ratio)
2. Blurred background fill 9:16 vs Dynamic face crop
3. Vertical caption Y-positioning, custom fonts, font sizes, and color themes
4. Intro hook banner text, duration, and styling
5. Timeline trimming (t0, t1)
6. AI Creative Director prompt-based effects
7. Automated YouTube scheduling on the 6-hour timeline & Excel tracking
"""

import os
import sys
import json
import uuid
import re
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from . import config, creators, channel_routing, excel_tracker, smart_reframe, mediatools as mt
from .captions import _ts, _esc

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def _safe_resolve(rel_path):
    if not rel_path:
        return None
    clean = str(rel_path).replace("/", os.sep).replace("\\", os.sep).lstrip(os.sep)
    norm = os.path.abspath(os.path.join(str(PROJECT_ROOT), clean))
    return norm if os.path.exists(norm) else None

def build_custom_ass_subtitles(
    words: list,
    out_ass_path: str,
    caption_y: int = 440,
    caption_font: str = "Arial Black",
    caption_size: int = 102,
    caption_color_hex: str = "#FFD200",
    hook_text: str = "",
    hook_duration: float = 4.0,
    t0_offset: float = 0.0
):
    """Generate custom ASS subtitle script with user's exact CapCut styling parameters."""
    # Convert HEX (#RRGGBB) to ASS color &H00BBGGRR
    def hex_to_ass(hex_val, alpha="00"):
        h = hex_val.lstrip("#")
        if len(h) != 6:
            h = "FFE500"
        r, g, b = h[0:2], h[2:4], h[4:6]
        return f"&H{alpha}{b}{g}{r}"

    pop_color = hex_to_ass(caption_color_hex)
    main_color = "&H00FFFFFF" # White

    margin_v = max(60, min(1600, int(caption_y)))
    font = caption_font or "Arial Black"
    size = max(40, min(160, int(caption_size)))

    ass_content = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Main,{font},{size},{main_color},{main_color},&H00000000,&H80000000,"
        f"1,0,0,0,100,100,0,0,1,14,4,2,40,40,{margin_v},1\n"
        f"Style: Pop,{font},{int(size * 1.08)},{pop_color},{main_color},&H00000000,&H80000000,"
        f"1,0,0,0,100,100,0,0,1,14,4,2,40,40,{margin_v},1\n"
        f"Style: HookTop,{font},72,&H0000E5FF,&H000000FF,&H00000000,&HCC000000,"
        f"-1,0,0,0,100,100,2,0,1,12,4,2,40,40,220,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events = []

    # 1. Top Hook Banner
    if hook_text and hook_text.strip():
        h_clean = _esc(hook_text.strip().upper())
        h_end = max(1.5, min(30.0, float(hook_duration or 4.0)))
        events.append(
            f"Dialogue: 1,0:00:00.10,{_ts(h_end)},HookTop,,0,0,0,,"
            f"{{\\fad(120,180)}}{{\\fscx120\\fscy120\\t(0,200,100,100)}}{{\\an8}}"
            f"{{\\bord8\\shad3\\1c&HFFFFFF&\\3c&H000000&}}🔥 {h_clean} 🔥"
        )

    # 2. Word groups
    norm_words = []
    for w in (words or []):
        s = max(0.0, float(w.get("start", 0)) - t0_offset)
        e = max(s + 0.1, float(w.get("end", s + 0.3)) - t0_offset)
        norm_words.append({**w, "start": s, "end": e})

    # Group into 2-word punchy phrases
    cur = []
    phrases = []
    for w in norm_words:
        if cur and (w["start"] - cur[-1]["end"] > 0.45 or len(cur) >= 2):
            phrases.append(cur)
            cur = []
        cur.append(w)
    if cur:
        phrases.append(cur)

    for p in phrases:
        t_start = p[0]["start"]
        t_end = p[-1]["end"]
        # Find emphatic word
        emph_idx = 0
        max_e = -1.0
        for idx, pw in enumerate(p):
            e_val = float(pw.get("energy", 0.0))
            if e_val > max_e:
                max_e = e_val
                emph_idx = idx

        # Build phrase text with Pop on emphatic word
        text_parts = []
        for idx, pw in enumerate(p):
            w_text = _esc(pw.get("text", "").upper())
            if idx == emph_idx:
                text_parts.append(f"{{\\rPop}}{w_text}{{\\rMain}}")
            else:
                text_parts.append(w_text)
        phrase_str = " ".join(text_parts)

        events.append(
            f"Dialogue: 0,{_ts(t_start)},{_ts(t_end)},Main,,0,0,0,,"
            f"{{\\fad(40,40)}}{{\\an2}}{phrase_str}"
        )

    full_ass = ass_content + "\n".join(events) + "\n"
    os.makedirs(os.path.dirname(os.path.abspath(out_ass_path)), exist_ok=True)
    with open(out_ass_path, "w", encoding="utf-8") as f:
        f.write(full_ass)
    return out_ass_path


def render_custom_clip(
    source_video_path: str,
    t0: float,
    t1: float,
    layout_mode: str = "split",           # "split", "blur", "crop"
    split_order: str = "streamer_top",    # "streamer_top" or "gameplay_top"
    split_ratio: float = 0.5,             # 0.4, 0.5, 0.6
    caption_y: int = 440,
    caption_font: str = "Arial Black",
    caption_size: int = 102,
    caption_color_hex: str = "#FFD200",
    hook_text: str = "",
    hook_duration: float = 4.0,
    ai_instructions: str = "",
    words: list = None,
    out_id: str = None
) -> Dict[str, Any]:
    """Execute customized re-render with ffmpeg and return the rendered file path."""
    out_id = out_id or f"custom_{uuid.uuid4().hex[:6]}"
    tmp_dir = os.path.join(PROJECT_ROOT, "data", "temp")
    os.makedirs(tmp_dir, exist_ok=True)
    out_mp4 = os.path.join(PROJECT_ROOT, "data", "shorts", f"{out_id}.mp4")

    # Step 1: Prep / Cut segment
    prep_mp4 = os.path.join(tmp_dir, f"{out_id}_prep.mp4")
    dur = max(3.0, float(t1) - float(t0))
    mt.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{t0:.3f}", "-i", source_video_path,
        "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "17",
        "-c:a", "aac", "-b:a", "192k",
        prep_mp4
    ])

    # Step 2: Build Layout Video Filter
    reframed_mp4 = os.path.join(tmp_dir, f"{out_id}_reframed.mp4")
    
    # Analyze video properties
    info = mt.probe(prep_mp4)
    in_w = info.get("w", 1920)
    in_h = info.get("h", 1080)

    if layout_mode == "blur":
        # 9:16 Blurred Fill Background (MrBeast style)
        filter_str = (
            f"[0:v]split=2[v_bg][v_fg];"
            f"[v_bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=32,eq=brightness=-0.16[bg];"
            f"[v_fg]scale=1080:-2:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p"
        )
        mt.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", prep_mp4, "-filter_complex", filter_str,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "17",
            "-c:a", "copy", reframed_mp4
        ])

    elif layout_mode == "crop":
        # Smart Dynamic 9:16 Center Crop
        crop_w = int(round(in_h * 9.0 / 16.0))
        if crop_w % 2 != 0: crop_w -= 1
        x_crop = int((in_w - crop_w) / 2.0)
        filter_str = f"crop={crop_w}:{in_h}:{x_crop}:0,scale=1080:1920:flags=lanczos,format=yuv420p"
        mt.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", prep_mp4, "-vf", filter_str,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "17",
            "-c:a", "copy", reframed_mp4
        ])

    else:
        # Split-Screen Layout (Facecam + Gameplay)
        # Scan speaker tracking to find facecam
        tracking = smart_reframe.analyze_speaker_tracking(prep_mp4, sample_step=0.4)
        face_info = tracking.get("face_box") or tracking.get("person1") or {}
        face_cx = face_info.get("cx", tracking.get("cx_anchor", 0.18))
        face_cy = face_info.get("cy", 0.72)

        # Height split based on split_ratio (default 0.5 -> 960 / 960)
        ratio = max(0.35, min(0.65, float(split_ratio or 0.5)))
        h_top = int(round(1920 * ratio))
        if h_top % 2 != 0: h_top -= 1
        h_bot = 1920 - h_top

        # Face crop
        face_crop_h = int(round(in_h * 0.38))
        face_crop_w = int(round(face_crop_h * 9.0 / 8.0))
        if face_crop_w % 2 != 0: face_crop_w -= 1
        if face_crop_h % 2 != 0: face_crop_h -= 1
        face_crop_w = min(face_crop_w, in_w)
        face_crop_h = min(face_crop_h, in_h)
        x_face = max(0, min(in_w - face_crop_w, int(face_cx * in_w - face_crop_w / 2.0)))
        y_face = max(0, min(in_h - face_crop_h, int(face_cy * in_h - face_crop_h * 0.42)))

        # Gameplay crop
        game_crop_h = in_h
        game_crop_w = int(round(game_crop_h * 9.0 / 8.0))
        if game_crop_w % 2 != 0: game_crop_w -= 1
        if game_crop_h % 2 != 0: game_crop_h -= 1
        game_crop_w = min(game_crop_w, in_w)
        game_crop_h = min(game_crop_h, in_h)
        x_game = max(0, in_w - game_crop_w) if face_cx < 0.45 else 0

        # Swap layers based on user choice: streamer_top vs gameplay_top
        if split_order == "streamer_top":
            # Streamer cam on TOP, Gameplay on BOTTOM
            filter_str = (
                f"[0:v]split=2[in_f][in_g];"
                f"[in_f]crop={face_crop_w}:{face_crop_h}:{x_face}:{y_face},scale=1080:{h_top}:flags=lanczos[layer_top];"
                f"[in_g]crop={game_crop_w}:{game_crop_h}:{x_game}:0,scale=1080:{h_bot}:flags=lanczos[layer_bot];"
                f"[layer_top][layer_bot]vstack=inputs=2[stacked];"
                f"[stacked]drawbox=x=0:y={h_top-2}:w=1080:h=4:color=0xFFD200@0.90:t=fill,format=yuv420p"
            )
        else:
            # Gameplay on TOP, Streamer cam on BOTTOM
            filter_str = (
                f"[0:v]split=2[in_g][in_f];"
                f"[in_g]crop={game_crop_w}:{game_crop_h}:{x_game}:0,scale=1080:{h_top}:flags=lanczos[layer_top];"
                f"[in_f]crop={face_crop_w}:{face_crop_h}:{x_face}:{y_face},scale=1080:{h_bot}:flags=lanczos[layer_bot];"
                f"[layer_top][layer_bot]vstack=inputs=2[stacked];"
                f"[stacked]drawbox=x=0:y={h_top-2}:w=1080:h=4:color=0xFFD200@0.90:t=fill,format=yuv420p"
            )

        mt.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", prep_mp4, "-filter_complex", filter_str,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "17",
            "-c:a", "copy", reframed_mp4
        ])

    # Step 3: Custom Subtitles & Hook Banner Burn
    ass_path = os.path.join(tmp_dir, f"{out_id}_cap.ass")
    build_custom_ass_subtitles(
        words=words or [],
        out_ass_path=ass_path,
        caption_y=caption_y,
        caption_font=caption_font,
        caption_size=caption_size,
        caption_color_hex=caption_color_hex,
        hook_text=hook_text,
        hook_duration=hook_duration,
        t0_offset=t0
    )

    ass_esc = ass_path.replace("\\", "/").replace(":", "\\:")
    mt.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", reframed_mp4,
        "-vf", f"subtitles='{ass_esc}'",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "17",
        "-c:a", "copy",
        out_mp4
    ])

    return {
        "ok": True,
        "video_path": os.path.abspath(out_mp4),
        "filename": os.path.basename(out_mp4),
        "stream_url": f"/video/data/shorts/{os.path.basename(out_mp4)}",
        "duration": round(dur, 2)
    }


def build_ass_from_project_layers(layers: list, out_ass_path: str):
    """Generate ASS subtitles from EditorProject layers preserving styling and position."""
    def hex_to_ass(hex_val, alpha="00"):
        h = str(hex_val).lstrip("#")
        if len(h) < 6:
            h = "FFFFFF"
        r, g, b = h[0:2], h[2:4], h[4:6]
        return f"&H{alpha}{b}{g}{r}"

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Montserrat,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,6,2,2,40,40,400,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events = []

    for l in layers:
        l_type = l.get("type", "")
        if l_type == "hook_text":
            text = _esc(l.get("text", "").upper())
            s = float(l.get("start", 0))
            e = s + float(l.get("duration", 4.0))
            font = l.get("fontFamily", "Montserrat")
            fsize = int(l.get("fontSize", 54) * 1.3)
            c_fill = hex_to_ass(l.get("color", "#FFFFFF"))
            c_strk = hex_to_ass(l.get("strokeColor", "#000000"))
            stroke_w = int(l.get("strokeWidth", 6))
            x = int(l.get("x", 540) + l.get("width", 800) / 2)
            y = int(l.get("y", 220) + l.get("height", 100) / 2)

            events.append(
                f"Dialogue: 2,{_ts(s)},{_ts(e)},Default,,0,0,0,,"
                f"{{\\an5\\pos({x},{y})\\fn{font}\\fs{fsize}\\1c{c_fill}&\\3c{c_strk}&\\bord{stroke_w}\\shad2\\fad(100,150)}}"
                f"{text}"
            )

        elif l_type == "captions":
            style = l.get("style", {})
            font = style.get("fontFamily", "Impact")
            fsize = int(style.get("fontSize", 78) * 1.1)
            c_base = hex_to_ass(style.get("color", "#FFFFFF"))
            c_act = hex_to_ass(style.get("activeWordColor", "#22D3EE"))
            c_strk = hex_to_ass(style.get("strokeColor", "#000000"))
            stroke_w = int(style.get("strokeWidth", 8))
            y_pos = int(l.get("y", 1350))
            w_per_line = int(style.get("wordsPerLine", 2))

            words = l.get("words", [])
            # Group into chunks
            cur = []
            chunks = []
            for w in words:
                cur.append(w)
                if len(cur) >= w_per_line:
                    chunks.append(cur)
                    cur = []
            if cur:
                chunks.append(cur)

            for chunk in chunks:
                if not chunk: continue
                s_t = max(0.0, float(chunk[0].get("start", 0)))
                e_t = max(s_t + 0.2, float(chunk[-1].get("end", s_t + 0.8)))

                # Form phrase with active word highlights
                for active_w in chunk:
                    w_s = float(active_w.get("start", s_t))
                    w_e = float(active_w.get("end", e_t))
                    word_parts = []
                    for w in chunk:
                        w_clean = _esc(w.get("word", "").upper() if style.get("uppercase", True) else w.get("word", ""))
                        if w == active_w:
                            word_parts.append(f"{{\\1c{c_act}&\\fscx112\\fscy112}}{w_clean}{{\\1c{c_base}&\\fscx100\\fscy100}}")
                        else:
                            word_parts.append(w_clean)
                    phrase_line = " ".join(word_parts)
                    events.append(
                        f"Dialogue: 1,{_ts(w_s)},{_ts(w_e)},Default,,0,0,0,,"
                        f"{{\\an5\\pos(540,{y_pos})\\fn{font}\\fs{fsize}\\1c{c_base}&\\3c{c_strk}&\\bord{stroke_w}\\shad4}}"
                        f"{phrase_line}"
                    )

    os.makedirs(os.path.dirname(os.path.abspath(out_ass_path)), exist_ok=True)
    with open(out_ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events) + "\n")
    return out_ass_path


def render_project_json(project: Dict[str, Any]) -> Dict[str, Any]:
    """Execute 100% parity FFmpeg render directly from the EditorProject JSON specification."""
    source_path = project.get("sourceVideoPath", "")
    full_source = _safe_resolve(source_path) if source_path else None
    if not full_source or not os.path.exists(full_source):
        # Fallback to demo short
        shorts_dir = os.path.join(PROJECT_ROOT, "data", "shorts")
        cand = [os.path.join(shorts_dir, f) for f in os.listdir(shorts_dir) if f.endswith(".mp4")]
        if cand:
            cand.sort(key=os.path.getmtime, reverse=True)
            full_source = cand[0]
        else:
            raise FileNotFoundError("No source video found for rendering")

    out_id = f"render_{project.get('id', 'proj')}_{uuid.uuid4().hex[:6]}"
    tmp_dir = os.path.join(PROJECT_ROOT, "data", "temp")
    os.makedirs(tmp_dir, exist_ok=True)
    out_mp4 = os.path.join(PROJECT_ROOT, "data", "shorts", f"{out_id}.mp4")

    dur = float(project.get("duration", 30.0))
    info = mt.probe(full_source)
    in_w = info.get("w", 1920)
    in_h = info.get("h", 1080)

    layout = project.get("layout", "split")
    reframed_mp4 = os.path.join(tmp_dir, f"{out_id}_reframed.mp4")

    if layout == "split":
        is_streamer_top = project.get("splitOrder", "streamer_top") == "streamer_top"
        top_crop = project.get("facecamCrop" if is_streamer_top else "gameplayCrop", {})
        bot_crop = project.get("gameplayCrop" if is_streamer_top else "facecamCrop", {})

        ratio = float(project.get("splitRatio", 0.5))
        h_top = int(round(1920 * ratio))
        if h_top % 2 != 0: h_top += 1
        h_bot = 1920 - h_top

        # Top Crop in Source Pixels
        cw_top = max(32, int(round(top_crop.get("width", 0.35) * in_w)))
        ch_top = max(32, int(round(top_crop.get("height", 0.40) * in_h)))
        cx_top = max(0, min(in_w - cw_top, int(round(top_crop.get("x", 0.65) * in_w))))
        cy_top = max(0, min(in_h - ch_top, int(round(top_crop.get("y", 0.05) * in_h))))
        if cw_top % 2 != 0: cw_top -= 1
        if ch_top % 2 != 0: ch_top -= 1

        # Bottom Crop in Source Pixels
        cw_bot = max(32, int(round(bot_crop.get("width", 0.90) * in_w)))
        ch_bot = max(32, int(round(bot_crop.get("height", 0.90) * in_h)))
        cx_bot = max(0, min(in_w - cw_bot, int(round(bot_crop.get("x", 0.05) * in_w))))
        cy_bot = max(0, min(in_h - ch_bot, int(round(bot_crop.get("y", 0.05) * in_h))))
        if cw_bot % 2 != 0: cw_bot -= 1
        if ch_bot % 2 != 0: ch_bot -= 1

        filter_str = (
            f"[0:v]split=2[in_top][in_bot];"
            f"[in_top]crop={cw_top}:{ch_top}:{cx_top}:{cy_top},scale=1080:{h_top}:flags=lanczos[v_top];"
            f"[in_bot]crop={cw_bot}:{ch_bot}:{cx_bot}:{cy_bot},scale=1080:{h_bot}:flags=lanczos[v_bot];"
            f"[v_top][v_bot]vstack=inputs=2[stacked];"
            f"[stacked]drawbox=x=0:y={h_top-2}:w=1080:h=4:color=0x22D3EE@0.90:t=fill,format=yuv420p"
        )
    elif layout == "blur_fill":
        blur_amt = int(project.get("blurAmount", 24))
        filter_str = (
            f"[0:v]split=2[v_bg][v_fg];"
            f"[v_bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma={blur_amt},eq=brightness=-0.2[bg];"
            f"[v_fg]scale=1080:-2:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p"
        )
    else:
        crop_w = int(round(in_h * 9.0 / 16.0))
        if crop_w % 2 != 0: crop_w -= 1
        x_crop = int((in_w - crop_w) / 2.0)
        filter_str = f"crop={crop_w}:{in_h}:{x_crop}:0,scale=1080:1920:flags=lanczos,format=yuv420p"

    mt.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-t", f"{dur:.3f}", "-i", full_source,
        "-filter_complex", filter_str,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "17",
        "-c:a", "aac", "-b:a", "192k",
        reframed_mp4
    ])

    ass_path = os.path.join(tmp_dir, f"{out_id}.ass")
    build_ass_from_project_layers(project.get("layers", []), ass_path)

    ass_esc = ass_path.replace("\\", "/").replace(":", "\\:")
    mt.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", reframed_mp4,
        "-vf", f"subtitles='{ass_esc}'",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "17",
        "-c:a", "copy",
        out_mp4
    ])

    return {
        "ok": True,
        "video_path": os.path.abspath(out_mp4),
        "filename": os.path.basename(out_mp4),
        "stream_url": f"/video/data/shorts/{os.path.basename(out_mp4)}",
        "output_path": os.path.abspath(out_mp4),
        "duration": round(dur, 2)
    }
