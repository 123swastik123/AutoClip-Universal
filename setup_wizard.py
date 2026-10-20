#!/usr/bin/env python3
"""AutoClip Universal Setup Wizard.

Interactive onboarding wizard that configures:
- Discord Bot Token & Server Connection
- Target YouTube Channel / Niche
- Active Video Editing Workflow Preset
- FFmpeg & Dependency Verification
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"

WORKFLOW_CHOICES = {
    "1": ("universal_auto", "Universal Auto-Adaptive (Dialogue, Face-Tracking & Energy)"),
    "2": ("countdown_montage", "Top N Countdown Montage (Animated Leaderboard & SFX)"),
    "3": ("smart_highlights", "Viral Highlights & Punchlines (Fast Pacing & Pop Subs)"),
    "4": ("podcast_split", "Podcast / Dual-Speaker Split (Vertical Multi-Speaker)"),
    "5": ("commentary_explainer", "Educational / Commentary Explainer (Presenter Framing)")
}


def print_banner():
    print("=" * 65)
    print("      🎬 WELCOME TO AUTOCLIP UNIVERSAL SETUP WIZARD 🎬")
    print("   Automated Short-Form Video Production & Discord Pipeline")
    print("=" * 65)
    print()


def check_dependencies():
    print("[1/4] Verifying System Dependencies...")
    ffmpeg_bin = shutil.which("ffmpeg")
    ffprobe_bin = shutil.which("ffprobe")

    if ffmpeg_bin:
        print(f"  ✓ FFmpeg detected: {ffmpeg_bin}")
    else:
        print("  ⚠️  WARNING: FFmpeg not found in PATH!")
        print("     Please install ffmpeg (e.g. `winget install Gyan.FFmpeg` or download from ffmpeg.org)")

    if ffprobe_bin:
        print(f"  ✓ FFprobe detected: {ffprobe_bin}")
    else:
        print("  ⚠️  WARNING: FFprobe not found in PATH!")
    print()


def prompt_user():
    print("[2/4] Configuring Discord Bot Integration...")
    print("  To enable Discord bot commands and auto-clipping from Discord chat,")
    print("  enter your bot token from the Discord Developer Portal.")
    print("  (You can press Enter to skip and configure later in .env)")
    discord_token = input("  > Discord Bot Token: ").strip()
    guild_id = input("  > Discord Guild / Server ID (optional): ").strip()
    print()

    print("[3/4] Configuring Your Target Channel & Content Niche...")
    print("  AutoClip adapts its pacing, layout, and metadata to your specific purpose.")
    niche = input("  > Target Niche / Purpose (e.g. Podcasts, Tech, Gaming, Funny Moments) [General]: ").strip()
    if not niche:
        niche = "General / Universal"

    ch_name = input("  > Your YouTube Channel Name [AutoClip Channel]: ").strip()
    if not ch_name:
        ch_name = "AutoClip Channel"

    ch_handle = input(f"  > Your YouTube Channel Handle [@{ch_name.replace(' ', '')}]: ").strip()
    if not ch_handle:
        ch_handle = f"@{ch_name.replace(' ', '')}"
    print()

    print("[4/4] Select Your Default Video Editing Workflow:")
    for num, (wid, desc) in WORKFLOW_CHOICES.items():
        print(f"    [{num}] {desc}")
    choice = input("  > Select workflow [1-5] (default: 1): ").strip()
    selected_wf = WORKFLOW_CHOICES.get(choice, WORKFLOW_CHOICES["1"])[0]
    print(f"  ✓ Selected default workflow: {selected_wf}\n")

    return {
        "DISCORD_BOT_TOKEN": discord_token,
        "DISCORD_GUILD_ID": guild_id,
        "TARGET_NICHE": niche,
        "YOUTUBE_CHANNEL_NAME": ch_name,
        "YOUTUBE_CHANNEL_HANDLE": ch_handle,
        "DEFAULT_WORKFLOW": selected_wf,
        "DEFAULT_CREATOR": "universal"
    }


def write_env(config: dict):
    lines = [
        "# ==================================================================",
        "# AutoClip Universal Environment Configuration",
        "# ==================================================================",
        "",
        "# Discord Bot Integration",
        f"DISCORD_BOT_TOKEN={config['DISCORD_BOT_TOKEN']}",
        f"DISCORD_GUILD_ID={config['DISCORD_GUILD_ID']}",
        "",
        "# Target Channel & Niche Configuration",
        f"TARGET_NICHE={config['TARGET_NICHE']}",
        f"YOUTUBE_CHANNEL_NAME={config['YOUTUBE_CHANNEL_NAME']}",
        f"YOUTUBE_CHANNEL_HANDLE={config['YOUTUBE_CHANNEL_HANDLE']}",
        f"DEFAULT_CREATOR={config['DEFAULT_CREATOR']}",
        "",
        "# Active Editing Workflow Preset",
        f"DEFAULT_WORKFLOW={config['DEFAULT_WORKFLOW']}",
        "",
        "# Media Processing Storage",
        "DATA_DIR=data",
        "SFX_DIR=data/sfx",
        "MUSIC_DIR=data/music",
        "FONTS_DIR=fonts",
        "",
        "# Optional Composio Integration for automated YouTube Studio upload",
        "COMPOSIO_API_KEY=",
        "COMPOSIO_ACCOUNT_ID=",
        "",
        "# Optional OpenAI / LLM API key for advanced hook optimization",
        "OPENAI_API_KEY=",
        "ANTHROPIC_API_KEY=",
        "GEMINI_API_KEY="
    ]

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"✓ Configuration successfully saved to: {ENV_FILE}")


def main():
    print_banner()
    check_dependencies()
    config = prompt_user()
    write_env(config)

    # Also update workflows.json active workflow
    try:
        from autoclip import workflows
        workflows.set_active_workflow(config["DEFAULT_WORKFLOW"])
    except Exception:
        pass

    print()
    print("=" * 65)
    print("🎉 SETUP COMPLETE!")
    print("=" * 65)
    print("You can now start AutoClip with:")
    print("  1. Start Discord Bot:  python scripts/discord_bot.py")
    print("  2. Assemble Top N:     python -m autoclip.cli top5 --help")
    print("  3. View Workflows:     python -c \"from autoclip import workflows; print(workflows.list_workflows())\"")
    print("=" * 65)


if __name__ == "__main__":
    main()
