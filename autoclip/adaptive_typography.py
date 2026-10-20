"""
AutoClip Adaptive Color & Creative Typography Director
Maps phrase sentiment, energy, and creator tone to dynamic color palettes.
Zero forced yellow. Fully context-aware.
"""

import re
from typing import Tuple, Dict, Any

class AdaptiveTypographyDirector:
    """Dynamically themes subtitles and graphic badges based on dialogue emotion."""

    # ASS Color Codes in BGR format (&H00BBGGRR&)
    PALETTES = {
        "cyan_neon":    "&H00FFFF00&",  # Shock, disbelief, cold facts, question (#00FFFF)
        "crimson_red":  "&H002020FF&",  # Rage, screaming, insults, fails, disgust (#FF2020)
        "mint_green":   "&H0030FF30&",  # Climax, win, #1 pick, perfection (#30FF30)
        "electric_gold":"&H0000D7FF&",  # Classic punchline, iconic quotes (#FFD700)
        "vivid_orange": "&H000080FF&",  # High energy, comedic emphasis (#FF8000)
        "purple_violet":"&H00FF40A0&",  # Weird, bizarre, absurd reactions (#A040FF)
        "pure_white":   "&H00FFFFFF&",  # Neutral baseline dialogue (#FFFFFF)
    }

    # Keyword emotion matching rules
    EMOTION_KEYWORDS = {
        "crimson_red": [
            "FELL OFF", "WORSE", "HATE", "DISGUSTING", "MID", "TRASH", "TERRIBLE",
            "BANNED", "SHUT UP", "GET OUT", "RAGE", "STOP", "NO WAY", "BOILED EGG",
            "NAH", "HORRIBLE", "AWFUL", "WHAT ARE YOU DOING", "DEAD", "ROAST"
        ],
        "mint_green": [
            "NUMBER ONE", "SOLID NUMBER ONE", "BEST", "GOAT", "AMAZING", "WIN",
            "PERFECT", "CLUTCH", "LOVE", "W", "TOP TIER", "ELITE", "UNREAL"
        ],
        "cyan_neon": [
            "WHAT", "WHO", "WHY", "HOW", "BRO", "WAIT", "SERIOUSLY", "EDITED",
            "EXCUSE ME", "LOOK AT", "HOLD ON", "CONFUSED", "ARE YOU KIDDING"
        ],
        "vivid_orange": [
            "OH MY GOODNESS", "CRAZY", "INSANE", "WILD", "DONETTES", "TWINKIES",
            "SNOBALLS", "DING DONG", "HOSTESS", "TACOS", "BURGER"
        ],
        "purple_violet": [
            "WEIRD", "ODD", "STRANGE", "TEXTURE", "GRANNY", "ALIEN", "SUS"
        ]
    }

    @classmethod
    def detect_emotion_style(cls, text: str) -> Tuple[str, str]:
        """
        Analyzes phrase text and returns: (highlighted_word_or_phrase, ass_bgr_color)
        Avoids forced yellow. Defaults to high-contrast white with adaptive accent.
        """
        clean_text = text.upper()

        for palette_key, words in cls.EMOTION_KEYWORDS.items():
            for w in words:
                if re.search(rf"\b{re.escape(w)}\b", clean_text):
                    return w, cls.PALETTES[palette_key]

        # If no explicit emotion keyword, pick the most impactful word (longest noun/verb)
        tokens = [t for t in re.findall(r"\b[A-Z]{4,}\b", clean_text) if t not in ["THAT", "THIS", "HAVE", "WITH", "THEY", "FROM", "JUST"]]
        if tokens:
            chosen = max(tokens, key=len)
            # Default to Cyan Neon or Vivid Orange (not yellow!)
            return chosen, cls.PALETTES["cyan_neon"]

        return "", cls.PALETTES["pure_white"]

    @classmethod
    def get_badge_theme(cls, creator: str, category: str = "food") -> Dict[str, Any]:
        """Provides custom color themes for the top hook badge."""
        c = creator.lower()
        if "speed" in c:
            # Energetic Crimson Red badge with White text and Gold border
            return {
                "pill_fill": (180, 15, 25, 255),
                "pill_outline": (255, 215, 0, 255),
                "text_color": (255, 255, 255, 255)
            }
        elif "jynx" in c:
            # Neon Cyan Cyberpunk theme
            return {
                "pill_fill": (10, 20, 35, 255),
                "pill_outline": (0, 240, 255, 255),
                "text_color": (0, 240, 255, 255)
            }
        else:
            # CaseOh / Entertainment: Deep Obsidian with Electric Gold border & White/Cyan text
            return {
                "pill_fill": (14, 14, 18, 255),
                "pill_outline": (255, 215, 0, 255),
                "text_color": (255, 255, 255, 255)
            }
