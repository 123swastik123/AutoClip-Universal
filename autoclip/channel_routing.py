"""Channel Routing & Multi-Brand YouTube Registry for AutoClip.

Strict 1-to-1 Creator-to-Channel Mapping:
1. IShowSpeed    -> Channel 1 (Speed Clips Daily) -> UC5c8tsR8aVidDIfFH89pyIg (youtube_rigid-easing)
2. CaseOh        -> Channel 2 (CaseOh Clips)      -> UCelQ7wkvHyI9j0Ab3ISMqEQ (youtube_bout-unfine)
3. Jynxzi        -> Channel 3 (Jynxzi Clips)      -> UCBaLUH8LwQQ2KMkxq7wNfCA (youtube_teredo-jolly)
4. AI/Technology -> Channel 4 (TechPulse Daily)   -> UCVrh_-HaHkEF8tEnYGJsW5A (youtube_begin-manner)
"""

import os
from typing import Dict, Any, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BRANDING_DIR = os.path.join(PROJECT_ROOT, "data", "branding")

CHANNELS: Dict[str, Dict[str, Any]] = {
    "speed": {
        "channel_number": 1,
        "niche": "IShowSpeed Clips",
        "current_name": "Tanvo",
        "target_name": "Speed Clips Daily",
        "alternative_name": "Speed Moments",
        "handle": "@tanvoiamhere",
        "recommended_handle": "@SpeedClipsDailyOfficial",
        "channel_id": "UCVrh_-HaHkEF8tEnYGJsW5A",
        "composio_account_id": "youtube_begin-manner",
        "is_fan_channel": True,
        "visual_style": {
            "theme": "Extremely energetic, Gaming/IRL aesthetic",
            "palette": ["#FF0033", "#000000", "#FFFFFF"],
            "icon_concept": "Circular esports badge with lightning emblem and bold white/red typography",
            "banner_concept": "Dark carbon theme with glowing red lightning and safe-zone centered typography"
        },
        "assets": {
            "avatar": os.path.join(BRANDING_DIR, "channel_1_speed_avatar.jpg"),
            "banner": os.path.join(BRANDING_DIR, "channel_1_speed_banner.jpg")
        },
        "description": (
            "Welcome to Speed Clips Daily — your #1 fan-curated hub for the wildest, funniest, "
            "and most high-energy IShowSpeed moments, streams, and viral reactions!\n\n"
            "⚡ Daily edited Shorts & stream highlights\n"
            "🎮 Gaming rages, IRL tours, football challenges & fan encounters\n"
            "🔔 Subscribe with notifications on for daily uploads!\n\n"
            "⚠️ Disclaimer: This is an unofficial, community-operated fan and clip channel dedicated "
            "to celebrating IShowSpeed's content. All rights belong to IShowSpeed. We publish transformative "
            "fan edits and commentary Shorts."
        ),
        "about_text": (
            "Speed Clips Daily is an unofficial fan channel bringing you the best edited stream highlights, "
            "reactions, and moments from IShowSpeed's daily broadcasts."
        ),
        "keywords": [
            "ishowspeed", "speed clips", "speed shorts", "ishowspeed clips", "speed moments",
            "speed funny moments", "speed reactions", "speed rage", "speed gaming", "speed irl",
            "streamer clips", "viral streamer clips", "youtube shorts", "shorts"
        ]
    },

    "caseoh": {
        "channel_number": 2,
        "niche": "CaseOh Clips",
        "current_name": "Cognita",
        "target_name": "Queso Clips",
        "alternative_name": "Keso Clips",
        "handle": "@fixlife-q7g",
        "recommended_handle": "@QuesoClipsOfficial",
        "channel_id": "UCelQ7wkvHyI9j0Ab3ISMqEQ",
        "composio_account_id": "youtube_bout-unfine",
        "is_fan_channel": True,
        "visual_style": {
            "theme": "Funny but premium, Streamer/Gaming aesthetic",
            "palette": ["#F59E0B", "#18181B", "#FFFFFF"],
            "icon_concept": "Dark charcoal and gold/orange emblem with crown controller motif",
            "banner_concept": "Sleek streamer studio background with bold gold 3D lettering"
        },
        "assets": {
            "avatar": os.path.join(BRANDING_DIR, "channel_2_caseoh_avatar.jpg"),
            "banner": os.path.join(BRANDING_DIR, "channel_2_caseoh_banner.jpg")
        },
        "description": (
            "Welcome to CaseOh Clips — the ultimate fan destination for the funniest scream reactions, "
            "horror game jumpscares, and top stream highlights from CaseOh!\n\n"
            "🎮 Horror games, 60 Seconds, simulator freakouts & stream rages\n"
            "🔥 Clean, high-cadence 9:16 Shorts with zero background clutter\n"
            "🔔 Hit subscribe to never miss a daily CaseOh moment!\n\n"
            "⚠️ Disclaimer: This is an unofficial, fan-curated clip channel. All original broadcast "
            "content belongs to CaseOh. Content presented here is edited and published under fair-use "
            "transformative fan highlights."
        ),
        "about_text": (
            "CaseOh Clips publishes daily fan-made edits, reactions, and funniest stream highlights "
            "from CaseOh's nightly gaming streams."
        ),
        "keywords": [
            "caseoh", "caseoh clips", "caseoh shorts", "caseoh moments", "caseoh funny moments",
            "caseoh reactions", "caseoh gaming", "caseoh rage", "caseoh stream", "streamer clips",
            "gaming clips", "viral clips", "youtube shorts", "shorts"
        ]
    },

    "jynxzi": {
        "channel_number": 3,
        "niche": "Jynxzi Clips",
        "current_name": "Ask What?",
        "target_name": "Jynxzi Clips",
        "alternative_name": "Jynxzi Moments",
        "handle": "@askwhatt",
        "recommended_handle": "@JynxziClipsHub",
        "channel_id": "UCBaLUH8LwQQ2KMkxq7wNfCA",
        "composio_account_id": "youtube_teredo-jolly",
        "is_fan_channel": True,
        "visual_style": {
            "theme": "Competitive, Tactical Gaming & High Energy",
            "palette": ["#DC2626", "#0F172A", "#FFFFFF"],
            "icon_concept": "Crosshair controller shield with crimson & white carbon fiber badge",
            "banner_concept": "Tactical operator aesthetic with neon red crossfire lighting"
        },
        "assets": {
            "avatar": os.path.join(BRANDING_DIR, "channel_3_jynxzi_avatar.jpg"),
            "banner": os.path.join(BRANDING_DIR, "channel_3_jynxzi_banner.jpg")
        },
        "description": (
            "Welcome to Jynxzi Clips — the premier fan channel for daily Jynxzi Rainbow Six Siege "
            "clutches, 1v1 tournaments, Guess the Rank, and hilarious IRL sanctuary moments!\n\n"
            "🎯 Siege gameplay, controller clutches, rank reactions & IRL vlogs\n"
            "💀 Frame-by-frame split-screen action with clean dialogue\n"
            "🔔 Subscribe for daily competitive and comedy Short highlights!\n\n"
            "⚠️ Disclaimer: This is an unofficial fan channel dedicated to curating and editing "
            "Jynxzi's stream highlights. All rights belong to Jynxzi. Published for transformative "
            "entertainment purposes."
        ),
        "about_text": (
            "Jynxzi Clips delivers edited daily Shorts, clutches, rages, and comedy moments from "
            "Jynxzi's Twitch streams and YouTube videos."
        ),
        "keywords": [
            "jynxzi", "jynxzi clips", "jynxzi shorts", "jynxzi moments", "jynxzi funny moments",
            "jynxzi rage", "jynxzi gaming", "jynxzi rainbow six", "jynxzi reactions",
            "streamer clips", "gaming shorts", "viral gaming clips", "youtube shorts", "shorts"
        ]
    },

    "backup": {
        "channel_number": 4,
        "niche": "Backup / Parked Channel",
        "current_name": "StudyHustle",
        "target_name": "StudyHustle (Backup)",
        "alternative_name": "Backup Hub",
        "handle": "@studyhustle-xo8tp",
        "recommended_handle": "@StudyHustleBackup",
        "channel_id": "UCuqqFCp0ft6ICxupcHu_PtQ",
        "composio_account_id": "youtube_flower-earwig",
        "is_fan_channel": False,
        "is_active": False,
        "visual_style": {
            "theme": "Parked / Backup Channel",
            "palette": ["#4B5563", "#1F2937", "#FFFFFF"],
            "icon_concept": "Standby backup channel icon",
            "banner_concept": "Standby banner"
        },
        "assets": {},
        "description": "Backup channel for AutoClip automation system.",
        "about_text": "Parked backup channel.",
        "keywords": ["shorts", "backup"]
    }
}


