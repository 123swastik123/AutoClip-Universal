"""
AutoClip SFX Director & Sound Department Bridge
-----------------------------------------------
Routes all audio planning and SFX retrieval through the autonomous Sound Department
(autoclip.sound_manager.SoundDepartment) to guarantee:
- Clean internet-sourced sound effects
- Millisecond-accurate transient attacks
- Strict "Silence is funnier" anti-spam limits
- Dynamic dialogue protection
"""

from pathlib import Path
from typing import List, Dict, Optional
from autoclip.sound_manager import SoundDepartment, SFX_DIR, PROCESSED_SFX_DIR


def get_sfx_path(name: str) -> str:
    """Return absolute path to transient-trimmed authentic SFX file."""
    path = SoundDepartment.fetch_or_generate_sfx(name)
    return str(path) if path.exists() else ""


def plan_sfx_for_clip(
    clip_words: List[Dict],
    video_info: Dict,
    creator: str = "caseoh",
    dur: float = 55.0,
    hint_sfx: Optional[str] = None
) -> List[Dict]:
    """Contextually analyze dialogue flow and scene vibe to schedule SFX via SoundDepartment."""
    cues = SoundDepartment.plan_sfx_composition(
        clip_words=clip_words,
        video_info=video_info,
        creator=creator,
        duration_sec=dur
    )
    if hint_sfx and not cues and clip_words:
        # If explicitly requested single hint SFX
        half_words = clip_words[len(clip_words)//2:]
        peak_w = max(half_words, key=lambda w: w.get("energy", 0.5), default=None)
        if peak_w:
            t_hit = round(peak_w.get("start", 0) - clip_words[0].get("start", 0), 2)
            cues.append({
                "time": t_hit,
                "sfx": str(hint_sfx).lower().strip(),
                "volume": 0.45,
                "reason": "AI directed climax impact"
            })
    return cues
