"""9:16 editing: prep -> reframe (face-follow) -> punch-ins -> karaoke captions ->
countdown cards / title / SFX / BGM (ducked) -> final assembly -> loudness normalize."""
import os, subprocess, json
from . import config, mediatools as mt
from . import captions as capgen
from . import music as musicgen
from . import smart_reframe

def _p(t):  # project media path
    d = config.media_dir()
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, t)

def prep(plan, out_id):
    src = plan.get("src_path") or _p(plan["src"])
    out = _p(f"{out_id}_prep.mp4")
    if os.path.exists(out):
        os.remove(out)

    # Resiliency guard: Check if source file exists
    if not os.path.exists(src):
        src_dir = os.path.dirname(src)
        src_name = os.path.basename(src)
        alt_names = []
        if "O" in src_name:
            alt_names.append(src_name.replace("O", "0"))
        if "0" in src_name:
            alt_names.append(src_name.replace("0", "O"))
        found = False
        for alt in alt_names:
            alt_path = os.path.join(src_dir, alt)
            if os.path.exists(alt_path):
                src = alt_path
                plan["src_path"] = alt_path
                found = True
                print(f"[Edit Prep] Auto-recovered alternate source file: {alt_path}")
                break

        if not found:
            stream_url = plan.get("url") or (f"https://www.youtube.com/watch?v={plan.get('id', '')}" if plan.get('id') else None)
            if stream_url:
                try:
                    from . import long_stream
                    print(f"[Edit Prep] Source video missing ({src}). Surgically fetching segment {plan['t0']:.1f}s - {plan['t1']:.1f}s from {stream_url}...")
                    dl_ok = long_stream.download_surgical_video(stream_url, plan["t0"], plan["t1"], out)
                    if dl_ok and os.path.exists(out) and os.path.getsize(out) > 1000:
                        return out
                except Exception as s_err:
                    print(f"[Edit Prep] Surgical fallback download failed: {s_err}")

    mt.prep_cut(src, plan["t0"], plan["t1"], out, fps=config.FPS_OUT)
    return out

def reframe(prep_path, plan, out_id):
    """Smart face-following and multi-speaker reframe to 1080x1920. Returns (video_path, face_stats)."""
    out = _p(f"{out_id}_reframed.mp4")
    if plan.get("kind") == "portrait":
        vf = ("scale=1080:1920:flags=lanczos,"
              "crop=1040:1856:(in_w-1040)/2+(in_w/2)*0.02*sin(t*0.6):(in_h-1856)/2,"
              "scale=1080:1920:flags=lanczos,format=yuv420p")
        plan["face_stats"] = {"cx0": 0.5, "cx1": 0.5, "hits": 1.0, "area": 0.05}
        mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", prep_path,
                "-vf", vf, "-r", str(config.FPS_OUT), "-c:v", "libx264", "-preset", "ultrafast",
                "-crf", "17", out])
        return out, plan.get("face_stats")

    # Smart multi-face & dynamic speaker tracking
    tracking = smart_reframe.analyze_speaker_tracking(prep_path)
    tracking["is_gaming"] = bool(plan.get("is_gaming", False))
    tracking["creator"] = plan.get("creator", "")
    if plan.get("reframe_mode"):
        tracking["mode"] = plan.get("reframe_mode")
    if plan.get("force_split_screen"):
        tracking["force_split"] = True
    elif plan.get("is_split_screen") is False:
        tracking["force_split"] = False
    filter_str, stats = smart_reframe.generate_reframe_filter(tracking)

    plan["is_split_screen"] = stats.get("split_screen", False)
    plan["face_stats"] = {
        "hits": tracking.get("hits", 0.9),
        "mode": tracking.get("mode", "single_track"),
        "is_two_people": tracking.get("is_two_people", False)
    }

    if stats.get("split_screen") or stats.get("mode") == "blur_fill" or "[0:v]" in filter_str:
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", prep_path,
               "-filter_complex", filter_str]
        if "[reframe_out]" in filter_str:
            cmd += ["-map", "[reframe_out]"]
        cmd += ["-r", str(config.FPS_OUT), "-c:v", "libx264",
                "-preset", "ultrafast", "-crf", "17", out]
        mt.run(cmd)
    else:
        mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", prep_path,
                "-vf", filter_str, "-r", str(config.FPS_OUT), "-c:v", "libx264",
                "-preset", "ultrafast", "-crf", "17", out])

    return out, plan.get("face_stats")

