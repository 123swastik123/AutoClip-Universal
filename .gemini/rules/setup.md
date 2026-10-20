# AutoClip Universal Agent Instructions

## Welcome & First-Run Setup
When the user opens this workspace or asks to set up, configure, or run AutoClip, proactively offer to run the interactive setup interview:
1. Ask the user for their target niche, Discord Bot Token, and YouTube channel details using `ask_question`.
2. Configure `.env` from their responses.
3. Validate that `ffmpeg` and Python dependencies from `requirements.txt` are installed.
4. Assist the user in executing whatever workflow they need (Top N countdowns, podcast splitting, highlight clipping, or Discord bot integration).
