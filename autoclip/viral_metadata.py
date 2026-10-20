"""Viral Metadata, High-CTR Titles, Descriptions & Pinned Comments Generator.

Eliminates all robotic AI output (no "Viral score 76/100", no "QA gates", etc.).
Generates human, high-velocity metadata designed strictly for maximum CTR, watch time, and comment engagement.
"""

from typing import Dict, Any, List

def format_viral_title(raw_title: str, creator: str = "speed", theme: str = None) -> str:
    """Format an explosive, high-CTR YouTube Shorts title."""
    t = (raw_title or "").strip()
    c = (creator or "speed").lower()

    # If title already ends with #shorts, strip it temporarily for clean processing
    t_no_hash = t.replace("#shorts", "").replace("#Shorts", "").replace("#SHORTS", "").strip()

    import re
    # Clean any internal robotic phrases
    for bad in ["AutoClip", "Rank #1", "Rank 1", "Clip 1", "Moment 1"]:
        t_no_hash = t_no_hash.replace(bad, "").strip()

    # Common speech-to-text mishearing corrections for top streamer memes
    phonetic_fixes = [
        (r"\bchad do the gift of messy\b", "Chat do the GIF of Messi"),
        (r"\bgift of messy\b", "GIF of Messi"),
        (r"\bgift of messi\b", "GIF of Messi"),
        (r"\bthe gift of\b", "the GIF of"),
        (r"\bchad\b", "Chat"),
    ]
    for pattern, repl in phonetic_fixes:
        t_no_hash = re.sub(pattern, repl, t_no_hash, flags=re.IGNORECASE)

    if not t_no_hash:
        if "speed" in c:
            t_no_hash = "SPEED CANNOT BELIEVE THIS HAPPENED 💀"
        elif "case" in c:
            t_no_hash = "CASEOH LOST HIS MIND OVER THIS 😭"
        elif "jynx" in c:
            t_no_hash = "JYNXZI HITS THE CRAZIEST 1V4 CLUTCH 😱"
        else:
            t_no_hash = "NO WAY THIS ACTUALLY HAPPENED 💀"

    # Ensure emotional punctuation (?! or 💀 or 😭) if not present
    if not any(t_no_hash.endswith(p) for p in ["?!", "?", "!", "💀", "😭", "😱", "🤬", "🔥"]):
        t_no_hash += " 💀"

    return f"{t_no_hash} #shorts"

def build_viral_metadata(
    title: str,
    hook: str = "",
    creator: str = "speed",
    theme: str = None
) -> Dict[str, Any]:
    """Build complete viral package: title, human description, tags, and pinned comment."""
    c = (creator or "speed").lower()
    clean_title = format_viral_title(title, creator=c, theme=theme)

    if "speed" in c:
        creator_name = "IShowSpeed"
        channel_handle = "@SpeedClipsDailyOfficial"
        hook_q = "Did Speed actually just pull this off?! 😭 Drop your reaction below 👇"
        pinned_comment = "Bro really thought he had it under control 💀 Rate this reaction from 1-10 in the comments! 👇"
        tags = ["ishowspeed", "speed", "speedclips", "funny", "reaction", "gaming", "shorts", "viral", "trending"]
        hashtags = "#shorts #ishowspeed #speed #speedclips #funny #viral #gaming #trending"

    elif "case" in c:
        creator_name = "CaseOh"
        channel_handle = "@CaseOhClipsDaily"
        hook_q = "He was NOT ready for that jumpscare 😭 What would you have done here?! 👇"
        pinned_comment = "The exact second his soul left his body 😭 What game should CaseOh play next? Drop suggestions below! 👇"
        tags = ["caseoh", "caseohclips", "horror", "jumpscare", "funny", "gaming", "streamer", "shorts", "viral", "trending"]
        hashtags = "#shorts #caseoh #caseohclips #horror #jumpscare #funny #gaming #trending"

    elif "jynx" in c:
        creator_name = "Jynxzi"
        channel_handle = "@JynxziClipsHub"
        hook_q = "Was this pure skill or 100% luck?! 😭 Let me know your rank below 👇"
        pinned_comment = "Best controller player in the world or carried by luck? 😂 Debate your thoughts in the comments! 👇"
        tags = ["jynxzi", "jynxziclips", "r6", "rainbowsixsiege", "clutch", "headshot", "gaming", "shorts", "viral"]
        hashtags = "#shorts #jynxzi #jynxziclips #r6 #rainbowsixsiege #clutch #gaming #viral"

    elif "kai" in c:
        creator_name = "Kai Cenat"
        channel_handle = "@KaiCenat"
        hook_q = "The room was completely out of control 😂 Drop a like if you watched this live! 👇"
        pinned_comment = "Who had the wildest energy in this room? 😂 Drop your vote below! 👇"
        tags = ["kaicenat", "kai", "amp", "roomchaos", "streamer", "funny", "shorts", "viral", "trending"]
        hashtags = "#shorts #kaicenat #kai #amp #funny #viral #trending"

    else:
        creator_name = "Streamer"
        channel_handle = "@TrendingShorts"
        hook_q = "Did you see that ending coming?! 😂 Drop a comment below 👇"
        pinned_comment = "Rate this moment from 1 to 10 in the comments! 👇"
        tags = ["shorts", "viral", "streamer", "funny", "gaming", "highlights", "trending"]
        hashtags = "#shorts #viral #streamer #funny #gaming #trending"

    description = (
        f"{hook_q}\n\n"
        f"🔔 Subscribe to {channel_handle} for daily insane clips & highlights!\n"
        f"All original broadcast footage belongs to {creator_name}.\n\n"
        f"{hashtags}"
    )

    return {
        "title": clean_title,
        "description": description,
        "tags": tags,
        "pinned_comment": pinned_comment,
        "creator": c
    }
