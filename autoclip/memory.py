"""AutoClip Continuous Learning & Adaptive Memory Engine.

Learns day by day from:
1. Interactive buttons clicked in Discord (👍 Love Clip, 👎 Adjust Next Time, ✏️ Edit)
2. Direct conversational critiques & instructions ("first clip, this is very good", "next time do this in the next clips", "remove BGM")
3. Layout choices (Split-screen: Top gameplay / Bottom creator facecam)
4. Story duration bounds (40-50s) and caption pacing.

Persists all preferences permanently to data/pipeline_memory.json.
"""
import os, json, time, re
from . import config

MEMORY_FILE = os.path.join(config.DATA, "pipeline_memory.json")

DEFAULT_MEMORY = {
    "version": "2.0",
    "updated_at": 0,
    "global_preferences": {
        "layout_style": "split_two",
        "split_arrangement": "gameplay_top_face_bottom",
        "music_enabled": False,
        "min_duration": 40.0,
        "max_duration": 52.0,
        "subtitles": "single_word_pop",
        "facecam_zoom_crop": 0.34
    },
    "creator_preferences": {
        "jynxzi": {
            "format": "split_two",
            "split_arrangement": "gameplay_top_face_bottom",
            "pacing": "fast",
            "music_enabled": False,
            "subtitles": "single_word_pop",
            "hook_style": "reaction_shout",
            "min_duration": 40.0,
            "max_duration": 52.0
        },
        "kai": {
            "format": "dynamic_speaker_track",
            "pacing": "rapid_cut",
            "music_enabled": False,
            "subtitles": "single_word_pop",
            "hook_style": "dialogue_climax",
            "min_duration": 40.0,
            "max_duration": 52.0
        },
        "mrbeast": {
            "format": "blur_fill",
            "pacing": "ultra_fast_story",
            "music_enabled": False,
            "subtitles": "single_word_pop",
            "hook_style": "stakes_question",
            "min_duration": 40.0,
            "max_duration": 52.0
        }
    },
    "history": [],
    "learned_rules": [],
    "feedback_log": [],
    "learned_keywords": {
        "hooks": ["WAIT FOR THIS", "BRO CANNOT BE REAL", "NO WAY", "WATCH TILL THE END", "HE REALLY SAID THIS"],
        "punch_tokens": ["WHAT", "WHY", "BRO", "NO", "WAIT", "OMG", "LOOK", "DEAD", "COOKED"]
    }
}

def load_memory():
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
    if not os.path.exists(MEMORY_FILE):
        save_memory(DEFAULT_MEMORY)
        return json.loads(json.dumps(DEFAULT_MEMORY))
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for k, v in DEFAULT_MEMORY.items():
                if k not in data:
                    data[k] = v
            if "global_preferences" not in data:
                data["global_preferences"] = DEFAULT_MEMORY["global_preferences"]
            if "learned_rules" not in data:
                data["learned_rules"] = []
            if "feedback_log" not in data:
                data["feedback_log"] = []
            return data
    except Exception:
        return json.loads(json.dumps(DEFAULT_MEMORY))

def save_memory(mem):
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
    mem["updated_at"] = time.time()
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(mem, f, indent=2)

