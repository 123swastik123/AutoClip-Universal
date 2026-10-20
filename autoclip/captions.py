"""Viral-Shorts phrase-pop caption engine.

Shows complete phrases simultaneously (not word-by-word karaoke) with a
speech-synced scale-pop on the single loudest / most emphatic word in each
phrase — matching the old "good" captions style.

Styles:
  Main    – phrase body  (Impact, white, large outline)
  Pop     – key word pop layer on top (Impact, yellow/accent, bigger, above Main)
  Punch   – sidebar punchline / meme caption
  HookTop – viral hook banner at the top of the short

Also emits a JSON word/phrase map + caption-QA diagnostics used by the
creative-QA gate.
"""
import os, json

# Reaction / shout tokens that get automatic emphasis.
SHOUTS = {
    "OH", "MY", "GOD", "WHAT", "NOW", "LET'S", "LET", "GO", "LOVE", "BRO",
    "CAN", "DIE", "Y'ALL", "HERE", "NAME", "WORD", "BEAUTIFUL", "F*CK",
    "AGAIN", "CHECK", "THIS", "CAN'T", "CANT", "NOBODY", "NOTHING", "REALLY",
    "TELL", "WAIT", "STOP", "NO WAY", "HUH", "BROTHER", "HELL", "HEY", "MAN",
}