def _zoom_expr(tin, rz, z):
    """Zoom factor z(t): 1 -> z ramping over rz seconds starting at tin, then hold."""
    zt = f"(1+({z}-1)*((t-{tin})/{rz}))"
    return f"if(lt(t,{tin}),1,if(lt(t,{tin}+{rz}),{zt},{z}))"

def add_punch(input_path, plan, out_id):
    """Single punch-in on the reaction peak (highest-energy word). Returns path."""
    if plan.get("is_split_screen"):
        return input_path
    punch = plan.get("punch")
    if not punch:
        return input_path
    tin = round(punch["tin"], 3); z = punch.get("z", 1.14); rz = 0.26
    cx, cy = 0.5, 0.38
    out = _p(f"{out_id}_punch.mp4")
    # Using ffmpeg zoompan with exact stationary focal center (cx, cy)
    # Crop offset: x = (iw - iw/zoom) * cx, y = (ih - ih/zoom) * cy
    fps = config.FPS_OUT
    f_in = int(tin * fps)
    f_rz = max(1, int(rz * fps))
    f_end = f_in + f_rz
    vf = (f"zoompan=z='if(between(in,{f_in},{f_end}),1+({z}-1)*((in-{f_in})/{f_rz}),if(gte(in,{f_end}),{z},1))':"
          f"x='(iw-iw/zoom)*{cx}':y='(ih-ih/zoom)*{cy}':d=1:s=1080x1920:fps={fps}")
    mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", input_path,
            "-vf", vf, "-r", str(config.FPS_OUT), "-c:v", "libx264", "-preset", "ultrafast",
            "-crf", "17", out])
    return out

def burn_karaoke(input_path, prep_path, words, emphasis, cap_profile, out_id, t0_offset=None, hook_text=None):
    """Burn word-pop captions & viral top hook banner; keep aligned audio from prep with tiny edge fades."""
    ass = _p(f"{out_id}_cap.ass")
    meta = _p(f"{out_id}_cap.json")
    capgen.make(words, cap_profile, emphasis, out_ass=ass, out_meta=meta, t0_offset=t0_offset, hook_text=hook_text)
    out = _p(f"{out_id}_capped.mp4")
    ass_esc = ass.replace("\\", "/").replace(":", "\\:")
    dur = mt.ffprobe_dur(input_path) or 0
    aout = max(0.0, dur - 0.20)
    mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", input_path, "-i", prep_path,
            "-map", "0:v", "-map", "1:a",
            "-vf", f"subtitles='{ass_esc}'",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-af", f"afade=t=in:st=0:d=0.08,afade=t=out:st={aout:.2f}:d=0.20", out])
    return out

# ---------------- SFX & cards ----------------
def make_sfx():
    who = _p("whoosh.wav")
    boom = _p("boom.wav")
    for f in (who, boom):
        if os.path.exists(f) and os.path.getsize(f) < 1000:
            os.remove(f)  # stale/partial generation from an earlier run
    if not os.path.exists(who):
        mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "anoisesrc=colour=white:r=48000:d=0.6:a=0.55",
                "-af", "highpass=f=500,lowpass=f=2600,afade=t=in:st=0:d=0.12,afade=t=out:st=0.42:d=0.18",
                "-ac", "2", who])
    # boom: low-frequency thud (tone + pink noise thump), 0.9s - primitives only
    # (custom aeval expressions are a parsing hazard in -af graphs)
    if not os.path.exists(boom):
        mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "sine=frequency=58:sample_rate=48000:duration=0.9",
                "-f", "lavfi", "-i", "anoisesrc=colour=pink:sample_rate=48000:duration=0.35:a=0.7",
                "-filter_complex",
                ("[0:a]afade=t=in:st=0:d=0.03,afade=t=out:st=0.55:d=0.35,lowpass=f=90[tone];"
                 "[1:a]lowpass=f=140,afade=t=out:st=0.02:d=0.30[thud];"
                 "[tone][thud]amix=inputs=2:duration=longest:normalize=0,"
                 "dynaudnorm=f=200:g=15,volume=1.6,atrim=0:0.9,aresample=48000,"
                 "aformat=channel_layouts=stereo[boom]"),
                "-map", "[boom]", "-ac", "2", boom])
    return who, boom

