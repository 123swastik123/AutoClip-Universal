---
name: autoclip-setup
description: Interactive onboarding workflow for configuring AutoClip Universal on a new machine.
---

# AutoClip Universal Onboarding Interview Protocol

When the user opens this workspace or asks to set up, configure, or run AutoClip, execute this interactive setup protocol using the `ask_question` tool.

## Objective
Guide the user through configuring their personal video clipping pipeline:
1. Connect their Discord Bot (token, server guild ID)
2. Define their target YouTube channel and niche (e.g. Podcasts, Tech, Gaming, Compilations, Commentary)
3. Select their default editing workflow preset
4. Verify ffmpeg and local dependencies
5. Generate the configured `.env` file

---

## Step 1: Niche & Content Category Interview
Use `ask_question` to ask:
"What type of content and niche will you be clipping with AutoClip?"
Options:
- (Recommended) Top N Countdown Montages (Ranked 5-to-1 compilations with animated leaderboards & SFX)
- General / Multi-Purpose (Adaptive dialogue, facial tracking, and energy analysis)
- Podcasts & Long Interviews (Vertical split-screen layout with boxed subtitles)
- Gaming & Creator Highlights (High-energy punchlines, kinetic zooms, and pop subtitles)
- Educational & Commentary Explainers (Presenter framing with keyword badges)

## Step 2: Discord Bot Connection Interview
Use `ask_question` to ask:
"Do you want to enable the AutoClip Discord Bot to paste YouTube links in Discord and receive edited Shorts automatically?"
Options:
- (Recommended) Yes, I have a Discord Bot Token ready from the Discord Developer Portal
- Configure Discord later (I will run AutoClip via CLI for now)

If the user selects Yes:
Prompt for their `DISCORD_BOT_TOKEN` and optional `DISCORD_GUILD_ID`.

## Step 3: Target Channel & Links Interview
Use `ask_question` to ask:
"What is your target YouTube channel name or the YouTube channel links you plan to clip from?"
Options:
- (Recommended) Specify custom YouTube Channel Name & Target URLs
- Use default Universal Profile (Accepts any YouTube or Twitch URL on demand)

## Step 4: Write Configuration & Verify Environment
1. Write the user's answers into `.env` (using `.env.example` as a template).
2. Set the chosen workflow in `workflows.json` via `autoclip.workflows.set_active_workflow()`.
3. Run `ffmpeg -version` to confirm FFmpeg is available.
4. Confirm to the user that setup is complete and provide commands:
   - Run Discord Bot: `python scripts/discord_bot.py`
   - Run Montage Assembler: `python -m autoclip.cli top5 --help`
   - View / Switch Workflows: `python -c "from autoclip import workflows; print([w['id'] for w in workflows.list_workflows()])"`
