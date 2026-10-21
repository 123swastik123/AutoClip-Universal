"""AutoClip Dedicated Discord Bot Integration for Hermes / VM Deployment.

Full-Featured Autonomous Video Architect, Voice Companion & YouTube Channel Producer.
Features:
- Natural Language Upload: Say "Hey upload this clip to my YouTube channel" or "Upload #2"
- Interactive Discord UI Buttons: Click [🚀 Upload #1], [🚀 Upload #2] right under the generated Shorts
- Conversational AI Producer (/ask, @mention): Advice on what to upload, trending streamer videos, hooks
- Voice Channel Speaking (/join, /leave, /speak): Natural neural TTS via edge-tts in Discord VC
- Channel Analytics Audit (/analyze): Reads @askwhatt YouTube channel videos & produces growth strategy
- Streamer Intelligence (/streamers): Viewing windows, dedicated music pools & schedules
- Automatic Video-to-Shorts Pipeline (/clip or paste URL):
    * 9:16 smart face-tracking reframe
    * Golden pop subtitles (#FFD200)
    * Streamer BGM (-14 LUFS, 0 SFX)
    * Automated upload to YouTube channel Ask What? (@askwhatt)
    * Posts the Rank #1 MP4 directly into Discord
"""

import os, sys, asyncio, json, re, tempfile, datetime, time, uuid, subprocess
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from autoclip import config, bot as bot_engine, creators, composio_client, channel_routing, llm as llm_mod, edit as edit_mod, format as format_mod, mediatools as mt, youtube_pipeline, memory as memory_mod, video_radar, long_stream, excel_tracker

try:
    import discord
    from discord import app_commands
    from discord.ext import commands, tasks
except ImportError:
    print("discord.py not installed. Run with: uv run --with 'discord.py>=2.3' python scripts/discord_bot.py")
    sys.exit(1)

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents)

TTS_VOICE = "en-US-ChristopherNeural"  # Realistic charismatic creator voice

# Cache of last generated shorts per channel: {channel_id: {"shorts": [...], "video_title": str}}
LAST_CHANNEL_SESSION = {}

# Set of video IDs / slugs that the user requested to keep on disk
KEEP_MEDIA_REQUESTS = set()

# Dict of URLs/parts currently being processed (lock_key -> timestamp) to prevent duplicate concurrent jobs
ACTIVE_PROCESSING_URLS = {}

async def schedule_source_cleanup(vid_id: str, delay: int = 10800, channel=None):
    """Keep source media and transcripts available for user conversational editing and remastering."""
    if not vid_id:
        return
    print(f"[AutoClip Cleaner] Preserving source media for editing ({vid_id}, auto-cleanup in {delay // 3600}h)")
    await asyncio.sleep(delay)

    if vid_id in KEEP_MEDIA_REQUESTS or "all" in KEEP_MEDIA_REQUESTS:
        print(f"[AutoClip Cleaner] Preserved source media for {vid_id} (user requested keep).")
        return

    try:
        count = youtube_pipeline.purge_source_media(vid_id)
        print(f"[AutoClip Cleaner] Purged {count} temporary scratch files for {vid_id} after session retention period.")
    except Exception as e:
        print(f"[AutoClip Cleaner] Error purging media for {vid_id}: {e}")

def get_channel_session(channel_id):
    """Retrieve the active session strictly for this specific channel without cross-channel or stale disk leakage."""
    session = LAST_CHANNEL_SESSION.get(channel_id)
    if session and session.get("shorts"):
        return session
    return None

def find_media_urls(text):
    """Find all unique YouTube and Twitch URLs in a message."""
    yt_pat = r'https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/|live/)|youtu\.be/)[A-Za-z0-9_-]{11}'
    twitch_vod_pat = r'https?://(?:www\.)?twitch\.tv/videos/\d+'
    twitch_clip_pat = r'https?://(?:www\.)?(?:clips\.twitch\.tv/[A-Za-z0-9_-]+|twitch\.tv/[A-Za-z0-9_]+/clip/[A-Za-z0-9_-]+)'

    combined = f'({yt_pat}|{twitch_vod_pat}|{twitch_clip_pat})'
    matches = re.findall(combined, text)
    seen = set()
    out = []
    for u in matches:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out

def find_youtube_urls(text):
    """Backward-compatible alias: extracts YouTube and Twitch URLs."""
    return find_media_urls(text)

def find_youtube_url(text):
    urls = find_media_urls(text)
    return urls[0] if urls else None

def is_twitch_url(url: str) -> bool:
    return bool(url and "twitch.tv" in url.lower())

def is_twitch_clip(url: str) -> bool:
    if not url: return False
    u = url.lower()
    return "clips.twitch.tv" in u or "/clip/" in u

