# 🎬 AutoClip Universal

> **Autonomous AI Video Clipping, Top N Montage Engine & Multi-Format Discord Pipeline for YouTube Shorts, TikTok & Instagram Reels.**

AutoClip Universal is a modular, niche-agnostic short-form video production platform. It automatically converts full-length YouTube videos, livestreams, or raw clips into high-retention 9:16 vertical videos with smart face-tracking reframe, dynamic animated subtitles, procedural sound effects, and customizable workflow styles.

---

## ✨ Features

- **Modular Workflow Engine (`workflows.json`)**: Switch between multiple editing styles with one click or command:
  - 🏆 **Top N Countdown Montage**: 5-to-1 ranked compilations with dynamic animated leaderboard ASS overlays, spring-pop active highlights (`#FFE600`), and comedic SFX transitions.
  - ⚡ **Universal Auto-Adaptive**: Real-time dialogue pace, facial presence, and audio energy analysis.
  - 🎙️ **Podcast / Dual-Speaker Split**: Smart vertical split-screen with boxed subtitles and clean voice focus.
  - 🚀 **Viral Highlights & Punchlines**: High-energy cuts, kinetic typography, and fast pacing.
  - 📚 **Commentary / Explainer**: Presenter framing, topic callouts, and keyword badges.
- **Discord Bot Integration (`scripts/discord_bot.py`)**:
  - Paste any YouTube or Twitch URL directly into Discord chat to trigger automated clipping.
  - Interactive buttons to preview, regenerate, and manage uploads.
  - Slash commands: `/workflows`, `/set_workflow`, `/clip`, `/status`, `/ask`.
- **Decoupled & Universal**: Not locked to any specific creator—adaptable to podcasts, tech, gaming, comedy, sports, or education.
- **Antigravity Interactive Onboarding**: Open this repository in Google Antigravity, and it will interactively interview you to connect your Discord bot and YouTube channels automatically.

---

## 🚀 Quick Start

### Option A: 1-Click Interactive Setup in Google Antigravity (Recommended)
If you have **Google Antigravity** installed:
1. Open this repository folder in Antigravity.
2. Antigravity will automatically detect `.agent/workflows/setup.md` and interview you with interactive prompts to configure your Discord Bot Token, target niche, and preferred editing style.

---

### Option B: Terminal Setup Wizard (Any Machine)
Clone the repository and run the setup wizard:

```bash
git clone https://github.com/123swastik123/AutoClip-Universal.git
cd AutoClip-Universal

# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Run the interactive setup wizard
python setup_wizard.py
```

The wizard will:
- Check for `ffmpeg` and `ffprobe`
- Connect your Discord Bot Token & Server ID
- Configure your target YouTube channel and niche
- Generate your `.env` file

---

## 🤖 Running the Discord Bot

Once `.env` is configured, launch the bot:

```bash
python scripts/discord_bot.py
```

### Discord Slash Commands:
- `/workflows` — View all available video editing workflow styles.
- `/set_workflow <id>` — Change active workflow (e.g. `countdown_montage`, `podcast_split`).
- `/clip <url>` — Turn any YouTube video into vertical Shorts.
- `/status` — View current pipeline status, voice status, and active channel.

---

## 🛠️ CLI Usage & Top N Montage Engine

You can also run AutoClip directly from the command line:

### 1. Assemble a Top 5 Countdown Montage
```bash
python -m autoclip.cli top5 \
  --clips "path/to/clip5.mp4" "path/to/clip4.mp4" "path/to/clip3.mp4" "path/to/clip2.mp4" "path/to/clip1.mp4" \
  --titles "INSANE PLAY, UNLUCKY MOMENT, CHAT TROLL, CLOSE CALL, THE CHAMPION" \
  --out "output/Top_5_Montage.mp4"
```

### 2. Auto-Clip Any YouTube Video
```bash
python -m autoclip.cli clip --url "https://www.youtube.com/watch?v=VIDEO_ID" --workflow universal_auto
```

---

## 🎨 Customizing Workflows (`workflows.json`)

All editing styles are configured in `workflows.json`. You can modify existing presets or add new ones:

```json
{
  "id": "my_custom_niche",
  "name": "My Custom Style",
  "description": "Tailored layout and captioning for my specific niche",
  "aspect_ratio": "9:16",
  "resolution": [1080, 1920],
  "layout": "smart_crop_center",
  "caption_style": "bold_pop_yellow",
  "subtitle_font": "Montserrat-ExtraBold",
  "subtitle_color": "&H0000E6FF",
  "sfx_enabled": true,
  "bgm_enabled": true,
  "bgm_track": "sneaky_snitch.mp3",
  "bgm_duck_db": -20,
  "max_duration": 60,
  "target_niche": "Tech Reviews"
}
```

---

## 📁 Project Structure

```text
AutoClip-Universal/
├── autoclip/                    # Core video processing engine
│   ├── top5_assembler.py        # Top N animated leaderboard montage engine
│   ├── smart_reframe.py         # 9:16 face-tracking reframe
│   ├── captions.py              # Word-level kinetic ASS subtitle generator
│   ├── workflows.py             # Modular workflow manager
│   ├── creators.py              # Dynamic channel profile resolver
│   ├── channel_routing.py       # Multi-brand routing & safety guards
│   ├── sfx_director.py          # Procedural sound effect scheduler
│   └── cli.py                   # Command-line interface dispatcher
├── data/
│   ├── sfx/                     # 21 royalty-free essential sound effects
│   └── music/                   # CC0 / DMCA-safe background tracks
├── fonts/                       # Bundled fonts (Montserrat, etc.)
├── scripts/
│   └── discord_bot.py           # Universal Discord bot integration
├── .agent/
│   └── workflows/setup.md       # Antigravity interactive onboarding workflow
├── setup_wizard.py              # CLI terminal onboarding wizard
├── workflows.json               # Workflow presets database
├── requirements.txt             # Python requirements
├── .env.example                 # Environment configuration template
└── README.md                    # Documentation
```

---

## 📄 License & Fair Use
Core sound effects and bundled music are CC0 / royalty-free. Transformed clips produced by this pipeline comply with transformative fair-use standards.