def get_route(creator_or_niche: Optional[str]) -> Dict[str, Any]:
    """Strictly resolve the designated target YouTube channel for a creator or custom niche.
    
    Checks environment overrides first, then registered presets, then generates a dynamic route.
    """
    env_cid = os.environ.get("YOUTUBE_CHANNEL_ID")
    env_acc = os.environ.get("COMPOSIO_ACCOUNT_ID", "default_youtube_account")
    env_cname = os.environ.get("YOUTUBE_CHANNEL_NAME", "Target Channel")

    if not creator_or_niche:
        if env_cid:
            return {
                "channel_number": 99,
                "niche": os.environ.get("TARGET_NICHE", "Custom Content"),
                "current_name": env_cname,
                "target_name": env_cname,
                "handle": f"@{env_cname.replace(' ', '')}",
                "channel_id": env_cid,
                "composio_account_id": env_acc,
                "is_fan_channel": False
            }
        return CHANNELS.get("backup", list(CHANNELS.values())[0])

    norm = str(creator_or_niche).strip().lower().replace(" ", "").replace("_", "").replace("-", "")

    # 1. IShowSpeed -> Channel 1 (Tanvo / Speed Clips Daily, youtube_begin-manner)
    if any(k in norm for k in ["ishowspeed", "speed", "tanvo"]):
        return CHANNELS["speed"]

    # 2. CaseOh -> Channel 2 (Cognita / CaseOh Clips, youtube_bout-unfine)
    if any(k in norm for k in ["caseoh", "case"]):
        return CHANNELS["caseoh"]

    # 3. Jynxzi -> Channel 3 (Ask What? / Jynxzi Clips, youtube_teredo-jolly)
    if any(k in norm for k in ["jynxzi", "jinxie", "jynx", "junko", "askwhat"]):
        return CHANNELS["jynxzi"]

    # 4. Backup -> StudyHustle (youtube_flower-earwig)
    if any(k in norm for k in ["backup", "studyhustle"]):
        return CHANNELS["backup"]

    # 5. Dynamic User Channel (Configured in .env or custom channel)
    return {
        "channel_number": 100,
        "niche": str(creator_or_niche).title(),
        "current_name": env_cname if env_cid else str(creator_or_niche).title(),
        "target_name": env_cname if env_cid else str(creator_or_niche).title(),
        "handle": f"@{str(creator_or_niche).replace(' ', '')}",
        "channel_id": env_cid or f"custom_{norm}",
        "composio_account_id": env_acc,
        "is_fan_channel": False
    }


