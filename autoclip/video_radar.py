"""AutoClip Video Radar & Content Scout.

Discovers the latest videos and viral clips uploaded by top creators (IShowSpeed, CaseOh, Jynxzi, Kai Cenat),
across both YouTube and Twitch platforms, analyzes view velocity, duration, and keyword density
to calculate a Clipability & Viral Opportunity Score (0-100), and presents 1-click 'Produce Clips' buttons directly in Discord.
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from . import composio_client

STREAMER_CHANNELS = {
    "speed": {
        "name": "IShowSpeed",
        "avatar": "⚡",
        "channels": [
            {"handle": "@LiveSpeedy", "url": "https://www.youtube.com/@LiveSpeedy/videos", "type": "Streams / Edits"},
            {"handle": "@IShowSpeed", "url": "https://www.youtube.com/@IShowSpeed/videos", "type": "Main Channel"}
        ],
        "keywords": ["1v1", "kfc", "challenge", "stream", "rage", "fight", "mbappe", "world cup", "football", "fifa", "ronaldo", "police", "dating", "speed"]
    },
    "caseoh": {
        "name": "CaseOh",
        "avatar": "🍔",
        "channels": [
            {"handle": "@caseoh_", "url": "https://www.youtube.com/@caseoh_/videos", "type": "Main Games & Streams"}
        ],
        "twitch": {
            "broadcaster_id": "267160288",
            "login": "caseoh_",
            "url": "https://www.twitch.tv/caseoh_/videos",
            "clips_url": "https://www.twitch.tv/caseoh_/clips?filter=clips&range=7d"
        },
        "keywords": ["night shift", "horror", "elevator", "backrooms", "scariest", "jumpscare", "banned", "food", "waffle", "supermarket", "inspection", "60 seconds", "granny", "fears to fathom"]
    },
    "jynxzi": {
        "name": "Jynxzi",
        "avatar": "🎯",
        "channels": [
            {"handle": "@Jynxzi", "url": "https://www.youtube.com/@Jynxzi/videos", "type": "Main & Reactions"}
        ],
        "twitch": {
            "broadcaster_id": "411377640",
            "login": "jynxzi",
            "url": "https://www.twitch.tv/jynxzi/videos",
            "clips_url": "https://www.twitch.tv/jynxzi/clips?filter=clips&range=7d"
        },
        "keywords": ["clips", "fan mail", "1v1", "ranked", "rage", "insane", "worst", "best", "tournament", "r6", "rainbow six", "messi", "gif", "bronze", "champ", "1v5", "clutch"]
    },
    "kai": {
        "name": "Kai Cenat",
        "avatar": "👑",
        "channels": [
            {"handle": "@KaiCenat", "url": "https://www.youtube.com/@KaiCenat/videos", "type": "Main Channel"},
            {"handle": "@KaiCenatLive", "url": "https://www.youtube.com/@KaiCenatLive/videos", "type": "Live Stream Highlights"}
        ],
        "twitch": {
            "broadcaster_id": "641972806",
            "login": "kaicenat",
            "url": "https://www.twitch.tv/kaicenat/videos",
            "clips_url": "https://www.twitch.tv/kaicenat/clips?filter=clips&range=7d"
        },
        "keywords": ["stream", "marathon", "sleepover", "amp", "date", "celebrity", "freestyle", "rage", "funny"]
    }
}

def fetch_channel_videos(channel_url: str, max_videos: int = 5) -> List[Dict[str, Any]]:
    """Fetch the latest videos from a YouTube channel using yt-dlp flat playlist."""
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "-J",
        "--playlist-end", str(max_videos),
        "--no-warnings",
        "--socket-timeout", "10",
        channel_url
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        if proc.returncode != 0:
            return []
        data = json.loads(proc.stdout)
        entries = data.get("entries", [])
        results = []
        for e in entries:
            v_id = e.get("id")
            if not v_id:
                continue
            u = e.get("url") or f"https://www.youtube.com/watch?v={v_id}"
            results.append({
                "id": v_id,
                "url": u,
                "title": e.get("title", "Untitled Video"),
                "duration": float(e.get("duration") or 0),
                "view_count": int(e.get("view_count") or 0),
                "thumbnail": e.get("thumbnail") or f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg",
                "channel": data.get("channel") or data.get("uploader") or e.get("uploader", ""),
                "channel_url": channel_url,
                "platform": "youtube",
                "is_clip": False
            })
        return results
    except Exception as ex:
        print(f"[Video Radar] Fetch error for {channel_url}: {ex}")
        return []

def fetch_twitch_clips(username: str, broadcaster_id: Optional[str] = None, max_clips: int = 4, range_days: str = "7d") -> List[Dict[str, Any]]:
    """Fetch top clips of the week for a Twitch streamer (Composio MCP + yt-dlp fallback)."""
    results = []

    # 1. Try Composio MCP if broadcaster_id is known
    if broadcaster_id:
        try:
            mcp_clips = composio_client.get_twitch_clips(broadcaster_id, first=max_clips)
            if mcp_clips:
                for c in mcp_clips:
                    c_url = c.get("url") or f"https://clips.twitch.tv/{c.get('id')}"
                    results.append({
                        "id": str(c.get("id")),
                        "url": c_url,
                        "title": c.get("title", "Twitch Clip"),
                        "duration": float(c.get("duration") or 30.0),
                        "view_count": int(c.get("view_count") or 0),
                        "thumbnail": c.get("thumbnail_url", "").replace("%{width}", "480").replace("%{height}", "272"),
                        "channel": username,
                        "channel_url": f"https://www.twitch.tv/{username}",
                        "platform": "twitch",
                        "is_clip": True
                    })
                return results
        except Exception as ex:
            print(f"[Video Radar] Composio Twitch clips note: {ex}")

    # 2. Fallback to yt-dlp flat playlist
    clips_url = f"https://www.twitch.tv/{username}/clips?filter=clips&range={range_days}"
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "-J",
        "--playlist-end", str(max_clips),
        "--no-warnings",
        "--socket-timeout", "10",
        clips_url
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            for e in data.get("entries", []):
                c_url = e.get("url")
                if not c_url:
                    continue
                results.append({
                    "id": str(e.get("id")),
                    "url": c_url,
                    "title": e.get("title", "Twitch Clip"),
                    "duration": float(e.get("duration") or 30.0),
                    "view_count": int(e.get("view_count") or 0),
                    "thumbnail": e.get("thumbnail") or "",
                    "channel": username,
                    "channel_url": f"https://www.twitch.tv/{username}",
                    "platform": "twitch",
                    "is_clip": True
                })
    except Exception as ex:
        print(f"[Video Radar] yt-dlp Twitch clips fetch error for {username}: {ex}")

    return results

def format_twitch_relative_date(iso_str: str) -> str:
    """Format ISO date to human relative date (Today, Yesterday, X days ago)."""
    if not iso_str:
        return "Recent Stream"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = (now.date() - dt.date()).days
        if diff == 0:
            return "Today"
        elif diff == 1:
            return "Yesterday"
        elif diff <= 7:
            return f"{diff} days ago ({dt.strftime('%a, %b %d')})"
        return dt.strftime("%b %d, %Y")
    except Exception:
        return "Recent Stream"

def format_twitch_duration(dur_sec: float) -> str:
    """Format duration in seconds to clean human-readable hours and minutes."""
    h = int(dur_sec // 3600)
    m = int((dur_sec % 3600) // 60)
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m"

def fetch_twitch_vods(username: str, user_id: Optional[str] = None, max_vods: int = 5) -> List[Dict[str, Any]]:
    """Fetch recent live stream VODs from the past 4-5 days / week (Composio MCP + yt-dlp fallback)."""
    results = []

    # 1. Try Composio MCP if user_id is known
    if user_id:
        try:
            mcp_vods = composio_client.execute_tool(
                "TWITCH_GET_VIDEOS",
                {"user_id": user_id, "first": max_vods, "type": "archive", "sort": "time"}
            )
            data_items = mcp_vods.get("data", []) if isinstance(mcp_vods, dict) else []
            if data_items:
                for v in data_items:
                    v_url = v.get("url") or f"https://www.twitch.tv/videos/{v.get('id')}"
                    dur_str = v.get("duration", "")
                    dur_sec = 0.0
                    import re
                    h_m = re.search(r'(\d+)h', dur_str)
                    m_m = re.search(r'(\d+)m', dur_str)
                    s_m = re.search(r'(\d+)s', dur_str)
                    if h_m: dur_sec += int(h_m.group(1)) * 3600
                    if m_m: dur_sec += int(m_m.group(1)) * 60
                    if s_m: dur_sec += int(s_m.group(1))
                    dur_sec = dur_sec or 14400.0

                    pub_at = v.get("published_at") or v.get("created_at") or ""
                    date_lbl = format_twitch_relative_date(pub_at)
                    dur_formatted = format_twitch_duration(dur_sec)

                    results.append({
                        "id": str(v.get("id")),
                        "url": v_url,
                        "title": v.get("title", "Twitch Live Stream"),
                        "duration": dur_sec,
                        "duration_str": dur_formatted,
                        "date_label": date_lbl,
                        "published_at": pub_at,
                        "view_count": int(v.get("view_count") or 0),
                        "thumbnail": v.get("thumbnail_url", "").replace("%{width}", "480").replace("%{height}", "270"),
                        "channel": username,
                        "channel_url": f"https://www.twitch.tv/{username}",
                        "platform": "twitch",
                        "is_clip": False,
                        "is_stream_vod": True
                    })
                return results
        except Exception as ex:
            print(f"[Video Radar] Composio Twitch VODs note: {ex}")

    # 2. Fallback to yt-dlp flat playlist
    vods_url = f"https://www.twitch.tv/{username}/videos"
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "-J",
        "--playlist-end", str(max_vods),
        "--no-warnings",
        "--socket-timeout", "10",
        vods_url
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            for e in data.get("entries", []):
                v_url = e.get("url")
                if not v_url:
                    continue
                dur = float(e.get("duration") or 0)
                dur_formatted = format_twitch_duration(dur)
                results.append({
                    "id": str(e.get("id")),
                    "url": v_url,
                    "title": e.get("title", "Twitch Stream VOD"),
                    "duration": dur,
                    "duration_str": dur_formatted,
                    "date_label": "Recent Stream",
                    "published_at": "",
                    "view_count": int(e.get("view_count") or 0),
                    "thumbnail": e.get("thumbnail") or "",
                    "channel": username,
                    "channel_url": f"https://www.twitch.tv/{username}",
                    "platform": "twitch",
                    "is_clip": False,
                    "is_stream_vod": True
                })
    except Exception as ex:
        print(f"[Video Radar] yt-dlp Twitch VODs fetch error for {username}: {ex}")

    return results

def calculate_clipability_score(video_entry: Dict[str, Any], creator_slug: str) -> Dict[str, Any]:
    """Calculate Viral Opportunity Score (0-100) based on view count, duration, and keyword signals."""
    views = video_entry.get("view_count", 0)
    dur_sec = video_entry.get("duration", 0)
    dur_min = dur_sec / 60.0
    title_lower = video_entry.get("title", "").lower()
    is_clip = video_entry.get("is_clip", False)

    score = 50
    reasons = []

    # Twitch Clips have distinct viral characteristics: <60s isolated viral scenes
    if is_clip:
        score += 25
        reasons.append("⚡ Viral Twitch Scene (<60s Instant Remaster)")
        if views >= 50_000:
            score += 20
            reasons.append("🔥 Trending Clip (>50K Twitch Views)")
        elif views >= 10_000:
            score += 15
            reasons.append("📈 High Fan Activity (>10K Views)")
        elif views >= 2_000:
            score += 10
            reasons.append("⚡ Solid Twitch Engagement")
    else:
        # Standard full video / VOD logic
        is_vod = video_entry.get("is_stream_vod", False)
        if is_vod:
            date_lbl = video_entry.get("date_label", "Recent Stream")
            reasons.append(f"📅 Stream Date: {date_lbl}")
            reasons.append("⚡ 2-Hour Surgical Chunk Engine Ready")
            if views >= 100_000:
                score += 20
                reasons.append("🔥 Trending Live Stream (>100K Views)")
            elif views >= 30_000:
                score += 15
                reasons.append("📈 Strong Live Audience (>30K Views)")
            elif views >= 5_000:
                score += 10
        else:
            if views >= 1_000_000:
                score += 30
                reasons.append("🔥 Mega Viral (>1M Views)")
            elif views >= 500_000:
                score += 22
                reasons.append("📈 High Momentum (>500K Views)")
            elif views >= 200_000:
                score += 15
                reasons.append("⚡ Solid Audience (>200K Views)")
            elif views >= 50_000:
                score += 8
            else:
                score -= 5

        # VOD Length Clipability
        if 15.0 <= dur_min <= 75.0:
            score += 15
            reasons.append(f"⏱️ Prime VOD Length ({dur_min:.0f}m: 5+ shorts potential)")
        elif 75.0 < dur_min <= 180.0:
            score += 10
            reasons.append(f"⏱️ Extended Stream ({dur_min/60:.1f}h: 2h chunkable)")
        elif dur_min > 180.0:
            score += 12
            reasons.append(f"🌊 Massive Stream ({dur_min/60:.1f}h: 2-Hour Chunk Engine)")

    # High-CTR Trigger Keywords
    creator_info = STREAMER_CHANNELS.get(creator_slug, {})
    keywords = creator_info.get("keywords", [])
    matched_kws = [k for k in keywords if k in title_lower]
    if matched_kws:
        score += 12
        reasons.append(f"🎯 High-CTR Topic ({', '.join(matched_kws[:2]).title()})")

    score = max(20, min(99, score))

    # Tier label
    if score >= 90:
        tier = "S-Tier Viral Goldmine"
    elif score >= 80:
        tier = "A-Tier High Potential"
    elif score >= 70:
        tier = "B-Tier Solid Candidate"
    else:
        tier = "C-Tier Standard"

    return {
        "score": score,
        "tier": tier,
        "reasons": reasons,
        "summary": " • ".join(reasons) if reasons else "Trending Streamer Content"
    }

def scout_creator_videos(creator_slug: str, max_per_channel: int = 3, platform: str = "all") -> List[Dict[str, Any]]:
    """Scout all channels and Twitch streams for a given creator."""
    info = STREAMER_CHANNELS.get(creator_slug)
    if not info:
        return []

    all_videos = []

    # 1. YouTube Channels
    if platform in ("all", "youtube"):
        for ch in info.get("channels", []):
            vids = fetch_channel_videos(ch["url"], max_videos=max_per_channel)
            for v in vids:
                v["creator_slug"] = creator_slug
                v["creator_name"] = info["name"]
                v["creator_avatar"] = info["avatar"]
                v["channel_type"] = ch.get("type", "YouTube Channel")
                scoring = calculate_clipability_score(v, creator_slug)
                v.update(scoring)
                all_videos.append(v)

    # 2. Twitch Live Streams (VODs) — STRICT: Full streams only, NO clips (as instructed by user)
    if platform in ("all", "twitch") and "twitch" in info:
        t_info = info["twitch"]
        max_v = 5 if platform == "twitch" else max_per_channel
        t_vods = fetch_twitch_vods(t_info["login"], user_id=t_info.get("broadcaster_id"), max_vods=max_v)
        for vd in t_vods:
            vd["creator_slug"] = creator_slug
            vd["creator_name"] = info["name"]
            vd["creator_avatar"] = info["avatar"]
            vd["channel_type"] = f"Twitch Live Stream ({vd.get('date_label', 'Recent')})"
            scoring = calculate_clipability_score(vd, creator_slug)
            vd.update(scoring)
            all_videos.append(vd)

    if platform == "twitch":
        # Newest streams first (Today, Yesterday, 2 days ago...)
        all_videos.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    else:
        all_videos.sort(key=lambda x: x.get("score", 0), reverse=True)

    return all_videos

def scout_all_streamers(creators: Optional[List[str]] = None, top_n: int = 6, platform: str = "all") -> List[Dict[str, Any]]:
    """Scout across Jynxzi, Speed, CaseOh, and Kai Cenat simultaneously."""
    if platform == "twitch":
        target_creators = [c for c in (creators or ["caseoh", "jynxzi", "kai"]) if "twitch" in STREAMER_CHANNELS.get(c, {})]
    else:
        target_creators = creators or ["speed", "caseoh", "jynxzi", "kai"]

    all_picks = []
    for c in target_creators:
        picks = scout_creator_videos(c, max_per_channel=3 if platform == "twitch" else 2, platform=platform)
        all_picks.extend(picks)

    if platform == "twitch":
        all_picks.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    else:
        all_picks.sort(key=lambda x: x.get("score", 0), reverse=True)

    return all_picks[:top_n]

def scout_twitch_trending(creators: Optional[List[str]] = None, top_n: int = 6) -> List[Dict[str, Any]]:
    """Specifically scout past 4-5 days full live streams across Twitch streamers."""
    return scout_all_streamers(creators=creators, top_n=top_n, platform="twitch")

def scout_custom_channel(channel_input: str, max_videos: int = 5) -> List[Dict[str, Any]]:
    """Scout any custom channel URL or @handle provided by user."""
    url = channel_input.strip()
    if "twitch.tv" in url.lower():
        # Custom Twitch stream VODs
        import re
        m = re.search(r'twitch\.tv/([A-Za-z0-9_]+)', url)
        uname = m.group(1) if m else "twitch_streamer"
        vods = fetch_twitch_vods(uname, max_vods=max_videos)
        results = []
        for vd in vods:
            vd["creator_slug"] = "custom"
            vd["creator_name"] = uname
            vd["creator_avatar"] = "🟣"
            vd["channel_type"] = f"Twitch Live Stream ({vd.get('date_label', 'Recent')})"
            scoring = calculate_clipability_score(vd, "custom")
            vd.update(scoring)
            results.append(vd)
        results.sort(key=lambda x: x.get("published_at", ""), reverse=True)
        return results

    if not url.startswith("http"):
        handle = url if url.startswith("@") else f"@{url}"
        url = f"https://www.youtube.com/{handle}/videos"

    vids = fetch_channel_videos(url, max_videos=max_videos)
    results = []
    for v in vids:
        v["creator_slug"] = "custom"
        v["creator_name"] = v.get("channel") or "YouTuber"
        v["creator_avatar"] = "🎥"
        v["channel_type"] = "Custom Channel"
        scoring = calculate_clipability_score(v, "custom")
        v.update(scoring)
        results.append(v)

    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results