def _card_ass(number, dur, special, out_ass, label=None):
    # Large 260pt high-contrast gradient number, thick black outline, golden glow drop shadow
    style = ("RankBadge, Impact, 250, &H00FFFFFF, &H0000D2FF, &H00000000, &H00000000, "
             "-1, 0, 0, 0, 100, 100, 8, 0, 1, 14, 8, 5, 5, 880, 1")
    sub = ("RankSub, Arial Black, 72, &H0000D2FF, &H000000FF, &H00000000, &H00000000, "
           "-1, 0, 0, 0, 100, 100, 3, 0, 1, 9, 4, 2, 5, 880, 1")
    glow = ("RankGlow, Impact, 252, &H0000D2FF, &H000000FF, &H00000000, &H00000000, "
            "-1, 0, 0, 0, 100, 100, 8, 0, 1, 22, 12, 5, 5, 880, 1")
    hdr = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\n"
           "ScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
           "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
           "Alignment, MarginL, MarginR, MarginV, Encoding\n"
           f"Style: {style}\nStyle: {glow}\nStyle: {sub}\n\n[Events]\n"
           "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    pop = "{\\fscx320\\fscy320\\t(0,250,110,110)\\t(260,500,100,100)}"
    ev_glow = f"Dialogue: 0,0:00:00.08,0:00:{int(dur*10):02d}.00,RankGlow,,0,0,0,,{{\\fad(60,120)}}{number}"
    ev = f"Dialogue: 1,0:00:00.08,0:00:{int(dur*10):02d}.00,RankBadge,,0,0,0,,{pop}{number}"
    lines = [hdr, ev_glow, ev]
    sub_title = (label or ("TOP MOMENT" if special else f"MOMENT {number}")).strip().upper()[:26]
    lines.append(f"Dialogue: 2,0:00:00.32,0:00:{int(dur*10):02d}.00,RankSub,,0,0,0,,{{\\fad(150,120)}}{sub_title}")
    with open(out_ass, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

def _clean_drawtext(s: str) -> str:
    if not s:
        return ""
    clean = str(s).encode("ascii", "ignore").decode("ascii")
    clean = clean.replace("\\", "\\\\").replace("'", "").replace(":", "\\:").replace("%", "\\%")
    return clean.strip().upper()

def make_card(number, dur, special, bg_src, out_id, boom, label=None):
    bg = _p(f"{out_id}_card_bg.png")
    out = _p(f"{out_id}_card.mp4")
    if str(bg_src).lower().endswith((".png", ".jpg", ".jpeg")):
        mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", bg_src,
                "-frames:v", "1", bg])
    else:
        mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", "0.3", "-i", bg_src,
                "-frames:v", "1", bg])

    font_impact = "C\\:/Windows/Fonts/impact.ttf" if os.path.exists("C:/Windows/Fonts/impact.ttf") else "arialbd.ttf"
    font_arial = "C\\:/Windows/Fonts/ariblk.ttf" if os.path.exists("C:/Windows/Fonts/ariblk.ttf") else "arialbd.ttf"

    raw_sub = label if label else ("TOP MOMENT" if special else f"MOMENT {number}")
    subtext = _clean_drawtext(raw_sub).upper()[:26]
    card_vf = (
        f"scale=1080:1920:flags=lanczos,boxblur=24:2,eq=brightness=-0.38:contrast=1.2,"
        f"drawbox=x=80:y=740:w=920:h=440:color=0x000000@0.82:t=fill,"
        f"drawbox=x=80:y=740:w=920:h=440:color=0xFFD200@0.95:t=6,"
        f"drawbox=x=80:y=734:w=920:h=8:color=0xFFD200:t=fill,"
        f"drawbox=x=80:y=1178:w=920:h=8:color=0xFFD200:t=fill,"
        f"drawtext=fontfile='{font_impact}':text='{number}':fontcolor=0xFFD200:fontsize=170:x=(w-text_w)/2:y=790:borderw=6:bordercolor=0x000000:shadowx=6:shadowy=6:shadowcolor=0x000000,"
        f"drawtext=fontfile='{font_impact}':text='{subtext}':fontcolor=0xFFFFFF:fontsize=52:x=(w-text_w)/2:y=1030:borderw=4:bordercolor=0x000000:shadowx=4:shadowy=4:shadowcolor=0x000000"
    )

    mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-loop", "1", "-i", bg, "-i", boom,
            "-map", "0:v", "-map", "1:a",
            "-vf", card_vf,
            "-t", str(round(dur + 0.25, 2)), "-r", str(config.FPS_OUT),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-af", "adelay=80|80,apad=pad_dur=1.0,atrim=0:" + str(round(dur + 0.25, 2)),
            out])
    return out