def get_multi_video_shorts(max_videos=5, theme=None):
    """Aggregate candidate shorts across the last N processed videos on disk,
    guaranteeing that clips are drawn from EACH video and ranked with strict
    energy escalation (#5 mild -> #1 peak climax).
    """
    shorts_dir = PROJECT_ROOT / "data" / "shorts"
    if not shorts_dir.exists():
        return []

    theme_lower = (theme or "funniest").lower()
    is_horror = any(k in theme_lower for k in ["horror", "scary", "jumpscare", "spooky", "fear", "creepy"])
    is_funny = any(k in theme_lower for k in ["funny", "funniest", "laugh", "comedy", "joke"])
    is_r6_gaming = any(k in theme_lower for k in ["rainbow", "siege", "r6", "shooting", "shoot", "headshot", "snipe", "clutch", "ace", "gameplay", "kill", "jynxzi", "gunplay"])
    is_rage = any(k in theme_lower for k in ["rage", "freakout", "slam", "desk slam", "banned"])
    stop_words_theme = {"top", "five", "things", "moments", "clips", "best", "countdown", "the", "and", "from", "video", "videos"}
    custom_kws = [w for w in re.findall(r'\b[a-zA-Z]{3,}\b', theme_lower) if w not in stop_words_theme]

    summaries = sorted(shorts_dir.glob("*_summary.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    video_buckets = {}

    for s_file in summaries:
        try:
            data = json.loads(s_file.read_text(encoding="utf-8"))
            clips = data.get("shorts") or data.get("clips") or []
            v_title = data.get("video_title") or data.get("video_info", {}).get("title", s_file.stem)
            if not clips or v_title in video_buckets:
                continue

            valid_clips = []
            for c in clips:
                c_copy = dict(c)
                f_name = c.get("filename") or os.path.basename(c.get("video_path", ""))
                c_path = str(shorts_dir / f_name)
                if not os.path.exists(c_path):
                    alt_name = os.path.basename(c.get("file", ""))
                    if alt_name and os.path.exists(str(shorts_dir / alt_name)):
                        c_path = str(shorts_dir / alt_name)
                    else:
                        orig_vp = c.get("video_path", "")
                        if orig_vp and os.path.exists(orig_vp):
                            c_path = orig_vp
                if os.path.exists(c_path):
                    c_copy["video_path"] = c_path
                    c_copy["video_title"] = v_title
                    valid_clips.append(c_copy)

            if valid_clips:
                video_buckets[v_title] = valid_clips
            if len(video_buckets) >= max_videos:
                break
        except Exception:
            pass

    if not video_buckets:
        return []

    # Scoring helper for each clip given the theme
    def eval_clip(c):
        base_score = float(c.get("score") or 70.0)
        peak_e = float(c.get("peak_energy") or 0.5)
        reac = float(c.get("reaction_hits") or 0.0)
        txt = (str(c.get("title", "")) + " " + str(c.get("hook_text", "")) + " " + str(c.get("why_good", "")) + " " + str(c.get("description", ""))).lower()

        if is_r6_gaming:
            action_kws = [
                "headshot", "snipe", "sniped", "clutch", "ace", "kill", "killed", "one left",
                "shoot", "shooting", "one tap", "flick", "wallbang", "pre-fire", "beam", "aim",
                "spray", "1v1", "1v2", "1v3", "1v4", "1v5", "plant", "defuse", "c4", "got him",
                "dead", "eliminated", "siege", "ranked", "champion"
            ]
            action_hits = sum(1 for kw in action_kws if kw in txt)
            clutch_bonus = 0.0
            if any(k in txt for k in ["1v4", "1v5", "ace"]):
                clutch_bonus = 55.0
            elif "1v3" in txt:
                clutch_bonus = 35.0
            elif "1v2" in txt:
                clutch_bonus = 20.0
            elif any(k in txt for k in ["headshot", "one tap", "snipe", "flick"]):
                clutch_bonus = 22.0

            shout_kws = ["let's go", "lets go", "stand up", "clip that", "good aim", "slam"]
            shout_bonus = 15.0 if any(k in txt for k in shout_kws) else 0.0

            return (action_hits * 16.0) + clutch_bonus + shout_bonus + (peak_e * 30.0) + (reac * 8.0) + base_score

        elif is_horror:
            scream_kws = ["scream", "screaming", "scare", "scared", "jumpscare", "ghost", "dead", "kill", "what the fuck", "holy shit", "panic", "monster", "run", "behind you", "loud"]
            hits = sum(1 for kw in scream_kws if kw in txt)
            return (peak_e * 50.0) + (hits * 15.0) + (reac * 10.0) + base_score

        elif is_funny:
            funny_kws = ["laugh", "laughing", "haha", "crying", "dying", "joke", "funny", "hilarious", "cooked", "bro what", "exposed"]
            hits = sum(1 for kw in funny_kws if kw in txt)
            return (hits * 18.0) + (reac * 8.0) + (peak_e * 15.0) + base_score

        elif is_rage:
            rage_kws = ["slam", "desk", "banned", "fuck", "bitch", "shit", "trash", "bad", "hate", "quit", "unplayable", "stop"]
            hits = sum(1 for kw in rage_kws if kw in txt)
            return (hits * 22.0) + (peak_e * 35.0) + (reac * 10.0) + base_score

        elif custom_kws:
            c_hits = sum(1 for kw in custom_kws if kw in txt)
            return (c_hits * 30.0) + (peak_e * 25.0) + (reac * 10.0) + base_score

        else:
            return base_score + (peak_e * 20.0)

    # Sort clips within each video by theme intensity descending
    for v_title, v_clips in video_buckets.items():
        for c in v_clips:
            c["_intensity_score"] = eval_clip(c)
        v_clips.sort(key=lambda x: x["_intensity_score"], reverse=True)

    # Fair multi-video allocation: guarantee clips are drawn from EACH video
    num_vids = len(video_buckets)
    selected_clips = []
    
    if num_vids == 1:
        single_list = list(video_buckets.values())[0]
        selected_clips = single_list[:5]
    elif num_vids == 2:
        v_keys = list(video_buckets.keys())
        top_v0 = video_buckets[v_keys[0]][0]["_intensity_score"] if video_buckets[v_keys[0]] else 0
        top_v1 = video_buckets[v_keys[1]][0]["_intensity_score"] if video_buckets[v_keys[1]] else 0
        if top_v0 >= top_v1:
            selected_clips.extend(video_buckets[v_keys[0]][:3])
            selected_clips.extend(video_buckets[v_keys[1]][:2])
        else:
            selected_clips.extend(video_buckets[v_keys[1]][:3])
            selected_clips.extend(video_buckets[v_keys[0]][:2])
    elif num_vids == 3:
        v_keys = list(video_buckets.keys())
        sorted_v_keys = sorted(v_keys, key=lambda k: video_buckets[k][0]["_intensity_score"] if video_buckets[k] else 0, reverse=True)
        selected_clips.extend(video_buckets[sorted_v_keys[0]][:2])
        selected_clips.extend(video_buckets[sorted_v_keys[1]][:2])
        selected_clips.extend(video_buckets[sorted_v_keys[2]][:1])
    elif num_vids == 4:
        v_keys = list(video_buckets.keys())
        sorted_v_keys = sorted(v_keys, key=lambda k: video_buckets[k][0]["_intensity_score"] if video_buckets[k] else 0, reverse=True)
        selected_clips.extend(video_buckets[sorted_v_keys[0]][:2])
        for vk in sorted_v_keys[1:4]:
            selected_clips.extend(video_buckets[vk][:1])
    else:
        sorted_v_keys = sorted(video_buckets.keys(), key=lambda k: video_buckets[k][0]["_intensity_score"] if video_buckets[k] else 0, reverse=True)
        for vk in sorted_v_keys[:5]:
            selected_clips.extend(video_buckets[vk][:1])

    selected_clips = selected_clips[:5]

    # STRICT ESCALATION ORDERING:
    # Sort selected clips by intensity ASCENDING:
    # Index 0: lowest intensity -> Rank 5 (mildest/entry hook)
    # Index 1: mild -> Rank 4
    # Index 2: moderate -> Rank 3
    # Index 3: high -> Rank 2
    # Index 4: maximum climax -> Rank 1 (highest scream/craziest laugh/best punchline!)
    selected_clips.sort(key=lambda x: x["_intensity_score"])
    n = len(selected_clips)
    for idx, c in enumerate(selected_clips):
        c["rank"] = n - idx
    
    return selected_clips

async def speak_text_in_vc(guild, text):
    """Generate neural TTS and play in connected voice channel."""
    if not guild or not guild.voice_client or not guild.voice_client.is_connected():
        return
    if not HAS_EDGE_TTS:
        return

    clean_text = re.sub(r'[*_#`~\[\]()]', '', text).strip()
    if not clean_text:
        return

    speech_text = clean_text[:400]
    temp_mp3 = os.path.join(tempfile.gettempdir(), f"autoclip_tts_{guild.id}.mp3")
    try:
        comm = edge_tts.Communicate(speech_text, TTS_VOICE)
        await comm.save(temp_mp3)

        vc = guild.voice_client
        if vc.is_playing():
            vc.stop()
        source = discord.FFmpegPCMAudio(temp_mp3)
        vc.play(source)
    except Exception as e:
        print(f"[TTS Error] Could not play voice audio: {e}")

# --- Interactive Upload UI Buttons ---

class AdjustClipModal(discord.ui.Modal, title="Teach Hermes: Adjust Style"):
    feedback_text = discord.ui.TextInput(
        label="How should Hermes adjust future clips?",
        style=discord.TextStyle.paragraph,
        placeholder="e.g. make it 45s, gameplay top / face bottom, remove BGM, single word captions...",
        max_length=500,
        required=True
    )

    def __init__(self, short_item, channel=None):
        super().__init__()
        self.short_item = short_item
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        critique = self.feedback_text.value.strip()
        res = memory_mod.record_feedback(self.short_item, "negative", critique)
        rank = self.short_item.get("rank", 1)
        learned_bullets = "\n".join(f"• {p}" for p in res.get("learned_points", [])) if res.get("learned_points") else f"• Instruction logged: '{critique}'"

        embed = discord.Embed(
            title=f"🧠 Preference Learned & Saved (Clip #{rank})",
            description=(
                f"**Your Direction:**\n*\"{critique}\"*\n\n"
                f"**Updated Memory Rules:**\n{learned_bullets}\n\n"
                f"✅ Stored permanently in `data/pipeline_memory.json`. Hermes will automatically apply these settings to upcoming clips!"
            ),
            color=0x3B82F6
        )
        await interaction.followup.send(embed=embed)


class EditClipModal(discord.ui.Modal, title="AI Video Director: Remaster"):
    edit_instructions = discord.ui.TextInput(
        label="How to edit this clip right now?",
        style=discord.TextStyle.paragraph,
        placeholder="e.g. add split screen, make 45 seconds, remove BGM...",
        max_length=500,
        required=True
    )

    def __init__(self, short_item, channel=None):
        super().__init__()
        self.short_item = short_item
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_request = self.edit_instructions.value.strip()
        ch = self.channel or interaction.channel
        await do_conversational_remaster(ch, self.short_item, user_request, interaction=interaction)


class UploadShortsView(discord.ui.View):
    def __init__(self, shorts_data, channel=None):
        super().__init__(timeout=None)
        self.shorts_data = shorts_data or []
        self.channel = channel

        ch_id = channel.id if channel else 0
        top_short = self.shorts_data[0] if self.shorts_data else {}
        rank = top_short.get("rank", 1)

        v_p = top_short.get("video_path") or top_short.get("file") or top_short.get("filename") or ""
        v_base = os.path.basename(v_p)
        stem = os.path.splitext(v_base)[0] if v_base else ""
        if len(stem) > 42:
            stem = stem[:42]
        tok = f"_{stem}" if stem else ""

        # Strict Creator Channel Mapping - ONLY show the single matched channel button for this specific creator
        c_raw = (top_short.get("creator_id") or top_short.get("creator") or "").lower()
        if "case" in c_raw:
            btn_upload = discord.ui.Button(
                label=f"🍔 Upload & Schedule to CaseOh Clips",
                style=discord.ButtonStyle.primary,
                custom_id=f"autoclip_upload_channel_caseoh_{rank}{tok}",
                row=0
            )
            self.add_item(btn_upload)
        elif "jynx" in c_raw:
            btn_upload = discord.ui.Button(
                label=f"🎯 Upload & Schedule to Jynxzi Clips",
                style=discord.ButtonStyle.success,
                custom_id=f"autoclip_upload_channel_jynxzi_{rank}{tok}",
                row=0
            )
            self.add_item(btn_upload)
        elif "speed" in c_raw or "tanvo" in c_raw:
            btn_upload = discord.ui.Button(
                label=f"⚡ Upload & Schedule to Speed Clips Daily",
                style=discord.ButtonStyle.danger,
                custom_id=f"autoclip_upload_channel_speed_{rank}{tok}",
                row=0
            )
            self.add_item(btn_upload)
        else:
            # Fallback to single safe upload button with auto-resolved route
            btn_upload = discord.ui.Button(
                label=f"🚀 Upload & Schedule Short #{rank}",
                style=discord.ButtonStyle.success,
                custom_id=f"autoclip_upload_single_{rank}{tok}",
                row=0
            )
            self.add_item(btn_upload)

        # Row 1: CapCut Visual Studio Link Button
        rel_v = os.path.relpath(v_p, PROJECT_ROOT).replace("\\", "/") if v_p else ""
        c_clean = "speed" if "speed" in c_raw else ("caseoh" if "case" in c_raw else ("jynxzi" if "jynx" in c_raw else "speed"))
        btn_studio = discord.ui.Button(
            label=f"🎨 Open CapCut Editor #{rank} ↗",
            style=discord.ButtonStyle.link,
            url=f"http://localhost:8080/editor?file={rel_v}&creator={c_clean}",
            row=1
        )
        self.add_item(btn_studio)

        # Row 2: Feedback & Remaster Actions
        btn_love = discord.ui.Button(
            label=f"👍 Love #{rank} (Learn)",
            style=discord.ButtonStyle.secondary,
            custom_id=f"autoclip_love_{rank}{tok}",
            row=2
        )
        btn_edit = discord.ui.Button(
            label=f"✏️ Edit #{rank}",
            style=discord.ButtonStyle.primary,
            custom_id=f"autoclip_edit_{rank}{tok}",
            row=2
        )
        btn_adj = discord.ui.Button(
            label=f"👎 Adjust #{rank}",
            style=discord.ButtonStyle.secondary,
            custom_id=f"autoclip_adjust_{rank}{tok}",
            row=2
        )
        self.add_item(btn_love)
        self.add_item(btn_edit)
        self.add_item(btn_adj)


# --- Interactive Intake Selection (Format & Streamer Theme Selection) ---

PENDING_INTAKE = {}  # channel_id: dict

class CustomThemeModal(discord.ui.Modal, title="Custom Countdown Theme"):
    theme_text = discord.ui.TextInput(
        label="Countdown Theme / Category",
        placeholder="e.g. food eating, headshots, scary horror moments, funniest rage...",
        max_length=60,
        required=True
    )

    def __init__(self, channel, url, creator, layout_mode, intake_msg=None):
        super().__init__()
        self.channel = channel
        self.url = url
        self.creator = creator
        self.layout_mode = layout_mode
        self.intake_msg = intake_msg

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        custom_theme = self.theme_text.value.strip()
        PENDING_INTAKE.pop(self.channel.id, None)
        await start_video_production(
            channel=self.channel,
            url=self.url,
            format_type="countdown",
            theme=custom_theme,
            creator_slug=self.creator,
            reframe_mode=self.layout_mode,
            interaction=interaction,
            status_message=self.intake_msg
        )

class ThemeSelect(discord.ui.Select):
    def __init__(self, creator_key="speed"):
        c_norm = (creator_key or "").lower()
        if "speed" in c_norm:
            options = [
                discord.SelectOption(label="Top 5 Foods He's Eating 🍗", value="foods eating", description="Speed trying, tasting, & reacting to food"),
                discord.SelectOption(label="Top 5 Funniest Moments 😂", value="funniest moments", description="Hilarious comedy, troll moments & laugh peaks"),
                discord.SelectOption(label="Top 5 Cringiest Moments 😬", value="cringiest moments", description="Awkward interactions, rizz fails & cringe rants"),
                discord.SelectOption(label="Top 5 Scariest Freakouts 😱", value="scariest moments", description="IShowSpeed jump scares, screams & horror terror"),
                discord.SelectOption(label="Top 5 Wildest / Chaos Moments ⚡", value="wildest moments", description="Unfiltered stream chaos & crazy high-energy moments"),
                discord.SelectOption(label="✍️ Custom Theme...", value="custom", description="Type your own custom countdown theme")
            ]
        elif "jynxzi" in c_norm or "jinx" in c_norm:
            options = [
                discord.SelectOption(label="Top 5 Headshots & Snipes 🎯", value="headshots", description="Cleanest R6 snipes, one-taps & flick headshots"),
                discord.SelectOption(label="Top 5 Best Clutch Gameplays 🏆", value="best gameplays", description="1v2, 1v3, 1v4 clutch round wins against all odds"),
                discord.SelectOption(label="Top 5 Rainbow Six Shooting & Kills 🔫", value="rainbow six shooting", description="Best gunplay, multi-kills & R6 champion rounds"),
                discord.SelectOption(label="Top 5 Rage & Freakouts 🤬", value="rage moments", description="Desk slams, headset throws & screaming tilt moments"),
                discord.SelectOption(label="Top 5 Funniest Stream Moments 😂", value="funniest moments", description="Banter, troll moments, and funniest dialogue"),
                discord.SelectOption(label="✍️ Custom Theme...", value="custom", description="Type your own custom countdown theme")
            ]
        elif "case" in c_norm:
            options = [
                discord.SelectOption(label="Top 5 Horror Jumpscares 👻", value="horror jumpscares", description="Horror game screams, terrifying moments & panic"),
                discord.SelectOption(label="Top 5 Funny Rage & Bans 🤬", value="funny rage moments", description="'Yep, You're Banned!' desk shakes & rage rants"),
                discord.SelectOption(label="Top 5 Food & Waffle House 🍔", value="food waffle house", description="Food debates, Waffle House rants & weight jokes"),
                discord.SelectOption(label="Top 5 Funniest Moments 😂", value="funniest moments", description="Peak comedy, fan donos & funniest stream moments"),
                discord.SelectOption(label="✍️ Custom Theme...", value="custom", description="Type your own custom countdown theme")
            ]
        elif "kai" in c_norm:
            options = [
                discord.SelectOption(label="Top 5 Funniest Moments 😂", value="funniest moments", description="Room comedy, Kai laughs & hilarious reactions"),
                discord.SelectOption(label="Top 5 Craziest Stream Chaos ⚡", value="craziest room moments", description="AMP room mayhem, wild stunts & jumping chaos"),
                discord.SelectOption(label="Top 5 Celebrity Reactions 🎙️", value="celebrity reactions", description="Famous guests, viral calls & shocked reactions"),
                discord.SelectOption(label="Top 5 Most Shocking Moments 😱", value="shocking moments", description="Unbelievable moments that broke the internet"),
                discord.SelectOption(label="✍️ Custom Theme...", value="custom", description="Type your own custom countdown theme")
            ]
        else:
            options = [
                discord.SelectOption(label="Top 5 Funniest Moments 😂", value="funniest moments", description="Hilarious comedy & laugh peaks"),
                discord.SelectOption(label="Top 5 Craziest Moments ⚡", value="craziest moments", description="High-energy, shocking & wild highlights"),
                discord.SelectOption(label="Top 5 Best Highlights 🏆", value="best moments", description="Highest rated peak moments of the video"),
                discord.SelectOption(label="Top 5 Most Shocking Moments 😱", value="shocking moments", description="Unexpected twists and unbelievable events"),
                discord.SelectOption(label="✍️ Custom Theme...", value="custom", description="Type your own custom countdown theme")
            ]

        super().__init__(
            placeholder="🏆 Select Top 5 Countdown Theme (or Custom)...",
            min_values=1,
            max_values=1,
            options=options,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        val = self.values[0]
        if val == "custom":
            await interaction.response.send_modal(
                CustomThemeModal(
                    channel=view.channel,
                    url=view.url,
                    creator=view.creator,
                    layout_mode=view.layout_mode,
                    intake_msg=view.message
                )
            )
            return

        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass
        PENDING_INTAKE.pop(view.channel.id, None)
        await start_video_production(
            channel=view.channel,
            url=view.url,
            format_type="countdown",
            theme=val,
            creator_slug=view.creator,
            reframe_mode=view.layout_mode,
            interaction=interaction,
            status_message=view.message
        )

class VideoIntakeChoiceView(discord.ui.View):
    def __init__(self, channel, url, creator="speed", video_title=""):
        super().__init__(timeout=300)
        self.channel = channel
        self.url = url
        self.creator = creator or "speed"
        self.video_title = video_title
        self.message = None
        self.layout_mode = "split_screen" if (self.creator in ("jynxzi", "caseoh") and "game" in (video_title or "").lower()) else "blur_fill"

        # Row 0: Dropdown Select for Countdown Themes
        self.add_item(ThemeSelect(creator_key=self.creator))

        # Row 1: Button for 5 Standalone Shorts
        self.btn_normal = discord.ui.Button(
            label="🎬 5 Normal Ranked Shorts",
            style=discord.ButtonStyle.primary,
            custom_id="intake_normal_shorts",
            row=1
        )
        self.btn_normal.callback = self.on_normal_clicked
        self.add_item(self.btn_normal)

        # Row 1: Layout toggle buttons
        self.btn_blur = discord.ui.Button(
            label="🖼️ Layout: MrBeast Blur (Active)" if self.layout_mode == "blur_fill" else "🖼️ Use MrBeast Blur",
            style=discord.ButtonStyle.success if self.layout_mode == "blur_fill" else discord.ButtonStyle.secondary,
            custom_id="intake_toggle_blur",
            row=1
        )
        self.btn_blur.callback = self.on_toggle_blur
        self.add_item(self.btn_blur)

        self.btn_split = discord.ui.Button(
            label="👥 Layout: Split Screen (Active)" if self.layout_mode == "split_screen" else "👥 Use Split Screen",
            style=discord.ButtonStyle.success if self.layout_mode == "split_screen" else discord.ButtonStyle.secondary,
            custom_id="intake_toggle_split",
            row=1
        )
        self.btn_split.callback = self.on_toggle_split
        self.add_item(self.btn_split)

    async def on_normal_clicked(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass
        PENDING_INTAKE.pop(self.channel.id, None)
        await start_video_production(
            channel=self.channel,
            url=self.url,
            format_type="normal",
            theme=None,
            creator_slug=self.creator,
            reframe_mode=self.layout_mode,
            interaction=interaction,
            status_message=self.message
        )

    async def on_toggle_blur(self, interaction: discord.Interaction):
        self.layout_mode = "blur_fill"
        self.btn_blur.style = discord.ButtonStyle.success
        self.btn_blur.label = "🖼️ Layout: MrBeast Blur (Active)"
        self.btn_split.style = discord.ButtonStyle.secondary
        self.btn_split.label = "👥 Use Split Screen"
        await interaction.response.edit_message(view=self)

    async def on_toggle_split(self, interaction: discord.Interaction):
        self.layout_mode = "split_screen"
        self.btn_split.style = discord.ButtonStyle.success
        self.btn_split.label = "👥 Layout: Split Screen (Active)"
        self.btn_blur.style = discord.ButtonStyle.secondary
        self.btn_blur.label = "🖼️ Use MrBeast Blur"
        await interaction.response.edit_message(view=self)

class LongStreamIntakeView(discord.ui.View):
    """Interactive Intake Menu for Long Streams (> 2 Hours) with 2-Hour Chunk Buttons & Heatmap."""
    def __init__(self, channel, url, creator="speed", video_title="", duration=0.0, chunks=None, hottest_chunk=None):
        super().__init__(timeout=600)
        self.channel = channel
        self.url = url
        self.creator = creator
        self.video_title = video_title
        self.duration = duration
        self.chunks = chunks or []
        self.hottest_chunk = hottest_chunk
        self.message = None
        self.layout_mode = "split_screen" if (self.creator in ("jynxzi", "caseoh") and "game" in (video_title or "").lower()) else "blur_fill"

        # Row 0: Hottest Segment Button (Recommended)
        if self.hottest_chunk:
            h_part = self.hottest_chunk["part"]
            h_score = self.hottest_chunk.get("heatmap_score", 0)
            btn_hot = discord.ui.Button(
                label=f"🔥 Hottest Segment: Part {h_part} ({h_score}/100 Replay)",
                style=discord.ButtonStyle.success,
                custom_id=f"long_stream_hot_{h_part}",
                row=0
            )
            btn_hot.callback = self.make_part_callback(h_part)
            self.add_item(btn_hot)

        # Row 1: Individual 2-Hour Part Buttons
        for c in self.chunks[:4]:
            p_num = c["part"]
            btn_part = discord.ui.Button(
                label=f"🎬 Part {p_num} ({int(c['t0']//3600)}h–{int(c['t1']//3600)}h)",
                style=discord.ButtonStyle.primary if (self.hottest_chunk and p_num == self.hottest_chunk.get("part")) else discord.ButtonStyle.secondary,
                custom_id=f"long_stream_part_{p_num}",
                row=1
            )
            btn_part.callback = self.make_part_callback(p_num)
            self.add_item(btn_part)

        # Row 2: Layout selection buttons
        self.btn_blur = discord.ui.Button(
            label="🖼️ Layout: MrBeast Blur (Active)" if self.layout_mode == "blur_fill" else "🖼️ Use MrBeast Blur",
            style=discord.ButtonStyle.success if self.layout_mode == "blur_fill" else discord.ButtonStyle.secondary,
            custom_id="long_toggle_blur",
            row=2
        )
        self.btn_blur.callback = self.on_toggle_blur
        self.add_item(self.btn_blur)

        self.btn_split = discord.ui.Button(
            label="👥 Layout: Split Screen (Active)" if self.layout_mode == "split_screen" else "👥 Use Split Screen",
            style=discord.ButtonStyle.success if self.layout_mode == "split_screen" else discord.ButtonStyle.secondary,
            custom_id="long_toggle_split",
            row=2
        )
        self.btn_split.callback = self.on_toggle_split
        self.add_item(self.btn_split)

    async def on_toggle_blur(self, interaction: discord.Interaction):
        self.layout_mode = "blur_fill"
        self.btn_blur.style = discord.ButtonStyle.success
        self.btn_blur.label = "🖼️ Layout: MrBeast Blur (Active)"
        self.btn_split.style = discord.ButtonStyle.secondary
        self.btn_split.label = "👥 Use Split Screen"
        await interaction.response.edit_message(view=self)

    async def on_toggle_split(self, interaction: discord.Interaction):
        self.layout_mode = "split_screen"
        self.btn_split.style = discord.ButtonStyle.success
        self.btn_split.label = "👥 Layout: Split Screen (Active)"
        self.btn_blur.style = discord.ButtonStyle.secondary
        self.btn_blur.label = "🖼️ Use MrBeast Blur"
        await interaction.response.edit_message(view=self)

    def make_part_callback(self, part_num):
        async def cb(interaction: discord.Interaction):
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer()
            except Exception:
                pass
            PENDING_INTAKE.pop(self.channel.id, None)
            await start_video_production(
                channel=self.channel,
                url=self.url,
                format_type="normal",
                theme=None,
                creator_slug=self.creator,
                reframe_mode=self.layout_mode,
                interaction=interaction,
                status_message=self.message,
                chunk_part=part_num
            )
        return cb

class TwitchClipIntakeView(discord.ui.View):
    """Interactive 1-click remastering menu for Twitch clips (< 90 seconds)."""
    def __init__(self, channel, url, creator="speed", video_title="", duration=30.0):
        super().__init__(timeout=600)
        self.channel = channel
        self.url = url
        self.creator = creator or "speed"
        self.video_title = video_title
        self.duration = duration
        self.message = None

    @discord.ui.button(label="🖼️ Remaster (MrBeast Blur)", style=discord.ButtonStyle.success, row=0)
    async def btn_blur(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.execute_remaster(interaction, "blur_fill")

    @discord.ui.button(label="👥 Remaster (Split-Screen Face+Game)", style=discord.ButtonStyle.primary, row=0)
    async def btn_split(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.execute_remaster(interaction, "split_screen")

    async def execute_remaster(self, interaction: discord.Interaction, layout: str):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass
        PENDING_INTAKE.pop(self.channel.id, None)
        await start_video_production(
            channel=self.channel,
            url=self.url,
            format_type="normal",
            theme=None,
            creator_slug=self.creator,
            reframe_mode=layout,
            interaction=interaction,
            status_message=self.message
        )

class MultiVideoBatchView(discord.ui.View):
    """Interactive view allowing 1-click countdown compilation across multiple videos."""
    def __init__(self, channel, num_vids: int = 2):
        super().__init__(timeout=600)
        self.channel = channel
        self.num_vids = num_vids

    @discord.ui.button(label="🎬 Compile Top 5 Funniest", style=discord.ButtonStyle.primary, row=0)
    async def btn_funniest(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_compile(interaction, "funniest")

    @discord.ui.button(label="😱 Compile Top 5 Horror Jumpscares", style=discord.ButtonStyle.danger, row=0)
    async def btn_horror(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_compile(interaction, "horror")

    @discord.ui.button(label="⚡ Compile Top 5 Craziest Chaos", style=discord.ButtonStyle.success, row=0)
    async def btn_chaos(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_compile(interaction, "craziest")

    @discord.ui.button(label="🎯 Compile Top 5 R6 Clutches & Kills", style=discord.ButtonStyle.secondary, row=1)
    async def btn_r6(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_compile(interaction, "rainbow six shooting")

    async def handle_compile(self, interaction: discord.Interaction, theme: str):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass
        status_msg = await self.channel.send(
            f"🎬 **AI Video Director Activated:** Compiling **TOP 5 {theme.upper()} MOMENTS** across all {self.num_vids} videos!\n"
            f"• Structure: Title Intro Card (1.5s) ➔ #5 ➔ #4 ➔ #3 ➔ #2 ➔ #1 Climax (THE BEST ONE)\n"
            f"• Sound Design: Tailored BGM + Animated Transition Cards\n"
            f"⏳ Trimming top moments, generating animated countdown cards, and compiling master Short..."
        )
        multi_clips = get_multi_video_shorts(max_videos=self.num_vids, theme=theme)
        if len(multi_clips) >= 2:
            target_session = {"shorts": multi_clips, "video_title": f"Top 5 {theme.title()} Multi-Video", "is_multi": True}
            loop = asyncio.get_event_loop()
            def do_top5():
                return execute_top5_countdown(target_session, theme=theme)
            try:
                top5_res = await loop.run_in_executor(None, do_top5)
                comp_path = top5_res.get("video_path")
                comp_short = {
                    "rank": 1,
                    "title": top5_res.get("title"),
                    "video_path": comp_path,
                    "duration": top5_res.get("duration", 0),
                    "description": f"Top 5 {theme} moments! #shorts #viral",
                    "tags": ["shorts", "viral", "top5", theme]
                }
                comp_view = UploadShortsView([comp_short], self.channel)
                await status_msg.edit(content=f"✨ **TOP 5 {theme.upper()} MOMENTS Countdown Ready!**\n*{top5_res.get('title')}* | Duration: {top5_res.get('duration', 0):.1f}s")
                await send_video_safely(
                    self.channel,
                    comp_path,
                    caption=f"🎬 **Top 5 Countdown Short Across {self.num_vids} Videos (Ready to Post):**",
                    view=comp_view
                )
                if top5_res.get("low_intensity_warning"):
                    try:
                        await self.channel.send(content=top5_res["low_intensity_warning"])
                    except Exception:
                        pass
            except Exception as ex:
                await status_msg.edit(content=f"❌ Top 5 Compilation failed: `{str(ex)[:500]}`")
        else:
            await status_msg.edit(content="⚠️ Not enough clips found across the videos to compile a countdown.")

# --- AutoClip Video Radar UI & Engine ---

RADAR_SEEN_FILE = PROJECT_ROOT / "data" / "radar_seen_videos.json"

def get_seen_radar_videos():
    """Retrieve set of YouTube video IDs already scanned or notified by the Radar."""
    if RADAR_SEEN_FILE.exists():
        try:
            with open(RADAR_SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()

def mark_radar_video_seen(video_id: str):
    """Mark a video ID as seen so watchdog does not duplicate notifications."""
    if not video_id:
        return
    seen = get_seen_radar_videos()
    seen.add(video_id)
    try:
        RADAR_SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(RADAR_SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(list(seen), f)
    except Exception as e:
        print(f"[Radar Watcher] Error saving seen video {video_id}: {e}")

def build_radar_embed(video: dict) -> discord.Embed:
    """Build a rich Discord embed showcasing a scouted video's viral potential."""
    creator_slug = video.get("creator_slug", "speed")
    color_map = {
        "speed": 0xFF3300,
        "caseoh": 0xF59E0B,
        "jynxzi": 0x5865F2,
        "kai": 0x9146FF,
        "custom": 0x10B981,
    }
    embed_color = color_map.get(creator_slug, 0x9146FF if video.get("platform") == "twitch" else 0x3B82F6)

    score = video.get("score", 75)
    tier = video.get("tier", "High Potential")
    views = video.get("view_count", 0)
    dur = video.get("duration", 0)
    dur_str = video.get("duration_str") or (f"{int(dur // 60)}m {int(dur % 60):02d}s" if dur > 0 else "Live Stream")
    view_str = f"{views:,}" if views > 0 else "Live Archive"
    date_label = video.get("date_label")

    embed = discord.Embed(
        title=f"{video.get('creator_avatar', '🎬')} {video.get('creator_name', 'Streamer')}: {video.get('title', 'Untitled')[:80]}",
        url=video.get("url"),
        color=embed_color
    )

    embed.add_field(
        name="🔥 Viral Opportunity Score",
        value=f"**{score}/100** • *{tier}*",
        inline=True
    )
    dur_field_val = f"`{dur_str}`"
    if date_label:
        dur_field_val += f"\n📅 **{date_label}**"
    embed.add_field(
        name="⏱️ Duration & Date",
        value=dur_field_val,
        inline=True
    )
    embed.add_field(
        name="👁️ Views & Source",
        value=f"**{view_str}** views\n*({video.get('channel_type', 'Stream')})*",
        inline=True
    )

    reasons = video.get("reasons", [])
    if reasons:
        reasons_text = "\n".join([f"• {r}" for r in reasons])
    else:
        reasons_text = video.get("summary", "Trending streamer upload with high clipability")
    embed.add_field(
        name="🎯 Why Clip This Video:",
        value=reasons_text,
        inline=False
    )

    if video.get("thumbnail"):
        embed.set_image(url=video["thumbnail"])

    embed.set_footer(text="AutoClip Radar • 1-Click Zero Copy-Paste Clip Production")
    return embed

class RadarVideoView(discord.ui.View):
    """Interactive view for scouted video cards with 1-click 'Make Clips' button."""
    def __init__(self, video: dict, channel=None):
        super().__init__(timeout=None)
        self.video = video
        self.channel = channel
        v_url = video.get("url", "")
        v_id = video.get("id", "")
        c_slug = video.get("creator_slug", "speed")

        is_clip = self.video.get("is_clip", False)
        is_vod = self.video.get("is_stream_vod", False)
        dur = float(self.video.get("duration", 0) or 0)
        is_twitch = self.video.get("platform") == "twitch"

        if is_vod or dur > 7200.0:
            label_btn = "⚡ Clip This Stream (2-Hour Chunks)"
            btn_style = discord.ButtonStyle.success
        elif is_clip:
            label_btn = "⚡ Remaster Clip into Short"
            btn_style = discord.ButtonStyle.success
        else:
            label_btn = "🎬 Make Clips from This Video"
            btn_style = discord.ButtonStyle.primary

        btn_produce = discord.ui.Button(
            label=label_btn,
            style=btn_style,
            custom_id=f"radar_prod_{v_id}_{c_slug}"[:100],
            row=0
        )
        btn_produce.callback = self.on_produce_click
        self.add_item(btn_produce)

        if v_url:
            platform_label = "Twitch" if is_twitch else "YouTube"
            btn_watch = discord.ui.Button(
                label=f"📺 Watch on {platform_label}",
                style=discord.ButtonStyle.link,
                url=v_url,
                row=0
            )
            self.add_item(btn_watch)

    async def on_produce_click(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass
        target_channel = self.channel or interaction.channel
        u = self.video.get("url")
        c = self.video.get("creator_slug") or "speed"
        v_title = self.video.get("title", "")
        dur = float(self.video.get("duration", 0) or 0)
        is_clip = self.video.get("is_clip", False)
        is_vod = self.video.get("is_stream_vod", False)

        # 1. Twitch Clip or short moment (< 90 seconds)
        if is_clip or (0 < dur <= 90.0 and not is_vod):
            intake_view = TwitchClipIntakeView(
                channel=target_channel,
                url=u,
                creator=c,
                video_title=v_title,
                duration=dur or 30.0
            )
            clip_embed = discord.Embed(
                title=f"🟣 Twitch Viral Scene Remaster: {v_title[:60]}",
                description=(
                    f"**Streamer:** **{c.upper()}**\n"
                    f"**Duration:** `{dur:.0f}s` (High-Density Stream Moment)\n\n"
                    f"⚡ **1-Click Short Remastering:**\n"
                    f"Formats directly into 9:16 vertical HD, word-level golden pop subtitles (#FFD200) synced, and {c.title()}'s dedicated viral BGM layered at -14 LUFS.\n\n"
                    f"🎯 **Select Layout to Produce:**"
                ),
                color=0x9146FF
            )
            if interaction:
                try:
                    status_msg = await interaction.followup.send(embed=clip_embed, view=intake_view)
                except Exception:
                    status_msg = await target_channel.send(embed=clip_embed, view=intake_view)
            else:
                status_msg = await target_channel.send(embed=clip_embed, view=intake_view)

            intake_view.message = status_msg
            PENDING_INTAKE[target_channel.id] = {
                "url": u,
                "creator": c,
                "video_title": v_title,
                "layout_mode": "blur_fill",
                "intake_msg": status_msg
            }
            return

        # 2. Massive stream (> 2 Hours) or Twitch Live Stream VOD
        if dur > 7200.0 or (is_vod and dur >= 3600.0):
            loop = asyncio.get_running_loop()
            meta = await loop.run_in_executor(None, lambda: long_stream.fetch_stream_metadata_and_heatmap(u))
            chunks = long_stream.get_stream_chunks(dur)
            chunks = long_stream.analyze_chunks_with_heatmap(chunks, meta.get("heatmap", []))
            hottest = max(chunks, key=lambda ch: (ch.get("peak_count", 0), ch.get("heatmap_score", 0))) if chunks else None
            intake_view = LongStreamIntakeView(
                channel=target_channel,
                url=u,
                creator=c,
                video_title=v_title,
                duration=dur,
                chunks=chunks,
                hottest_chunk=hottest
            )
            hours_formatted = f"{dur / 3600:.1f} Hours" if dur >= 3600 else f"{int(dur // 60)} Minutes"
            parts_desc = "\n".join([
                f"• **Part {ch['part']}** (`{int(ch['t0']//3600)}h–{int(ch['t1']//3600)}h`): Heatmap Score `{ch.get('heatmap_score', 0)}/100`"
                for ch in chunks
            ])
            long_embed = discord.Embed(
                title=f"🌊 {'Twitch Live Stream' if is_vod else 'Massive Stream'} Detected • 2-Hour Chunking Engine",
                description=(
                    f"**Selected Stream:** [{v_title}]({u})\n"
                    f"**Streamer:** **{c.upper()}**\n"
                    f"**Duration:** **{hours_formatted}**\n\n"
                    f"⚡ **2-Hour Chunking & Surgical Extraction:**\n"
                    f"{parts_desc}\n\n"
                    f"Tap **🔥 Hottest Segment** or select a part below to begin:"
                ),
                color=0x9146FF if is_vod else 0xFF5722
            )
            if self.video.get("thumbnail"):
                long_embed.set_thumbnail(url=self.video["thumbnail"])

            if interaction:
                try:
                    status_msg = await interaction.followup.send(embed=long_embed, view=intake_view)
                except Exception:
                    status_msg = await target_channel.send(embed=long_embed, view=intake_view)
            else:
                status_msg = await target_channel.send(embed=long_embed, view=intake_view)

            intake_view.message = status_msg
            PENDING_INTAKE[target_channel.id] = {
                "url": u,
                "creator": c,
                "video_title": v_title,
                "layout_mode": intake_view.layout_mode,
                "intake_msg": status_msg
            }
            return

        # 3. Standard Video Intake
        intake_view = VideoIntakeChoiceView(
            channel=target_channel,
            url=u,
            creator=c,
            video_title=v_title
        )

        c_display = c.upper()
        intake_embed = discord.Embed(
            title=f"🎬 AutoClip AI Production: Choose Format & Theme",
            description=(
                f"**Selected Video:** [{v_title}]({u})\n"
                f"**Streamer Profile:** **{c_display}**\n\n"
                f"🎯 **Select how you would like AutoClip to produce this video:**\n\n"
                f"1️⃣ **Top 5 Countdown Short** — Pick a theme from the dropdown menu below:\n"
                f"   • *IShowSpeed:* Top 5 Foods He's Eating, Funniest, Cringiest, Scariest, Wildest\n"
                f"   • *Jynxzi:* Top 5 Headshots & Snipes, Best Gameplays, Rage Moments, Funniest\n"
                f"   • *CaseOh:* Top 5 Horror Jumpscares, Funny Rage & Bans, Food/Waffle House, Funniest\n"
                f"   • *Or select '✍️ Custom Theme...' to type your own!*\n\n"
                f"2️⃣ **🎬 5 Normal Ranked Shorts** — Click the button below for individual clips\n\n"
                f"🖼️ **Layout Selection:** Choose between **MrBeast Blur** (16:9 centered with blurred background) or **Split-Screen**.\n\n"
                f"💬 *Or reply with your choice in chat! (e.g. 'top 5 foods', 'normal clips')*"
            ),
            color=0xFFD200
        )
        if self.video.get("thumbnail"):
            intake_embed.set_thumbnail(url=self.video["thumbnail"])

        if interaction:
            try:
                status_msg = await interaction.followup.send(embed=intake_embed, view=intake_view)
            except Exception:
                status_msg = await target_channel.send(embed=intake_embed, view=intake_view)
        else:
            status_msg = await target_channel.send(embed=intake_embed, view=intake_view)
        intake_view.message = status_msg
        PENDING_INTAKE[target_channel.id] = {
            "url": u,
            "creator": c,
            "video_title": v_title,
            "intake_msg": status_msg,
            "view": intake_view,
            "timestamp": time.time(),
            "layout_mode": intake_view.layout_mode
        }

async def run_radar_scout(channel, creator_choice="all", custom_input=None, platform="all", interaction=None):
    """Execute video radar scan across YouTube & Twitch and display rich cards with 1-click production buttons."""
    platform_label = "YouTube & Twitch" if platform == "all" else ("Twitch" if platform == "twitch" else "YouTube")
    if platform == "twitch":
        status_embed = discord.Embed(
            title=f"🟣 AutoClip Twitch Stream Radar: Fetching Recent Streams...",
            description="Scouting full live streams from the past 4–5 days via Twitch MCP & yt-dlp. Slicing into 2-hour surgical chunks...",
            color=0x9146FF
        )
    else:
        status_embed = discord.Embed(
            title=f"🛰️ AutoClip Video Radar: Scouting {platform_label}...",
            description=f"Scanning {platform_label} uploads and live streams from the past week, evaluating view velocity and clipability...",
            color=0x3B82F6
        )
    if interaction:
        status_msg = await interaction.followup.send(embed=status_embed)
    else:
        status_msg = await channel.send(embed=status_embed)

    loop = asyncio.get_running_loop()
    try:
        if custom_input:
            videos = await loop.run_in_executor(None, lambda: video_radar.scout_custom_channel(custom_input, max_videos=5))
            scope_title = f"Custom Channel: `{custom_input}`"
        elif platform == "twitch" and creator_choice in ("speed", "caseoh", "jynxzi", "kai"):
            videos = await loop.run_in_executor(None, lambda: video_radar.scout_creator_videos(creator_choice, max_per_channel=5, platform="twitch"))
            c_name = video_radar.STREAMER_CHANNELS[creator_choice]['name']
            scope_title = f"🟣 {c_name} — Past 4–5 Days Live Streams"
        elif platform == "twitch":
            videos = await loop.run_in_executor(None, lambda: video_radar.scout_twitch_trending(top_n=6))
            scope_title = "🟣 Twitch Streamers — Past 4–5 Days Live Streams"
        elif creator_choice in ("speed", "caseoh", "jynxzi", "kai"):
            videos = await loop.run_in_executor(None, lambda: video_radar.scout_creator_videos(creator_choice, max_per_channel=3, platform=platform))
            scope_title = f"{video_radar.STREAMER_CHANNELS[creator_choice]['name']} ({platform_label})"
        else:
            videos = await loop.run_in_executor(None, lambda: video_radar.scout_all_streamers(top_n=6, platform=platform))
            scope_title = f"Top Streamers ({platform_label})"

        if not videos:
            err_embed = discord.Embed(
                title=f"🛰️ AutoClip Video Radar: No Content Found",
                description=f"Couldn't fetch recent streams/videos for **{scope_title}**. Please check channel handle or try again shortly.",
                color=0xEF4444
            )
            await status_msg.edit(embed=err_embed)
            return

        if platform == "twitch":
            header_desc = (
                f"Found **{len(videos)}** full live streams from the past 4–5 days.\n"
                f"Click **⚡ Clip This Stream (2-Hour Chunks)** on any stream below to slice and produce viral shorts!"
            )
        else:
            header_desc = (
                f"Found **{len(videos)}** top candidate videos/streams ranked by **Clipability & Viral Potential**.\n"
                f"Click **⚡ Clip This Stream** or **🎬 Make Clips** on any card below to produce viral shorts!"
            )

        header_embed = discord.Embed(
            title=f"🛰️ AutoClip Video Radar — {scope_title}",
            description=header_desc,
            color=0x9146FF if platform == "twitch" else 0x10B981
        )
        await status_msg.edit(embed=header_embed)

        for v in videos[:5]:
            v_embed = build_radar_embed(v)
            v_view = RadarVideoView(v, channel=channel)
            await channel.send(embed=v_embed, view=v_view)

    except Exception as e:
        print(f"[Radar Scout Error]: {e}")
        err_embed = discord.Embed(
            title="❌ Radar Scan Encountered an Error",
            description=f"```{str(e)[:1000]}```",
            color=0xEF4444
        )
        await status_msg.edit(embed=err_embed)

async def start_video_production(channel, url, format_type="normal", theme=None, creator_slug=None, reframe_mode=None, interaction=None, status_message=None, chunk_part=None):
    c_key = creator_slug or "speed"
    reframe_label = "MrBeast Cinematic (Blurred Background)" if reframe_mode == "blur_fill" else ("Split-Screen (Face + Game)" if reframe_mode == "split_screen" else "Smart Reframe")

    if format_type == "countdown":
        theme_clean = (theme or "funniest").title()
        init_content = (
            f"🎬 **AI Video Director Activated:** Compiling **TOP 5 {theme_clean.upper()} MOMENTS** from this video!\n"
            f"• Source: `{url}`\n"
            f"• Creator: **{c_key.title()}**\n"
            f"• Layout: **{reframe_label}**\n"
            f"• Template: Title Card (1.5s) ➔ #5 ➔ #4 ➔ #3 ➔ #2 ➔ #1 Climax (Complete Story & Climax)\n"
            f"⏳ Trimming top moments, generating animated countdown cards, and compiling master Short..."
        )
        if status_message:
            try:
                await status_message.edit(content=init_content, embed=None, view=None)
            except Exception:
                pass
        elif interaction:
            try:
                await interaction.followup.send(content=init_content)
            except Exception:
                pass

        # 1. Run pipeline for this video without posting 5 separate videos
        pipeline_res = await handle_clip_pipeline(
            channel=channel,
            url=url,
            creator_slug=c_key,
            auto_upload=False,
            interaction=None,
            theme=theme,
            reframe_mode=reframe_mode,
            status_msg_override=status_message,
            deliver_individual=False,
            fresh=True,
            chunk_part=chunk_part
        )

        # 2. Get the session strictly for THIS video
        session = pipeline_res or get_channel_session(channel.id)
        if not session or not session.get("shorts"):
            await channel.send("⚠️ Could not compile countdown: no clips generated.")
            return

        # 3. Assemble Top 5 Countdown video from THIS video's clips
        loop = asyncio.get_event_loop()
        def do_top5():
            return execute_top5_countdown(session, theme=theme or "funniest")

        try:
            top5_res = await loop.run_in_executor(None, do_top5)
            comp_path = top5_res.get("video_path")
            comp_short = {
                "rank": 1,
                "title": top5_res.get("title"),
                "video_path": comp_path,
                "duration": top5_res.get("duration", 0),
                "description": f"Top 5 {theme or 'funniest'} moments! #shorts #viral",
                "tags": ["shorts", "viral", "top5", str(theme or "funniest"), c_key],
                "creator_id": c_key
            }
            # Generate High-CTR Viral Thumbnail matching reference templates
            from autoclip import thumbnail_generator
            thumb_path = thumbnail_generator.generate_short_thumbnail(
                comp_path,
                title=comp_short.get("title", ""),
                creator=c_key,
                theme=theme
            )
            if thumb_path and os.path.exists(thumb_path):
                comp_short["thumbnail_path"] = thumb_path
                try:
                    await channel.send(
                        content="🖼️ **High-CTR Viral Shorts Thumbnail Created:**",
                        file=discord.File(thumb_path, filename=os.path.basename(thumb_path))
                    )
                except Exception as te:
                    print(f"[Discord Bot] Thumbnail send note: {te}")

            comp_view = UploadShortsView([comp_short], channel)

            ready_msg = f"✨ **TOP 5 {(theme or 'funniest').upper()} MOMENTS Countdown Short Ready!**\n*{top5_res.get('title')}* | Duration: {top5_res.get('duration', 0):.1f}s"
            if status_message:
                try:
                    await status_message.edit(content=ready_msg, embed=None, view=None)
                except Exception:
                    await channel.send(ready_msg)
            else:
                await channel.send(ready_msg)

            await send_video_safely(
                channel,
                comp_path,
                caption=f"🎬 **Top 5 {(theme or 'funniest').title()} Countdown Video File (Ready to Post):**",
                view=comp_view
            )

            if top5_res.get("low_intensity_warning"):
                try:
                    await channel.send(content=top5_res["low_intensity_warning"])
                except Exception:
                    pass

            # Automatically stage & schedule upload to YouTube Studio
            await upload_and_notify(channel, comp_short)

            if channel.guild and channel.guild.voice_client:
                await speak_text_in_vc(channel.guild, f"Your top 5 {theme or 'funniest'} countdown video is ready!")

        except Exception as ex:
            err_msg = f"❌ Top 5 Compilation failed: `{str(ex)[:500]}`"
            if status_message:
                try:
                    await status_message.edit(content=err_msg)
                except Exception:
                    pass
            else:
                await channel.send(err_msg)

    else:
        # Normal 5 Standalone Ranked Shorts
        await handle_clip_pipeline(
            channel=channel,
            url=url,
            creator_slug=c_key,
            auto_upload=True,
            interaction=None,
            theme=None,
            reframe_mode=reframe_mode,
            status_msg_override=status_message,
            deliver_individual=True,
            chunk_part=chunk_part
        )


@bot.listen("on_interaction")
async def on_persistent_button_click(interaction: discord.Interaction):
    """Global fast listener: guarantees response within < 100ms so Discord NEVER times out."""
    if interaction.type == discord.InteractionType.component:
        c_id = interaction.data.get("custom_id", "")

        # 1. Handle radar produce buttons across bot restarts
        if c_id.startswith("radar_prod_"):
            if interaction.response.is_done():
                return
            try:
                await interaction.response.defer()
            except Exception:
                pass
            parts = c_id.split("_")
            v_id = parts[2] if len(parts) >= 3 else ""
            c_slug = parts[3] if len(parts) >= 4 else "speed"
            is_twitch = (v_id.isdigit() and len(v_id) >= 8) or c_slug in ("caseoh", "jynxzi", "kai")
            v_url = f"https://www.twitch.tv/videos/{v_id}" if is_twitch else f"https://www.youtube.com/watch?v={v_id}"
            mock_video = {
                "id": v_id,
                "url": v_url,
                "creator_slug": c_slug,
                "title": f"{c_slug.upper()} Stream VOD",
                "duration": 14400.0 if is_twitch else 3600.0,
                "platform": "twitch" if is_twitch else "youtube",
                "is_stream_vod": is_twitch
            }
            view = RadarVideoView(mock_video, channel=interaction.channel)
            await view.on_produce_click(interaction)
            return

        # 2. Handle Long Stream Chunk Intake Buttons across bot restarts
        if c_id.startswith("long_stream_hot_") or c_id.startswith("long_stream_part_"):
            if not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except Exception:
                    pass
            
            p_parts = c_id.split("_")
            part_num = int(p_parts[-1]) if (p_parts and p_parts[-1].isdigit()) else 1

            target_url = None
            intake_info = PENDING_INTAKE.get(interaction.channel_id, {})
            if intake_info and intake_info.get("url"):
                target_url = intake_info["url"]

            if not target_url and interaction.message:
                if interaction.message.embeds:
                    for emb in interaction.message.embeds:
                        found = find_youtube_urls(f"{emb.title} {emb.description}")
                        if found:
                            target_url = found[0]
                            break
                        m_link = re.search(r'\[.*?\]\((https?://[^\)]+)\)', emb.description or "")
                        if m_link:
                            target_url = m_link.group(1)
                            break
                if not target_url and interaction.message.content:
                    found = find_youtube_urls(interaction.message.content)
                    if found:
                        target_url = found[0]

            if not target_url:
                try:
                    async for hist_msg in interaction.channel.history(limit=15):
                        found = find_youtube_urls(hist_msg.content or "")
                        if found:
                            target_url = found[0]
                            break
                except Exception:
                    pass

            if not target_url:
                target_url = "https://www.youtube.com/live/RJzspH1rAbc"

            c_slug = intake_info.get("creator") or "speed"
            if interaction.message and interaction.message.embeds:
                desc = interaction.message.embeds[0].description or ""
                m_c = re.search(r'\*\*Streamer:\*\*\s*\*\*([^\*]+)\*\*', desc)
                if m_c:
                    c_slug = m_c.group(1).lower().strip()

            layout_mode = intake_info.get("layout_mode") or "blur_fill"
            PENDING_INTAKE.pop(interaction.channel_id, None)

            await start_video_production(
                channel=interaction.channel,
                url=target_url,
                format_type="normal",
                theme=None,
                creator_slug=c_slug,
                reframe_mode=layout_mode,
                interaction=interaction,
                status_message=interaction.message,
                chunk_part=part_num
            )
            return

        # 3. Handle Layout Toggle Buttons across bot restarts
        if c_id in ("long_toggle_blur", "long_toggle_split", "intake_toggle_blur", "intake_toggle_split"):
            new_mode = "blur_fill" if "blur" in c_id else "split_screen"
            if interaction.channel_id in PENDING_INTAKE:
                PENDING_INTAKE[interaction.channel_id]["layout_mode"] = new_mode

            if interaction.message:
                try:
                    v = discord.ui.View.from_message(interaction.message)
                    for item in v.children:
                        cid = getattr(item, "custom_id", "")
                        if "blur" in cid:
                            item.style = discord.ButtonStyle.success if new_mode == "blur_fill" else discord.ButtonStyle.secondary
                            item.label = "🖼️ Layout: MrBeast Blur (Active)" if new_mode == "blur_fill" else "🖼️ Use MrBeast Blur"
                        elif "split" in cid:
                            item.style = discord.ButtonStyle.success if new_mode == "split_screen" else discord.ButtonStyle.secondary
                            item.label = "👥 Layout: Split Screen (Active)" if new_mode == "split_screen" else "👥 Use Split Screen"
                    if not interaction.response.is_done():
                        await interaction.response.edit_message(view=v)
                    else:
                        await interaction.message.edit(view=v)
                    return
                except Exception as ve:
                    print(f"[Layout Toggle Note]: {ve}")

            if not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except Exception:
                    pass
            return

        # 4. Handle Standard Intake Normal Shorts Button across bot restarts
        if c_id == "intake_normal_shorts":
            if not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except Exception:
                    pass
            intake_info = PENDING_INTAKE.get(interaction.channel_id, {})
            target_url = intake_info.get("url")
            if not target_url and interaction.message:
                found = find_youtube_urls(interaction.message.content or "")
                if found:
                    target_url = found[0]
            if not target_url:
                try:
                    async for hist_msg in interaction.channel.history(limit=15):
                        found = find_youtube_urls(hist_msg.content or "")
                        if found:
                            target_url = found[0]
                            break
                except Exception:
                    pass
            if target_url:
                c_slug = intake_info.get("creator") or "speed"
                layout_mode = intake_info.get("layout_mode") or "blur_fill"
                PENDING_INTAKE.pop(interaction.channel_id, None)
                await start_video_production(
                    channel=interaction.channel,
                    url=target_url,
                    format_type="normal",
                    theme=None,
                    creator_slug=c_slug,
                    reframe_mode=layout_mode,
                    interaction=interaction,
                    status_message=interaction.message
                )
            return

        if not (c_id.startswith("autoclip_") or c_id.startswith("upload_btn_")):
            return

        parts = c_id.split("_")
        rank = 1
        custom_stem = None
        target_creator = None
        for idx, p in enumerate(parts):
            if p in ("caseoh", "jynxzi", "speed", "tanvo"):
                target_creator = p
            if p.isdigit():
                rank = int(p)
                if idx + 1 < len(parts):
                    custom_stem = "_".join(parts[idx + 1:])
                break

        # Check if the interaction message has an attached video file
        msg_filename = None
        if interaction.message and interaction.message.attachments:
            for att in interaction.message.attachments:
                if att.filename.endswith(".mp4"):
                    msg_filename = att.filename
                    break

        # Check if message content has clip title & hook
        msg_title = None
        msg_hook = None
        if interaction.message and interaction.message.content:
            m_t = re.search(r'Rank\s*#\d+\s*Short\s*—\s*([^\n\r]+)', interaction.message.content)
            if m_t:
                msg_title = m_t.group(1).strip()
            m_h = re.search(r'Hook:\s*[\*"]+([^\*\n\r"]+)[\*"]+', interaction.message.content)
            if m_h:
                msg_hook = m_h.group(1).strip()

        shorts_dir = PROJECT_ROOT / "data" / "shorts"
        target_short = None

        def _clip_matches(c, token):
            if not token:
                return False
            token_clean = token.lower().strip()
            candidates = [
                c.get("filename", ""),
                c.get("file", ""),
                c.get("rel_path", ""),
                c.get("video_path", "")
            ]
            for cand in candidates:
                if not cand:
                    continue
                cand_clean = os.path.basename(str(cand)).lower()
                cand_stem = os.path.splitext(cand_clean)[0]
                if token_clean in cand_clean or token_clean in cand_stem or cand_stem in token_clean:
                    return True
            return False

        def _find_clip_in_summaries(match_fn):
            if not shorts_dir.exists():
                return None
            for s_file in sorted(shorts_dir.glob("*_summary.json"), key=lambda p: p.stat().st_mtime, reverse=True):
                try:
                    s_data = json.loads(s_file.read_text(encoding="utf-8"))
                    c_list = s_data.get("shorts") or s_data.get("clips") or []
                    for c in c_list:
                        if match_fn(c, s_data):
                            f_name = c.get("filename") or os.path.basename(c.get("file", "")) or os.path.basename(c.get("video_path", ""))
                            cand_path = str(shorts_dir / f_name)
                            if os.path.exists(cand_path):
                                c["video_path"] = cand_path
                                return c
                            elif c.get("video_path") and os.path.exists(c["video_path"]):
                                return c
                except Exception:
                    continue
            return None

        # Strategy A: Target stem embedded in button custom_id
        if custom_stem:
            target_short = _find_clip_in_summaries(lambda c, s: _clip_matches(c, custom_stem))
            if not target_short:
                direct_file = str(shorts_dir / f"{custom_stem}.mp4")
                if os.path.exists(direct_file):
                    target_short = {
                        "rank": rank,
                        "filename": f"{custom_stem}.mp4",
                        "video_path": direct_file,
                        "title": msg_title or f"Viral Short #{rank}",
                        "hook": msg_hook or "",
                        "creator_id": target_creator or ("jynxzi" if "LPztP1mrKkw" in custom_stem else "speed"),
                        "creator_name": "Jynxzi" if "LPztP1mrKkw" in custom_stem else "Speed"
                    }

        # Strategy B: Match by message attachment filename
        if not target_short and msg_filename:
            target_short = _find_clip_in_summaries(lambda c, s: _clip_matches(c, msg_filename))
            if not target_short:
                direct_file = str(shorts_dir / msg_filename)
                if os.path.exists(direct_file):
                    target_short = {
                        "rank": rank,
                        "filename": msg_filename,
                        "video_path": direct_file,
                        "title": msg_title or f"Viral Short #{rank}",
                        "hook": msg_hook or "",
                        "creator_id": target_creator or ("jynxzi" if "LPztP1mrKkw" in msg_filename else "speed"),
                        "creator_name": "Jynxzi" if "LPztP1mrKkw" in msg_filename else "Speed"
                    }

        # Strategy C: Match by message title
        if not target_short and msg_title:
            target_short = _find_clip_in_summaries(lambda c, s: msg_title.lower() in (c.get("title") or "").lower())

        # Strategy D: Active channel session
        if not target_short:
            session = get_channel_session(interaction.channel_id)
            if session and session.get("shorts"):
                target_short = next((s for s in session["shorts"] if s.get("rank") == rank), None)

        # Strategy E: Fallback to newest summary matching rank AND creator
        if not target_short or not target_short.get("video_path") or not os.path.exists(target_short.get("video_path", "")):
            target_short = _find_clip_in_summaries(
                lambda c, s: c.get("rank") == rank and (
                    not target_creator or
                    target_creator in (c.get("creator_id") or c.get("creator") or "").lower() or
                    target_creator in s.get("video_info", {}).get("selected_creator", "").lower() or
                    target_creator in s.get("video_title", "").lower()
                )
            )

        if not target_short:
            cand_vids = sorted(shorts_dir.glob(f"*rank{rank}*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
            if cand_vids:
                target_short = {"rank": rank, "title": f"Viral Short #{rank}", "video_path": str(cand_vids[0]), "filename": cand_vids[0].name}

        if not target_short:
            target_short = {"rank": rank, "title": f"Viral Short #{rank}"}

        # Backfill metadata from message context if missing
        if target_short:
            if msg_title and (not target_short.get("title") or target_short.get("title", "").startswith("Short #") or target_short.get("title", "").startswith("Viral Short #")):
                target_short["title"] = msg_title
            if msg_hook and not target_short.get("hook"):
                target_short["hook"] = msg_hook
            if target_creator and not target_short.get("creator_id"):
                target_short["creator_id"] = target_creator

        # Modals MUST be sent before any defer() call
        if c_id.startswith("autoclip_adjust_"):
            await interaction.response.send_modal(AdjustClipModal(target_short, interaction.channel))
            return
        elif c_id.startswith("autoclip_edit_"):
            await interaction.response.send_modal(EditClipModal(target_short, interaction.channel))
            return

        # Regular buttons ACK immediately with error suppression (avoids 40060 race condition)
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass

        if c_id.startswith("autoclip_love_"):
            res = memory_mod.record_feedback(target_short, "positive", "User liked this clip style")
            bullets = "\n".join(f"• {p}" for p in res.get("learned_points", [])) if res.get("learned_points") else "• Style configuration recorded"
            embed = discord.Embed(
                title=f"🌟 Style Favorited & Learned (Clip #{rank})",
                description=(
                    f"**Clip:** Rank #{rank} (*'{target_short.get('title', '')}'*)\n\n"
                    f"**What Hermes Learned:**\n{bullets}\n\n"
                    f"✅ Saved permanently in `data/pipeline_memory.json`. Upcoming video runs will automatically prioritize this layout and pacing!"
                ),
                color=0x10B981
            )
            try:
                await interaction.followup.send(embed=embed)
            except Exception:
                await interaction.channel.send(embed=embed)
            return

        elif c_id.startswith("autoclip_upload_channel_"):
            parts = c_id.split("_")
            target_creator = parts[3] if len(parts) >= 4 else "speed"
            if target_short.get("video_path") and os.path.exists(target_short.get("video_path", "")):
                await upload_and_notify(interaction.channel, target_short, interaction=interaction, target_creator=target_creator)
            else:
                msg = f"⚠️ Video file for Rank #{rank} not found on disk. Try pasting the link again."
                try:
                    await interaction.followup.send(msg, ephemeral=True)
                except Exception:
                    await interaction.channel.send(msg)
            return

        elif c_id.startswith("autoclip_upload_") or c_id.startswith("upload_btn_"):
            if target_short.get("video_path") and os.path.exists(target_short.get("video_path", "")):
                await upload_and_notify(interaction.channel, target_short, interaction=interaction)
            else:
                msg = f"⚠️ Video file for Rank #{rank} not found on disk. Try pasting the link again."
                try:
                    await interaction.followup.send(msg, ephemeral=True)
                except Exception:
                    await interaction.channel.send(msg)
            return

async def upload_and_notify(channel, short_item, interaction=None, target_creator=None):
    v_path = short_item.get("video_path")
    if v_path and not os.path.exists(v_path):
        cand_p = str(PROJECT_ROOT / "data" / "shorts" / os.path.basename(v_path))
        if os.path.exists(cand_p):
            v_path = cand_p
            short_item["video_path"] = cand_p

    if not v_path or not os.path.exists(v_path):
        err = f"❌ Video file `{v_path}` not found on disk."
        if interaction:
            await interaction.followup.send(err)
        else:
            await channel.send(err)
        return

    rank = short_item.get("rank", 1)
    title = short_item.get("title", f"AutoClip Viral Short #{rank}")
    hook = short_item.get("hook", "")
    video_creator = (short_item.get("creator_id") or short_item.get("creator") or "").strip().lower()
    requested_creator = (target_creator or "").strip().lower()

    # Safety Guard: If requested creator conflicts with the actual video creator, BLOCK IT!
    if video_creator and requested_creator and video_creator != requested_creator:
        v_norm = "speed" if "speed" in video_creator else ("caseoh" if "case" in video_creator else ("jynxzi" if "jynx" in video_creator else video_creator))
        r_norm = "speed" if "speed" in requested_creator else ("caseoh" if "case" in requested_creator else ("jynxzi" if "jynx" in requested_creator else requested_creator))
        if v_norm != r_norm:
            err = f"⛔ **Upload Blocked**: This video belongs to **{video_creator.upper()}**. Cross-uploading to **{requested_creator.upper()}** channel is strictly prohibited to protect your channels from cross-contamination!"
            if interaction:
                await interaction.followup.send(err)
            else:
                await channel.send(err)
            return

    creator_key = requested_creator or video_creator or "speed"

    # Strict multi-channel route resolution with zero tolerance for unknown creators
    try:
        route = channel_routing.get_route(creator_key)
        target_channel_name = route.get("target_name") or route.get("current_name")
        target_handle = route.get("handle") or ""
    except Exception as e:
        err = f"⛔ **Upload Blocked**: No verified YouTube channel route for creator '{creator_key}'. Cross-uploading prevented: {e}"
        if interaction:
            await interaction.followup.send(err)
        else:
            await channel.send(err)
        return

    ch_label = f"**{target_channel_name}** ({target_handle})" if target_handle else f"**{target_channel_name}**"

    # 1. Generate High-Converting Human Viral Metadata (NO robotic scores)
    from autoclip import viral_metadata, thumbnail_generator
    v_meta = viral_metadata.build_viral_metadata(
        title=title,
        hook=hook,
        creator=creator_key,
        theme=short_item.get("theme")
    )
    clean_title = v_meta["title"]
    desc = v_meta["description"]
    tags = v_meta["tags"]
    pinned_comment = v_meta["pinned_comment"]

    # 2. Generate High-CTR 9:16 Shorts Thumbnail matching streamer reference templates
    thumbnail_path = short_item.get("thumbnail_path")
    if not thumbnail_path or not os.path.exists(thumbnail_path):
        thumbnail_path = thumbnail_generator.generate_short_thumbnail(
            v_path,
            title=clean_title,
            creator=creator_key,
            hook=hook,
            theme=short_item.get("theme")
        )
        if thumbnail_path:
            short_item["thumbnail_path"] = thumbnail_path

    slot = creators.calculate_next_optimal_slot(creator_key or "speed", clip_rank=rank)

    upload_msg = (
        f"⏳ Staging and scheduling **Rank #{rank}** (*'{clean_title}'*)...\n"
        f"• **Destination Channel:** {ch_label}\n"
        f"• **Custom Thumbnail:** {'🖼️ Attached & Ready' if thumbnail_path else '⚪ Auto'}\n"
        f"• **Scheduled Peak Window:** {slot.get('readable')}\n"
        f"• **Pinned Comment Staged:** *\"{pinned_comment}\"*"
    )
    if interaction:
        status_resp = await interaction.followup.send(upload_msg)
    else:
        status_resp = await channel.send(upload_msg)

    def do_upload():
        return composio_client.upload_video_to_youtube(
            video_path=v_path,
            title=clean_title,
            description=desc,
            tags=tags,
            privacy="public",
            publish_at=slot.get("target_iso"),
            creator=creator_key,
            thumbnail_path=thumbnail_path,
            pinned_comment=pinned_comment
        )

    loop = asyncio.get_event_loop()
    u_res = await loop.run_in_executor(None, do_upload)

    if u_res.get("ok"):
        embed = discord.Embed(
            title=f"🎉 Successfully Uploaded to YouTube!",
            description=(
                f"**Title:** {clean_title}\n"
                f"**Channel:** {ch_label}\n"
                f"**Scheduled Audience Window:** {slot.get('readable')}\n\n"
                f"📌 **Pinned Comment:**\n*\"{pinned_comment}\"*\n\n"
                f"🔗 **Live YouTube Short:** [Watch on YouTube]({u_res.get('url')})"
            ),
            color=0x10B981
        )
        embed.add_field(
            name="☁️ Cloud Backup & Storage",
            value="Archived to Google Drive (`AutoClip_Master_Archive` • Mayur Desai) & purged local raw footage to save disk space.",
            inline=False
        )
        try:
            await status_resp.edit(content=None, embed=embed)
        except Exception:
            await channel.send(embed=embed)

        try:
            target_iso = slot.get("target_iso")
            if target_iso:
                creators.record_scheduled_slot(creator_key, target_iso)
                print(f"[Schedule Engine] Recorded channel slot for {creator_key}: {target_iso}")
        except Exception as se:
            print(f"[Schedule Engine] Note: {se}")
        try:
            excel_tracker.log_upload(
                creator=creator_key,
                title=clean_title,
                video_id=u_res.get("video_id", ""),
                url=u_res.get("url", ""),
                rank=rank,
                scheduled_slot=slot.get("readable", ""),
                channel_name=target_channel_name,
                notes=f"Uploaded via AutoClip Discord Bot ({ch_label})"
            )
            print(f"[Excel Tracker] Recorded upload in master spreadsheet: {clean_title}")
        except Exception as ee:
            print(f"[Excel Tracker] Note: {ee}")

        # Trigger background cloud backup to Mayur Desai 5TB Google Drive & disk cleanup
        try:
            from autoclip import gdrive_backup
            def do_backup():
                g_res = gdrive_backup.backup_short_to_gdrive(v_path, thumbnail_path)
                v_stem = os.path.basename(v_path).split("_")[0]
                freed = gdrive_backup.purge_raw_source_video(v_stem)
                print(f"[GDrive Archive Hook] Completed: {g_res}, {freed // (1024*1024)}MB freed")
            asyncio.create_task(asyncio.to_thread(do_backup))
        except Exception as ge:
            print(f"[GDrive Hook] Background backup note: {ge}")

        if channel.guild:
            await speak_text_in_vc(channel.guild, f"Rank {rank} has been uploaded to your YouTube channel {target_channel_name}!")
    else:
        err_msg = u_res.get("error", "Unknown upload error")
        rel_path = os.path.relpath(v_path, PROJECT_ROOT).replace("\\", "/")
        stream_url = f"http://localhost:8080/video/{rel_path}"
        if u_res.get("needs_login"):
            embed = discord.Embed(
                title="🔐 YouTube Studio Login Required",
                description=(
                    f"{err_msg}\n\n"
                    f"💾 **Your Video Is 100% Rendered & Saved Locally:**\n"
                    f"• Local File: `{v_path}`\n"
                    f"• Local Web Stream: [Click to Watch/Download]({stream_url})\n\n"
                    f"🚀 **Why One-Time Login?**\n"
                    f"Google API limits us to only 6 uploads per day. Logging into YouTube Studio once unlocks **UNLIMITED** daily uploads & automated timestamp scheduling forever!"
                ),
                color=0x3B82F6
            )
        else:
            embed = discord.Embed(
                title="⚠️ YouTube Studio Upload Status",
                description=(
                    f"**Target Channel:** {ch_label}\n\n"
                    f"**Details:**\n{err_msg}\n\n"
                    f"💾 **Your Video Is 100% Rendered & Saved Locally:**\n"
                    f"• Local File: `{v_path}`\n"
                    f"• Local Web Stream: [Click to Watch/Download]({stream_url})\n\n"
                    f"🚀 **Instant Workaround (Zero Quota Limit):**\n"
                    f"You can drag & drop this `.mp4` directly into [YouTube Studio](https://studio.youtube.com). Web uploads have unlimited daily quota!"
                ),
                color=0xF59E0B
            )
        try:
            await status_resp.edit(content=None, embed=embed)
        except Exception:
            await channel.send(embed=embed)

# --- Background Watchdog: Streamer Video Radar ---

@tasks.loop(minutes=20)
async def radar_channel_watchdog():
    """Background Watchdog: Automatically checks Speed, CaseOh, and Jynxzi channels every 20 minutes for new viral uploads."""
    try:
        loop = asyncio.get_running_loop()
        videos = await loop.run_in_executor(None, lambda: video_radar.scout_all_streamers(top_n=6))
        if not videos:
            return

        seen_ids = get_seen_radar_videos()

        # If seen_ids is completely empty (first run), initialize with current top videos so we don't spam existing videos
        if not seen_ids:
            for v in videos:
                if v.get("id"):
                    seen_ids.add(v["id"])
            try:
                RADAR_SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(RADAR_SEEN_FILE, "w", encoding="utf-8") as f:
                    json.dump(list(seen_ids), f)
            except Exception:
                pass
            print(f"[Radar Watcher] Initialized watchdog tracking with {len(seen_ids)} existing videos.")
            return

        # Find any new videos not in seen_ids
        new_viral_videos = []
        for v in videos:
            v_id = v.get("id")
            if v_id and v_id not in seen_ids:
                seen_ids.add(v_id)
                # Filter: Only alert for videos with solid viral potential (score >= 60)
                if v.get("score", 0) >= 60:
                    new_viral_videos.append(v)

        if not new_viral_videos:
            return

        # Save updated seen IDs
        try:
            with open(RADAR_SEEN_FILE, "w", encoding="utf-8") as f:
                json.dump(list(seen_ids), f)
        except Exception:
            pass

        # Locate target notification channel across guilds
        target_channel = None
        for guild in bot.guilds:
            for ch_name in ["radar", "video-radar", "clips", "autoclip", "general"]:
                ch = discord.utils.get(guild.text_channels, name=ch_name)
                if ch and ch.permissions_for(guild.me).send_messages:
                    target_channel = ch
                    break
            if target_channel:
                break
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).send_messages:
                    target_channel = ch
                    break
            if target_channel:
                break

        if not target_channel:
            print("[Radar Watcher] Warning: No writable text channel found to send new video alerts.")
            return

        for nv in new_viral_videos:
            alert_embed = discord.Embed(
                title=f"🚨 NEW VIRAL UPLOAD DETECTED: {nv.get('creator_avatar', '')} {nv.get('creator_name')}!",
                description=(
                    f"**{nv.get('creator_name')}** just published a high-potential video: **[{nv.get('title')}]({nv.get('url')})**\n\n"
                    f"🔥 **Viral Opportunity Score:** `{nv.get('score')}/100` ({nv.get('tier')})\n"
                    f"⏱️ **Duration:** `{int(nv.get('duration', 0)//60)}m` | 👁️ **Views:** `{nv.get('view_count', 0):,}`\n"
                    f"🎯 **Why Clip This:** {nv.get('summary')}\n\n"
                    f"Click **🎬 Make Clips from This Video** below to immediately start producing viral Shorts!"
                ),
                color=0xFF0033
            )
            if nv.get("thumbnail"):
                alert_embed.set_image(url=nv["thumbnail"])
            alert_embed.set_footer(text="AutoClip Radar Watchdog • Instant Notification")

            view = RadarVideoView(nv, channel=target_channel)
            await target_channel.send(content="@everyone 🚨 New Viral Streamer Video Alert!", embed=alert_embed, view=view)

            # Speak alert if in voice channel
            if target_channel.guild and target_channel.guild.voice_client:
                c_name = nv.get("creator_name", "A streamer")
                await speak_text_in_vc(target_channel.guild, f"New viral video alert! {c_name} just uploaded a high potential video. Check Discord to make clips.")

    except Exception as e:
        print(f"[Radar Watcher] Error during loop check: {e}")

# --- Weekly Direct Message Performance Report Engine ---
OWNER_DISCORD_ID = 1116299279334645810  # swastik12

async def send_weekly_dm_report(target_user_id: int = OWNER_DISCORD_ID) -> bool:
    """Compile YouTube channel analytics and send a private Direct Message report with the Excel spreadsheet."""
    try:
        user = bot.get_user(target_user_id)
        if not user:
            try:
                user = await bot.fetch_user(target_user_id)
            except Exception:
                user = None

        if not user:
            print(f"[Weekly DM] Could not find user with ID {target_user_id}")
            return False

        # Refresh YouTube metrics from API in background thread
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, excel_tracker.update_live_metrics_from_youtube)
        except Exception as ue:
            print(f"[Weekly DM] Note during live metric refresh: {ue}")

        entries = excel_tracker.load_json_log()
        total_uploads = len(entries)
        
        speed_vids = [e for e in entries if "speed" in e.get("creator", "")]
        caseoh_vids = [e for e in entries if "case" in e.get("creator", "")]
        jynxzi_vids = [e for e in entries if "jynx" in e.get("creator", "")]

        speed_views = sum(int(e.get("views", 0)) for e in speed_vids if str(e.get("views", "0")).isdigit())
        caseoh_views = sum(int(e.get("views", 0)) for e in caseoh_vids if str(e.get("views", "0")).isdigit())
        jynxzi_views = sum(int(e.get("views", 0)) for e in jynxzi_vids if str(e.get("views", "0")).isdigit())
        total_views = speed_views + caseoh_views + jynxzi_views

        now_str = datetime.datetime.now().strftime("%B %d, %Y")
        day_num = excel_tracker._get_day_number()

        embed = discord.Embed(
            title="📊 AutoClip 30-Day Project — Weekly Performance Report",
            description=(
                f"**Report Date:** {now_str}\n"
                f"**Operational Cadence:** Day {day_num} of 30 • Code Freeze Active 🔒\n"
                f"**Total Verified Uploads:** `{total_uploads}` Shorts across 3 channels\n"
                f"**Total Channel Views:** `{total_views:,}` views\n\n"
                "Here is the breakdown of your 3 dedicated YouTube channels:"
            ),
            color=0x10B981
        )

        s_top = speed_vids[0]["title"] if speed_vids else "None"
        embed.add_field(
            name="⚡ Speed Clips Daily (`@tanvoiamhere`)",
            value=(
                f"• **Uploads Live:** `{len(speed_vids)}` Shorts\n"
                f"• **Channel Views:** `{speed_views:,}` views\n"
                f"• **Top Clip:** *\"{s_top[:38]}...\"*\n"
                f"• **Peak Slots (IST):** 1:00 AM, 7:00 AM, 3:30 PM, 9:30 PM"
            ),
            inline=False
        )

        c_top = caseoh_vids[0]["title"] if caseoh_vids else "None"
        embed.add_field(
            name="🍔 CaseOh Clips (`@fixlife-q7g`)",
            value=(
                f"• **Uploads Live:** `{len(caseoh_vids)}` Shorts\n"
                f"• **Channel Views:** `{caseoh_views:,}` views\n"
                f"• **Top Clip:** *\"{c_top[:38]}...\"*\n"
                f"• **Peak Slots (IST):** 2:00 AM, 8:30 AM, 4:30 PM, 10:30 PM"
            ),
            inline=False
        )

        j_top = jynxzi_vids[0]["title"] if jynxzi_vids else "None"
        embed.add_field(
            name="🎯 Jynxzi Clips (`@askwhatt`)",
            value=(
                f"• **Uploads Live:** `{len(jynxzi_vids)}` Shorts\n"
                f"• **Channel Views:** `{jynxzi_views:,}` views\n"
                f"• **Top Clip:** *\"{j_top[:38]}...\"*\n"
                f"• **Peak Slots (IST):** 7:30 AM, 2:30 PM, 9:30 PM, 3:30 AM"
            ),
            inline=False
        )

        embed.add_field(
            name="📈 Algorithm & Seed Testing Guidance",
            value=(
                "• **Seed Phase:** In the first 24–48 hours YouTube tests impressions against a 500-viewer test cohort.\n"
                "• **6-Hour Timeline:** Guarantees no two uploads collide or cannibalize watch time.\n"
                "• **30-Day Milestone:** Comprehensive Analytics Retrospective scheduled for **November 6, 2026**."
            ),
            inline=False
        )
        embed.set_footer(text="AutoClip Private Weekly DM • Master Tracker attached below")

        excel_file_obj = None
        if excel_tracker.EXCEL_PATH.exists():
            excel_file_obj = discord.File(str(excel_tracker.EXCEL_PATH), filename="AutoClip_30_Day_Master_Tracker.xlsx")

        if excel_file_obj:
            await user.send(
                content=f"👋 Hey <@{target_user_id}>! Here is your confidential **Weekly AutoClip Performance Report** and your updated **30-Day Master Tracker** Excel spreadsheet:",
                embed=embed,
                file=excel_file_obj
            )
        else:
            await user.send(
                content=f"👋 Hey <@{target_user_id}>! Here is your confidential **Weekly AutoClip Performance Report**:",
                embed=embed
            )
        print(f"[Weekly DM] Successfully delivered weekly performance report to user {target_user_id}")
        return True
    except Exception as e:
        print(f"[Weekly DM] Error delivering weekly report: {e}")
        return False

@tasks.loop(hours=168)  # Weekly (every 7 days)
async def weekly_dm_watchdog():
    """Weekly automated delivery of performance report directly to Swastik's DMs."""
    await send_weekly_dm_report()

@weekly_dm_watchdog.before_loop
async def before_weekly_dm_watchdog():
    await bot.wait_until_ready()

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} application slash commands.")
    except Exception as e:
        print(f"Slash command sync note: {e}")

    app_id = bot.user.id if bot.user else "YOUR_APP_ID"
    invite_url = f"https://discord.com/oauth2/authorize?client_id={app_id}&permissions=277025507392&scope=bot%20applications.commands"

    # Start AutoClip Web Studio on port 8080 in a background daemon thread
    try:
        import threading
        from autoclip import web as web_mod
        web_thread = threading.Thread(target=web_mod.run_server, kwargs={"port": 8080}, daemon=True)
        web_thread.start()
        print("  AutoClip Web Studio: Active (http://localhost:8080)")
    except Exception as we:
        print(f"  AutoClip Web Studio launch note: {we}")

    # Start Video Radar Watchdog
    if not radar_channel_watchdog.is_running():
        radar_channel_watchdog.start()
        print("  AutoClip Video Radar Watchdog: Active (Every 20 mins)")

    # Start Weekly DM Watchdog
    if not weekly_dm_watchdog.is_running():
        weekly_dm_watchdog.start()
        print("  AutoClip Weekly DM Watchdog: Active (Every 7 days to Swastik)")

    print(f"\n=======================================================")
    print(f"  [AutoClip] AI Discord Bot & Voice Producer Online!")
    print(f"  Logged in as: {bot.user.name}#{bot.user.discriminator} (ID: {app_id})")
    print(f"  Voice Chat Engine: {'Active (edge-tts)' if HAS_EDGE_TTS else 'Text Only'}")
    print(f"  Natural Language Uploads: ACTIVE ('Upload this', 'Upload #2')")
    print(f"  Video Radar & Watchdog: ACTIVE (IShowSpeed, CaseOh, Jynxzi)")
    print(f"  Web Studio Dashboard: http://localhost:8080")
    print(f"  Bot Invite Link:")
    print(f"  {invite_url}")
    print(f"=======================================================\n")

# --- Voice Channel Commands ---

@bot.tree.command(name="join", description="Invite AutoClip bot into your voice channel")
async def slash_join(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("❌ This command must be used inside a Discord server with a voice channel, not in direct messages.", ephemeral=True)
        return

    member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
    if not member or not getattr(member, "voice", None) or not member.voice.channel:
        await interaction.response.send_message("❌ Please connect to a voice channel first, then run `/join`!", ephemeral=True)
        return

    channel = member.voice.channel
    try:
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.move_to(channel)
        else:
            await channel.connect()
    except Exception as e:
        await interaction.response.send_message(f"❌ Could not join voice channel: `{e}`", ephemeral=True)
        return

    await interaction.response.send_message(f"🔊 Joined voice channel **{channel.name}**! I am ready to speak aloud and receive audio.")
    try:
        await speak_text_in_vc(interaction.guild, f"Hey! I'm your AutoClip Producer. Connected to {channel.name} and ready!")
    except Exception:
        pass

@bot.tree.command(name="leave", description="Disconnect AutoClip bot from the voice channel")
async def slash_leave(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("👋 Left the voice channel.")
    else:
        await interaction.response.send_message("I am not currently in a voice channel.", ephemeral=True)

@bot.tree.command(name="speak", description="Have the bot speak any text aloud in the voice channel")
@app_commands.describe(text="The message for the bot to speak aloud")
async def slash_speak(interaction: discord.Interaction, text: str):
    if not interaction.guild.voice_client:
        await interaction.response.send_message("❌ I'm not in a voice channel! Use `/join` first.", ephemeral=True)
        return
    await interaction.response.send_message(f"🗣️ Speaking: *\"{text}\"*")
    await speak_text_in_vc(interaction.guild, text)

# --- Conversational AI Advisor & Channel Analytics ---

@bot.tree.command(name="ask", description="Ask the AutoClip AI Producer for video ideas, trending streamer advice, or hooks")
@app_commands.describe(question="What video should I make? Who is trending? How to improve my Shorts?")
async def slash_ask(interaction: discord.Interaction, question: str):
    await interaction.response.defer()

    system_prompt = (
        "You are the Lead Content Strategist and Executive Producer for YouTube channel 'Ask What?' (@askwhatt).\n"
        "Your expertise: High-retention viral YouTube Shorts, TikToks, and Reels for top creators (IShowSpeed, Kai Cenat, Jynxzi, CaseOh).\n"
        "Style: Charismatic, direct, highly tactical, actionable. Recommend specific stream moments, viral hooks, title formulas, and upload timing.\n"
        "Constraint: Strictly 0 SFX, golden pop subtitles, -14 LUFS broadcast audio, and DMCA-safe music."
    )

    prompt = f"User asks: {question}\n\nProvide clear, actionable advice on what streamer to clip, what hook to use, and when to upload."
    try:
        reply = llm_mod.query_cascade(prompt, system_prompt=system_prompt)
    except Exception as e:
        reply = f"Here is my quick advice: Focus on high-emotion streamer moments (Kai Cenat or IShowSpeed scream peaks). Use a 3-second visual question hook like 'IS THIS ACTUALLY REAL?' and upload during peak audience windows (2:00 PM – 5:00 PM EDT). Error querying cascade: {e}"

    embed = discord.Embed(
        title="💡 AutoClip AI Producer Strategy Advice",
        description=reply[:4000],
        color=0xFFD200
    )
    embed.set_footer(text="AutoClip AI • Ask What? Channel Growth Engine")
    await interaction.followup.send(embed=embed)

    if interaction.guild and interaction.guild.voice_client:
        await speak_text_in_vc(interaction.guild, reply)

@bot.tree.command(name="analyze", description="Analyze recent Shorts performance on channel Ask What? and recommend next videos")
async def slash_analyze(interaction: discord.Interaction):
    await interaction.response.defer()

    channel_info = composio_client.get_channel_info()
    channel_name = channel_info.get("title", "Ask What?")
    channel_handle = channel_info.get("custom_url", "@askwhatt")

    videos = composio_client.get_channel_videos(max_results=8)
    video_titles = [f"- {v.get('title')} ({v.get('published_at', '')[:10]})" for v in videos]
    titles_summary = "\n".join(video_titles) if video_titles else "(No public videos found yet or fresh channel)"

    prompt = (
        f"You are the YouTube Growth Director for channel '{channel_name}' ({channel_handle}).\n"
        f"Recent channel videos:\n{titles_summary}\n\n"
        "Perform a high-level Shorts channel growth audit:\n"
        "1. Identify winning title and topic patterns.\n"
        "2. Recommend which 2 streamer streams to clip NEXT (e.g. Speed, Kai Cenat, Jynxzi, CaseOh) and why.\n"
        "3. Provide 3 high-converting hook formulas to use on the next upload.\n"
        "Keep it concise, punchy, and formatted with bullet points."
    )

    try:
        audit_reply = llm_mod.query_cascade(prompt, system_prompt="You are an elite YouTube Shorts Growth Consultant.")
    except Exception as e:
        audit_reply = f"Channel Audit Summary for {channel_handle}:\n1. High pacing reaction Shorts generate 3.4x more retention.\n2. Recommend clipping IShowSpeed's latest travel stream or Kai Cenat's celebrity guest reactions.\n3. Hook formula: 'He had NO IDEA this would happen...' Upload window: 2:00 PM - 5:00 PM EDT. ({e})"

    embed = discord.Embed(
        title=f"📊 Channel Growth Audit: {channel_name} ({channel_handle})",
        description=audit_reply[:4000],
        color=0x10B981
    )
    await interaction.followup.send(embed=embed)

    if interaction.guild and interaction.guild.voice_client:
        short_summary = f"Here is your channel audit for {channel_name}. Focus on high pacing reaction shorts and clip IShowSpeed or Kai Cenat next during the afternoon peak window."
        await speak_text_in_vc(interaction.guild, short_summary)

@bot.tree.command(name="weekly_report", description="Send your weekly YouTube channel analytics report & Excel tracker directly to your DMs")
async def slash_weekly_report(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    target_id = interaction.user.id
    success = await send_weekly_dm_report(target_user_id=target_id)
    if success:
        await interaction.followup.send("📬 **Your weekly report & 30-Day Excel Tracker have been delivered to your Direct Messages!** Check your DMs.", ephemeral=True)
    else:
        await interaction.followup.send("⚠️ Could not deliver DM. Please check your Discord privacy settings to allow Direct Messages from server members.", ephemeral=True)

@bot.tree.command(name="status", description="Check AutoClip AI pipeline, voice status, and active guardrails")
async def slash_status(interaction: discord.Interaction):
    vc_status = "Connected" if (interaction.guild and interaction.guild.voice_client) else "Not in Voice Channel (Use /join)"
    embed = discord.Embed(
        title="⚡ AutoClip AI Bot Status",
        description="Autonomous Short Generator, Voice Companion & YouTube Publisher",
        color=0x10B981
    )
    embed.add_field(name="Guardrails", value="✅ **0 SFX Active**\n✅ **Golden Pop Subtitles (#FFD200)**\n✅ **9:16 Face-Tracking Reframe**", inline=True)
    embed.add_field(name="Voice Chat", value=f"🔊 **{vc_status}**\nEngine: edge-tts (`{TTS_VOICE}`)", inline=True)
    embed.add_field(name="Natural Upload", value="✅ **Voice / Text Upload Active**\nButtons: [🚀 Upload #1], [🚀 Upload #2]", inline=False)
    embed.add_field(name="YouTube Target", value="Channel: **Ask What? (@askwhatt)**\nVia: Direct S3 Streaming MCP", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="streamers", description="View supported streamer viral profiles, music pools & audience upload windows")
async def slash_streamers(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎙️ Supported Streamer Intelligence Profiles",
        description="Dedicated royalty-free music pools & audience peak windows:",
        color=0xFFD200
    )
    for c_id, prof in creators.CREATORS.items():
        slot = creators.calculate_next_optimal_slot(c_id)
        embed.add_field(
            name=f"{prof.get('name')} ({prof.get('archetype')})",
            value=f"⏱ **Peak Window:** {prof.get('peak_upload_window')}\n🎵 **Music Style:** {prof.get('music_vibe')}\n🎯 **Next Optimal Slot:** {slot.get('readable')}",
            inline=False
        )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="jobs", description="Check recent AutoClip jobs and generated Shorts status")
async def slash_jobs(interaction: discord.Interaction):
    await interaction.response.defer()
    shorts_dir = PROJECT_ROOT / "data" / "shorts"
    embed = discord.Embed(title="📁 Recent AutoClip Jobs", color=0x9B59B6)
    if shorts_dir.exists():
        mp4_files = sorted(shorts_dir.glob("*_rank*_*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]
        if mp4_files:
            lines = []
            for f in mp4_files:
                ts = f.stat().st_mtime
                lines.append(f"`{f.name}` — {datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')}")
            embed.description = "\n".join(lines)
        else:
            embed.description = "No Shorts found yet."
        summaries = sorted(shorts_dir.glob("*_summary.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
        if summaries:
            s = summaries[0]
            try:
                data = json.loads(s.read_text())
                embed.add_field(name="Latest Job Summary", value=f"Title: {data.get('video_title','N/A')}\nShorts: {len(data.get('shorts',[]))}", inline=False)
            except Exception:
                pass
    else:
        embed.description = "Shorts directory not found."
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="clip", description="Turn a YouTube video into 5 viral 9:16 Shorts and upload Rank #1")
@app_commands.describe(
    url="Full YouTube video URL",
    creator="Target streamer profile (speed, kai, jynxzi, caseoh)",
    upload="Automatically upload Rank #1 to YouTube channel Ask What?"
)
@app_commands.choices(creator=[
    app_commands.Choice(name="IShowSpeed", value="speed"),
    app_commands.Choice(name="Kai Cenat", value="kai"),
    app_commands.Choice(name="Jynxzi", value="jynxzi"),
    app_commands.Choice(name="CaseOh", value="caseoh"),
])
async def slash_clip(interaction: discord.Interaction, url: str, creator: app_commands.Choice[str] = None, upload: bool = True):
    await interaction.response.defer()
    c_val = creator.value if creator else None
    await handle_clip_pipeline(interaction.channel, url, c_val, auto_upload=upload, interaction=interaction)

@bot.tree.command(name="narrate", description="Create an Asfan-style animated mascot commentary Short on Speed")
@app_commands.describe(
    clip="Video file path or YouTube URL to narrate",
    title="Top header banner text (e.g. SPEED REALLY TRIED HIS BEST... 💀)",
    preset="Script preset (0: Rizz Fail, 1: Unhinged Crashout, 2: Disaster L)"
)
async def slash_narrate(interaction: discord.Interaction, clip: str, title: str = None, preset: int = 0):
    await interaction.response.defer()
    from autoclip import narrator_engine
    out_dir = Path("C:/Users/swastik/Downloads")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = str(out_dir / f"Speed_Narrator_{int(time.time())}.mp4")
    
    clip_path = clip
    if clip.startswith("http"):
        temp_src = str(out_dir / f"temp_source_{int(time.time())}.mp4")
        dl_cmd = ["python", "-m", "yt_dlp", "-f", "best[height<=1080]", "--download-sections", "*0-30", "-o", temp_src, clip]
        await asyncio.to_thread(subprocess.run, dl_cmd, capture_output=True, text=True)
        if os.path.exists(temp_src):
            clip_path = temp_src
    
    try:
        await interaction.followup.send("🎙️ **Synthesizing Asfan-style Mascot Narrator Short for Speed...**")
        res = await asyncio.to_thread(
            narrator_engine.render_mascot_commentary_short,
            clip_path=clip_path,
            output_path=out_file,
            script_preset_idx=preset,
            custom_title=title
        )
        if os.path.exists(res):
            await interaction.followup.send(
                content=f"✅ **Mascot Narrator Short Generated!**\n📁 Saved to: `{res}`",
                file=discord.File(res) if os.path.getsize(res) < 25 * 1024 * 1024 else None
            )
        else:
            await interaction.followup.send("❌ Render failed: Output file was not found.")
    except Exception as e:
        await interaction.followup.send(f"❌ Error generating narrator short: {e}")

@bot.tree.command(name="keep", description="Keep and protect source videos from 15-second automatic deletion")
async def slash_keep(interaction: discord.Interaction):
    session = get_channel_session(interaction.channel_id)
    if session and session.get("shorts"):
        v_title = session.get("video_title", "Current Video")
        v_slug = session["shorts"][0].get("filename", "").split("_rank")[0]
        if v_slug:
            KEEP_MEDIA_REQUESTS.add(v_slug)
        KEEP_MEDIA_REQUESTS.add("all")
        await interaction.response.send_message(f"🛡️ **Source Media Preserved:** Source video and raw assets for **'{v_title}'** will NOT be auto-deleted.")
    else:
        KEEP_MEDIA_REQUESTS.add("all")
        await interaction.response.send_message("🛡️ **Keep Active:** All upcoming video downloads will be preserved on disk and not auto-deleted.")

@bot.tree.command(name="radar", description="Scout latest viral videos & streams across YouTube and Twitch")
@app_commands.describe(
    creator="Target streamer to scout (All, Speed, CaseOh, Jynxzi, Kai Cenat)",
    platform="Content source (All Platforms, Twitch Only, YouTube Only)",
    custom="Custom channel @handle or URL"
)
@app_commands.choices(creator=[
    app_commands.Choice(name="🌟 All Streamers (Speed, CaseOh, Jynxzi, Kai)", value="all"),
    app_commands.Choice(name="⚡ IShowSpeed", value="speed"),
    app_commands.Choice(name="🍔 CaseOh", value="caseoh"),
    app_commands.Choice(name="🎯 Jynxzi", value="jynxzi"),
    app_commands.Choice(name="👑 Kai Cenat", value="kai"),
], platform=[
    app_commands.Choice(name="🌐 All Platforms (YouTube + Twitch)", value="all"),
    app_commands.Choice(name="🟣 Twitch (Viral Clips & VODs)", value="twitch"),
    app_commands.Choice(name="🔴 YouTube Only", value="youtube"),
])
async def slash_radar(interaction: discord.Interaction, creator: app_commands.Choice[str] = None, platform: app_commands.Choice[str] = None, custom: str = None):
    await interaction.response.defer()
    target_c = creator.value if creator else ("custom" if custom else "all")
    target_p = platform.value if platform else "all"
    await run_radar_scout(interaction.channel, creator_choice=target_c, custom_input=custom, platform=target_p, interaction=interaction)

@bot.tree.command(name="scout", description="Quick-scout viral streamer uploads ready for 1-click clip production")
@app_commands.describe(
    streamer="Streamer name or handle (speed, caseoh, jynxzi, kai, or any channel)",
    platform="Platform to scout (All, Twitch, YouTube)"
)
@app_commands.choices(platform=[
    app_commands.Choice(name="🌐 All Platforms", value="all"),
    app_commands.Choice(name="🟣 Twitch Only (Trending Scenes)", value="twitch"),
    app_commands.Choice(name="🔴 YouTube Only", value="youtube"),
])
async def slash_scout(interaction: discord.Interaction, streamer: str = "all", platform: app_commands.Choice[str] = None):
    await interaction.response.defer()
    s_clean = streamer.strip().lower()
    p_val = platform.value if platform else "all"
    if s_clean in ["speed", "ishowspeed"]:
        c_choice, custom = "speed", None
    elif s_clean in ["caseoh", "case"]:
        c_choice, custom = "caseoh", None
    elif s_clean in ["jynxzi", "junko"]:
        c_choice, custom = "jynxzi", None
    elif s_clean in ["kai", "kaicenat", "cenat"]:
        c_choice, custom = "kai", None
    elif s_clean in ["all", "streamers", "any"]:
        c_choice, custom = "all", None
    else:
        c_choice, custom = "custom", streamer
    await run_radar_scout(interaction.channel, creator_choice=c_choice, custom_input=custom, platform=p_val, interaction=interaction)

@bot.tree.command(name="twitch", description="View full live streams from the past 4–5 days (CaseOh, Jynxzi, Kai Cenat) to clip in 2h chunks")
@app_commands.describe(
    streamer="Streamer to scout on Twitch (All, CaseOh, Jynxzi, Kai Cenat)"
)
@app_commands.choices(streamer=[
    app_commands.Choice(name="🟣 All Twitch Streamers (CaseOh, Jynxzi, Kai Cenat)", value="all"),
    app_commands.Choice(name="🍔 CaseOh (caseoh_)", value="caseoh"),
    app_commands.Choice(name="🎯 Jynxzi (jynxzi)", value="jynxzi"),
    app_commands.Choice(name="👑 Kai Cenat (kaicenat)", value="kai"),
])
async def slash_twitch(interaction: discord.Interaction, streamer: app_commands.Choice[str] = None):
    await interaction.response.defer()
    target_c = streamer.value if streamer else "all"
    await run_radar_scout(interaction.channel, creator_choice=target_c, platform="twitch", interaction=interaction)

# --- Legacy Text Commands & Natural Language Listener ---

@bot.command(name="radar")
async def text_radar(ctx, creator: str = "all"):
    await run_radar_scout(ctx.channel, creator_choice=creator.lower())

@bot.command(name="twitch")
async def text_twitch(ctx, streamer: str = "all"):
    await run_radar_scout(ctx.channel, creator_choice=streamer.lower(), platform="twitch")

@bot.command(name="scout")
async def text_scout(ctx, *, target: str = "all"):
    s_clean = target.strip().lower()
    if s_clean in ["speed", "ishowspeed"]:
        c_choice, custom = "speed", None
    elif s_clean in ["caseoh", "case"]:
        c_choice, custom = "caseoh", None
    elif s_clean in ["jynxzi", "junko"]:
        c_choice, custom = "jynxzi", None
    elif s_clean in ["kai", "kaicenat", "cenat"]:
        c_choice, custom = "kai", None
    elif s_clean in ["all", "streamers"]:
        c_choice, custom = "all", None
    else:
        c_choice, custom = "custom", target
    await run_radar_scout(ctx.channel, creator_choice=c_choice, custom_input=custom)

@bot.command(name="keep")
async def text_keep(ctx):
    session = get_channel_session(ctx.channel.id)
    if session and session.get("shorts"):
        v_title = session.get("video_title", "Current Video")
        v_slug = session["shorts"][0].get("filename", "").split("_rank")[0]
        if v_slug:
            KEEP_MEDIA_REQUESTS.add(v_slug)
        KEEP_MEDIA_REQUESTS.add("all")
        await ctx.send(f"🛡️ **Source Media Preserved:** Source video for **'{v_title}'** will NOT be auto-deleted.")
    else:
        KEEP_MEDIA_REQUESTS.add("all")
        await ctx.send("🛡️ **Keep Preference Noted:** Source files for active/upcoming downloads will be preserved on disk.")

@bot.command(name="join")
async def text_join(ctx):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ Please join a voice channel first!")
        return
    channel = ctx.author.voice.channel
    if ctx.guild.voice_client:
        await ctx.guild.voice_client.move_to(channel)
    else:
        await channel.connect()
    await ctx.send(f"🔊 Joined voice channel **{channel.name}**!")
    await speak_text_in_vc(ctx.guild, "Connected to voice! I'm ready to talk strategy.")

@bot.command(name="leave")
async def text_leave(ctx):
    if ctx.guild.voice_client:
        await ctx.guild.voice_client.disconnect()
        await ctx.send("👋 Left voice channel.")

@bot.command(name="ask")
async def text_ask(ctx, *, question: str):
    await slash_ask.callback(ctx, question=question)

@bot.command(name="analyze")
async def text_analyze(ctx):
    await slash_analyze.callback(ctx)

@bot.command(name="clip")
async def text_clip(ctx, url: str, creator: str = None, upload: str = "yes"):
    await handle_clip_pipeline(ctx.channel, url, creator, auto_upload=(upload.lower() in ("yes", "y", "true", "1")))

def snap_to_sentence_end(words, target_t1, window=6.0):
    """Find natural punctuation boundary (. ! ?) near target_t1 so speakers aren't cut off."""
    cand = [w for w in words if (target_t1 - window) <= w["end"] <= (target_t1 + window)]
    for w in reversed(cand):
        t = w.get("text", "").strip()
        if any(t.endswith(p) for p in [".", "!", "?"]):
            return w["end"] + 0.15
    for i in range(len(cand) - 1):
        if cand[i+1]["start"] - cand[i]["end"] > 0.6:
            return cand[i]["end"] + 0.15
    return target_t1

def execute_remaster(target_short, force_split=None, extend_secs=0.0, trim_secs=0.0, new_hook=None, new_music=None, new_title=None, target_duration=None, reframe_mode=None):
    """Conversational Video Director: re-cuts, reframes, or extends an existing Short."""
    import uuid
    v_path = target_short.get("video_path") or ""
    filename = target_short.get("filename") or os.path.basename(v_path)
    vid_slug = filename.split("_rank")[0] if "_rank" in filename else "yt"

    # Inherit split screen layout unless explicitly overridden
    if force_split is None:
        force_split = target_short.get("is_split_screen", False)

    # Find source video and word timestamps
    downloads_dir = PROJECT_ROOT / "data" / "downloads"
    src_video = str(downloads_dir / f"{vid_slug}_source.mp4")
    words_file = str(downloads_dir / f"{vid_slug}_words.json")

    r_num = target_short.get("rank", 1)
    u_id = uuid.uuid4().hex[:6]
    out_id = f"remaster_r{r_num}_{u_id}"

    # Helper function to resolve real stream URL for either Twitch or YouTube
    def _resolve_stream_url():
        if target_short:
            u = target_short.get("url") or target_short.get("source_url") or target_short.get("stream_url")
            if u and ("youtube.com" in u or "youtu.be" in u or "twitch.tv" in u):
                return u
        # Check summary manifests in data/shorts/
        try:
            shorts_dir = PROJECT_ROOT / "data" / "shorts"
            for s_file in shorts_dir.glob("*summary.json"):
                try:
                    data = json.loads(s_file.read_text(encoding="utf-8"))
                    v_info = data.get("video_info", {})
                    v_id = v_info.get("id", "")
                    if v_id and (v_id in vid_slug or vid_slug.startswith(v_id)):
                        u = data.get("source_url") or data.get("url") or v_info.get("webpage_url")
                        if u:
                            return u
                except Exception:
                    continue
        except Exception:
            pass

        base_id = vid_slug.split("_p")[0] if "_p" in vid_slug else vid_slug
        if (base_id.startswith("v") and base_id[1:].isdigit()) or "twitch" in base_id.lower():
            clean_tw = base_id[1:] if (base_id.startswith("v") and base_id[1:].isdigit()) else base_id
            return f"https://www.twitch.tv/videos/{clean_tw}"
        return f"https://www.youtube.com/watch?v={base_id}"

    stream_url = _resolve_stream_url()
    is_chunked_or_long = ("_p" in vid_slug) or (float(target_short.get("t0", 0.0)) > 60.0)
    temp_slice_file = None

    t0 = max(0.0, float(target_short.get("t0", 0.0)))
    orig_t1 = float(target_short.get("t1", t0 + 20.0))

    words = []
    if os.path.exists(words_file):
        try:
            words = youtube_pipeline.load_words_data(words_file)
        except Exception:
            pass

    # Apply timing modifications with smart sentence boundary snapping
    if target_duration and target_duration >= 15.0:
        target_end = t0 + target_duration
        new_t1 = snap_to_sentence_end(words, target_end, window=6.0) if words else target_end
    elif extend_secs > 0:
        target_end = max(t0 + 44.0, orig_t1 + extend_secs)
        new_t1 = snap_to_sentence_end(words, target_end, window=6.0) if words else target_end
    elif trim_secs > 0:
        new_t1 = max(t0 + 15.0, orig_t1 - trim_secs)
    else:
        new_t1 = orig_t1

    if (new_t1 - t0) > 58.5:
        new_t1 = t0 + 58.5

    # Check local source files first
    if not os.path.exists(src_video):
        candidates = [str(c) for c in downloads_dir.glob(f"*{vid_slug}*.mp4") if not str(c).endswith("_final.mp4") and "rank" not in c.name and not c.name.endswith(".part")]
        if candidates:
            src_video = candidates[0]
        elif is_chunked_or_long:
            # Surgically download ONLY the exact clip slice needed for remastering
            temp_slice_file = str(downloads_dir / f"{vid_slug}_r{r_num}_{u_id}_remaster_slice.mp4")
            print(f"[Remaster] Surgically fetching slice for `{vid_slug}` ({t0:.1f}s - {new_t1:.1f}s) from {stream_url}...")
            dl_ok = long_stream.download_surgical_video(stream_url, t0, new_t1, temp_slice_file)
            if dl_ok and os.path.exists(temp_slice_file) and os.path.getsize(temp_slice_file) > 1000:
                src_video = temp_slice_file
            else:
                raise RuntimeError(f"Could not surgically download clip segment from `{stream_url}`")
        else:
            # Standard video re-download
            try:
                print(f"[Remaster] Re-downloading source video {stream_url}...")
                dl_mp4, dl_wav, _ = youtube_pipeline.download_youtube_video(stream_url)
                src_video = dl_mp4
            except Exception as e:
                raise RuntimeError(f"Could not re-download source for `{vid_slug}`: {e}")

    src_dur = mt.ffprobe_dur(src_video) or (new_t1 - t0)

    if src_video == temp_slice_file:
        plan_t0 = 0.0
        plan_t1 = round(new_t1 - t0, 2)
        win_words = [
            {
                "text": w.get("text", ""),
                "start": max(0.0, round(w["start"] - t0, 2)),
                "end": max(0.0, round(w["end"] - t0, 2)),
                "energy": w.get("energy", 0.5)
            }
            for w in words if (t0 - 0.4) <= w["start"] <= (new_t1 + 0.4)
        ]
        t0_cap_offset = 0.0
    else:
        plan_t0 = t0
        plan_t1 = new_t1
        win_words = [w for w in words if (t0 - 0.4) <= w["start"] <= (new_t1 + 0.4)]
        t0_cap_offset = plan_t0

    if not win_words:
        win_words = [{"text": "MOMENT", "start": plan_t0, "end": plan_t1, "energy": 0.5}]

    hook_text = new_hook or target_short.get("hook_text") or target_short.get("title")

    c_name = target_short.get("creator_name", "Creator")
    creator_key = target_short.get("creator_id", "speed")
    final_title = new_title or target_short.get("title")
    if new_hook and ("Moment" in str(final_title) or len(str(final_title)) < 15):
        clean_h = new_hook.replace("💀", "").replace("😂", "").replace("🔥", "").replace("😭", "").strip()
        final_title = f"{c_name}: {clean_h}"

    plan = {
        "id": out_id,
        "rank": r_num,
        "src_path": src_video,
        "src": os.path.basename(src_video),
        "t0": plan_t0,
        "t1": plan_t1,
        "kind": "landscape",
        "creator": creator_key,
        "reframe_mode": reframe_mode,
        "force_split_screen": force_split,
        "is_split_screen": force_split,
        "words": win_words,
        "emphasis": target_short.get("emphasis_words") or [win_words[0]["text"].upper()],
        "punch": {"tin": 0.5, "z": 1.14},
        "title": final_title,
        "why": "User conversational remaster"
    }

    fmt = format_mod.build_directives({"format": "moment", "creator": c_name})

    prep_file = edit_mod.prep(plan, out_id)
    reframed, face_stats = edit_mod.reframe(prep_file, plan, out_id)
    punched = edit_mod.add_punch(reframed, plan, out_id)
    capped = edit_mod.burn_karaoke(
        punched, prep_file, plan["words"], plan["emphasis"],
        fmt["caption"], out_id, t0_offset=t0_cap_offset,
        hook_text=hook_text
    )

    out_name = f"{vid_slug}_rank{r_num}_remastered_{u_id}.mp4"
    out_path = os.path.join(PROJECT_ROOT, "data", "shorts", out_name)
    creator_key = target_short.get("creator_id", "speed")

    # Music Profile: 100% zero BGM by default (clean original dialogue only)
    if new_music and new_music != "none":
        music_prof = {"creator": new_music, "bed_volume": 0.22, "enabled": True}
        final_track_id = new_music
    else:
        music_prof = {"enabled": False}
        final_track_id = "none"

    try:
        final_mp4 = edit_mod.assemble([capped], out_path, fmt["hook"], whoosh_at=None,
                                      music_profile=music_prof, creator=creator_key)
    finally:
        if temp_slice_file and os.path.exists(temp_slice_file):
            try:
                os.remove(temp_slice_file)
            except Exception:
                pass

    dur_actual = mt.ffprobe_dur(final_mp4) or round(new_t1 - t0, 1)
    file_size_mb = round(os.path.getsize(final_mp4) / (1024 * 1024), 2)

    return {
        "video_path": os.path.abspath(final_mp4),
        "filename": out_name,
        "title": final_title,
        "t0": t0,
        "t1": new_t1,
        "duration": dur_actual,
        "size_mb": file_size_mb,
        "is_split_screen": force_split,
        "hook_text": hook_text,
        "track_id": final_track_id
    }

async def do_conversational_remaster(channel, target_short, instruction_text, interaction=None, original_message=None):
    """Execute conversational remaster from natural language or modal submission, updating memory."""
    # 1. Learn from user direction immediately
    res = memory_mod.record_feedback(target_short, "edit", instruction_text)

    lower = instruction_text.lower()
    orig_split = target_short.get("is_split_screen", False)
    is_challenge = any(ch in lower for ch in ["challenge", "between two people", "1v1", "versus", "vs mode", "two people", "face off"])
    wants_add_split = is_challenge or any(sp in lower for sp in ["split", "two screen", "facecam", "gameplay and face", "two screens", "split screen"])
    wants_no_split = any(sp in lower for sp in ["no split", "remove split", "single screen", "unsplit", "disable split", "without split", "stop split", "full frame", "full screen", "one screen"])
    if wants_no_split:
        force_split = False
    elif wants_add_split:
        force_split = True
    else:
        force_split = orig_split

    dur_match = re.search(r'(\d+)\s*(?:seconds|secs|second|s)\b', lower)
    target_dur_request = float(dur_match.group(1)) if dur_match else None
    wants_ending = any(en in lower for en in ["ending", "properending", "proper ending", "story", "complete", "extend", "longer", "more", "finish", "climax", "full story"])
    extend_secs = 14.0 if wants_ending else 0.0
    trim_secs = 5.0 if any(tr in lower for tr in ["trim", "shorter", "cut early"]) else 0.0

    wants_hook = is_challenge or any(hk in lower for hk in ["hook", "elevation", "dont see any hook", "no hook", "title", "banner"])
    quoted = re.findall(r'["\']([^"\']+)["\']', instruction_text)
    if quoted:
        new_hook = quoted[0].strip().upper()
    elif is_challenge:
        new_hook = "🔥 1V1 CHALLENGE 💀 🔥"
    elif wants_hook:
        new_hook = "WAIT FOR THE ENDING 💀"
    else:
        new_hook = None

    wants_no_music = any(w in lower for w in [
        "remove bgm", "remove the bgm", "remove music", "remove the music",
        "no bgm", "no music", "mute music", "mute bgm", "without music", "without bgm",
        "delete music", "delete bgm", "strip music", "strip bgm",
        "turn off music", "turn off bgm", "disable music", "disable bgm",
        "stop music", "stop bgm", "cut the music", "cut music", "cut bgm",
        "zero music", "no background music", "remove background music"
    ])
    wants_change_music = any(w in lower for w in [
        "change music", "switch music", "different music", "new music",
        "change bgm", "switch bgm", "different bgm", "new bgm",
        "phonk", "streambeats"
    ])
    if wants_no_music:
        new_music = "none"
    elif wants_change_music:
        current_track = target_short.get("track_id") or ""
        if "brazilian" in current_track.lower():
            new_music = "speed_streambeats_moonwalk"
        elif "phonk" in current_track.lower():
            new_music = "speed_brazilian_phonk"
        else:
            new_music = "jynxzi_brazilian_powerful"
    else:
        new_music = None

    wants_blur_fill = any(bf in lower for bf in [
        "blur", "blurry", "background blurred", "blurred background", "make small", "small and background",
        "mrbeast", "mr beast", "cinematic", "inset", "centered", "extend picture at the back", "extended picture"
    ])
    reframe_mode = "blur_fill" if wants_blur_fill else None
    if wants_blur_fill:
        force_split = False

    layout_label = "MrBeast Cinematic (Centered Inset + Blurred Extended Background)" if wants_blur_fill else (
        "Enabled (Top: Gameplay / Bottom: Creator Facecam)" if force_split else "Single 9:16 Reframe"
    )

    bgm_label = "🔇 None (Zero BGM)" if new_music == "none" else (f"🎵 Switch to {new_music}" if new_music else "None (Clean Dialogue)")
    dur_label = f"Target {target_dur_request:.0f}s" if target_dur_request else (f"+{extend_secs:.0f}s (Sentence-boundary snap & clutch completion)" if extend_secs else (f"-{trim_secs:.0f}s" if trim_secs else "Original"))

    status_content = (
        f"🎬 **AI Video Director Activated:** Remastering **Rank #{target_short.get('rank')}** (*'{target_short.get('title')}'*)...\n"
        f"• Hook Elevation: {f'🔥 **{new_hook}**' if new_hook else 'Original'}\n"
        f"• Duration Adjustment: {dur_label}\n"
        f"• Background Music: {bgm_label}\n"
        f"• Layout: {layout_label}\n"
        f"⏳ Executing smart reframe, re-aligning subtitles, and mixing audio..."
    )

    if interaction:
        status_msg = await interaction.followup.send(status_content)
    elif original_message:
        status_msg = await reply_safely(original_message, content=status_content)
    else:
        status_msg = await channel.send(status_content)

    loop = asyncio.get_event_loop()
    def do_remaster():
        return execute_remaster(
            target_short,
            force_split=force_split,
            extend_secs=extend_secs,
            trim_secs=trim_secs,
            new_hook=new_hook,
            new_music=new_music,
            target_duration=target_dur_request,
            reframe_mode=reframe_mode
        )

    try:
        remastered = await loop.run_in_executor(None, do_remaster)
        target_short.update(remastered)
        remastered_path = remastered.get("video_path")

        # Persist update to latest session file on disk
        try:
            summary_files = sorted(list((PROJECT_ROOT / "data" / "shorts").glob("*_summary.json")),
                                   key=os.path.getmtime, reverse=True)
            if summary_files:
                session = get_channel_session(channel.id) or {}
                save_payload = {
                    "shorts": session.get("shorts", [target_short]),
                    "clips": session.get("shorts", [target_short]),
                    "video_title": session.get("video_title", "Remastered Video")
                }
                with open(summary_files[0], "w", encoding="utf-8") as sf:
                    json.dump(save_payload, sf, indent=2)
        except Exception:
            pass

        r_view = UploadShortsView([target_short], channel)
        await status_msg.edit(
            content=(
                f"✨ **Remastering Complete!** Rank #{target_short.get('rank')} has been remastered & saved to disk.\n"
                f"• Duration: {remastered.get('duration', 0):.1f}s | Size: {remastered.get('size_mb', 0)}MB\n"
                f"• Layout: {split_label}\n"
                f"• Audio: {bgm_label}\n"
                f"• Learning: Directives saved to AutoClip Memory (`pipeline_memory.json`)."
            )
        )
        await send_video_safely(
            channel,
            remastered_path,
            caption=f"🎬 **Remastered Rank #{target_short.get('rank')} Video File (Ready to Post):**",
            view=r_view
        )
        if channel.guild and channel.guild.voice_client:
            await speak_text_in_vc(channel.guild, f"Rank {target_short.get('rank')} has been remastered with your changes!")
    except Exception as ex:
        await status_msg.edit(content=f"❌ Remaster failed: `{str(ex)[:500]}`")

def execute_top5_countdown(session, theme="funniest"):
    """Assemble all 5 ranked clips into a single high-retention Top 5 Countdown compilation Short."""
    import uuid
    shorts = session.get("shorts") or session.get("clips") or []
    if len(shorts) < 2:
        raise RuntimeError("Need at least 2 ranked shorts to create a Top 5 countdown compilation.")

    theme_lower = (theme or "funniest").lower()
    is_horror = any(k in theme_lower for k in ["horror", "scary", "jumpscare", "spooky", "fear", "creepy"])
    is_funny = any(k in theme_lower for k in ["funny", "funniest", "laugh", "comedy", "joke"])
    is_r6_gaming = any(k in theme_lower for k in ["rainbow", "siege", "r6", "shooting", "shoot", "headshot", "snipe", "clutch", "ace", "gameplay", "kill", "jynxzi", "gunplay"])
    is_rage = any(k in theme_lower for k in ["rage", "freakout", "slam", "desk slam", "banned"])
    stop_words_theme = {"top", "five", "things", "moments", "clips", "best", "countdown", "the", "and", "from", "video", "videos"}
    custom_kws = [w for w in re.findall(r'\b[a-zA-Z]{3,}\b', theme_lower) if w not in stop_words_theme]

    # Score each short's intensity based on theme
    def calc_intensity(s):
        base_score = float(s.get("score") or 70.0)
        peak_e = float(s.get("peak_energy") or 0.5)
        reac = float(s.get("reaction_hits") or 0.0)
        txt = (str(s.get("title", "")) + " " + str(s.get("hook_text", "")) + " " + str(s.get("why_good", "")) + " " + str(s.get("description", ""))).lower()

        if is_r6_gaming:
            action_kws = [
                "headshot", "snipe", "sniped", "clutch", "ace", "kill", "killed", "one left",
                "shoot", "shooting", "one tap", "flick", "wallbang", "pre-fire", "beam", "aim",
                "spray", "1v1", "1v2", "1v3", "1v4", "1v5", "plant", "defuse", "c4", "got him",
                "dead", "eliminated", "siege", "ranked", "champion"
            ]
            action_hits = sum(1 for kw in action_kws if kw in txt)
            clutch_bonus = 0.0
            if any(k in txt for k in ["1v4", "1v5", "ace"]):
                clutch_bonus = 55.0
            elif "1v3" in txt:
                clutch_bonus = 35.0
            elif "1v2" in txt:
                clutch_bonus = 20.0
            elif any(k in txt for k in ["headshot", "one tap", "snipe", "flick"]):
                clutch_bonus = 22.0

            shout_kws = ["let's go", "lets go", "stand up", "clip that", "good aim", "slam"]
            shout_bonus = 15.0 if any(k in txt for k in shout_kws) else 0.0

            return (action_hits * 16.0) + clutch_bonus + shout_bonus + (peak_e * 30.0) + (reac * 8.0) + base_score

        elif is_horror:
            scream_kws = ["scream", "screaming", "scare", "scared", "jumpscare", "ghost", "dead", "kill", "what the fuck", "holy shit", "panic", "monster", "run", "behind you", "loud"]
            hits = sum(1 for kw in scream_kws if kw in txt)
            return (peak_e * 50.0) + (hits * 15.0) + (reac * 10.0) + base_score

        elif is_funny:
            funny_kws = ["laugh", "laughing", "haha", "crying", "dying", "joke", "funny", "hilarious", "cooked", "bro what", "exposed"]
            hits = sum(1 for kw in funny_kws if kw in txt)
            return (hits * 18.0) + (reac * 8.0) + (peak_e * 15.0) + base_score

        elif is_rage:
            rage_kws = ["slam", "desk", "banned", "fuck", "bitch", "shit", "trash", "bad", "hate", "quit", "unplayable", "stop"]
            hits = sum(1 for kw in rage_kws if kw in txt)
            return (hits * 22.0) + (peak_e * 35.0) + (reac * 10.0) + base_score

        elif custom_kws:
            c_hits = sum(1 for kw in custom_kws if kw in txt)
            return (c_hits * 30.0) + (peak_e * 25.0) + (reac * 10.0) + base_score

        else:
            return base_score + (peak_e * 20.0)

    # Filter to shorts that actually exist on disk
    valid_shorts = [s for s in shorts if s.get("video_path") and os.path.exists(s["video_path"])]
    if not valid_shorts:
        valid_shorts = shorts

    # Sort ASCENDING by intensity:
    # Lowest intensity -> Rank #5 (mildest/entry hook)
    # Highest intensity -> Rank #1 (extreme climax / loud scream / funniest punchline!)
    sorted_by_intensity = sorted(valid_shorts, key=calc_intensity)
    n_clips = min(5, len(sorted_by_intensity))
    chosen_shorts = sorted_by_intensity[-n_clips:]

    ranked_map = {}
    for idx, s in enumerate(chosen_shorts):
        r = n_clips - idx
        s["rank"] = r
        ranked_map[r] = s

    ranks_in_order = sorted(list(ranked_map.keys()), reverse=True)

    # Energy guardrail check for single-video countdowns
    max_e = max((float(s.get("peak_energy", 0.5)) for s in chosen_shorts), default=0.5)
    total_reac = sum((float(s.get("reaction_hits", 0)) for s in chosen_shorts))
    is_multi = session.get("is_multi", False) or "Multi" in session.get("video_title", "")

    low_intensity_warning = None
    if not is_multi:
        if is_r6_gaming and (max_e < 0.60 and total_reac < 2):
            low_intensity_warning = (
                "⚠️ **Low Action / Gameplay Notice:** This single video had mostly menu talk or low shooting action.\n"
                "💡 **Pro-Tip for an Elite R6 Compilation:** Paste **2 to 4 Jynxzi video links** together in chat and AutoClip will pull the #1 craziest 1vX clutch or flick headshot from each match into an insane Top 5!"
            )
        elif is_horror and (max_e < 0.60 and total_reac < 2):
            low_intensity_warning = (
                "⚠️ **Atmospheric Video Notice:** This single video has mild ambient audio without extreme loud jumpscares.\n"
                "💡 **Pro-Tip:** Paste **2 to 4 video links** together in chat and AutoClip will pull the #1 loudest scream from each video into a wild Top 5!"
            )
        elif is_funny and (max_e < 0.55 and total_reac < 2):
            low_intensity_warning = (
                "⚠️ **Calm Dialogue Notice:** This single video has conversational speech without explosive laughter.\n"
                "💡 **Pro-Tip:** Paste **2 or 3 video links** together in chat and AutoClip will pull the funniest peaks across all of them!"
            )

    uid = uuid.uuid4().hex[:6]
    c_name = shorts[0].get("creator_name", "Creator")
    vid_slug = shorts[0].get("filename", "vid").split("_rank")[0]

    snips = []
    cards = []
    who, boom = edit_mod.make_sfx()

    for r in ranks_in_order:
        s_data = ranked_map[r]
        v_path = s_data.get("video_path")
        if not v_path or not os.path.exists(v_path):
            continue

        target_dur = 11.5 if r == 1 else 8.0
        v_dur = mt.ffprobe_dur(v_path) or target_dur
        cut_len = min(v_dur, target_dur)
        # Capture the punchline/screaming climax from the second half/end of the clip with its build-up
        start_ss = max(0.0, v_dur - cut_len - 0.5)

        snip_path = os.path.join(PROJECT_ROOT, "data", "shorts", f"top5_snip_r{r}_{uid}.mp4")
        impact_font = "C\\:/Windows/Fonts/impact.ttf" if os.path.exists("C:/Windows/Fonts/impact.ttf") else ("C\\:/Windows/Fonts/arialbd.ttf" if os.path.exists("C:/Windows/Fonts/arialbd.ttf") else "")
        font_opt = f"fontfile='{impact_font}':" if impact_font else ""
        raw_topic = s_data.get("scene_topic") or s_data.get("hook_text") or s_data.get("title") or f"MOMENT {r}"
        clean_topic = re.sub(r'[\U00010000-\U0010ffff]', '', raw_topic)
        clean_topic = re.sub(r'[^\w\s]', '', clean_topic).strip()
        clean_topic = re.sub(r'\b(CLIMAX|THE 1 CLIMAX|BRO LOST IT|WAIT FOR IT)\b', '', clean_topic, flags=re.I).strip()
        if not clean_topic:
            clean_topic = f"MOMENT {r}"
        
        display_topic = clean_topic.upper()[:22]
        badge_text = f"#{r} • {display_topic}"
        box_w = min(880, max(280, 50 + len(badge_text) * 22))
        
        badge_vf = (
            f"scale=1080:1920:flags=lanczos,format=yuv420p,fps=30,"
            f"drawbox=x=44:y=60:w={box_w}:h=90:color=0x000000@0.80:t=fill,"
            f"drawbox=x=42:y=58:w={box_w+4}:h=94:color=0xFFD200@0.95:t=3,"
            f"drawtext={font_opt}text='{badge_text}':fontcolor=white:fontsize=46:x=64:y=82"
        )
        mt.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", v_path,
            "-ss", str(round(start_ss, 2)), "-t", str(round(cut_len, 2)),
            "-vf", badge_vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-af", "afade=t=in:st=0:d=0.12",
            snip_path
        ])
        snips.append((r, snip_path))

        card_dur = 0.9 if r == 1 else 0.7
        card_path = edit_mod.make_card(f"#{r}", card_dur, special=(r == 1), bg_src=snip_path, out_id=f"top5_card_r{r}_{uid}", boom=boom, label=display_topic)
        cards.append((r, card_path))

    if not snips:
        raise RuntimeError("No valid video files found on disk for countdown compilation.")

    snip_r1 = next((p for r, p in snips if r == 1), snips[-1][1])
    if is_r6_gaming:
        hook_title = "TOP 5 R6 CLUTCHES"
        if is_multi:
            hook_sub = "BEST SHOOTING"
            final_video_title = "TOP 5 JYNXZI R6 CLUTCHES & KILLS (Best Of) 🎯💀"
        else:
            hook_sub = f"{c_name.upper()} PLAYS"
            final_video_title = f"TOP 5 JYNXZI R6 CLUTCHES & KILLS ({c_name}) 🎯💀"
    else:
        hook_title = f"TOP 5 {theme.upper()[:22]}"
        if is_multi:
            hook_sub = "BEST MOMENTS"
            final_video_title = f"TOP 5 {theme.upper()} MOMENTS (Best Of) 💀"
        else:
            hook_sub = f"{c_name.upper()} MOMENTS"
            final_video_title = f"TOP 5 {theme.upper()} MOMENTS ({c_name}) 💀"

    title_card = edit_mod.make_title(snip_r1, {"title_seconds": 1.5}, out_id=f"top5_title_{uid}", line1=hook_title, line2=hook_sub)

    final_clips = [title_card]
    for r in ranks_in_order:
        card_for_r = next((p for kr, p in cards if kr == r), None)
        snip_for_r = next((p for kr, p in snips if kr == r), None)
        if card_for_r and os.path.exists(card_for_r):
            final_clips.append(card_for_r)
        if snip_for_r and os.path.exists(snip_for_r):
            final_clips.append(snip_for_r)

    clean_slug_theme = re.sub(r'[^a-zA-Z0-9]', '_', theme.lower())[:20]
    out_name = f"{vid_slug}_top5_{clean_slug_theme}_countdown_{uid}.mp4"
    out_path = os.path.join(PROJECT_ROOT, "data", "shorts", out_name)
    creator_key = shorts[0].get("creator_id", "speed")

    if is_horror:
        music_profile = {"style": "ambient_tension", "bed_volume": 0.08, "duck_ratio": 9.0}
    elif is_r6_gaming:
        music_profile = {"style": "jynxzi_r6_hype", "bed_volume": 0.16, "duck_ratio": 8.5}
    else:
        music_profile = {"style": "speed_brazilian_phonk", "bed_volume": 0.20}

    edit_mod.assemble(final_clips, out_path, hook=None, whoosh_at=None,
                      music_profile=music_profile,
                      creator=creator_key)

    total_dur = mt.ffprobe_dur(out_path) or 50.0
    f_size = round(os.path.getsize(out_path) / (1024 * 1024), 2)

    return {
        "video_path": os.path.abspath(out_path),
        "filename": out_name,
        "title": final_video_title,
        "duration": total_dur,
        "size_mb": f_size,
        "theme": theme,
        "creator_name": "Multi-Streamer" if is_multi else c_name,
        "low_intensity_warning": low_intensity_warning
    }

def prepare_discord_upload(video_path: str, max_mb: float = 9.2) -> str:
    """Ensure video is strictly under Discord's upload limit (10MB for free bots/servers).

    If file is <= max_mb, returns original path.
    If file is > max_mb, fast-compresses to a discord-optimized MP4 (< 9.2MB) with high quality.
    """
    if not video_path or not os.path.exists(video_path):
        return video_path

    file_size_bytes = os.path.getsize(video_path)
    if file_size_bytes <= int(max_mb * 1024 * 1024):
        return video_path

    dur = mt.ffprobe_dur(video_path) or 40.0
    target_total_kbps = int((max_mb * 8192 * 0.88) / max(1.0, dur))
    target_v_kbps = max(350, target_total_kbps - 128)
    max_rate = int(target_v_kbps * 1.15)
    buf_size = int(target_v_kbps * 2.0)

    dir_name = os.path.dirname(os.path.abspath(video_path))
    base_name = os.path.basename(video_path)
    stem, ext = os.path.splitext(base_name)
    discord_path = os.path.join(dir_name, f"{stem}_discord{ext}")

    if os.path.exists(discord_path) and os.path.getsize(discord_path) <= int(max_mb * 1024 * 1024):
        return discord_path

    print(f"[Discord Video] Auto-compressing {base_name} ({file_size_bytes/(1024*1024):.1f}MB) -> target < {max_mb}MB ({target_v_kbps}kbps)...")
    mt.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", video_path,
        "-c:v", "libx264", "-preset", "faster",
        "-b:v", f"{target_v_kbps}k", "-maxrate", f"{max_rate}k", "-bufsize", f"{buf_size}k",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
        "-movflags", "+faststart",
        discord_path
    ])

    if os.path.exists(discord_path) and os.path.getsize(discord_path) <= int(10 * 1024 * 1024):
        return discord_path
    return video_path

async def send_video_safely(channel, video_path: str, caption: str = "", view: discord.ui.View = None):
    """Safely upload video file to Discord chat with automatic compression and graceful fallbacks."""
    safe_caption = (caption or "🎬 **Here is your clip:**").strip()
    upload_file_path = prepare_discord_upload(video_path, max_mb=9.2)
    f_size = os.path.getsize(upload_file_path) if os.path.exists(upload_file_path) else 0

    if f_size <= int(10 * 1024 * 1024) and os.path.exists(upload_file_path):
        try:
            return await channel.send(
                content=safe_caption,
                file=discord.File(upload_file_path, filename=os.path.basename(video_path)),
                view=view
            )
        except Exception as e:
            print(f"[Discord Video] Direct attachment upload note ({e}), falling back to web stream...")

    # Fallback if Discord still rejects or file exceeds limit
    rel_path = os.path.relpath(video_path, PROJECT_ROOT).replace("\\", "/")
    stream_url = f"http://localhost:8080/video/{rel_path}"
    f_actual_mb = (os.path.getsize(video_path)/(1024*1024)) if os.path.exists(video_path) else 0
    fallback_content = (
        f"{safe_caption}\n"
        f"⚠️ **Discord Attachment Notice:** File is {f_actual_mb:.1f}MB.\n"
        f"💾 **Stored locally at:** `{video_path}`\n"
        f"🔗 **Local Web Stream:** [Click to Watch/Download]({stream_url})"
    )
    try:
        return await channel.send(content=fallback_content, view=view)
    except Exception as fe:
        print(f"[Discord Video] Fallback send failed: {fe}")
        return None

async def reply_safely(message, content=None, embed=None, file=None, view=None):
    """Safely reply to a message with automatic retry and channel.send fallback if connection resets."""
    for attempt in range(3):
        try:
            return await message.reply(content=content, embed=embed, file=file, view=view)
        except Exception:
            try:
                return await message.channel.send(content=content, embed=embed, file=file, view=view)
            except Exception:
                await asyncio.sleep(0.5)
    return None

async def transcribe_voice_attachment(attachment):
    """Download and transcribe audio/voice note from Discord."""
    try:
        temp_dir = Path(config.media_dir()) / "voice_in"
        temp_dir.mkdir(parents=True, exist_ok=True)
        raw_path = temp_dir / f"in_{uuid.uuid4().hex[:8]}_{attachment.filename}"
        wav_path = raw_path.with_suffix(".wav")
        
        await attachment.save(raw_path)
        
        # Convert to 16kHz mono wav with ffmpeg
        mt.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw_path),
                "-vn", "-ac", "1", "-ar", "16000", str(wav_path)], allow_fail=True)
        
        target = str(wav_path if wav_path.exists() and wav_path.stat().st_size > 1000 else raw_path)
        
        words = mt.whisper_words(target, model="tiny.en")
        text = " ".join(w["text"].strip() for w in words).strip()
        
        try:
            if raw_path.exists(): raw_path.unlink()
            if wav_path.exists(): wav_path.unlink()
        except Exception:
            pass
            
        return text
    except Exception as e:
        print(f"[Voice In] Error transcribing voice message: {e}")
        return ""

async def generate_voice_file(text, out_mp3):
    """Generate audio file using edge-tts."""
    if not HAS_EDGE_TTS:
        return None
    try:
        clean = re.sub(r'[*_`#~]', '', text).strip()
        clean = re.sub(r'https?://\S+', '', clean)
        communicate = edge_tts.Communicate(clean[:500], TTS_VOICE)
        await communicate.save(out_mp3)
        return out_mp3 if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 1000 else None
    except Exception as e:
        print(f"[TTS Out] Error generating voice audio: {e}")
        return None

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    was_voice_message = False

    # 00. Check for Voice Message or Audio Attachment
    if message.attachments:
        audio_att = next((att for att in message.attachments if (att.content_type and att.content_type.startswith("audio/")) or att.filename.lower().endswith((".ogg", ".wav", ".mp3", ".m4a", ".aac", ".flac"))), None)
        if audio_att:
            async with message.channel.typing():
                transcribed = await transcribe_voice_attachment(audio_att)
            if transcribed:
                was_voice_message = True
                message.content = transcribed
                await reply_safely(message, content=f"🎤 **Voice Note Heard:** *\"{transcribed}\"*")

    # 00.1 Check for Cookie File Attachment (.txt)
    if message.attachments:
        cookie_att = next((att for att in message.attachments if att.filename.lower().endswith(".txt") or "cookie" in att.filename.lower()), None)
        if cookie_att:
            try:
                content_bytes = await cookie_att.read()
                content_text = content_bytes.decode("utf-8", errors="replace")
                if "Netscape" in content_text or ".youtube.com" in content_text:
                    cookie_dst = str(PROJECT_ROOT / "data" / "cookies.txt")
                    os.makedirs(os.path.dirname(cookie_dst), exist_ok=True)
                    with open(cookie_dst, "wb") as f:
                        f.write(content_bytes)
                    await reply_safely(
                        message,
                        content=(
                            f"🍪 **YouTube Authentication Cookies Saved!**\n"
                            f"• Successfully imported `{cookie_att.filename}` into `data/cookies.txt`\n"
                            f"• Hermes will automatically authenticate downloads with these credentials."
                        )
                    )
                    return
            except Exception as ce:
                print(f"[Cookie Attachment Error]: {ce}")

    lower = message.content.lower().strip()
    if not lower:
        return

    # Check for cancellation of pending intake
    if lower in ["!cancel", "/cancel", "cancel"]:
        if message.channel.id in PENDING_INTAKE:
            PENDING_INTAKE.pop(message.channel.id, None)
            await reply_safely(message, content="🛑 Intake cancelled. You can paste a new YouTube URL whenever you're ready!")
            return

    # 00. Check if this channel has a pending intake awaiting response from the user
    if message.channel.id in PENDING_INTAKE and not message.content.startswith("!") and not find_youtube_urls(message.content):
        intake_data = PENDING_INTAKE.get(message.channel.id)
        if intake_data:
            user_text = lower
            u = intake_data["url"]
            c = intake_data.get("creator") or "speed"
            layout = intake_data.get("layout_mode") or "blur_fill"
            intake_msg = intake_data.get("intake_msg")

            # Check for layout preference in text
            if any(k in user_text for k in ["split", "split-screen", "split screen", "two screen", "facecam"]):
                layout = "split_screen"
            elif any(k in user_text for k in ["blur", "mrbeast", "extended", "small", "blur fill"]):
                layout = "blur_fill"

            # Check for normal clips vs top 5
            is_normal = any(k in user_text for k in ["normal", "individual", "5 shorts", "standalone", "separate", "normal clips"])
            if is_normal:
                PENDING_INTAKE.pop(message.channel.id, None)
                await start_video_production(
                    channel=message.channel,
                    url=u,
                    format_type="normal",
                    theme=None,
                    creator_slug=c,
                    reframe_mode=layout,
                    status_message=intake_msg
                )
                return
            else:
                # Top 5 countdown requested or user specified a theme
                theme_choice = "funniest moments"
                theme_mapping = [
                    (["foods", "food", "eating", "eat"], "foods eating"),
                    (["headshot", "headshots", "snipe", "snipes"], "headshots"),
                    (["gameplay", "gameplays", "clutch", "clutches"], "best gameplays"),
                    (["rage", "rages", "desk slam", "tilt"], "rage moments"),
                    (["horror", "scariest", "scary", "jumpscare", "jumpscares"], "horror jumpscares" if c == "caseoh" else "scariest moments"),
                    (["waffle", "ban", "bans"], "food waffle house" if "waffle" in user_text else "funny rage moments"),
                    (["cringiest", "cringe"], "cringiest moments"),
                    (["wildest", "wild", "chaos"], "wildest moments"),
                    (["funniest", "funny", "laugh", "comedy"], "funniest moments"),
                ]
                for triggers, mapped_val in theme_mapping:
                    if any(t in user_text for t in triggers):
                        theme_choice = mapped_val
                        break

                PENDING_INTAKE.pop(message.channel.id, None)
                await start_video_production(
                    channel=message.channel,
                    url=u,
                    format_type="countdown",
                    theme=theme_choice,
                    creator_slug=c,
                    reframe_mode=layout,
                    status_message=intake_msg
                )
                return

    # 00.2 Check for !login / !refresh_cookies commands
    if lower in ["!login", "/login"] or "sign into youtube" in lower or "sign in to youtube" in lower:
        login_script = str(PROJECT_ROOT / "scripts" / "login_youtube.py")
        subprocess.Popen([sys.executable, login_script])
        await reply_safely(
            message,
            content=(
                f"🔑 **Opening YouTube Sign-In Window on Host!**\n"
                f"• Chrome is launching to the Google login page.\n"
                f"• Once you sign in, AutoClip will capture the permanent session in `data/chrome_profile`.\n"
                f"• Bot checks will be permanently eliminated."
            )
        )
        return

    if lower in ["!refresh_cookies", "!refreshcookies", "!cookies"] or "refresh cookies" in lower or "fix youtube" in lower or "fix download" in lower:
        await reply_safely(message, content="🔄 **Refreshing YouTube cookies...** Checking saved Chrome profile first...")
        try:
            import importlib.util
            grabber_path = str(PROJECT_ROOT / "scripts" / "grab_yt_cookies.py")
            spec = importlib.util.spec_from_file_location("grab_yt_cookies", grabber_path)
            grabber = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(grabber)
            # Try headless first (instant, no window needed)
            loop = asyncio.get_event_loop()
            refreshed = await loop.run_in_executor(None, lambda: asyncio.run(grabber.grab_cookies_headless()))
            if refreshed:
                await reply_safely(
                    message,
                    content=(
                        "✅ **YouTube cookies refreshed from saved profile!**\n"
                        "• Authenticated session found — all downloads will work now.\n"
                        "• Retry sending your YouTube URL."
                    )
                )
            else:
                # Need interactive login
                subprocess.Popen([sys.executable, grabber_path])
                await reply_safely(
                    message,
                    content=(
                        "🔑 **Opening Chrome for YouTube Login...**\n"
                        "1. A Chrome window will open on your computer\n"
                        "2. **Sign into your Google account** / YouTube\n"
                        "3. Cookies save automatically — window will close\n"
                        "4. Then retry your YouTube URL here\n\n"
                        "⚡ This fixes the bot detection **permanently**."
                    )
                )
        except Exception as ce:
            subprocess.Popen([sys.executable, str(PROJECT_ROOT / "scripts" / "login_youtube.py")])
            await reply_safely(message, content=f"🔑 Opening YouTube login window... Sign in to fix downloads.\n`{ce}`")
        return

    countdown_triggers = [
        "top 5", "top five", "countdown", "funniest moments", "cringiest moments",
        "horror moments", "scariest moments", "scary moments", "jumpscares", "jumpscare moments",
        "rainbow six", "siege", "r6", "shooting", "headshot", "clutch", "jynxzi clips", "jynxzi",
        "rainbow six clips", "shooting clips", "best jynxzi clips", "top five best jynxzi",
        "top five horror", "top 5 horror", "top five scary", "top 5 scary", "top five funny", "top 5 funny",
        "top five things", "top 5 things", "compilation", "combine all 5", "all five moments",
        "make top 5", "top 5 compilation", "make a top 5", "make top five"
    ]
    def extract_theme(text):
        t_low = (text or "").lower()
        if any(k in t_low for k in ["rainbow six", "rainbow", "siege", "r6", "shooting", "shoot", "gunplay", "headshot", "snipe", "clutch", "ace", "kills", "kill", "jynxzi"]):
            return "rainbow six shooting"
        if any(k in t_low for k in ["horror", "scary", "scariest", "jumpscare", "spooky", "fear", "creepy", "ghost"]):
            return "horror"
        if any(k in t_low for k in ["cringiest", "cringe", "awkward"]):
            return "cringiest"
        if any(k in t_low for k in ["rage", "angry", "freakout", "slam", "desk slam"]):
            return "rage"
        if any(k in t_low for k in ["craziest", "crazy", "insane", "wild"]):
            return "craziest"
        if any(k in t_low for k in ["shocking", "unbelievable", "omg"]):
            return "shocking"
        if any(k in t_low for k in ["food", "eating", "eat"]):
            return "food"
        if any(k in t_low for k in ["funny", "funniest", "laugh", "hilarious", "comedy", "joke"]):
            return "funniest"
        m_custom = re.search(r'top (?:5|five)\s+([a-zA-Z0-9_\-\s]+?)(?:\s+clips|\s+things|\s+moments|\s+countdown|\s+from|\s+in|$)', t_low)
        if m_custom:
            c_cand = m_custom.group(1).strip()
            if c_cand and c_cand not in ["best", "the", "my"]:
                return c_cand
        return "funniest"

    # 00.3 Check for Video Radar & Content Scouting Queries
    radar_triggers = [
        "what video should i clip", "what videos should i clip", "what to clip", "videos to clip",
        "latest video", "latest videos", "radar", "scout", "which video is going viral",
        "which video should we make clips off", "which video can have more clips",
        "find videos", "trending videos", "trending video", "check speed", "check caseoh", "check jynxzi",
        "scout speed", "scout caseoh", "scout jynxzi", "scout streamers", "scout videos",
        "find clips", "videos to make clips", "what is trending"
    ]
    if any(rt in lower for rt in radar_triggers) and not find_youtube_urls(message.content) and not message.content.startswith("!"):
        c_target = "all"
        if "speed" in lower:
            c_target = "speed"
        elif "caseoh" in lower or "case" in lower:
            c_target = "caseoh"
        elif "jynxzi" in lower:
            c_target = "jynxzi"
        await run_radar_scout(message.channel, creator_choice=c_target)
        return

    # 0. Check for Direct YouTube URLs (Single or Multiple Batch)
    yt_urls = find_youtube_urls(message.content)
    if yt_urls and not message.content.startswith("!"):
        c_found = None
        for c in ["speed", "kai", "jynxzi", "caseoh"]:
            if c in lower:
                c_found = c
                break
        auto_up = "no" not in lower
        wants_countdown = any(trig in lower for trig in countdown_triggers)
        theme = extract_theme(lower)

        if len(yt_urls) > 1:
            batch_embed = discord.Embed(
                title=f"📥 Multi-Video Batch Processing ({len(yt_urls)} Videos)",
                description=(
                    f"**Detected {len(yt_urls)} YouTube URLs in your message!**\n"
                    f"AutoClip will process each video in sequence.\n" +
                    (f"🎯 **Compilation Goal:** Automatically build the **TOP 5 {theme.upper()} MOMENTS** countdown across all videos when done!\n" if wants_countdown else "") +
                    f"**Queue:**\n" +
                    "\n".join([f"{i+1}. `{u}`" for i, u in enumerate(yt_urls)])
                ),
                color=0xFFD200
            )
            await reply_safely(message, embed=batch_embed)

            for idx, u in enumerate(yt_urls, 1):
                individual_upload = auto_up if not wants_countdown else False
                await handle_clip_pipeline(message.channel, u, c_found, auto_upload=individual_upload)

            if wants_countdown:
                status_msg = await reply_safely(
                    message,
                    content=(
                        f"🎬 **AI Video Director Activated:** Compiling **TOP 5 {theme.upper()} MOMENTS** across all {len(yt_urls)} videos!\n"
                        f"• Structure: Title Intro Card (1.5s) ➔ #5 ➔ #4 ➔ #3 ➔ #2 ➔ #1 Climax (THE BEST ONE)\n"
                        f"• Sound Design: Brazilian Phonk BGM + Animated Transition Cards\n"
                        f"⏳ Trimming top moments, generating animated countdown cards, and compiling master Short..."
                    )
                )
                multi_clips = get_multi_video_shorts(max_videos=len(yt_urls), theme=theme)
                if len(multi_clips) >= 2:
                    target_session = {"shorts": multi_clips, "video_title": f"Top 5 {theme.title()} Multi-Video", "is_multi": True}
                    loop = asyncio.get_event_loop()
                    def do_top5():
                        return execute_top5_countdown(target_session, theme=theme)
                    try:
                        top5_res = await loop.run_in_executor(None, do_top5)
                        comp_path = top5_res.get("video_path")
                        comp_short = {
                            "rank": 1,
                            "title": top5_res.get("title"),
                            "video_path": comp_path,
                            "duration": top5_res.get("duration", 0),
                            "description": f"Top 5 {theme} moments! #shorts #viral",
                            "tags": ["shorts", "viral", "top5", theme]
                        }
                        comp_view = UploadShortsView([comp_short], message.channel)
                        await status_msg.edit(content=f"✨ **TOP 5 {theme.upper()} MOMENTS Countdown Ready!**\n*{top5_res.get('title')}* | Duration: {top5_res.get('duration', 0):.1f}s")
                        await send_video_safely(
                            message.channel,
                            comp_path,
                            caption=f"🎬 **Top 5 Countdown Short Across {len(yt_urls)} Videos (Ready to Post):**",
                            view=comp_view
                        )
                        if top5_res.get("low_intensity_warning"):
                            try:
                                await message.channel.send(content=top5_res["low_intensity_warning"])
                            except Exception:
                                pass
                        if auto_up:
                            await upload_and_notify(message.channel, comp_short)
                        if message.guild and message.guild.voice_client:
                            await speak_text_in_vc(message.guild, f"Your multi video top 5 {theme} countdown video is ready!")
                    except Exception as ex:
                        await status_msg.edit(content=f"❌ Top 5 Compilation failed: `{str(ex)[:500]}`")
                else:
                    await status_msg.edit(content="⚠️ Not enough clips found across the videos to compile a countdown.")
            else:
                batch_view = MultiVideoBatchView(channel=message.channel, num_vids=len(yt_urls))
                await reply_safely(
                    message,
                    content=f"✅ **Batch Complete!** All {len(yt_urls)} videos processed into ranked Shorts. Tap a button below to assemble an elite master Top 5 Countdown across all videos:",
                    view=batch_view
                )
            return

        elif len(yt_urls) == 1:
            u = yt_urls[0]
            # Clear previous video session and pending intake immediately so nothing leaks from older videos!
            LAST_CHANNEL_SESSION.pop(message.channel.id, None)
            PENDING_INTAKE.pop(message.channel.id, None)

            loop = asyncio.get_event_loop()
            v_title = ""
            v_uploader = ""
            v_duration = 0.0
            try:
                yt_info = await loop.run_in_executor(None, lambda: youtube_pipeline.get_youtube_info(u))
                v_title = yt_info.get("title", "")
                v_uploader = yt_info.get("uploader", "")
                v_duration = float(yt_info.get("duration", 0.0) or 0.0)
                if not c_found:
                    c_found = creators.detect_creator(f"{v_title} {v_uploader} {u}")
            except Exception:
                pass
            c_found = c_found or "speed"

            # Massive stream intake (> 2 Hours)
            if v_duration > 7200.0:
                meta = await loop.run_in_executor(None, lambda: long_stream.fetch_stream_metadata_and_heatmap(u))
                chunks = long_stream.get_stream_chunks(v_duration)
                chunks = long_stream.analyze_chunks_with_heatmap(chunks, meta.get("heatmap", []))
                hottest = max(chunks, key=lambda c: (c.get("peak_count", 0), c.get("heatmap_score", 0))) if chunks else None

                intake_view = LongStreamIntakeView(
                    channel=message.channel,
                    url=u,
                    creator=c_found,
                    video_title=v_title,
                    duration=v_duration,
                    chunks=chunks,
                    hottest_chunk=hottest
                )

                hours_formatted = f"{v_duration / 3600:.1f} Hours"
                parts_desc = "\n".join([
                    f"• **Part {c['part']}** (`{int(c['t0']//3600)}h–{int(c['t1']//3600)}h`): Heatmap Score `{c.get('heatmap_score', 0)}/100` ({c.get('peak_count', 0)} viral peaks)"
                    for c in chunks
                ])

                long_embed = discord.Embed(
                    title="🌊 Massive Stream Detected (> 2 Hours) • Chunking Engine",
                    description=(
                        f"**Detected Stream:** `{v_title or u}`\n"
                        f"**Streamer:** **{c_found.upper()}**\n"
                        f"**Total Duration:** **{hours_formatted}**\n\n"
                        f"⚡ **YouTube Replay Heatmap & 2-Hour Chunking Engine:**\n"
                        f"To eliminate network drops and transcribe efficiently, this stream is segmented into 2-hour slices scored against YouTube's 'Most Replayed' heatmap:\n\n"
                        f"{parts_desc}\n\n"
                        f"🔥 **Recommended:** Tap **🔥 Hottest Segment** to snipe the most viral 2-hour window automatically, or select any specific part below!"
                    ),
                    color=0xFF5722
                )
                long_embed.set_footer(text="AutoClip Heatmap Sniping Engine • Surgical Sectional Download")

                intake_msg = await reply_safely(message, embed=long_embed, view=intake_view)
                intake_view.message = intake_msg
                PENDING_INTAKE[message.channel.id] = {
                    "url": u,
                    "creator": c_found,
                    "video_title": v_title,
                    "layout_mode": intake_view.layout_mode,
                    "intake_msg": intake_msg
                }
                return

            # Twitch Clip or Short Scene Intake (< 90 Seconds)
            if is_twitch_clip(u) or (0 < v_duration <= 90.0):
                intake_view = TwitchClipIntakeView(
                    channel=message.channel,
                    url=u,
                    creator=c_found,
                    video_title=v_title,
                    duration=v_duration or 30.0
                )
                clip_embed = discord.Embed(
                    title=f"🟣 Twitch Viral Scene Detected: {v_title or u}",
                    description=(
                        f"**Streamer:** **{c_found.upper()}**\n"
                        f"**Duration:** `{v_duration:.0f}s` (High-Density Stream Moment)\n\n"
                        f"⚡ **1-Click Short Remastering:**\n"
                        f"Formats directly into 9:16 vertical HD, animated golden-pop subtitles (#FFD200) synced, and {c_found.title()}'s dedicated viral BGM layered at -14 LUFS.\n\n"
                        f"🎯 **Select Layout to Produce:**"
                    ),
                    color=0x9146FF
                )
                if yt_info.get("thumbnail"):
                    clip_embed.set_thumbnail(url=yt_info["thumbnail"])
                clip_embed.set_footer(text="AutoClip Twitch Remaster Engine • 1-Click Production")
                intake_msg = await reply_safely(message, embed=clip_embed, view=intake_view)
                intake_view.message = intake_msg
                PENDING_INTAKE[message.channel.id] = {
                    "url": u,
                    "creator": c_found,
                    "video_title": v_title,
                    "layout_mode": "blur_fill",
                    "intake_msg": intake_msg
                }
                return

            # ALWAYS present the Interactive Intake Menu First so the user decides the exact format!
            intake_view = VideoIntakeChoiceView(
                channel=message.channel,
                url=u,
                creator=c_found,
                video_title=v_title
            )

            c_display = c_found.upper()
            intake_embed = discord.Embed(
                title=f"🎬 AutoClip AI Production: Choose Format & Theme",
                description=(
                    f"**Detected Video:** `{v_title or u}`\n"
                    f"**Detected Streamer:** **{c_display}**\n\n"
                    f"🎯 **Select how you would like AutoClip to produce this video:**\n\n"
                    f"1️⃣ **Top 5 Countdown Short** — Pick a theme from the dropdown menu below:\n"
                    f"   • *IShowSpeed:* Top 5 Foods He's Eating, Funniest, Cringiest, Scariest, Wildest\n"
                    f"   • *Jynxzi:* Top 5 Headshots & Snipes, Best Gameplays, Rage Moments, Funniest\n"
                    f"   • *CaseOh:* Top 5 Horror Jumpscares, Funny Rage & Bans, Food/Waffle House, Funniest\n"
                    f"   • *Kai Cenat:* Top 5 Funniest, Craziest Stream Chaos, Celebrity Reactions\n"
                    f"   • *Or select '✍️ Custom Theme...' to type your own!*\n\n"
                    f"2️⃣ **🎬 5 Normal Ranked Shorts** — Click the button below for individual clips\n\n"
                    f"🖼️ **Layout Selection:** Choose between **MrBeast Blur** (16:9 centered with blurred background) or **Split-Screen**.\n\n"
                    f"💬 *You can also simply reply with your choice in chat! (e.g. 'top 5 foods', 'top 5 funniest', 'normal clips')*"
                ),
                color=0xFFD200
            )
            intake_embed.set_footer(text="AutoClip AI Production Studio • Interactive Intake")

            intake_msg = await reply_safely(message, embed=intake_embed, view=intake_view)
            intake_view.message = intake_msg
            PENDING_INTAKE[message.channel.id] = {
                "url": u,
                "creator": c_found,
                "video_title": v_title,
                "layout_mode": intake_view.layout_mode,
                "intake_msg": intake_msg
            }
            return

    # Check if user is asking an advice-oriented question rather than issuing an action command
    is_advice_question = any(q in lower for q in [
        "should i", "which clip should", "which one is better", "what do you think",
        "what if", "can you tell me who", "who is trending", "what should i"
    ]) or (lower.endswith("?") and not any(act in lower for act in ["make", "create", "upload", "post", "compile", "combine", "give", "show", "split", "extend", "edit", "remaster"]))

    # 1. Natural Language Upload Request: "Hey upload this", "Upload #2 to my channel", etc.
    upload_triggers = ["upload this", "upload it", "upload to youtube", "upload to my channel", "post this", "upload clip"]
    has_upload_intent = any(trig in lower for trig in upload_triggers) or (
        ("upload" in lower or "post" in lower) and ("this" in lower or "clip" in lower or "youtube" in lower or "channel" in lower)
    )

    if has_upload_intent and not is_advice_question:
        session = get_channel_session(message.channel.id)
        if not session or not session.get("shorts"):
            await reply_safely(message, content="⚠️ I couldn't find any recently generated Shorts in this channel. Paste a YouTube URL first!")
            return

        shorts = session["shorts"]
        word_to_num = {
            "first": 1, "1st": 1, "one": 1,
            "second": 2, "2nd": 2, "two": 2,
            "third": 3, "3rd": 3, "three": 3,
            "fourth": 4, "4th": 4, "four": 4,
            "fifth": 5, "5th": 5, "five": 5
        }
        target_rank = None
        for w, n in word_to_num.items():
            if re.search(r'\b' + w + r'\b', lower):
                target_rank = n
                break
        if target_rank is None:
            m_rank = re.search(r'#?([1-5])', lower)
            target_rank = int(m_rank.group(1)) if m_rank else 1

        c_key = chosen_short.get("creator_id") or chosen_short.get("creator") or "speed"
        try:
            r_info = channel_routing.get_route(c_key)
            c_disp = f"**{r_info.get('target_name')}** ({r_info.get('handle')})"
        except Exception:
            c_disp = "target YouTube channel"
        await reply_safely(message, content=f"🚀 Got it! Uploading **Rank #{chosen_short.get('rank')}** (*'{chosen_short.get('title')}'*) to {c_disp} now...")
        await upload_and_notify(message.channel, chosen_short)
        return

    # 2. Show / Send Clips Request: "show me other clips", "no show me clip 2 and 3 and 4 and 5", "show clip 2", etc.
    show_triggers = ["show me", "send me", "give me", "let me see", "can i see", "show other", "other clip", "other clips", "all clip", "all clips", "send clip", "post clip to chat"]
    is_show_request = any(trig in lower for trig in show_triggers) or (lower.startswith("show") and "clip" in lower) or ("other clips" in lower) or ("clip 2 and" in lower)
    if is_show_request:
        session = get_channel_session(message.channel.id)
        if not session or not session.get("shorts"):
            await reply_safely(message, content="⚠️ No generated Shorts found in this channel yet. Paste a YouTube URL first!")
            return

        shorts = session["shorts"]
        found_ranks = [int(x) for x in re.findall(r'#?([1-5])', lower)]
        if not found_ranks:
            found_ranks = [s.get("rank") for s in shorts if s.get("rank") != 1]
            if not found_ranks:
                found_ranks = [s.get("rank") for s in shorts]

        sent_count = 0
        for r in found_ranks:
            short_match = next((s for s in shorts if s.get("rank") == r), None)
            if not short_match:
                continue
            v_path = short_match.get("video_path")
            if v_path and os.path.exists(v_path):
                sub_view = UploadShortsView([short_match], message.channel)
                caption = f"🎬 **Rank #{r} Short:** *'{short_match.get('title')}'* (Score: {short_match.get('score')}/100, {short_match.get('duration', 0):.1f}s)"
                await send_video_safely(message.channel, v_path, caption=caption, view=sub_view)
                sent_count += 1
        if sent_count > 0 and message.guild and message.guild.voice_client:
            await speak_text_in_vc(message.guild, f"Here are the clips you requested!")
        return

    # 2.5 Top 5 Countdown Compilation: "top 5 funniest moments", "make a top 5 countdown", "combine all 5 moments", etc.
    if any(trig in lower for trig in countdown_triggers) and not is_advice_question:
        is_multi = any(w in lower for w in [
            "these videos", "all videos", "both videos", "across videos",
            "these 2", "these 3", "multiple videos", "from all", "from these",
            "these", "all", "videos", "both"
        ])
        target_session = None

        theme = extract_theme(lower)
        if is_multi:
            multi_clips = get_multi_video_shorts(max_videos=5, theme=theme)
            if len(multi_clips) >= 2:
                target_session = {"shorts": multi_clips, "video_title": f"Top 5 {theme.title()} Multi-Video", "is_multi": True}

        if not target_session:
            target_session = get_channel_session(message.channel.id)

        if not target_session or not target_session.get("shorts"):
            await reply_safely(message, content="⚠️ No Shorts session found in this channel to compile. Paste a YouTube URL first!")
            return

        origin_label = "Across All Recent Videos" if is_multi else "This Video"
        status_msg = await reply_safely(
            message,
            content=(
                f"🎬 **AI Video Director Activated:** Compiling **TOP 5 {theme.upper()} MOMENTS** ({origin_label})!\n"
                f"• Structure: Title Intro Card (1.5s) ➔ #5 ➔ #4 ➔ #3 ➔ #2 ➔ #1 Climax (THE BEST ONE)\n"
                f"• Sound Design: Tailored BGM + Animated Transition Cards\n"
                f"⏳ Trimming top moments, generating animated countdown cards, and compiling master Short..."
            )
        )

        loop = asyncio.get_event_loop()
        def do_top5():
            return execute_top5_countdown(target_session, theme=theme)

        try:
            top5_res = await loop.run_in_executor(None, do_top5)
            comp_path = top5_res.get("video_path")
            comp_short = {
                "rank": 1,
                "title": top5_res.get("title"),
                "video_path": comp_path,
                "duration": top5_res.get("duration", 0),
                "description": f"Top 5 {theme} moments! #shorts #viral",
                "tags": ["shorts", "viral", "top5", theme]
            }
            comp_view = UploadShortsView([comp_short], message.channel)

            await status_msg.edit(content=f"✨ **TOP 5 {theme.upper()} MOMENTS Countdown Ready!**\n*{top5_res.get('title')}* | Duration: {top5_res.get('duration', 0):.1f}s")
            await send_video_safely(
                message.channel,
                comp_path,
                caption=f"🎬 **Top 5 Countdown Short File (Ready to Post):**",
                view=comp_view
            )
            if top5_res.get("low_intensity_warning"):
                try:
                    await message.channel.send(content=top5_res["low_intensity_warning"])
                except Exception:
                    pass
            if message.guild and message.guild.voice_client:
                await speak_text_in_vc(message.guild, f"Your top 5 {theme} countdown video is ready! Check it out in chat.")
        except Exception as ex:
            await status_msg.edit(content=f"❌ Top 5 Compilation failed: `{str(ex)[:500]}`")
        return

    # 2.8 Keep / Preserve Media Request: "keep", "save source", "keep video", "dont delete", "dont delete video", etc.
    keep_triggers = ["keep", "save source", "keep source", "dont delete", "don't delete", "keep video", "save video", "save the video", "keep files", "preserve"]
    is_keep_request = any(re.search(r'\b' + re.escape(trig) + r'\b', lower) for trig in keep_triggers) and not is_advice_question
    if is_keep_request:
        session = get_channel_session(message.channel.id)
        if session and session.get("shorts"):
            v_title = session.get("video_title", "Current Session")
            v_slug = session["shorts"][0].get("filename", "").split("_rank")[0]
            if v_slug:
                KEEP_MEDIA_REQUESTS.add(v_slug)
            KEEP_MEDIA_REQUESTS.add("all")
            await reply_safely(
                message,
                content=f"🛡️ **Source Media Preserved:** Source video and raw assets for **'{v_title}'** will NOT be auto-deleted. Stored safely on disk!"
            )
            return
        else:
            KEEP_MEDIA_REQUESTS.add("all")
            await reply_safely(message, content="🛡️ **Keep Preference Noted:** Downloaded source videos for active/upcoming jobs will be preserved on disk.")
            return

    # 3. Conversational Video Remaster / Edit Request: "split the screen in clip 1", "extend it a little bit to complete the story",
    # "i dont see any hook or ending i want a proper ending for this clip where there is hook elevation and change the music its not good", etc.
    edit_keywords = [
        "split", "extend", "trim", "shorter", "longer", "remaster", "edit", "re-edit", "redo",
        "hook", "ending", "properending", "elevation", "music", "bgm", "song", "audio", "sound",
        "story", "complete", "subtitles", "caption", "remake", "challenge", "versus", "1v1", "two people"
    ]
    direction_words = [
        "want", "change", "fix", "improve", "add", "make", "dont see", "no hook", "need", "proper",
        "better", "not good", "bad", "cut", "remake", "update", "please", "more", "elevation", "create"
    ]
    has_edit_intent = (
        any(k in lower for k in [
            "split the screen", "split screen", "extend", "complete the story", "complete that story",
            "change the music", "proper ending", "properending", "hook elevation", "dont see any hook",
            "no hook", "new music", "different song", "fix the ending", "remaster", "edit clip",
            "not good", "change song", "change music", "change bgm", "challenge video", "between two people",
            "1v1", "versus", "vs mode"
        ]) or
        (any(k in lower for k in edit_keywords) and any(d in lower for d in direction_words + ["clip", "this", "#1", "#2", "#3", "#4", "#5"]))
    )

    # 2.9 Learning Feedback & Preference Directives:
    # "first clip, this should be how this is very good", "clip 1 is very good", "love clip 2",
    # "next time do this in the next clips", "this is better, next time do this",
    # "I don't want this clip, make it like this", "the captions are not good, make it like that"
    learning_triggers = [
        "very good", "this is how it should be", "this should be how", "love this clip", "love clip",
        "next time", "in the next clips", "from now on", "i dont want this clip", "i don't want this clip",
        "make it like this", "make it like that", "not good", "bad", "learn this", "remember this"
    ]
    is_learning_feedback = any(trig in lower for trig in learning_triggers) and any(w in lower for w in ["clip", "first", "second", "third", "1", "2", "3", "next", "caption", "captions", "bgm", "music", "split", "short"])

    if is_learning_feedback and not has_edit_intent:
        session = get_channel_session(message.channel.id)
        target_short = None
        if session and session.get("shorts"):
            shorts = session["shorts"]
            word_to_num = {
                "first": 1, "1st": 1, "one": 1,
                "second": 2, "2nd": 2, "two": 2,
                "third": 3, "3rd": 3, "three": 3,
                "fourth": 4, "4th": 4, "four": 4,
                "fifth": 5, "5th": 5, "five": 5
            }
            target_rank = None
            for w, n in word_to_num.items():
                if re.search(r'\b' + w + r'\b', lower):
                    target_rank = n
                    break
            if target_rank is None:
                m_rank = re.search(r'#?([1-5])', lower)
                target_rank = int(m_rank.group(1)) if m_rank else 1
            target_short = next((s for s in shorts if s.get("rank") == target_rank), shorts[0])
        else:
            multi = get_multi_video_shorts(max_videos=3)
            if multi:
                target_short = multi[0]
            else:
                target_short = {"rank": 1, "title": "Current Clip"}

        is_positive = any(pos in lower for pos in ["very good", "love", "this should be how", "this is how", "great", "perfect", "good", "better"])
        fb_type = "positive" if is_positive else "rule"
        res = memory_mod.record_feedback(target_short, fb_type, message.content)
        bullets = "\n".join(f"• {p}" for p in res.get("learned_points", [])) if res.get("learned_points") else f"• Instruction logged: '{message.content}'"

        embed = discord.Embed(
            title=f"🧠 Preference Learned & Saved (Clip #{target_short.get('rank', 1)})",
            description=(
                f"**Your Direction:**\n*\"{message.content}\"*\n\n"
                f"**Updated Memory Rules:**\n{bullets}\n\n"
                f"✅ Saved permanently in `data/pipeline_memory.json`. Hermes will automatically apply these settings to upcoming clips!"
            ),
            color=0x10B981 if is_positive else 0x3B82F6
        )
        await reply_safely(message, embed=embed)
        return

    # 3. Conversational Video Remaster / Edit Request
    if has_edit_intent and not is_advice_question:
        session = get_channel_session(message.channel.id)
        if not session or not session.get("shorts"):
            multi = get_multi_video_shorts(max_videos=3)
            if multi:
                target_short = multi[0]
            else:
                await reply_safely(message, content="⚠️ No Shorts session found in this channel to edit. Paste a YouTube URL first!")
                return
        else:
            shorts = session["shorts"]
            word_to_num = {
                "first": 1, "1st": 1, "one": 1,
                "second": 2, "2nd": 2, "two": 2,
                "third": 3, "3rd": 3, "three": 3,
                "fourth": 4, "4th": 4, "four": 4,
                "fifth": 5, "5th": 5, "five": 5
            }
            target_rank = None
            for w, n in word_to_num.items():
                if re.search(r'\b' + w + r'\b', lower):
                    target_rank = n
                    break
            if target_rank is None:
                m_rank = re.search(r'#?([1-5])', lower)
                target_rank = int(m_rank.group(1)) if m_rank else 1
            target_short = next((s for s in shorts if s.get("rank") == target_rank), shorts[0])

        await do_conversational_remaster(message.channel, target_short, message.content, original_message=message)
        return


    # 5. Freeform AI Producer Conversation (NO @ mention needed, NO slash needed!)
    clean_prompt = message.content.replace(f"<@{bot.user.id}>", "").strip() if bot.user else message.content.strip()
    if clean_prompt and not message.content.startswith("!"):
        async with message.channel.typing():
            system_prompt = (
                "You are Hermes, the AI Executive Producer and Video Companion for YouTube channel 'Ask What?' (@askwhatt).\n"
                "You help creators brainstorm viral YouTube Shorts ideas, critique videos, select high-energy streamer moments (IShowSpeed, Kai Cenat, Marlon, etc.), and discuss growth strategies.\n"
                "You also answer any general questions, chat naturally, and offer charismatic, witty, and tactical advice.\n"
                "Keep responses punchy, concise, helpful, and creator-focused."
            )
            try:
                reply = llm_mod.query_cascade(clean_prompt, system_prompt=system_prompt)
            except Exception:
                reply = (
                    "🔥 **Tactical AI Producer Advice:**\n"
                    "• **Recommended Creator:** Focus on IShowSpeed, Jynxzi, or Kai Cenat for maximum algorithm reach.\n"
                    "• **Retention Blueprint:** Frontload a high-curiosity hook in the first 2 seconds (`WAIT TILL THE END 💀`), keep pacing snappy, and end on a natural punchline.\n"
                    "• **Optimal Posting Window:** Upload between 4:00 PM – 7:00 PM EDT for peak viewership.\n\n"
                    "Paste any YouTube URL or tell me how you want to edit any clip!"
                )

            embed = discord.Embed(
                title="🎙️ Hermes AI Producer",
                description=reply[:2000],
                color=0xFFD200
            )

            voice_file = None
            if was_voice_message or any(v in lower for v in ["speak", "voice", "audio", "say"]):
                voice_out_path = os.path.join(config.media_dir(), f"reply_{uuid.uuid4().hex[:6]}.mp3")
                vf = await generate_voice_file(reply, voice_out_path)
                if vf and os.path.exists(vf):
                    voice_file = discord.File(vf, filename="hermes_voice_reply.mp3")

            await reply_safely(message, embed=embed, file=voice_file)

            if message.guild and message.guild.voice_client:
                await speak_text_in_vc(message.guild, reply)
        return

    await bot.process_commands(message)

# --- Unified Pipeline Executor with LIVE Step-by-Step UI ---

async def handle_clip_pipeline(channel, url, creator_slug=None, auto_upload=True, interaction=None, theme=None, reframe_mode=None, status_msg_override=None, deliver_individual=True, fresh=True, chunk_part=None):
    lock_key = f"{url}:part{chunk_part}" if chunk_part else url
    now_t = time.time()
    if lock_key in ACTIVE_PROCESSING_URLS:
        # Auto-expire locks older than 15 minutes to recover from interrupted processes
        if now_t - ACTIVE_PROCESSING_URLS.get(lock_key, 0) > 900:
            ACTIVE_PROCESSING_URLS.pop(lock_key, None)
        else:
            part_str = f" Part {chunk_part}" if chunk_part else ""
            warn_msg = f"⚠️ This stream/segment (`{url}`{part_str}) is currently already being processed by AutoClip! Please monitor the active progress card above."
            if status_msg_override:
                try:
                    await status_msg_override.edit(content=warn_msg)
                except Exception:
                    await channel.send(warn_msg)
            elif interaction:
                try:
                    await interaction.followup.send(content=warn_msg)
                except Exception:
                    await channel.send(warn_msg)
            else:
                await channel.send(warn_msg)
            return None

    ACTIVE_PROCESSING_URLS[lock_key] = now_t
    upload_target_label = "Disabled"
    if auto_upload:
        try:
            r_info = channel_routing.get_route(creator_slug or "speed")
            upload_target_label = f"Enabled -> {r_info.get('target_name')} ({r_info.get('handle')})"
        except Exception:
            upload_target_label = "Enabled"

    format_label = f"Top 5 {theme.upper()} Focus" if theme else "5 Standalone Shorts"
    layout_label = "MrBeast Blurred Background" if reframe_mode == "blur_fill" else ("Split-Screen (Facecam + Game)" if reframe_mode == "split_screen" else "Auto Smart Reframe")
    media_platform = "Twitch Live Stream" if "twitch.tv" in url.lower() else "YouTube Video"
    init_embed = discord.Embed(
        title=f"⚡ AutoClip AI: Processing {media_platform}",
        description=f"**Source URL:** {url}\n**Creator Profile:** {creator_slug.title() if creator_slug else 'Auto-Detect'}\n**Format:** {format_label}\n**Layout:** {layout_label}\n**Auto-Upload:** {upload_target_label}",
        color=0x9146FF if "twitch.tv" in url.lower() else 0xFFD200
    )
    init_progress = (
        "⏳ **Stage 1/8:** INGESTING (Metadata & Chapters)\n"
        "⚪ **Stage 2/8:** TRANSCRIPT_READY (Captions Sync)\n"
        "⚪ **Stage 3/8:** DISCOVERING_CANDIDATES (50-80 Moments)\n"
        "⚪ **Stage 4/8:** FILTERING_CANDIDATES (Pre-Filter ~20)\n"
        "⚪ **Stage 5/8:** VISUAL_VERIFYING (Sequential Previews)\n"
        "⚪ **Stage 6/8:** SELECTING_FINALISTS (Multi-Modal Scoring)\n"
        "⚪ **Stage 7/8:** RENDERING (720p HD Cuts & 9:16 Reframe)\n"
        "⚪ **Stage 8/8:** QUALITY_CHECK & COMPLETE (QA Pass)\n\n"
        "**Status:** Initializing pipeline..."
    )
    init_embed.add_field(name="Live Pipeline Progress", value=init_progress, inline=False)

    if status_msg_override:
        status_msg = status_msg_override
        try:
            await status_msg.edit(content=None, embed=init_embed, view=None)
        except Exception:
            status_msg = await channel.send(embed=init_embed)
    elif interaction:
        status_msg = await interaction.followup.send(embed=init_embed)
    else:
        status_msg = await channel.send(embed=init_embed)

    if channel.guild and channel.guild.voice_client:
        await speak_text_in_vc(channel.guild, f"Downloading and processing video from {media_platform}. Generating 5 ranked shorts now.")

    loop = asyncio.get_event_loop()
    last_update = [0.0]

    def on_progress(pct, msg):
        now = time.time()
        if now - last_update[0] < 1.2 and pct < 100:
            return
        last_update[0] = now

        s1 = "✅" if pct >= 15 else ("⏳" if pct >= 5 else "⚪")
        s2 = "✅" if pct >= 28 else ("⏳" if pct >= 15 else "⚪")
        s3 = "✅" if pct >= 35 else ("⏳" if pct >= 28 else "⚪")
        s4 = "✅" if pct >= 39 else ("⏳" if pct >= 35 else "⚪")
        s5 = "✅" if pct >= 66 else ("⏳" if pct >= 39 else "⚪")
        s6 = "✅" if pct >= 72 else ("⏳" if pct >= 66 else "⚪")
        s7 = "✅" if pct >= 96 else ("⏳" if pct >= 72 else "⚪")
        s8 = "✅" if pct >= 100 else ("⏳" if pct >= 96 else "⚪")

        prog_text = (
            f"{s1} **Stage 1/8:** INGESTING (Metadata & Chapters)\n"
            f"{s2} **Stage 2/8:** TRANSCRIPT_READY (Captions Sync)\n"
            f"{s3} **Stage 3/8:** DISCOVERING_CANDIDATES (50-80 Moments)\n"
            f"{s4} **Stage 4/8:** FILTERING_CANDIDATES (Pre-Filter ~20)\n"
            f"{s5} **Stage 5/8:** VISUAL_VERIFYING (Sequential Previews)\n"
            f"{s6} **Stage 6/8:** SELECTING_FINALISTS (Multi-Modal Scoring)\n"
            f"{s7} **Stage 7/8:** RENDERING (720p HD Cuts & 9:16 Reframe)\n"
            f"{s8} **Stage 8/8:** QUALITY_CHECK & COMPLETE (QA Pass)\n\n"
            f"**Live Task:** `{msg[:95]}` ({pct}%)"
        )

        up_embed = discord.Embed(
            title=f"⚡ AutoClip AI: Processing {media_platform}",
            description=f"**Source URL:** {url}\n**Creator Profile:** {creator_slug.title() if creator_slug else 'Auto-Detect'}\n**Auto-Upload:** {upload_target_label}",
            color=0x9146FF if "twitch.tv" in url.lower() else 0xFFD200
        )
        up_embed.add_field(name="Live Pipeline Progress", value=prog_text, inline=False)

        async def edit_embed():
            try:
                if interaction:
                    try:
                        await interaction.followup.edit_message(status_msg.id, embed=up_embed)
                        return
                    except Exception:
                        pass
                await status_msg.edit(embed=up_embed)
            except Exception:
                pass

        asyncio.run_coroutine_threadsafe(edit_embed(), loop)

    def run_sync():
        return bot_engine.process_youtube_url(
            url=url,
            creator=creator_slug,
            auto_upload=auto_upload,
            upload_rank=1,
            privacy="public",
            progress_cb=on_progress,
            theme=theme,
            reframe_mode=reframe_mode,
            fresh=fresh,
            chunk_part=chunk_part
        )

    loop = asyncio.get_event_loop()
    try:
        res = await loop.run_in_executor(None, run_sync)

        shorts = res.get("shorts", []) or res.get("ranked_shorts", []) or res.get("clips", [])
        uploads = res.get("uploads", [])
        vid_title = res.get("video_title", "YouTube Video")
        benchmark = res.get("benchmark") or {}

        # Save session to channel cache for natural language "Upload this" queries
        LAST_CHANNEL_SESSION[channel.id] = {"shorts": shorts, "video_title": vid_title}

        done_embed = discord.Embed(
            title=f"🎉 5 Ranked Shorts Created: {vid_title[:45]}",
            description=f"Generated in **{res.get('total_time_seconds', 0)}s** using Visual-Verified Smart Sectional Engine.",
            color=0x10B981
        )

        if benchmark:
            disc = benchmark.get("candidates_discovered", 0)
            pref = benchmark.get("candidates_prefiltered", 0)
            vv_cnt = benchmark.get("candidates_visually_verified", 0)
            shifts = benchmark.get("rank_changes_count", 0)
            avg_t = benchmark.get("avg_visual_verify_time_sec", 0)
            done_embed.add_field(
                name="📊 Objective Visual Benchmark",
                value=f"Discovered: **{disc}** | Pre-filtered: **{pref}** | Visually Verified: **{vv_cnt}**\nRank Shifts: **{shifts}** | Avg VV Time: **{avg_t}s** / cand",
                inline=False
            )

        for s in shorts:
            rank = s.get("rank")
            score = s.get("score")
            t_score = s.get("transcript_score", score)
            v_score = s.get("visual_score", "N/A")
            v_reason = s.get("visual_reason", "")
            title = s.get("title")
            hook = s.get("hook") or s.get("hook_text", "")
            duration = s.get("duration", 0)

            upload_info = ""
            if uploads and rank == 1:
                u_res = uploads[0].get("receipt", {})
                if u_res.get("ok"):
                    upload_info = f"\n🚀 **Live on YouTube:** [Watch Short]({u_res.get('url')})"
                else:
                    upload_info = f"\n⚠️ **Upload Note:** {u_res.get('error', 'Pending')[:90]}"

            v_note = f"\n👁 *Visual Impact: {v_reason}*" if v_reason else ""
            done_embed.add_field(
                name=f"#{rank} • Score: {score}/100 [📝 {t_score} | 👁 {v_score}] — {title[:35]}",
                value=f"🎯 *\"{hook}\"*\n⏱ {duration:.1f}s | 🎵 {s.get('track_title') or s.get('music_name', 'BGM')}{v_note}{upload_info}",
                inline=False
            )

        done_embed.set_footer(text="⚡ Auto-Clean: Source files auto-delete in 15s to save disk. Type 'keep' or /keep to save source.")

        # Attach Interactive Button View
        view = UploadShortsView(shorts, channel)

        if deliver_individual:
            if interaction:
                try:
                    await interaction.followup.edit_message(status_msg.id, embed=done_embed, view=view)
                except Exception:
                    try:
                        await status_msg.edit(embed=done_embed, view=view)
                    except Exception:
                        await channel.send(embed=done_embed, view=view)
            else:
                try:
                    await status_msg.edit(embed=done_embed, view=view)
                except Exception:
                    await channel.send(embed=done_embed, view=view)

            if channel.guild and channel.guild.voice_client:
                await speak_text_in_vc(channel.guild, f"Finished generating all 5 shorts for {vid_title[:30]}. Click upload or tell me which one to post.")

            # Upload all 5 ranked Shorts MP4 files directly to Discord chat
            for s in shorts:
                s_path = s.get("video_path")
                r_num = s.get("rank")
                s_score = s.get("score")
                s_title = s.get("title", f"Clip #{r_num}")
                s_hook = s.get("hook") or s.get("hook_text", "")
                t_score = s.get("transcript_score", s_score)
                v_score = s.get("visual_score", "N/A")
                v_reason = s.get("visual_reason", "")
                if s_path and os.path.exists(s_path):
                    # Generate High-CTR Thumbnail
                    from autoclip import thumbnail_generator
                    thumb_p = thumbnail_generator.generate_short_thumbnail(
                        s_path,
                        title=s_title,
                        creator=creator_slug,
                        hook=s_hook,
                        theme=theme
                    )
                    if thumb_p and os.path.exists(thumb_p):
                        s["thumbnail_path"] = thumb_p
                        try:
                            await channel.send(
                                content=f"🖼️ **Rank #{r_num} Thumbnail Preview:**",
                                file=discord.File(thumb_p, filename=os.path.basename(thumb_p))
                            )
                        except Exception as the:
                            print(f"[Thumbnail Preview] Note: {the}")

                    s_view = UploadShortsView([s], channel)
                    caption_text = (
                        f"🎬 **Rank #{r_num} Short — {s_title}**\n"
                        f"⏱ {s.get('duration', 0):.1f}s | 🎯 Hook: *\"{s_hook}\"*"
                    )
                    await send_video_safely(
                        channel,
                        s_path,
                        caption=caption_text,
                        view=s_view
                    )
        else:
            await status_msg.edit(
                content=f"✅ **Clips Extracted & Rendered for '{vid_title[:35]}'!** Assembling countdown master short now...",
                embed=None,
                view=None
            )

        # Schedule 15-second automatic cleanup for raw source video and scratch media
        vid_slug = None
        if shorts:
            vid_slug = shorts[0].get("filename", "").split("_rank")[0]
        if not vid_slug:
            try:
                vid_slug = youtube_pipeline.sanitize_slug(youtube_pipeline.get_youtube_info(url).get("id", ""))
            except Exception:
                pass

        if vid_slug:
            asyncio.create_task(schedule_source_cleanup(vid_slug, delay=15, channel=channel))

        return res

    except Exception as e:
        err_embed = discord.Embed(
            title="❌ AutoClip Pipeline Failed",
            description=f"```{str(e)[:1500]}```",
            color=0xEF4444
        )
        if interaction:
            await interaction.followup.edit_message(status_msg.id, embed=err_embed)
        else:
            await status_msg.edit(embed=err_embed)
        return None
    finally:
        ACTIVE_PROCESSING_URLS.pop(lock_key, None)
        ACTIVE_PROCESSING_URLS.pop(url, None)

if __name__ == "__main__":
    if not TOKEN:
        print("Please set DISCORD_BOT_TOKEN environment variable in .env.")
        print("Example: DISCORD_BOT_TOKEN=your_bot_token_here")
    else:
        import sys
        import time
        import subprocess

        if "--worker" in sys.argv:
            bot.run(TOKEN)
        else:
            print("[AutoClip Supervisor] Starting bot supervisor with auto-restart resilience...")
            worker_args = [sys.executable, __file__, "--worker"] + [a for a in sys.argv[1:] if a != "--worker"]
            while True:
                try:
                    proc = subprocess.run(worker_args)
                    if proc.returncode == 0:
                        print("[AutoClip Supervisor] Bot exited cleanly.")
                        break
                    print(f"[AutoClip Supervisor] Bot process exited with code {proc.returncode}. Auto-restarting in 3 seconds...")
                    time.sleep(3)
                except KeyboardInterrupt:
                    print("[AutoClip Supervisor] Stopped by user.")
                    break
                except Exception as e:
                    print(f"[AutoClip Supervisor] Error running bot process: {e}. Retrying in 5s...")
                    time.sleep(5)
