"""Research stage: current viral Shorts / formats / creator signal + background music trends.

Consumes research notes (produced by live web research) and compiles them into a
structured Builder profile that downstream stages read. Nothing is hardcoded as
"the one true style" - the research determines the edit language.

The CLI itself does not browse; the orchestrating agent performs web searches and
records findings via `record_findings()`. `load()` returns the current profile.
"""
import json, os, datetime
from . import config
from .config import RESEARCH

DEFAULTS = {
    "window_time": datetime.date.today().isoformat(),
    "caption_trend": {
        "style": config.CaptionAnimation.PHRASE_POP.value,
        "font": "Impact",
        "color": "white",
        "outline": "black",
        "size": 80,
        "pos": "center_lower_third",
        "margin_v": 460,
        "words_per_line": 5,
        "emphasis_color": "#FFD200",
        "pop_ms": 160,
        "uppercase": True,
        "animation": config.CaptionAnimation.PHRASE_POP.value,
        "highlight_style": "bold_scale",   # bold_scale, color_shift, underline
        "emphasis_words": [],              # auto-detected + manual
        "safe_zone_margin": 0.15,          # 15% from edges
    },
    "edit_trend": {
        "max_silence_before_cut": 0.5,
        "hook_seconds": 2.5,
        "runtime_ideal": (20, 45),
        "punch_ins": True,
        "face_follow": True,
        "silence_trim": True,
        "sfx": ["whoosh", "boom"],
        "transition_style": "hard_cut",    # hard_cut, smooth_slide, zoom_punch
        "pacing": "energetic",             # energetic, breathing, mixed
    },
    "music_trend": {
        "enabled": True,
        "style": "lofi_hiphop",            # lofi_hiphop, phonk, synthwave, ambient, trending_sound
        "volume_duck_db": -18,             # duck level during speech
        "fade_in_ms": 300,
        "fade_out_ms": 500,
        "use_trending": True,              # try to use current trending sounds
        "copyright_safe": True,            # prefer royalty-free / library
        "match_creator": True,             # adapt to creator's usual vibe
        "track_per_moment": False,         # one track whole video or per-moment
        "build_ups": True,                 # use music builds for escalation
    },
    "countdown_trend": {
        "n": 5,
        "card_seconds": 1.1,
        "card_animation": "number_pop",
        "gradient": True,
        "number_special_last": True,
        "last_card_seconds": 1.6,
        "rank_label": "none",
    },
    "creator_signal": {
        "weight_bonus": [],
        "notes": [],
        "typical_music": [],               # creator's usual music style
        "common_topics": [],               # recurring themes for connection scoring
    },
    "sequence_trend": {
        "require_escalation": True,        # #5->#1 must escalate
        "topic_threads": True,             # prefer thematic connections
        "reaction_escalation": True,       # reaction intensity should increase
        "context_bridges": True,           # look for contextual links
        "max_gap_between": 2.0,            # max dead air between moments
    },
}

def _path():
    os.makedirs(RESEARCH, exist_ok=True)
    return os.path.join(RESEARCH, "builder.json")

def record_findings(findings: dict, extra_notes: list[str] = None) -> dict:
    """Merge live research notes into the current builder."""
    builder = load(raw=True)
    if "creator_name" in findings:
        builder["creator_name"] = findings["creator_name"]
    for k in ("caption_trend", "edit_trend", "music_trend", "countdown_trend", 
              "sequence_trend"):
        if k in findings and isinstance(findings[k], dict):
            builder[k].update(findings[k])
    if "creator_signal" in findings and isinstance(findings["creator_signal"], dict):
        builder["creator_signal"] = findings["creator_signal"]
    if extra_notes:
        builder.setdefault("creator_signal", {}).setdefault("notes", []).extend(extra_notes)
    builder["window_time"] = findings.get("window_time", builder.get("window_time"))
    os.makedirs(RESEARCH, exist_ok=True)
    with open(_path(), "w", encoding="utf-8") as f:
        json.dump(builder, f, indent=1)
    return builder

def load(raw=False):
    if os.path.exists(_path()):
        with open(_path(), "r", encoding="utf-8") as f:
            builder = json.load(f)
    else:
        builder = {}
    # deep-merge defaults so new research sections are always present
    merged = json.loads(json.dumps(DEFAULTS))
    merged.update(builder)
    for k, v in builder.items():
        if isinstance(v, dict) and isinstance(DEFAULTS.get(k), dict):
            merged[k] = {**DEFAULTS[k], **v}
    merged["window_time"] = builder.get("window_time", merged.get("window_time"))
    return merged