def make_title(bg_src, hook, out_id="title_raw", line1="TOP 5 FUNNIEST", line2="MOMENTS"):
    """Fast hook title card (~1.6s) - viral YouTube Shorts countdown intro."""
    bg = _p(f"{out_id}_bg.png")
    out = _p(f"{out_id}.mp4")
    who, _boom = make_sfx()
    if str(bg_src).lower().endswith((".png", ".jpg", ".jpeg")):
        mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", bg_src,
                "-frames:v", "1", bg])
    else:
        mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", "0.5", "-i", bg_src,
                "-frames:v", "1", bg])

    font_impact = "C\\:/Windows/Fonts/impact.ttf" if os.path.exists("C:/Windows/Fonts/impact.ttf") else "arialbd.ttf"
    font_arial = "C\\:/Windows/Fonts/ariblk.ttf" if os.path.exists("C:/Windows/Fonts/ariblk.ttf") else "arialbd.ttf"

    def _clean_drawtext(s: str) -> str:
        if not s:
            return ""
        clean = s.encode("ascii", "ignore").decode("ascii")
        clean = clean.replace("\\", "\\\\").replace("'", "").replace(":", "\\:").replace("%", "\\%")
        return clean.strip().upper()

    l1 = _clean_drawtext(line1) or "TOP 5 COUNTDOWN"
    l2 = _clean_drawtext(line2) or "MOMENTS"
    tagline = "COUNTDOWN #5 TO #1"

    fs1 = 80 if len(l1) > 18 else (90 if len(l1) > 14 else 100)
    fs2 = 72 if len(l2) > 18 else (82 if len(l2) > 14 else 90)

    title_vf = (
        f"scale=1080:1920:flags=lanczos,boxblur=24:2,eq=brightness=-0.35:contrast=1.2,"
        f"drawbox=x=40:y=720:w=1000:h=480:color=0x000000@0.80:t=fill,"
        f"drawbox=x=40:y=720:w=1000:h=480:color=0xFFD200@0.95:t=6,"
        f"drawbox=x=40:y=714:w=1000:h=8:color=0xFFD200:t=fill,"
        f"drawbox=x=40:y=1198:w=1000:h=8:color=0xFFD200:t=fill,"
        f"drawtext=fontfile='{font_impact}':text='{l1}':fontcolor=0xFFFFFF:fontsize={fs1}:x=(w-text_w)/2:y=790:borderw=5:bordercolor=0x000000:shadowx=5:shadowy=5:shadowcolor=0x000000,"
        f"drawtext=fontfile='{font_impact}':text='{l2}':fontcolor=0xFFD200:fontsize={fs2}:x=(w-text_w)/2:y=910:borderw=5:bordercolor=0x000000:shadowx=5:shadowy=5:shadowcolor=0x000000,"
        f"drawtext=fontfile='{font_arial}':text='{tagline}':fontcolor=0x00E5FF:fontsize=46:x=(w-text_w)/2:y=1040:borderw=3:bordercolor=0x000000"
    )

    dur = hook.get("title_seconds", 1.6)
    mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-loop", "1", "-i", bg, "-i", who,
            "-map", "0:v", "-map", "1:a",
            "-vf", title_vf,
            "-t", str(dur), "-r", str(config.FPS_OUT),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-af", "afade=t=in:st=0:d=0.08", out])
    return out

