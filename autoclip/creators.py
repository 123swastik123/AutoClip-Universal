"""Creator Profiles, 4-Track Streamer Sound Libraries & Full 40-Streamer Music Map.

Implements the 4-track sound design architecture for the Top 4 Streamers:
1. IShowSpeed (4 dedicated tracks)
2. Kai Cenat (4 dedicated tracks)
3. Jynxzi (4 dedicated tracks)
4. CaseOh (4 dedicated tracks)

Plus the complete 40-streamer viral sound signature registry, 5 viral music pools,
and audience upload timelines.
All tracks are 100% copyright-free & DMCA-safe (StreamBeats, CC0, Original Synthesis).
"""

import datetime
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

# =========================================================================
# 1. TOP 4 STREAMERS WITH 4 DEDICATED TRACKS EACH
# =========================================================================

CREATORS: Dict[str, Dict[str, Any]] = {
    "universal": {
        "id": "universal",
        "name": "Universal Creator",
        "handle": "@Creator",
        "avatar": "🎬",
        "tag": "Short-Form Highlights & Automated Montages",
        "demographics": "Universal Audience · Peak Evening Hours",
        "schedule": {
            "best_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            "best_hours_edt": [15.0, 19.0],
            "peak_label": "3:00 PM – 7:00 PM EDT (Peak Engagement)",
            "reason": "Optimal mobile viewing buffer before evening prime-time feeds.",
            "seeding_hours": 2.0
        },
        "tracks": [
            {
                "id": "sneaky_snitch",
                "name": "Sneaky Snitch (Quirky Comedy & Narrative)",
                "genre": "Comedy / Orchestral Sneak",
                "bpm": 120,
                "pool": "🟡 FUNNY / CHAOTIC",
                "vibe": "Pizzicato strings and playful bass for comedic moments and ranking reveals",
                "license": "CC0 / Royalty Free (Kevin MacLeod)",
                "bed_volume": 0.12,
                "duck_ratio": 7.0
            },
            {
                "id": "monkeys_spinning",
                "name": "Monkeys Spinning Monkeys (Upbeat Lighthearted)",
                "genre": "Playful Upbeat Acoustic",
                "bpm": 128,
                "pool": "🟠 HYPE / MEME",
                "vibe": "Fast bouncy flute and xylophone for high energy action",
                "license": "CC0 / Royalty Free (Kevin MacLeod)",
                "bed_volume": 0.12,
                "duck_ratio": 7.0
            }
        ]
    },
    "speed": {
        "id": "speed",
        "name": "IShowSpeed",
        "handle": "@IShowSpeed",
        "avatar": "⚡",
        "tag": "High Energy · Screaming Reactions · Challenges · Rages",
        "demographics": "Males 13–22 (US, UK, Brazil, Global) · After-School & Weekend Peak",
        "schedule": {
            "best_days": ["Friday", "Saturday", "Sunday"],
            "best_hours_edt": [14.5, 17.0],  # 2:30 PM - 5:00 PM EDT
            "peak_label": "Fri/Sat/Sun 2:30 PM – 5:00 PM EDT (US School Dismissal)",
            "reason": "Teens in US timezones finish school between 2:30–3:30 PM EDT. YouTube Shorts requires 2–3 hours of micro-cohort test indexing before exploding into prime-time evening feeds.",
            "seeding_hours": 2.5
        },
        # 4 Dedicated Viral Tracks
        "tracks": [
            {
                "id": "speed_brazilian_phonk",
                "name": "Brazilian Phonk (Rage & Climax)",
                "genre": "Brazilian Phonk",
                "bpm": 138,
                "pool": "🔴 RAGE / CLUTCH",
                "vibe": "Aggressive distorted 808 sub-bass, cowbell riffs, heavy phonk bounce for screaming freakouts",
                "license": "100% Royalty-Free & Safe (Original Synthesis)",
                "bed_volume": 0.20,
                "duck_ratio": 8.5
            },
            {
                "id": "speed_persona_surprise",
                "name": "Persona Surprise (Meme Crash-Out)",
                "genre": "Acid-Jazz / Latin Funk Homage",
                "bpm": 130,
                "pool": "🟠 HYPE / MEME",
                "vibe": "Fast energetic groove ('You'll Never See It Coming' meme vibe) with punchy brass stabs for Roblox rages",
                "license": "100% Royalty-Free Original Homage Bed",
                "bed_volume": 0.18,
                "duck_ratio": 8.0
            },
            {
                "id": "speed_streambeats_moonwalk",
                "name": "StreamBeats Moonwalk (EDM Drift)",
                "genre": "Festival EDM / Synth Drift",
                "bpm": 132,
                "pool": "🟠 HYPE",
                "vibe": "Driving synth arpeggios, high-velocity EDM bounce for insane speed stunts & energy runs",
                "license": "StreamBeats DMCA-Safe (Harris Heller)",
                "bed_volume": 0.19,
                "duck_ratio": 8.0
            },
            {
                "id": "speed_streambeats_slaps",
                "name": "StreamBeats Slaps (Goofy Slap Bounce)",
                "genre": "Quirky Trap Bounce",
                "bpm": 124,
                "pool": "🟡 FUNNY / CHAOTIC",
                "vibe": "Bouncy 808 glides with sudden dropouts on punchlines for funny reactions & laughing moments",
                "license": "StreamBeats DMCA-Safe (Harris Heller)",
                "bed_volume": 0.19,
                "duck_ratio": 7.5
            }
        ],
        "music": {
            "style": "speed_brazilian_phonk",
            "name": "Brazilian Phonk (Rage & Climax) (138 BPM)",
            "bpm": 138,
            "vibe": "Aggressive distorted 808 sub-bass, cowbell riffs, heavy phonk bounce for screaming freakouts",
            "bed_volume": 0.20,
            "duck_ratio": 8.5,
            "duck_threshold": 0.045
        },
        "metadata": {
            "title_prefix": "SPEED",
            "title_template": "{title} #shorts",
            "hashtags": ["#shorts", "#ishowspeed", "#speed", "#viral", "#funny", "#reaction", "#challenge", "#trending"],
            "tags": ["ishowspeed", "speed", "viral", "funny", "reaction", "shorts", "challenge", "streamer", "trending"],
            "desc_cta": "Speed loses his mind in the wildest stream moment! 🔥😂 Subscribe for daily high-energy clips!"
        }
    },
    "kai": {
        "id": "kai",
        "name": "Kai Cenat",
        "handle": "@KaiCenat",
        "avatar": "🎮",
        "tag": "Stream Chaos · AMP House · Celebrity Guests · Viral Comedy",
        "demographics": "Youth 14–25 (US East Coast, Atlanta, NYC, Global) · Late Afternoon Peak",
        "schedule": {
            "best_days": ["Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            "best_hours_edt": [15.5, 18.5],  # 3:30 PM - 6:30 PM EDT
            "peak_label": "Wed–Sun 3:30 PM – 6:30 PM EDT (Pre-Stream Surge)",
            "reason": "AMP and Kai Cenat viewers peak heavily during late afternoon commute and hours leading into his marquee evening Twitch streams.",
            "seeding_hours": 2.0
        },
        # 4 Dedicated Viral Tracks
        "tracks": [
            {
                "id": "kai_mamp_bouncy_trap",
                "name": "MAMP Bouncy Trap (Room Chaos)",
                "genre": "Bouncy NYC Stream Trap",
                "bpm": 118,
                "pool": "🟡 FUNNY / CHAOTIC",
                "vibe": "Bouncy syncopated 808s, playful marimba plucks, handclaps for room chaos and dancing",
                "license": "100% Royalty-Free & Safe (Original Synthesis)",
                "bed_volume": 0.20,
                "duck_ratio": 7.5
            },
            {
                "id": "kai_do_you_mind_nostalgia",
                "name": "Do You Mind (Late-Night UK Garage)",
                "genre": "UK Garage 2-Step / R&B Chops",
                "bpm": 124,
                "pool": "🔵 STORY / REACTION",
                "vibe": "Soulful electric piano chops, bouncy 2-step groove for Kai & Rakai singing / emotional comedic moments",
                "license": "100% Royalty-Free Safe Homage",
                "bed_volume": 0.18,
                "duck_ratio": 7.5
            },
            {
                "id": "kai_streambeats_prime",
                "name": "StreamBeats Prime (Celebrity Hype)",
                "genre": "Modern Hip-Hop Bounce",
                "bpm": 112,
                "pool": "🟠 HYPE",
                "vibe": "Punchy modern hip-hop drums, brass stabs, confident swagger groove for celebrity guest entrances",
                "license": "StreamBeats DMCA-Safe (Harris Heller)",
                "bed_volume": 0.19,
                "duck_ratio": 8.0
            },
            {
                "id": "kai_streambeats_groovy",
                "name": "StreamBeats Groovy (Chill Boom-Bap)",
                "genre": "Neo-Soul / Lo-Fi Boom-Bap",
                "bpm": 94,
                "pool": "🔵 STORY / REACTION",
                "vibe": "Smooth Rhodes piano, laid-back rim clicks for story setups and chat reactions before the drop",
                "license": "StreamBeats DMCA-Safe (Harris Heller)",
                "bed_volume": 0.18,
                "duck_ratio": 7.0
            }
        ],
        "music": {
            "style": "kai_mamp_bouncy_trap",
            "name": "MAMP Bouncy Trap (Room Chaos) (118 BPM)",
            "bpm": 118,
            "vibe": "Bouncy syncopated 808s, playful marimba plucks, handclaps for room chaos and dancing",
            "bed_volume": 0.20,
            "duck_ratio": 7.5,
            "duck_threshold": 0.05
        },
        "metadata": {
            "title_prefix": "KAI CENAT",
            "title_template": "{title} #shorts",
            "hashtags": ["#shorts", "#kaicenat", "#kai", "#amp", "#funny", "#reaction", "#streamer", "#viral"],
            "tags": ["kaicenat", "kai", "amp", "streamer", "funny", "reaction", "viral", "shorts", "trending"],
            "desc_cta": "Kai Cenat with an unforgettable stream moment! 💀🎮 Drop a like and subscribe for more AMP highlights!"
        }
    },
    "jynxzi": {
        "id": "jynxzi",
        "name": "Jynxzi",
        "handle": "@Jynxzi",
        "avatar": "🎯",
        "tag": "Rainbow Six Siege · Rage Clutches · Microphone Eating",
        "demographics": "Console Gamers 12–21 (US & UK) · Prime Gaming Hours",
        "schedule": {
            "best_days": ["Friday", "Saturday", "Sunday"],
            "best_hours_edt": [16.0, 19.0],  # 4:00 PM - 7:00 PM EDT
            "peak_label": "Fri/Sat/Sun 4:00 PM – 7:00 PM EDT (Prime Console Gaming Rush)",
            "reason": "Aligns with peak console gaming and tournament hours when young competitive gamers browse Shorts between matches.",
            "seeding_hours": 2.0
        },
        # 4 Dedicated Viral Tracks
        "tracks": [
            {
                "id": "jynxzi_tactical_phonk",
                "name": "Tactical Drift Phonk (1v5 Clutch)",
                "genre": "Dark Drift Phonk",
                "bpm": 142,
                "pool": "🔴 RAGE / CLUTCH",
                "vibe": "Fast aggressive drift phonk, rapid 16th hats, punchy distorted kicks for tense 1v5 gunfights",
                "license": "100% Royalty-Free & Safe (Original Synthesis)",
                "bed_volume": 0.20,
                "duck_ratio": 8.5
            },
            {
                "id": "jynxzi_streambeats_recon",
                "name": "StreamBeats Recon (Tension Riser)",
                "genre": "Tactical Cinematic Buildup",
                "bpm": 126,
                "pool": "🟣 CINEMATIC / SUSPENSE",
                "vibe": "Dark suspenseful low synth drone, ticking hi-hats, tension building until the final kill ('Wait for it...')",
                "license": "StreamBeats DMCA-Safe (Harris Heller)",
                "bed_volume": 0.18,
                "duck_ratio": 8.0
            },
            {
                "id": "jynxzi_streambeats_slaps",
                "name": "StreamBeats Slaps (Freakout Drop)",
                "genre": "Heavy EDM Bounce",
                "bpm": 135,
                "pool": "🔴 RAGE / CLUTCH",
                "vibe": "Heavy distorted bass drop, aggressive bounce, abrupt comedic silences for chair slams & freakouts",
                "license": "StreamBeats DMCA-Safe (Harris Heller)",
                "bed_volume": 0.19,
                "duck_ratio": 8.5
            },
            {
                "id": "jynxzi_brazilian_powerful",
                "name": "Brazilian Phonk Powerful (Victory Win)",
                "genre": "Brazilian Phonk Powerful",
                "bpm": 130,
                "pool": "🟠 HYPE",
                "vibe": "Heroic bass drop, infectious syncopated Brazilian rhythm, triumphant high energy for round wins",
                "license": "100% Royalty-Free Safe (Original Synthesis)",
                "bed_volume": 0.19,
                "duck_ratio": 8.0
            }
        ],
        "music": {
            "style": "jynxzi_tactical_phonk",
            "name": "Tactical Drift Phonk (1v5 Clutch) (142 BPM)",
            "bpm": 142,
            "vibe": "Fast aggressive drift phonk, rapid 16th hats, punchy distorted kicks for tense 1v5 gunfights",
            "bed_volume": 0.20,
            "duck_ratio": 8.5,
            "duck_threshold": 0.045
        },
        "metadata": {
            "title_prefix": "JYNXZI",
            "title_template": "{title} #shorts",
            "hashtags": ["#shorts", "#jynxzi", "#r6", "#twitch", "#gaming", "#funny", "#clip", "#viral"],
            "tags": ["jynxzi", "r6", "rainbowsix", "twitch", "gaming", "clutch", "funny", "shorts", "reaction"],
            "desc_cta": "Jynxzi cannot believe what just happened! 💀🎯 Subscribe for the best R6 clutches and rage clips!"
        }
    },
    "caseoh": {
        "id": "caseoh",
        "name": "CaseOh",
        "handle": "@CaseOh",
        "avatar": "🍔",
        "tag": "Chair Breaks · Waffle House Rants · Dono Roasts · Horror Jumps",
        "demographics": "Youth & Gen-Z 13–26 (US & Global) · Evening Stream Peaks",
        "schedule": {
            "best_days": ["Thursday", "Friday", "Saturday", "Sunday"],
            "best_hours_edt": [18.0, 21.0],  # 6:00 PM - 9:00 PM EDT
            "peak_label": "Thu–Sun 6:00 PM – 9:00 PM EDT (Evening Prime & Dono Rants)",
            "reason": "CaseOh streams peak in the evening when viewers tune in for outrageous donation alerts, food tier lists, and horror games.",
            "seeding_hours": 2.0
        },
        # 4 Dedicated Viral Tracks
        "tracks": [
            {
                "id": "caseoh_hypnotic_trap",
                "name": "Hypnotic Dream Trap (Slowed Lo-Fi)",
                "genre": "Slowed + Reverb Lo-Fi Trap",
                "bpm": 82,
                "pool": "🔵 STORY / REACTION",
                "vibe": "Dreamy warm bells, reverb atmosphere, smooth 808 glide for chat banter, quiet setups, and reading donos",
                "license": "100% Royalty-Free Safe Homage",
                "bed_volume": 0.18,
                "duck_ratio": 7.0
            },
            {
                "id": "caseoh_streambeats_arcade",
                "name": "StreamBeats Arcade (Chair Break Meme)",
                "genre": "8-Bit Chiptune / Sub Bass Drop",
                "bpm": 108,
                "pool": "🟡 FUNNY / CHAOTIC",
                "vibe": "Quirky 8-bit melodies with absurdly heavy booming sub drops for falling through chairs and dono roasts",
                "license": "StreamBeats DMCA-Safe (Harris Heller)",
                "bed_volume": 0.19,
                "duck_ratio": 8.0
            },
            {
                "id": "caseoh_streambeats_midnight",
                "name": "StreamBeats Midnight (Horror Suspense)",
                "genre": "Dark Atmospheric Synthwave",
                "bpm": 96,
                "pool": "🟣 CINEMATIC",
                "vibe": "Tense cinematic pulse, sudden drop on screams for 60 Seconds and horror game jump scares",
                "license": "StreamBeats DMCA-Safe (Harris Heller)",
                "bed_volume": 0.18,
                "duck_ratio": 7.5
            },
            {
                "id": "caseoh_quirky_ban_rant",
                "name": "Quirky Ban Rant (Cartoon Bounce)",
                "genre": "Comedic Walking Bass / Woodblock",
                "bpm": 115,
                "pool": "🟡 FUNNY / CHAOTIC",
                "vibe": "Goofy cartoon walking bassline and woodblock clicks for 'Yep, You're Banned!' and waffle house debates",
                "license": "100% Royalty-Free Safe (Original Synthesis)",
                "bed_volume": 0.19,
                "duck_ratio": 7.5
            }
        ],
        "music": {
            "style": "caseoh_hypnotic_trap",
            "name": "Hypnotic Dream Trap (Slowed Lo-Fi) (82 BPM)",
            "bpm": 82,
            "vibe": "Dreamy warm bells, reverb atmosphere, smooth 808 glide for chat banter, quiet setups, and reading donos",
            "bed_volume": 0.18,
            "duck_ratio": 7.0,
            "duck_threshold": 0.05
        },
        "metadata": {
            "title_prefix": "CASEOH",
            "title_template": "{title} #shorts",
            "hashtags": ["#shorts", "#caseoh", "#caseohgames", "#funny", "#streamer", "#rage", "#viral", "#trending"],
            "tags": ["caseoh", "caseohgames", "funny", "streamer", "rage", "shorts", "wafflehouse", "gaming", "viral"],
            "desc_cta": "CaseOh cannot take this anymore! 😂🍔 Like and subscribe for more daily CaseOh rants and moments!"
        }
    },
    "xqc": {
        "id": "xqc",
        "name": "xQc",
        "handle": "@xQcOW",
        "avatar": "🔥",
        "tag": "Rapid-Fire 300WPM Rants · Gaming Clutches · The Juicer",
        "demographics": "Males 16–28 (North America & European Cross-Atlantic Crossover)",
        "schedule": {
            "best_days": ["Daily"],
            "best_hours_edt": [11.5, 14.5],
            "peak_label": "Daily 11:30 AM – 2:30 PM EDT (US Lunch & EU Prime Evening)",
            "reason": "Captures the prime European evening audience (5:30 PM – 8:30 PM CEST) and North American lunchtime traffic simultaneously.",
            "seeding_hours": 2.0
        },
        "tracks": [
            {
                "id": "xqc_cyber_speed",
                "name": "Fast Cyber Glitchwave",
                "genre": "Synthwave / Glitch",
                "bpm": 138,
                "pool": "🟠 HYPE",
                "vibe": "Fast arcade synth arpeggios, driving kick-bass rhythm matching ultra-fast speech cadence",
                "license": "100% Royalty-Free",
                "bed_volume": 0.18,
                "duck_ratio": 8.0
            }
        ],
        "music": {
            "style": "xqc_cyber_speed",
            "name": "Fast Cyber Glitchwave (138 BPM, Non-Copyrighted)",
            "bpm": 138,
            "vibe": "Fast arcade synth arpeggios, driving kick-bass rhythm matching ultra-fast speech cadence",
            "bed_volume": 0.18,
            "duck_ratio": 8.0,
            "duck_threshold": 0.05
        },
        "metadata": {
            "title_prefix": "XQC",
            "title_template": "{title} #shorts",
            "hashtags": ["#shorts", "#xqc", "#xqcow", "#juicer", "#twitch", "#gaming", "#funny", "#reaction"],
            "tags": ["xqc", "xqcow", "juicer", "twitch", "gaming", "funny", "reaction", "shorts", "clutch"],
            "desc_cta": "The Juicer goes full speed! ⚡😂 Subscribe for the funniest daily xQc moments and rants!"
        }
    },
    "adin": {
        "id": "adin",
        "name": "Adin Ross",
        "handle": "@AdinRoss",
        "avatar": "🎙️",
        "tag": "Kick Streams · Celebrity Calls · Unfiltered Reactions",
        "demographics": "Males 15–24 (US Night Owls & Mobile TikTok Community)",
        "schedule": {
            "best_days": ["Thursday", "Friday", "Saturday", "Sunday"],
            "best_hours_edt": [17.0, 20.5],
            "peak_label": "Thu–Sun 5:00 PM – 8:30 PM EDT (Prime Evening & Kick Pre-Show)",
            "reason": "Adin's community is heavily active in the evening hours leading into his nighttime Kick broadcasts.",
            "seeding_hours": 2.0
        },
        "tracks": [
            {
                "id": "adin_lofi_trap",
                "name": "Nocturnal Melodic Piano Trap",
                "genre": "Late-Night Trap / Rhodes",
                "bpm": 92,
                "pool": "🔵 STORY / REACTION",
                "vibe": "Smooth Rhodes electric piano chords, warm sub 808 bass, relaxed conversational vibe",
                "license": "100% Royalty-Free",
                "bed_volume": 0.18,
                "duck_ratio": 7.0
            }
        ],
        "music": {
            "style": "adin_lofi_trap",
            "name": "Nocturnal Melodic Piano Trap (92 BPM, Non-Copyrighted)",
            "bpm": 92,
            "vibe": "Smooth Rhodes electric piano chords, warm sub 808 bass, relaxed conversational vibe",
            "bed_volume": 0.18,
            "duck_ratio": 7.0,
            "duck_threshold": 0.06
        },
        "metadata": {
            "title_prefix": "ADIN ROSS",
            "title_template": "{title} #shorts",
            "hashtags": ["#shorts", "#adinross", "#adin", "#kick", "#viral", "#streamer", "#funny", "#reaction"],
            "tags": ["adinross", "adin", "kick", "streamer", "funny", "viral", "reaction", "shorts", "entertainment"],
            "desc_cta": "Adin Ross with an insane reaction! 😭🎙️ Subscribe for more exclusive moments!"
        }
    },
    "default": {
        "id": "default",
        "name": "General Streamer",
        "handle": "@TrendingStreamer",
        "avatar": "✨",
        "tag": "Universal Viral Short · Modern Upbeat Vibe",
        "demographics": "Broad Shorts Audience 13–30 · Afternoon Surge",
        "schedule": {
            "best_days": ["Daily"],
            "best_hours_edt": [14.0, 17.5],
            "peak_label": "Daily 2:00 PM – 5:30 PM EDT (Universal Shorts Peak)",
            "reason": "Optimal algorithm test slot capturing global afternoon and evening cross-timezone viewing.",
            "seeding_hours": 2.0
        },
        "tracks": [
            {
                "id": "viral_shorts_lofi_bounce",
                "name": "Upbeat Modern Lo-Fi Shorts Beat",
                "genre": "Lo-Fi Bounce",
                "bpm": 110,
                "pool": "🟡 FUNNY / CHAOTIC",
                "vibe": "Infectious subtle bounce, warm Rhodes chords, punchy modern groove",
                "license": "100% Royalty-Free",
                "bed_volume": 0.20,
                "duck_ratio": 7.5
            }
        ],
        "music": {
            "style": "viral_shorts_lofi_bounce",
            "name": "Upbeat Modern Lo-Fi Shorts Beat (110 BPM, Non-Copyrighted)",
            "bpm": 110,
            "vibe": "Infectious subtle bounce, warm Rhodes chords, punchy modern groove",
            "bed_volume": 0.20,
            "duck_ratio": 7.5,
            "duck_threshold": 0.06
        },
        "metadata": {
            "title_prefix": "VIRAL",
            "title_template": "{title} #shorts",
            "hashtags": ["#shorts", "#viral", "#funny", "#trending", "#streamer", "#shortsfeed"],
            "tags": ["shorts", "viral", "funny", "trending", "streamer", "highlight", "entertainment"],
            "desc_cta": "Catch the most viral moment of the day! 🔥 Drop a like and subscribe for more daily clips!"
        }
    }
}

# =========================================================================
# 2. FULL 40-STREAMER VIRAL SOUND SIGNATURE REGISTRY
# =========================================================================

STREAMER_MUSIC_MAP_40: List[Dict[str, Any]] = [
    {"rank": 1, "streamer": "IShowSpeed", "vibe": "Aggressive phonk / dramatic meme", "substitute": "Brazilian Phonk / Persona Surprise", "pool": "🔴 RAGE / CLUTCH", "track_id": "speed_brazilian_phonk", "bpm": "130-160"},
    {"rank": 2, "streamer": "Kai Cenat", "vibe": "Hip-hop / upbeat / comedy / nostalgic", "substitute": "MAMP Bouncy Trap / Do You Mind UKG", "pool": "🟡 FUNNY / CHAOTIC", "track_id": "kai_mamp_bouncy_trap", "bpm": "95-125"},
    {"rank": 3, "streamer": "Jynxzi", "vibe": "Fast phonk / trap / aggressive gaming", "substitute": "Tactical Drift Phonk / Recon Tension", "pool": "🔴 RAGE / CLUTCH", "track_id": "jynxzi_tactical_phonk", "bpm": "140-170"},
    {"rank": 4, "streamer": "CaseOh", "vibe": "Lo-fi / game music / absurd meme drops", "substitute": "Hypnotic Dream Trap / Arcade Chair Break", "pool": "🔵 STORY / REACTION", "track_id": "caseoh_hypnotic_trap", "bpm": "70-110"},
    {"rank": 5, "streamer": "xQc", "vibe": "EDM / dramatic / chaotic meme audio", "substitute": "Fast Cyber Glitchwave / Arcade Glitch", "pool": "🟠 HYPE", "track_id": "xqc_cyber_speed", "bpm": "135-145"},
    {"rank": 6, "streamer": "Adin Ross", "vibe": "Hip-hop / trap / dramatic", "substitute": "Nocturnal Melodic Piano Trap", "pool": "🔵 STORY / REACTION", "track_id": "adin_lofi_trap", "bpm": "90-95"},
    {"rank": 7, "streamer": "Duke Dennis", "vibe": "R&B / chill hip-hop / edit beats", "substitute": "R&B Slowed Trap & Vocal Chops", "pool": "🔵 STORY / REACTION", "track_id": "adin_lofi_trap", "bpm": "85-100"},
    {"rank": 8, "streamer": "Fanum", "vibe": "Chill hip-hop / comedic Fanum tax", "substitute": "MAMP Bouncy Trap / Boom-Bap Chill", "pool": "🟡 FUNNY / CHAOTIC", "track_id": "kai_mamp_bouncy_trap", "bpm": "95-115"},
    {"rank": 9, "streamer": "PlaqueBoyMax", "vibe": "Modern hip-hop / underground rap", "substitute": "Dark Underground 808 Trap", "pool": "🟠 HYPE", "track_id": "kai_streambeats_prime", "bpm": "120-140"},
    {"rank": 10, "streamer": "N3on", "vibe": "Dark trap / aggressive phonk", "substitute": "Memphis Phonk / Dark Drift Bass", "pool": "🔴 RAGE / CLUTCH", "track_id": "speed_brazilian_phonk", "bpm": "130-150"},
    {"rank": 11, "streamer": "Clix", "vibe": "Fast EDM / trap / Fortnite edit", "substitute": "StreamBeats Moonwalk / Gaming EDM", "pool": "🟠 HYPE", "track_id": "speed_streambeats_moonwalk", "bpm": "130-150"},
    {"rank": 12, "streamer": "Tarik", "vibe": "Meme / electronic / FPS hype", "substitute": "StreamBeats Recon / Tactical Trap", "pool": "🟣 CINEMATIC", "track_id": "jynxzi_streambeats_recon", "bpm": "120-135"},
    {"rank": 13, "streamer": "HasanAbi", "vibe": "Dramatic / ironic / political meme music", "substitute": "Dramatic Orchestral / Lo-Fi Commentary", "pool": "🔵 STORY / REACTION", "track_id": "caseoh_hypnotic_trap", "bpm": "80-100"},
    {"rank": 14, "streamer": "TheBurntPeanut", "vibe": "Gaming / absurd comedy", "substitute": "StreamBeats Arcade / Quirky Comedy", "pool": "🟡 FUNNY / CHAOTIC", "track_id": "caseoh_streambeats_arcade", "bpm": "100-115"},
    {"rank": 15, "streamer": "Lacy", "vibe": "Trap / hip-hop / energetic", "substitute": "StreamBeats Prime / Upbeat Trap", "pool": "🟠 HYPE", "track_id": "kai_streambeats_prime", "bpm": "115-130"},
    {"rank": 16, "streamer": "Rayasianboy", "vibe": "Rap / melodic / emotional", "substitute": "Soulful R&B Lo-Fi / Do You Mind Style", "pool": "🔵 STORY / REACTION", "track_id": "kai_do_you_mind_nostalgia", "bpm": "90-110"},
    {"rank": 17, "streamer": "YourRAGE", "vibe": "Dark trap / hip-hop", "substitute": "Dark Trap + Slowed 808 Glide", "pool": "🔴 RAGE / CLUTCH", "track_id": "jynxzi_tactical_phonk", "bpm": "110-130"},
    {"rank": 18, "streamer": "Agent 00", "vibe": "Hip-hop / R&B / basketball edits", "substitute": "Soulful Boom-Bap & StreamBeats Prime", "pool": "🔵 STORY / REACTION", "track_id": "kai_streambeats_prime", "bpm": "95-115"},
    {"rank": 19, "streamer": "Kai Mafia / AMP", "vibe": "Rap / energetic / comedy", "substitute": "MAMP Bouncy Trap & Big 808 Drops", "pool": "🟡 FUNNY / CHAOTIC", "track_id": "kai_mamp_bouncy_trap", "bpm": "115-125"},
    {"rank": 20, "streamer": "Sketch", "vibe": "Meme music / game OST / absurd", "substitute": "StreamBeats Arcade / Goofy Chiptune", "pool": "🟡 FUNNY / CHAOTIC", "track_id": "caseoh_streambeats_arcade", "bpm": "100-120"},
    {"rank": 21, "streamer": "Icy3P", "vibe": "Phonk / gaming", "substitute": "Drift Phonk / Speed Brazilian Phonk", "pool": "🔴 RAGE / CLUTCH", "track_id": "speed_brazilian_phonk", "bpm": "135-150"},
    {"rank": 22, "streamer": "Stable Ronaldo", "vibe": "Trap / phonk / hype", "substitute": "StreamBeats Slaps / Fast Drift Beat", "pool": "🔴 RAGE / CLUTCH", "track_id": "speed_streambeats_slaps", "bpm": "125-140"},
    {"rank": 23, "streamer": "Silky", "vibe": "R&B / hip-hop / chill", "substitute": "Smooth Rhodes & Melodic Trap", "pool": "🔵 STORY / REACTION", "track_id": "adin_lofi_trap", "bpm": "88-105"},
    {"rank": 24, "streamer": "Mafiathon creators", "vibe": "Hype hip-hop / cinematic", "substitute": "StreamBeats Pulse / Epic Buildup", "pool": "🟣 CINEMATIC", "track_id": "jynxzi_brazilian_powerful", "bpm": "120-135"},
    {"rank": 25, "streamer": "Jerma", "vibe": "Weird / retro / comedy", "substitute": "Quirky Ban Rant / Retro Chiptune", "pool": "🟡 FUNNY / CHAOTIC", "track_id": "caseoh_quirky_ban_rant", "bpm": "105-120"},
    {"rank": 26, "streamer": "Ludwig", "vibe": "Cinematic / upbeat / orchestral", "substitute": "Bright Synthwave & StreamBeats Prime", "pool": "🟣 CINEMATIC", "track_id": "kai_streambeats_prime", "bpm": "110-125"},
    {"rank": 27, "streamer": "Valkyrae", "vibe": "Chill / pop / lo-fi", "substitute": "Warm Lo-Fi Shorts Bounce", "pool": "🔵 STORY / REACTION", "track_id": "caseoh_hypnotic_trap", "bpm": "80-100"},
    {"rank": 28, "streamer": "Pokimane", "vibe": "Pop / chill / cute electronic", "substitute": "StreamBeats Groovy / Warm Electric Piano", "pool": "🔵 STORY / REACTION", "track_id": "kai_streambeats_groovy", "bpm": "85-105"},
    {"rank": 29, "streamer": "Amouranth", "vibe": "Pop / electronic / meme", "substitute": "StreamBeats Moonwalk / Upbeat Dance", "pool": "🟠 HYPE", "track_id": "speed_streambeats_moonwalk", "bpm": "125-135"},
    {"rank": 30, "streamer": "ChrisNxtDoor", "vibe": "Hip-hop / meme / upbeat", "substitute": "MAMP Bouncy Trap / Comedy Plucks", "pool": "🟡 FUNNY / CHAOTIC", "track_id": "kai_mamp_bouncy_trap", "bpm": "115-125"},
    {"rank": 31, "streamer": "iShowMeat edits", "vibe": "Phonk / distorted bass", "substitute": "Speed Brazilian Phonk (Distorted Sub)", "pool": "🔴 RAGE / CLUTCH", "track_id": "speed_brazilian_phonk", "bpm": "140-160"},
    {"rank": 32, "streamer": "AuronPlay", "vibe": "Spanish meme / Latin / dramatic", "substitute": "Quirky Comedy Bounce & Reggaeton Trap", "pool": "🟡 FUNNY / CHAOTIC", "track_id": "caseoh_quirky_ban_rant", "bpm": "100-115"},
    {"rank": 33, "streamer": "Ibai", "vibe": "Cinematic / Spanish / hype", "substitute": "StreamBeats Prime / Stadium Hype", "pool": "🟣 CINEMATIC", "track_id": "jynxzi_brazilian_powerful", "bpm": "120-135"},
    {"rank": 34, "streamer": "Caedrel", "vibe": "Gaming / esports / dramatic", "substitute": "StreamBeats Recon / Tactical Gaming Buildup", "pool": "🟣 CINEMATIC", "track_id": "jynxzi_streambeats_recon", "bpm": "125-140"},
    {"rank": 35, "streamer": "ElRubius", "vibe": "Electronic / meme / Spanish", "substitute": "StreamBeats Arcade & Cyber Glitch", "pool": "🟡 FUNNY / CHAOTIC", "track_id": "xqc_cyber_speed", "bpm": "130-145"},
    {"rank": 36, "streamer": "TheGrefg", "vibe": "EDM / Spanish hype", "substitute": "Festival EDM / StreamBeats Moonwalk", "pool": "🟠 HYPE", "track_id": "speed_streambeats_moonwalk", "bpm": "130-145"},
    {"rank": 37, "streamer": "Westcol", "vibe": "Latin trap / reggaeton", "substitute": "Bouncy Latin Trap Beat", "pool": "🟠 HYPE", "track_id": "kai_mamp_bouncy_trap", "bpm": "95-115"},
    {"rank": 38, "streamer": "AmineMaTue", "vibe": "French rap / football hype", "substitute": "Aggressive Drift Trap / Stadium Beat", "pool": "🟠 HYPE", "track_id": "speed_brazilian_phonk", "bpm": "130-145"},
    {"rank": 39, "streamer": "eliasn97", "vibe": "German rap / football / energetic", "substitute": "Fast Electronic & Drill 808", "pool": "🟠 HYPE", "track_id": "speed_brazilian_phonk", "bpm": "130-145"},
    {"rank": 40, "streamer": "StRoGo", "vibe": "Fast gaming / meme / electronic", "substitute": "Tactical Drift Phonk / Fast EDM", "pool": "🔴 RAGE / CLUTCH", "track_id": "jynxzi_tactical_phonk", "bpm": "140-160"}
]


def detect_creator(text_or_url: str) -> str:
    """Detect streamer ID from a text prompt, video title, or YouTube URL."""
    if not text_or_url:
        return "speed"
    low = text_or_url.lower()
    if any(k in low for k in ["speed", "ishowspeed", "darren", "b2yhlgtgxpm", "kfc"]):
        return "speed"
    if any(k in low for k in ["kai", "cenat", "amp", "mamp", "rakai"]):
        return "kai"
    if any(k in low for k in ["jynxzi", "junko", "rainbow", "r6", "siege"]):
        return "jynxzi"
    if any(k in low for k in ["caseoh", "case", "waffle", "dono", "chair"]):
        return "caseoh"
    if any(k in low for k in ["xqc", "xqcow", "lengyel", "juicer"]):
        return "xqc"
    if any(k in low for k in ["adin", "ross", "kick"]):
        return "adin"
    # Check 40 registry
    for entry in STREAMER_MUSIC_MAP_40:
        if entry["streamer"].lower() in low:
            # Map back to closest profile
            if entry["pool"] == "🔴 RAGE / CLUTCH":
                return "jynxzi"
            elif entry["pool"] == "🟡 FUNNY / CHAOTIC":
                return "kai"
            elif entry["pool"] == "🔵 STORY / REACTION":
                return "caseoh"
            return "speed"
    return "speed"


def get_creator_profile(creator_key: str) -> Dict[str, Any]:
    """Retrieve full creator profile by key or creator name, dynamically synthesizing one if unknown."""
    import os
    default_key = os.environ.get("DEFAULT_CREATOR", "universal")
    fallback = CREATORS.get(default_key, CREATORS.get("universal", CREATORS["speed"]))

    if not creator_key:
        return fallback

    low = creator_key.lower().strip()
    if low in CREATORS:
        return CREATORS[low]
    for k, profile in CREATORS.items():
        if profile["name"].lower() == low or k in low:
            return profile

    detected = detect_creator(creator_key)
    if detected in CREATORS and detected != "speed":
        return CREATORS[detected]

    # Dynamically synthesize a custom profile for unknown channels/niche
    clean_name = creator_key.replace("@", "").strip().title()
    custom_profile = {
        "id": low.replace(" ", "_"),
        "name": clean_name,
        "handle": f"@{clean_name.replace(' ', '')}",
        "avatar": "🎬",
        "tag": f"Custom {clean_name} Content & Highlights",
        "demographics": "Global Audience · Evening Prime",
        "schedule": fallback["schedule"],
        "tracks": fallback["tracks"]
    }
    return custom_profile


def get_streamer_tracks(creator_key: str) -> List[Dict[str, Any]]:
    """Return dedicated tracks for a creator/channel."""
    profile = get_creator_profile(creator_key)
    return profile.get("tracks", CREATORS["universal"]["tracks"])


# Persistent channel schedule tracker: maintains spaced upload timeline
SCHEDULE_HISTORY_FILE = Path(__file__).resolve().parent.parent / "data" / "channel_schedule_history.json"


def _normalize_creator_key(creator_key: str) -> str:
    c_norm = str(creator_key or "").strip().lower()
    if "speed" in c_norm or "tanvo" in c_norm:
        return "speed"
    elif "case" in c_norm:
        return "caseoh"
    elif "jynx" in c_norm or "jinx" in c_norm:
        return "jynxzi"
    return "speed"


def get_last_scheduled_slot(creator_key: str) -> Optional[datetime.datetime]:
    """Retrieve the latest scheduled publication datetime for this creator's channel."""
    try:
        if SCHEDULE_HISTORY_FILE.exists():
            data = json.loads(SCHEDULE_HISTORY_FILE.read_text(encoding="utf-8"))
            c_slug = _normalize_creator_key(creator_key)
            iso_str = data.get(c_slug)
            if iso_str:
                return datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except Exception:
        pass
    return None


def record_scheduled_slot(creator_key: str, target_iso_utc: str):
    """Persist the latest scheduled slot for this creator to enforce the 6-hour timeline."""
    try:
        SCHEDULE_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if SCHEDULE_HISTORY_FILE.exists():
            try:
                data = json.loads(SCHEDULE_HISTORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        c_slug = _normalize_creator_key(creator_key)
        data[c_slug] = target_iso_utc
        SCHEDULE_HISTORY_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[Schedule History] Save note: {e}")


# 4 Distinct Daily Viral Peaks spaced strictly ~6 hours apart per creator
CREATOR_DAILY_PEAKS: Dict[str, List[Dict[str, Any]]] = {
    "speed": [
        {"hour": 15.5, "name": "After-School Youth Dismissal Peak", "reason": "High-schoolers in US East/Central dismiss and scroll Shorts before homework (3:30 PM EDT / 1:00 AM IST)"},
        {"hour": 21.5, "name": "Late-Night Phone Scroll", "reason": "High-retention late-night bedside Shorts consumption (9:30 PM EDT / 7:00 AM IST)"},
        {"hour": 6.0, "name": "UK & European Peak / US Early Surge", "reason": "Massive global European daytime audience & early US morning feeds (6:00 AM EDT / 3:30 PM IST)"},
        {"hour": 12.0, "name": "Midday & Global Lunch Peak", "reason": "Global teen lunchtime & European/UK peak afternoon feed traffic (12:00 PM EDT / 9:30 PM IST)"}
    ],
    "caseoh": [
        {"hour": 16.5, "name": "Afternoon Warm-Up & Comedy React", "reason": "After-school/work comedy seekers before dinner (4:30 PM EDT / 2:00 AM IST)"},
        {"hour": 23.0, "name": "Marquee Live Stream & Horror Climax", "reason": "Peak Twitch live stream hours, dono rants & horror game climax (11:00 PM EDT / 8:30 AM IST)"},
        {"hour": 7.0, "name": "Global Morning Commute & Europe Feed", "reason": "Morning commuters & European daytime viewers catching up on stream craziness (7:00 AM EDT / 4:30 PM IST)"},
        {"hour": 13.5, "name": "Midday Lunchtime Re-watch", "reason": "Lunch break comedy browsing & simulator clips (1:30 PM EDT / 11:00 PM IST)"}
    ],
    "jynxzi": [
        {"hour": 16.0, "name": "After-School 1v1 Tournament Hour", "reason": "Console players finish school, jump on Siege & browse clutches (4:00 PM EDT / 1:30 AM IST)"},
        {"hour": 22.0, "name": "Late-Night Bedside Console Scroll & Clutches", "reason": "High-retention bedtime gaming scroll with peak completion rate (10:00 PM EDT / 7:30 AM IST)"},
        {"hour": 5.0, "name": "UK/European Gaming Rush & Early US Wake-Up", "reason": "UK/European console audience midday rush & US early morning feeds (5:00 AM EDT / 2:30 PM IST)"},
        {"hour": 12.0, "name": "US Midday Lunch & Free Period Browse", "reason": "High school and college gamers browsing Shorts during lunch and study breaks (12:00 PM EDT / 9:30 PM IST)"}
    ],
    "default": [
        {"hour": 16.0, "name": "Late Afternoon Surge", "reason": "School dismissal & commute browse (4:00 PM EDT / 1:30 AM IST)"},
        {"hour": 22.0, "name": "Night Scroll", "reason": "Late-night mobile consumption (10:00 PM EDT / 7:30 AM IST)"},
        {"hour": 6.0, "name": "Morning Global Peak", "reason": "European afternoon & US morning browse (6:00 AM EDT / 3:30 PM IST)"},
        {"hour": 12.0, "name": "Midday Peak", "reason": "Lunch break traffic surge (12:00 PM EDT / 9:30 PM IST)"}
    ]
}


def calculate_next_optimal_slot(creator_key: str, now_utc: Optional[datetime.datetime] = None, clip_rank: int = 1, stagger_minutes: Optional[int] = None) -> Dict[str, Any]:
    """Calculate schedule slots enforcing a strict 6-hour timeline across the 3 streamers.

    Key Guarantees:
    1. Zero Spam Flags: Clips are spaced at least 6.0 hours apart to guarantee independent
       algorithm seed testing (500–2,500 impressions) without cannibalization.
    2. Persistent Memory: If a video is already scheduled on the channel (e.g. Jynxzi at 1:30 AM IST),
       the next video is scheduled at least 6 hours after that existing video.
    3. Multi-Rank 6-Hour Staggering:
       - Rank 1 -> First available 6-hour peak slot
       - Rank 2 -> Next 6-hour peak slot (+6h to +7h)
       - Rank 3 -> Next 6-hour peak slot (+12h to +14h)
       - Rank 4 -> Next 6-hour peak slot (+18h to +21h)
       - Rank 5 -> Next 6-hour peak slot (+24h to +28h)
    """
    c_slug = _normalize_creator_key(creator_key)
    peaks = CREATOR_DAILY_PEAKS.get(c_slug, CREATOR_DAILY_PEAKS["default"])
    c_label = CREATORS.get(c_slug, {}).get("name", c_slug.title())

    now_utc = now_utc or datetime.datetime.now(datetime.timezone.utc)
    edt_tz = datetime.timezone(datetime.timedelta(hours=-4))
    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    now_edt = now_utc.astimezone(edt_tz)

    # Base buffer: Minimum 20 minutes for YouTube HD processing
    min_buffer_minutes = 20
    earliest_allowed_edt = now_edt + datetime.timedelta(minutes=min_buffer_minutes)

    # Check persistent history for any video currently scheduled in the future on this channel
    last_scheduled_utc = get_last_scheduled_slot(c_slug)
    if last_scheduled_utc:
        last_scheduled_edt = last_scheduled_utc.astimezone(edt_tz)
        if last_scheduled_edt > now_edt:
            # Enforce 6.0 hours separation from the existing scheduled slot
            earliest_allowed_edt = max(earliest_allowed_edt, last_scheduled_edt + datetime.timedelta(hours=6.0))

    # Build candidate slots across the next 5 days
    candidate_slots = []
    for day_offset in range(5):
        cand_day = now_edt + datetime.timedelta(days=day_offset)
        for p in peaks:
            h_float = p["hour"]
            h = int(h_float)
            m = int(round((h_float - h) * 60))
            slot_dt = cand_day.replace(hour=h, minute=m, second=0, microsecond=0)
            if slot_dt >= earliest_allowed_edt:
                candidate_slots.append((slot_dt, p["name"], p["reason"]))

    candidate_slots.sort(key=lambda x: x[0])

    # Rank staggering: each rank takes the next 6-hour peak slot in sequence
    slot_idx = max(0, clip_rank - 1)
    if candidate_slots and slot_idx < len(candidate_slots):
        target_dt_edt, peak_name, peak_reason = candidate_slots[slot_idx]
    elif candidate_slots:
        base_dt_edt, peak_name, peak_reason = candidate_slots[-1]
        extra_ranks = slot_idx - (len(candidate_slots) - 1)
        target_dt_edt = base_dt_edt + datetime.timedelta(hours=6.0 * extra_ranks)
    else:
        target_dt_edt = earliest_allowed_edt + datetime.timedelta(hours=6.0 * slot_idx)
        peak_name = "6-Hour Algorithmic Separation Slot"
        peak_reason = "6-hour spaced viral distribution buffer"

    # Allow custom stagger override if explicitly specified
    if stagger_minutes is not None and candidate_slots:
        target_dt_edt = candidate_slots[0][0] + datetime.timedelta(minutes=stagger_minutes)

    target_utc = target_dt_edt.astimezone(datetime.timezone.utc)
    target_ist = target_dt_edt.astimezone(ist_tz)

    delta_sec = max(0.0, (target_utc - now_utc).total_seconds())
    if delta_sec < 1800:
        rel_str = f"in ~{int(round(delta_sec / 60))}m (Imminent)"
    else:
        hours_rel = round(delta_sec / 3600.0, 1)
        rel_str = f"in ~{hours_rel}h"

    is_today = (target_dt_edt.date() == now_edt.date())
    is_tomorrow = (target_dt_edt.date() == (now_edt.date() + datetime.timedelta(days=1)))
    day_prefix = "Today" if is_today else ("Tomorrow" if is_tomorrow else target_dt_edt.strftime("%a, %b %d"))
    edt_time_str = target_dt_edt.strftime("%I:%M %p").lstrip("0")
    ist_time_str = target_ist.strftime("%I:%M %p").lstrip("0")

    human_str = f"{day_prefix} at {edt_time_str} EDT ({ist_time_str} IST) • {rel_str} [{peak_name}]"
    target_iso_utc = target_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "target_iso": target_iso_utc,
        "target_utc": target_utc.isoformat(),
        "target_edt": target_dt_edt.isoformat(),
        "readable": human_str,
        "human_readable": human_str,
        "input_value": target_dt_edt.strftime("%Y-%m-%dT%H:%M"),
        "peak_label": peak_name,
        "reason": peak_reason,
        "delay_hours": round(delta_sec / 3600.0, 2),
        "creator": c_label,
        "rank": clip_rank
    }