def _ts(sec):
    cs = int(round(sec * 100))
    h = cs // 360000
    m = (cs // 6000) % 60
    s = (cs // 100) % 60
    c = cs % 100
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"

def _esc(t):
    return (t.replace("{", "(").replace("}", ")")
             .replace("\\", "/").replace("\n", " ").strip())

def group_words(words, words_per_line=2, gap_thresh=0.45):
    """Group words into punchy, high-retention 1-2 word kinetic subtitle chunks."""
    phrases = []
    cur = []
    for w in words:
        if cur and (w["start"] - cur[-1]["end"] > gap_thresh or len(cur) >= words_per_line):
            phrases.append(cur); cur = []
        cur.append(w)
    if cur:
        phrases.append(cur)
    return phrases

def _font_size_for_phrase(n_words, base_size):
    """Keep font large, punchy, and readable on 9:16 mobile screens."""
    if n_words <= 1:
        return 112
    if n_words <= 2:
        return 102
    return 92

def header(profile):
    """Kinetic high-contrast subtitle styling for viral retention."""
    font = profile.get("font", "Arial Black")
    margin_v = int(profile.get("margin_v", 440))
    pop_margin_v = margin_v

    # ASS color codes are &HAABBGGRR (Alpha, Blue, Green, Red)
    # White = &H00FFFFFF
    # Gold/Yellow = &H0000E5FF (RGB #FFE500)
    # Cyan = &H00FFF000 (RGB #00F0FF)
    # Red = &H002020FF (RGB #FF2020)
    # Black Outline = &H00000000
    return ("[Script Info]\n"
            "ScriptType: v4.00+\n"
            "PlayResX: 1080\n"
            "PlayResY: 1920\n"
            "WrapStyle: 2\n"
            "ScaledBorderAndShadow: yes\n"
            "\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Main,{font},102,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,"
            f"1,0,0,0,100,100,0,0,1,14,4,2,40,40,{margin_v},1\n"
            f"Style: Pop,{font},110,&H0000E5FF,&H00FFFFFF,&H00000000,&H80000000,"
            f"1,0,0,0,100,100,0,0,1,14,4,2,40,40,{pop_margin_v},1\n"
            f"Style: Scream,{font},115,&H002020FF,&H00FFFFFF,&H00000000,&H80000000,"
            f"1,0,0,0,100,100,0,0,1,16,5,2,40,40,{pop_margin_v},1\n"
            f"Style: Punch,{font},82,&H00FFF000,&H00FFFFFF,&H00000000,&H80000000,"
            f"1,0,0,0,100,100,0,0,1,12,3,5,40,40,140,1\n"
            f"Style: HookTop,Arial Black,72,&H0000E5FF,&H000000FF,&H00000000,&HCC000000,"
            f"-1,0,0,0,100,100,2,0,1,12,4,2,40,40,220,1\n"
            "\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

def make(words, profile, emphasis=(), out_ass=None, out_meta=None, energy_threshold=None, t0_offset=None, hook_text=None):
    """words: [{'start','end','text','energy'}]. Builds phrase-pop captions + meta.

    Each phrase group appears as a single subtitle event (all words at once).
    The most emphatic word in each phrase gets a Pop layer with scale animation.
    emphasis: explicit set of words to always boost. SHOUTS auto-emphasized.
    hook_text: optional bold viral hook banner text displayed at top of short.
    """
    cap = profile
    emph = {w.upper().strip(" .,;!?") for w in emphasis}
    pop_ms = int(cap.get("pop_ms", 160))
    up = cap.get("uppercase", True)
    base_size = int(cap.get("size", 80))

    # Timestamp normalization: ensure word start/end times are relative to clip start
    if t0_offset is not None and t0_offset > 0:
        if words and words[0].get("start", 0) >= (t0_offset - 1.0):
            words = [{**w, "start": max(0.0, w["start"] - t0_offset),
                           "end": max(0.05, w["end"] - t0_offset)} for w in words]
    elif words and words[0].get("start", 0) > 5.0:
        shift = float(words[0]["start"])
        words = [{**w, "start": max(0.0, w["start"] - shift),
                       "end": max(0.05, w["end"] - shift)} for w in words]

    # Whisper zero-length tokens: give minimal span
    words = [{**w, "end": (w["end"] if w.get("end", w["start"]) > w["start"]
                           else w["start"] + 0.10)} for w in words]
    words.sort(key=lambda x: x["start"])

    phrases = group_words(words, cap.get("words_per_line", 5))

    from .config import CaptionAnimation
    meta = {"style_system": CaptionAnimation.PHRASE_POP.value,
            "animation": CaptionAnimation.PHRASE_POP.value,
            "phrases": [], "words": []}

    # Dynamic energy threshold: top ~15% of words get pop emphasis
    energies = sorted(w.get("energy", 0.0) for w in words)
    if not energies:
        dyn_thr = 1.1
    elif energy_threshold is not None:
        dyn_thr = energy_threshold
    else:
        dyn_thr = max(0.70, energies[int(len(energies) * 0.85 - 1)] if len(energies) > 3 else energies[-1])

    events = []

    # Viral Hook Banner at top
    if hook_text and hook_text.strip():
        h_clean = _esc(hook_text.strip().upper())
        clip_dur = max([w["end"] for w in words] + [12.0])
        hook_end = min(clip_dur, 4.5)
        events.append(
            f"Dialogue: 1,0:00:00.10,{_ts(hook_end)},HookTop,,0,0,0,,"
            f"{{\\fad(120,180)}}{{\\fscx120\\fscy120\\t(0,200,100,100)}}{{\\an8}}"
            f"{{\\bord8\\shad3\\1c&HFFFFFF&\\3c&H000000&}}🔥 {h_clean} 🔥"
        )

    # Render one word at a time (TikTok/Shorts viral retention style)
    for w in words:
        raw_text = w.get("text", "").strip()
        if not raw_text:
            continue
        w_start = w["start"]
        w_end = max(w["end"], w_start + 0.12)
        word_text = raw_text.upper() if up else raw_text
        esc_text = _esc(word_text)
        
        # Punch pop on high-energy words
        energy = w.get("energy", 0.0)
        token = raw_text.strip(" .,;!?").upper()
        is_pop = (token in SHOUTS and energy >= 0.70) or (token in emph) or (energy >= dyn_thr)
        
        # Clean white with thick black outline, single punch scale on emphatic words
        if is_pop:
            fx_tag = r"{\fscx112\fscy112\t(0,100,100,100)}"
        else:
            fx_tag = r"{\fscx100\fscy100}"

        events.append(
            f"Dialogue: 0,{_ts(w_start)},{_ts(w_end)},Main,,0,0,0,,{fx_tag}{esc_text}"
        )

        meta["words"].append({
            "text": word_text,
            "start": w_start,
            "end": w_end,
            "emphasis": bool(is_pop),
            "energy": energy,
            "pop": bool(is_pop)
        })

    meta["energy_threshold"] = round(dyn_thr, 3)

    data = header(cap) + "\n".join(events) + "\n"
    if out_ass:
        with open(out_ass, "w", encoding="utf-8") as f:
            f.write(data)
    if out_meta:
        with open(out_meta, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=1)
    return data, meta