# ---------------- assembly ----------------
def assemble(clip_paths, out_file, hook=None, whoosh_at=None, music_profile=None, sfx_cues=None, creator="speed"):
    """Concat + timebase-normalize + streamer-tailored BGM (sidechain-ducked) + broadcast loudnorm.

    Sound effects (SFX) are completely eliminated as requested.
    BGM is 100% royalty-free, matched to the streamer, ducked cleanly under speech, and normalized to -14 LUFS.
    """
    import uuid
    if len(clip_paths) == 1:
        merged = clip_paths[0]
        temp_merged = None
    else:
        u_id = uuid.uuid4().hex[:8]
        lst = _p(f"concat_{u_id}.txt")
        with open(lst, "w", encoding="utf-8") as f:
            for p in clip_paths:
                abs_p = os.path.abspath(p).replace("\\", "/")
                f.write(f"file '{abs_p.replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n")
        merged = _p(f"merged_{u_id}.mp4")
        temp_merged = merged
        if os.path.exists(merged):
            try:
                os.remove(merged)
            except OSError:
                pass
        mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
                "-i", lst, "-c", "copy", merged])
        try:
            os.remove(lst)
        except OSError:
            pass

    input_files = [merged]
    filter_complex = "[0:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]"

    # Contextual SFX mixing
    sfx_filters = []
    if sfx_cues and isinstance(sfx_cues, list):
        from . import sfx_director
        for idx, cue in enumerate(sfx_cues[:2]):
            sfx_name = cue.get("sfx")
            sfx_time = cue.get("time", 0.0)
            sfx_vol = cue.get("volume", 0.6)
            sfx_path = sfx_director.get_sfx_path(sfx_name)
            if sfx_path and os.path.exists(sfx_path):
                sfx_idx = len(input_files)
                input_files.append(sfx_path)
                delay_ms = int(max(0, sfx_time) * 1000)
                sfx_filters.append(f"[{sfx_idx}:a]adelay={delay_ms}|{delay_ms},volume={sfx_vol}[sfx_{idx}];")

    # Royalty-free BGM only added if explicitly enabled
    if music_profile and isinstance(music_profile, dict) and music_profile.get("enabled"):
        creator_key = music_profile.get("creator") or music_profile.get("style") or creator
        bgm = musicgen.get_streamer_bgm(creator_key)
        if os.path.exists(bgm):
            bgm_idx = len(input_files)
            input_files.append(bgm)
            bed_vol = float(music_profile.get("bed_volume", 0.16))
            duck_thresh = float(music_profile.get("duck_threshold", 0.05))
            duck_ratio = float(music_profile.get("duck_ratio", 7.5))

            sfx_str = "".join(sfx_filters)
            if sfx_filters:
                # Combine dialogue + sfx first, then sidechain duck BGM
                sfx_in_labels = "".join(f"[sfx_{i}]" for i in range(len(sfx_filters)))
                total_speech_inputs = 1 + len(sfx_filters)
                chain = (
                    f"{sfx_str}"
                    f"[0:a]{sfx_in_labels}amix=inputs={total_speech_inputs}:duration=first:dropout_transition=2[dialogue_sfx];"
                    f"[{bgm_idx}:a]volume='if(lt(t,2.2),0.03,if(lt(t,5.5),0.10,{bed_vol}))':eval=frame[mus_curved];"
                    f"[mus_curved][dialogue_sfx]sidechaincompress=threshold={duck_thresh}:ratio={duck_ratio}:attack=20:release=260[duck];"
                    f"[dialogue_sfx][duck]amix=inputs=2:duration=first:dropout_transition=2,"
                    f"loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]"
                )
            else:
                chain = (
                    f"[{bgm_idx}:a]volume='if(lt(t,2.2),0.03,if(lt(t,5.5),0.10,{bed_vol}))':eval=frame[mus_curved];"
                    f"[mus_curved][0:a]sidechaincompress=threshold={duck_thresh}:ratio={duck_ratio}:attack=20:release=260[duck];"
                    f"[0:a][duck]amix=inputs=2:duration=first:dropout_transition=2,"
                    f"loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]"
                )
            filter_complex = chain
    elif sfx_filters:
        # No BGM, but SFX cues present
        sfx_str = "".join(sfx_filters)
        sfx_in_labels = "".join(f"[sfx_{i}]" for i in range(len(sfx_filters)))
        total_inputs = 1 + len(sfx_filters)
        filter_complex = (
            f"{sfx_str}"
            f"[0:a]{sfx_in_labels}amix=inputs={total_inputs}:duration=first:dropout_transition=2,"
            f"loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]"
        )

    # Construct command line inputs
    inputs = []
    for f in input_files:
        inputs += ["-i", f]

    # Sharp, crystal-clear 1080p output (crf 17, faster preset, unsharp filter)
    mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + inputs +
           ["-filter_complex", filter_complex,
            "-map", "0:v", "-map", "[aout]",
            "-vf", "fps=30,settb=AVTB,unsharp=3:3:0.6:3:3:0.0,format=yuv420p",
            "-c:v", "libx264", "-preset", "faster", "-crf", "17", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out_file])
    if temp_merged and os.path.exists(temp_merged):
        try:
            os.remove(temp_merged)
        except OSError:
            pass
    return out_file