def get_all_channel_routes() -> Dict[str, Dict[str, Any]]:
    """Return all channel routing mappings."""
    return CHANNELS


def verify_routing_integrity() -> bool:
    """Run an automated self-check to confirm zero overlap and 100% routing uniqueness."""
    c_ids = set()
    acc_ids = set()

    test_cases = [
        ("IShowSpeed", "speed", "UCVrh_-HaHkEF8tEnYGJsW5A", "youtube_begin-manner"),
        ("CaseOh", "caseoh", "UCelQ7wkvHyI9j0Ab3ISMqEQ", "youtube_bout-unfine"),
        ("Jynxzi", "jynxzi", "UCBaLUH8LwQQ2KMkxq7wNfCA", "youtube_teredo-jolly"),
        ("Backup", "backup", "UCuqqFCp0ft6ICxupcHu_PtQ", "youtube_flower-earwig")
    ]

    for label, key, expected_cid, expected_acc in test_cases:
        route = get_route(label)
        assert route["channel_id"] == expected_cid, f"Mismatch on {label} channel_id: {route['channel_id']} != {expected_cid}"
        assert route["composio_account_id"] == expected_acc, f"Mismatch on {label} account_id: {route['composio_account_id']} != {expected_acc}"
        c_ids.add(route["channel_id"])
        acc_ids.add(route["composio_account_id"])

    # Strict check: Never use Shivkumar Pappas account
    assert "youtube_rigid-easing" not in acc_ids, "CRITICAL: Shivkumar Pappas account must never be used!"
    assert "UC5c8tsR8aVidDIfFH89pyIg" not in c_ids, "CRITICAL: Shivkumar channel ID must never be used!"

    assert len(c_ids) == 4, "Channel IDs must be 4 distinct channels!"
    assert len(acc_ids) == 4, "Composio account IDs must be 4 distinct accounts!"
    return True