def report_markdown():
    """Render the research profile as a readable report."""
    b = load()
    creator = b.get("creator_name") or b.get("creator_signal", {}).get("name") or "IShowSpeed"
    lines = [
        f"# AutoClip Research Dossier: {creator}",
        "",
        f"**Analysis Window**: {b['window_time']} | **Viral Calibration**: Active",
        "",
        "## 1. Caption & Subtitle Trend",
        f"- **Style**: {b['caption_trend']['style']} ({b['caption_trend']['pos']})",
        f"- **Font & Size**: {b['caption_trend']['font']}, {b['caption_trend']['size']}pt",
        f"- **Animation**: {b['caption_trend']['animation']}",
        f"- **Highlight**: {b['caption_trend']['highlight_style']} with emphasis color `{b['caption_trend']['emphasis_color']}`",
        "",
        "## 2. Edit & Cut Pacing",
        f"- **Silence Trim Threshold**: {b['edit_trend']['max_silence_before_cut']}s (fast cut rate)",
        f"- **Ideal Runtime**: {b['edit_trend']['runtime_ideal'][0]} - {b['edit_trend']['runtime_ideal'][1]}s",
        f"- **SFX**: {', '.join(b['edit_trend'].get('sfx', ['whoosh', 'boom']))}",
        f"- **Transition**: {b['edit_trend']['transition_style']}",
        f"- **Pacing Style**: {b['edit_trend']['pacing']}",
        "",
        "## 3. Background Music & Sound Design",
        f"- **Enabled**: {b['music_trend']['enabled']}",
        f"- **Style**: {b['music_trend']['style']}",
        f"- **Dialogue Ducking**: {b['music_trend']['volume_duck_db']}dB",
        f"- **Copyright Safe**: {b['music_trend']['copyright_safe']}",
        "",
        f"## 4. Viral Retention Signals for {creator}",
    ]
    notes = b.get("creator_signal", {}).get("notes", []) or b.get("creator_signal", {}).get("insights", [])
    for note in notes:
        lines.append(f"- {note}")
    if b.get("creator_signal", {}).get("typical_music"):
        lines.append(f"- **Typical BGM Vibe**: {', '.join(b['creator_signal']['typical_music'])}")
    if b.get("creator_signal", {}).get("common_topics"):
        lines.append(f"- **Core Topics**: {', '.join(b['creator_signal']['common_topics'])}")
    return "\n".join(lines) + "\n"

def save_report():
    path = os.path.join(RESEARCH, "research_report.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report_markdown())
    return path

def ai_research(creator: str, topic: str = None, format_kind: str = None):
    """Use the cascading LLM models to perform trend, style, and creator research."""
    from . import llm as llm_mod
    system = ("You are an elite YouTube Shorts research analyst and viral video strategist. "
              "You analyze creators, audience retention, comedic timing, pacing, caption styling, "
              "and background music trends. You ALWAYS reply with JSON matching exactly the given schema.")
    anim_choices = ", ".join(config.CaptionAnimation.valid_styles())
    user = (f"Creator: {creator}\n"
            f"Topic hint: {topic or 'viral comedy / skit / highlight'}\n"
            f"Format: {format_kind or 'moment'}\n\n"
            "Analyze this creator's viral Short profile. Determine:\n"
            f"1. caption_trend: font, size (80-100), pos, emphasis_color (hex e.g. #FFD200), "
            f"animation ({anim_choices}), highlight_style\n"
            "2. edit_trend: max_silence_before_cut (0.3-0.6), hook_seconds (1.5-3.0), "
            "pacing ('energetic'), transition_style ('hard_cut')\n"
            "3. music_trend: style ('lofi_hiphop', 'bouncy_hiphop', 'phonk', 'comedic'), "
            "volume_duck_db (-18 to -12), copyright_safe (true)\n"
            "4. creator_signal: 2-4 insightful bullet notes on what makes their clips hit, "
            "typical_music genres, and common_topics list.\n"
            "Return valid JSON matching the schema.")
    schema = {
        "caption_trend": {"style": "str", "font": "str", "size": "int", "pos": "str",
                          "emphasis_color": "str", "animation": "str", "highlight_style": "str"},
        "edit_trend": {"max_silence_before_cut": "float", "hook_seconds": "float",
                       "pacing": "str", "transition_style": "str"},
        "music_trend": {"style": "str", "volume_duck_db": "int", "copyright_safe": "bool"},
        "creator_signal": {"notes": "str[]", "typical_music": "str[]", "common_topics": "str[]"},
    }
    print(f"[AutoClip Research] Conducting AI research on '{creator}'...", flush=True)
    parsed = llm_mod.chat(system, user, schema=schema)
    findings = {
        "creator_name": creator,
        "window_time": datetime.date.today().isoformat(),
        "caption_trend": parsed.get("caption_trend", {}),
        "edit_trend": parsed.get("edit_trend", {}),
        "music_trend": parsed.get("music_trend", {}),
        "creator_signal": parsed.get("creator_signal", {}),
    }
    record_findings(findings)
    rep_path = save_report()
    print(f"[AutoClip Research] Saved to {_path()} and {rep_path}", flush=True)
    return findings