def render_moment(plan):
    """End-to-end rendering pipeline for a single moment plan.

    Processes: prep cut -> 9:16 reframe -> punch-in zoom -> kinetic subtitles -> SFX/BGM -> assemble.
    """
    out_id = str(plan.get("id", "moment"))
    out_path = plan.get("output") or _p(f"{out_id}_final.mp4")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    # 1. Prep segment
    prep_file = prep(plan, out_id)

    # 2. Reframe (MrBeast blur or Split-screen)
    reframed, _ = reframe(prep_file, plan, out_id)

    # 3. Punch-in zoom
    punched = add_punch(reframed, plan, out_id)

    # 4. Burn karaoke subtitles & hook banner
    sub_cfg = plan.get("subtitles") or {}
    words = sub_cfg.get("words") or plan.get("words") or []
    emph = sub_cfg.get("emphasis_words") or plan.get("emphasis") or []
    hook_cfg = plan.get("hook") or {}
    hook_text = hook_cfg.get("text") or plan.get("hook_text") or ""

    from . import format as format_mod
    creator_id = plan.get("creator") or "speed"
    fmt = format_mod.build_directives({"format": "moment", "creator": creator_id})

    capped = burn_karaoke(
        punched, prep_file, words, emph,
        fmt["caption"], out_id, t0_offset=plan.get("t0", 0.0),
        hook_text=hook_text
    )

    # 5. SFX and BGM
    from . import sfx_director
    sfx_cfg = plan.get("sfx") or {}
    sfx_cues = sfx_director.plan_sfx_for_clip(
        clip_words=words,
        video_info={"title": plan.get("title", "")},
        creator=creator_id,
        dur=plan.get("t1", 45.0) - plan.get("t0", 0.0),
        hint_sfx=sfx_cfg.get("type")
    )

    audio_cfg = plan.get("audio") or {}
    bed_vol = float(audio_cfg.get("music_volume", 0.16)) if (audio_cfg.get("music_path") or audio_cfg.get("music_volume")) else 0.0
    _music_profile = {
        **fmt.get("music", {}),
        "enabled": (bed_vol > 0.0),
        "creator": creator_id,
        "bed_volume": bed_vol,
        "music_path": audio_cfg.get("music_path")
    }

    final_mp4 = assemble(
        [capped], out_path, fmt["hook"], whoosh_at=None,
        music_profile=_music_profile,
        sfx_cues=sfx_cues,
        creator=creator_id
    )

    # Clean intermediate scratch files
    for tmp in [prep_file, reframed, punched, capped]:
        if tmp and os.path.exists(tmp) and tmp != final_mp4 and tmp != plan.get("src_path"):
            try:
                os.remove(tmp)
            except Exception:
                pass

    return {"output_path": final_mp4, "ok": True}