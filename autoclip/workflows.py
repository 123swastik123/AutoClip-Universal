"""Modular Workflow Engine for AutoClip Universal.

Enables seamless switching between different editing styles, niches, and output formats:
- Top N Countdown Montage (dynamic leaderboard, spring pop, SFX transitions)
- Viral Highlights & Punchlines (fast face tracking, kinetic captions)
- Podcast / Dual-Speaker Split (top/bottom multi-speaker layout)
- Commentary / Educational Explainer (topic callouts, kinetic word highlight)
- Universal Auto-Adaptive (analyzes audio/dialogue to select treatment)
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

WORKFLOWS_FILE = Path(__file__).resolve().parent.parent / "workflows.json"

DEFAULT_WORKFLOWS = {
    "active_workflow": "universal_auto",
    "workflows": {
        "universal_auto": {
            "id": "universal_auto",
            "name": "Universal Auto-Adaptive",
            "description": "Adaptive engine that analyzes dialogue pace, facial presence, and audio energy.",
            "aspect_ratio": "9:16",
            "resolution": [1080, 1920],
            "layout": "smart_crop_center",
            "caption_style": "bold_pop_yellow",
            "subtitle_font": "Montserrat-ExtraBold",
            "subtitle_color": "&H0000E6FF",
            "sfx_enabled": True,
            "bgm_enabled": True,
            "bgm_track": "sneaky_snitch.mp3",
            "bgm_duck_db": -20,
            "max_duration": 60,
            "target_niche": "General / Universal"
        },
        "countdown_montage": {
            "id": "countdown_montage",
            "name": "Top N Countdown Montage",
            "description": "Ranked 5-to-1 countdown with dynamic animated leaderboard ASS overlay and SFX.",
            "aspect_ratio": "9:16",
            "resolution": [1080, 1920],
            "layout": "dynamic_leaderboard",
            "header_text": "TOP %N% MOMENTS",
            "header_font": "Impact",
            "caption_style": "minimal_or_none",
            "sfx_enabled": True,
            "sfx_pack": ["whoosh.wav", "buzzer.wav", "error.wav", "alert.wav", "vine_boom.wav"],
            "bgm_enabled": True,
            "bgm_track": "sneaky_snitch.mp3",
            "bgm_duck_db": -20,
            "max_duration": 60,
            "target_niche": "Rankings & Compilations"
        },
        "smart_highlights": {
            "id": "smart_highlights",
            "name": "Viral Highlights & Punchlines",
            "description": "High-retention punchline highlights with smart face-tracking reframe.",
            "aspect_ratio": "9:16",
            "resolution": [1080, 1920],
            "layout": "smart_crop_center",
            "caption_style": "bold_pop_yellow",
            "subtitle_font": "Montserrat-ExtraBold",
            "subtitle_color": "&H0000E6FF",
            "sfx_enabled": True,
            "bgm_enabled": False,
            "max_duration": 50,
            "target_niche": "Highlights & Reactions"
        },
        "podcast_split": {
            "id": "podcast_split",
            "name": "Podcast / Dual-Speaker Split",
            "description": "Split-screen vertical format with boxed subtitles and ambient lo-fi music.",
            "aspect_ratio": "9:16",
            "resolution": [1080, 1920],
            "layout": "split_screen_vertical",
            "caption_style": "boxed_clean_white",
            "subtitle_font": "Montserrat-Bold",
            "subtitle_color": "&H00FFFFFF",
            "sfx_enabled": False,
            "bgm_enabled": False,
            "max_duration": 60,
            "target_niche": "Podcasts & Interviews"
        },
        "commentary_explainer": {
            "id": "commentary_explainer",
            "name": "Educational / Commentary Explainer",
            "description": "Framed presenter layout with kinetic word-by-word highlights.",
            "aspect_ratio": "9:16",
            "resolution": [1080, 1920],
            "layout": "explainer_card",
            "caption_style": "kinetic_word_by_word",
            "subtitle_font": "Montserrat-ExtraBold",
            "subtitle_color": "&H0000FFFF",
            "sfx_enabled": False,
            "bgm_enabled": True,
            "bgm_track": "monkeys_spinning.mp3",
            "bgm_duck_db": -24,
            "max_duration": 60,
            "target_niche": "Educational & Commentary"
        }
    }
}


def load_workflows() -> Dict[str, Any]:
    """Load workflows from disk or return default template."""
    if WORKFLOWS_FILE.exists():
        try:
            with open(WORKFLOWS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WorkflowManager] Error reading workflows.json: {e}")
    return DEFAULT_WORKFLOWS.copy()


def save_workflows(data: Dict[str, Any]) -> None:
    """Save workflows back to workflows.json."""
    try:
        with open(WORKFLOWS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[WorkflowManager] Failed to write workflows.json: {e}")


def get_active_workflow() -> Dict[str, Any]:
    """Return configuration dict for the currently selected active workflow."""
    data = load_workflows()
    active_id = os.environ.get("DEFAULT_WORKFLOW", data.get("active_workflow", "universal_auto"))
    workflows = data.get("workflows", {})
    return workflows.get(active_id, workflows.get("universal_auto", list(workflows.values())[0]))


def set_active_workflow(workflow_id: str) -> bool:
    """Switch active workflow to workflow_id."""
    data = load_workflows()
    if workflow_id in data.get("workflows", {}):
        data["active_workflow"] = workflow_id
        save_workflows(data)
        return True
    return False


def list_workflows() -> List[Dict[str, Any]]:
    """List all registered workflow presets."""
    data = load_workflows()
    active_id = data.get("active_workflow", "universal_auto")
    result = []
    for wid, wcfg in data.get("workflows", {}).items():
        w_copy = dict(wcfg)
        w_copy["is_active"] = (wid == active_id)
        result.append(w_copy)
    return result


def register_workflow(workflow_id: str, config_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add or update a custom workflow preset."""
    data = load_workflows()
    config_dict["id"] = workflow_id
    data.setdefault("workflows", {})[workflow_id] = config_dict
    save_workflows(data)
    return config_dict
