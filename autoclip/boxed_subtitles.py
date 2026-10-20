"""
AutoClip Boxed Keyword Subtitles & High-Res PNG Emoji Overlay Engine
Renders modern Hormozi / MrBeast style highlight boxes around key punchlines,
with crisp transparent PNG emoji overlays (zero broken font glyphs).
"""

import os
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(r"C:\Users\swastik\Desktop\AutoClip")
EMOJI_DIR = BASE_DIR / "data" / "emojis"


class BoxedSubtitleEngine:
    """Renders dynamic colored highlight boxes and crisp PNG emojis on subtitle frames."""

    BOX_STYLES = {
        "fire_red": {
            "fill": (220, 20, 25, 255),
            "outline": (255, 255, 255, 255),
            "text": (255, 255, 255, 255),
            "emoji": "skull.png"
        },
        "mint_green": {
            "fill": (30, 200, 60, 255),
            "outline": (255, 215, 0, 255),
            "text": (255, 255, 255, 255),
            "emoji": "medal1.png"
        },
        "ice_cyan": {
            "fill": (0, 160, 220, 255),
            "outline": (255, 255, 255, 255),
            "text": (255, 255, 255, 255),
            "emoji": "scream.png"
        },
        "obsidian_gold": {
            "fill": (15, 15, 20, 245),
            "outline": (255, 215, 0, 255),
            "text": (255, 230, 0, 255),
            "emoji": "sob.png"
        }
    }

    @classmethod
    def render_boxed_phrase(cls, text: str, highlight_phrase: str, style_name: str = "fire_red", emoji_name: str = None) -> Image.Image:
        """
        Creates a transparent 1080x1920 overlay image with the text phrase,
        a colored rounded box behind the highlighted keyword, and a crisp PNG emoji next to it.
        """
        overlay = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        style = cls.BOX_STYLES.get(style_name, cls.BOX_STYLES["fire_red"])

        try:
            font = ImageFont.truetype("impact.ttf", 64)
            font_box = ImageFont.truetype("impact.ttf", 64)
        except Exception:
            font = ImageFont.load_default()
            font_box = ImageFont.load_default()

        # Center Y for subtitle capsule (y: 585)
        cy = 585

        clean_text = text.upper()
        clean_hl = highlight_phrase.upper() if highlight_phrase else ""

        # Measure dimensions
        bbox_full = draw.textbbox((0, 0), clean_text, font=font)
        total_w = bbox_full[2] - bbox_full[0]
        start_x = (1080 - total_w) // 2

        # Draw highlight box if keyword is present
        if clean_hl and clean_hl in clean_text:
            parts = clean_text.split(clean_hl)
            prefix_w = draw.textbbox((0, 0), parts[0], font=font)[2] - draw.textbbox((0, 0), parts[0], font=font)[0] if parts[0] else 0
            hl_w = draw.textbbox((0, 0), clean_hl, font=font_box)[2] - draw.textbbox((0, 0), clean_hl, font=font_box)[0]
            hl_h = draw.textbbox((0, 0), clean_hl, font=font_box)[3] - draw.textbbox((0, 0), clean_hl, font=font_box)[1]

            bx0 = start_x + prefix_w - 14
            by0 = cy - (hl_h // 2) - 10
            bx1 = bx0 + hl_w + 28
            by1 = by0 + hl_h + 20

            # Draw colored rounded box pill behind highlighted keyword
            draw.rounded_rectangle(
                [bx0, by0, bx1, by1],
                radius=18,
                fill=style["fill"],
                outline=style["outline"],
                width=3
            )

            # Draw PNG emoji next to the box if available
            target_emoji = emoji_name or style["emoji"]
            emoji_path = EMOJI_DIR / target_emoji
            if emoji_path.exists():
                emoji_img = Image.open(emoji_path).convert("RGBA").resize((60, 60), Image.Resampling.LANCZOS)
                # Paste emoji right beside the badge
                ex = bx1 + 10
                ey = by0 - 4
                if ex + 60 < 1060:
                    overlay.paste(emoji_img, (ex, ey), emoji_img)

        # Draw full text with clean drop shadow
        draw.text((start_x + 3, cy - 30 + 3), clean_text, font=font, fill=(0, 0, 0, 220))
        draw.text((start_x, cy - 30), clean_text, font=font, fill=(255, 255, 255, 255))

        return overlay