def record_feedback(clip_info, feedback_type, user_text=""):
    """Record user feedback (love, dislike, rule, adjustment) and update memory rules.
    
    Args:
        clip_info: dict containing clip metadata (rank, title, is_split_screen, creator, dur, etc.)
        feedback_type: 'positive' | 'negative' | 'rule' | 'edit'
        user_text: Optional comment or critique from the user.
    Returns:
        dict with action summary and applied rules.
    """
    mem = load_memory()
    text_lower = (user_text or "").lower()
    creator = (clip_info.get("creator") or clip_info.get("uploader") or "").lower()
    rank = clip_info.get("rank", 1)
    title = clip_info.get("title", "")

    learned_points = []

    # 1. Parse Duration Directives
    dur_match = re.search(r'(\d+)\s*(?:seconds|secs|second|s)\b', text_lower)
    if dur_match:
        dur_val = float(dur_match.group(1))
        mem["global_preferences"]["min_duration"] = max(30.0, dur_val - 5.0)
        mem["global_preferences"]["max_duration"] = min(60.0, dur_val + 5.0)
        learned_points.append(f"Story duration locked to ~{dur_val:.0f}s (range {mem['global_preferences']['min_duration']:.0f}-{mem['global_preferences']['max_duration']:.0f}s)")
    elif any(w in text_lower for w in ["longer", "complete the story", "proper ending", "full ending"]):
        mem["global_preferences"]["min_duration"] = 40.0
        mem["global_preferences"]["max_duration"] = 52.0
        learned_points.append("Story duration floor raised to 40-52s narrative complete")

    # 2. Parse Music / BGM Directives
    if any(w in text_lower for w in ["no bgm", "remove bgm", "no music", "remove music", "mute music", "zero music", "shit music", "cut bgm"]):
        mem["global_preferences"]["music_enabled"] = False
        learned_points.append("Background music permanently disabled (100% dialogue broadcast audio)")
    elif any(w in text_lower for w in ["add music", "enable music", "with bgm"]):
        mem["global_preferences"]["music_enabled"] = True
        learned_points.append("Background music enabled")

    # 3. Parse Split Screen & Layout Directives
    if any(w in text_lower for w in ["split screen", "split the screen", "two screen", "gameplay on top", "creator down"]):
        mem["global_preferences"]["layout_style"] = "split_two"
        mem["global_preferences"]["split_arrangement"] = "gameplay_top_face_bottom"
        learned_points.append("Layout set to Split Screen (Top: In-game action, Bottom: Zoomed Creator Facecam)")
    elif any(w in text_lower for w in ["single screen", "full frame", "no split", "disable split"]):
        mem["global_preferences"]["layout_style"] = "single_track"
        learned_points.append("Layout set to Single 9:16 Reframe")

    # 4. Parse Subtitle / Caption Directives
    if any(w in text_lower for w in ["caption", "subtitle", "word at a time", "single caption", "single word"]):
        mem["global_preferences"]["subtitles"] = "single_word_pop"
        learned_points.append("Captions locked to single-word pop karaoke animation")

    # If positive feedback: reinforce current clip configuration
    if feedback_type == "positive":
        clip_format = "split_two" if clip_info.get("is_split_screen") else mem["global_preferences"].get("layout_style", "split_two")
        mem["global_preferences"]["layout_style"] = clip_format
        for known in mem["creator_preferences"]:
            if known in creator or known in title.lower():
                mem["creator_preferences"][known]["format"] = clip_format
                mem["creator_preferences"][known]["music_enabled"] = False
                mem["creator_preferences"][known]["last_used"] = time.time()
        if not learned_points:
            learned_points.append(f"Affinity locked: Favored #{rank} style ({clip_format}, 0 BGM, 40-50s story arc)")

    # Record log entry
    log_entry = {
        "timestamp": time.time(),
        "type": feedback_type,
        "rank": rank,
        "title": title,
        "user_text": user_text,
        "learned": learned_points
    }
    mem["feedback_log"].append(log_entry)
    mem["feedback_log"] = mem["feedback_log"][-100:]

    if user_text:
        mem["learned_rules"].append({
            "timestamp": time.time(),
            "rule": user_text,
            "actions": learned_points
        })
        mem["learned_rules"] = mem["learned_rules"][-50:]

    save_memory(mem)
    print(f"[AutoClip Memory] Feedback recorded ({feedback_type}): {learned_points}")
    return {
        "ok": True,
        "type": feedback_type,
        "learned_points": learned_points,
        "global_preferences": mem["global_preferences"]
    }

def record_session(video_id, title, creator, chosen_clips, format_mode="split_two"):
    """Learn from a completed pipeline run."""
    mem = load_memory()
    entry = {
        "timestamp": time.time(),
        "video_id": video_id,
        "title": title,
        "creator": creator,
        "format_mode": format_mode,
        "clip_count": len(chosen_clips),
        "clips": [
            {
                "t0": c.get("t0"),
                "t1": c.get("t1"),
                "dur": c.get("dur"),
                "title": c.get("title"),
                "punch_word": c.get("punch_word")
            }
            for c in chosen_clips
        ]
    }
    mem["history"].append(entry)
    mem["history"] = mem["history"][-50:]

    # Update creator profile
    c_lower = creator.lower()
    for known in mem["creator_preferences"]:
        if known in c_lower or known in title.lower():
            mem["creator_preferences"][known]["last_used"] = time.time()
            mem["creator_preferences"][known]["format"] = format_mode

    # Learn new punch tokens
    for c in chosen_clips:
        pw = c.get("punch_word")
        if pw and len(pw) >= 3 and pw.upper() not in mem["learned_keywords"]["punch_tokens"]:
            mem["learned_keywords"]["punch_tokens"].append(pw.upper())

    save_memory(mem)

def get_active_preferences(creator_hint="", title_hint=""):
    """Retrieve active pipeline parameters dynamically adapted from memory."""
    mem = load_memory()
    hint = f"{creator_hint} {title_hint}".lower()
    global_p = mem.get("global_preferences", DEFAULT_MEMORY["global_preferences"])

    # Creator override if known
    creator_p = {}
    for key, pref in mem.get("creator_preferences", {}).items():
        if key in hint:
            creator_p = pref
            break

    merged = dict(global_p)
    merged.update(creator_p)
    return merged

def get_format_preset(creator_hint, title_hint=""):
    """Backwards compatible layout resolver."""
    return get_active_preferences(creator_hint, title_hint)
