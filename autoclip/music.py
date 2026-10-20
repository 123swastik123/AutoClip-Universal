"""Streamer-Specific 4-Track Music Synthesizer - 100% Copyright-Free & DMCA-Safe.

Synthesizes the dedicated 4-track sound design libraries for the Top 4 Streamers:
1. IShowSpeed:
   - Brazilian Phonk (Rage & Climax) [138 BPM]
   - Persona Surprise (Meme Crash-Out) [130 BPM]
   - StreamBeats Moonwalk (EDM Drift) [132 BPM]
   - StreamBeats Slaps (Goofy Slap Bounce) [124 BPM]
2. Kai Cenat:
   - MAMP Bouncy Trap (Room Chaos) [118 BPM]
   - Do You Mind (Late-Night UK Garage) [124 BPM]
   - StreamBeats Prime (Celebrity Hype) [112 BPM]
   - StreamBeats Groovy (Chill Boom-Bap) [94 BPM]
3. Jynxzi:
   - Tactical Drift Phonk (1v5 Clutch) [142 BPM]
   - StreamBeats Recon (Tension Riser) [126 BPM]
   - StreamBeats Slaps (Freakout Drop) [135 BPM]
   - Brazilian Phonk Powerful (Victory Win) [130 BPM]
4. CaseOh:
   - Hypnotic Dream Trap (Slowed Lo-Fi) [82 BPM]
   - StreamBeats Arcade (Chair Break Meme) [108 BPM]
   - StreamBeats Midnight (Horror Suspense) [96 BPM]
   - Quirky Ban Rant (Cartoon Bounce) [115 BPM]

Plus xQc, Adin Ross, and Universal Viral Lo-Fi styles.
All tracks are procedurally synthesized, 48kHz stereo, duration 75s.
Safe from Content ID flags and cleared for YouTube, TikTok, and Instagram Reels.
"""

import os
import wave
import numpy as np
from .config import media_dir

SR = 48000  # Broadcast standard 48kHz

def _envelope(length, attack_sec, decay_sec, sr=SR):
    env = np.ones(length, dtype=np.float32)
    a_len = int(attack_sec * sr)
    d_len = int(decay_sec * sr)
    if 0 < a_len < length:
        env[:a_len] = np.linspace(0.0, 1.0, a_len, dtype=np.float32)
    if 0 < d_len < length:
        env[-d_len:] = np.linspace(1.0, 0.0, d_len, dtype=np.float32)
    return env

def _generate_808_kick(dur=0.35, pitch_start=145.0, pitch_end=40.0, sr=SR):
    n = int(dur * sr)
    t = np.linspace(0, dur, n, endpoint=False, dtype=np.float32)
    freq = pitch_end + (pitch_start - pitch_end) * np.exp(-t * 22.0)
    phase = 2 * np.pi * np.cumsum(freq) / sr
    sine = np.sin(phase)
    sat = np.tanh(sine * 2.0) * 0.75
    env = np.exp(-t * 8.5)
    return sat * env

def _generate_snare(dur=0.22, sr=SR):
    n = int(dur * sr)
    t = np.linspace(0, dur, n, endpoint=False, dtype=np.float32)
    tone = np.sin(2 * np.pi * 185.0 * t) * np.exp(-t * 24.0)
    noise = np.random.uniform(-1.0, 1.0, n).astype(np.float32) * np.exp(-t * 16.0)
    return (tone * 0.35 + noise * 0.65) * 0.6

def _generate_hihat(dur=0.06, open_hat=False, sr=SR):
    d = 0.18 if open_hat else dur
    n = int(d * sr)
    t = np.linspace(0, d, n, endpoint=False, dtype=np.float32)
    noise = np.random.uniform(-1.0, 1.0, n).astype(np.float32)
    decay_rate = 35.0 if open_hat else 95.0
    return noise * np.exp(-t * decay_rate) * 0.28

def _generate_chord(freqs, dur, chord_type="warm", sr=SR):
    n = int(dur * sr)
    t = np.linspace(0, dur, n, endpoint=False, dtype=np.float32)
    wave_out = np.zeros(n, dtype=np.float32)
    for f in freqs:
        if chord_type == "phonk":
            harm = (np.sin(2*np.pi*f*t) + 
                    0.55 * np.sin(2*np.pi*2*f*t) + 
                    0.30 * np.sin(2*np.pi*3*f*t)) * 0.38
        elif chord_type == "synthwave":
            harm = (np.sin(2*np.pi*f*t) + 
                    0.40 * np.sin(2*np.pi*1.004*f*t) + 
                    0.30 * np.sin(2*np.pi*2*f*t)) * 0.42
        elif chord_type == "pizzicato":
            harm = np.sin(2*np.pi*f*t) * np.exp(-t * 15.0)
        elif chord_type == "acid_jazz":
            harm = (np.sin(2*np.pi*f*t) + 
                    0.45 * np.sin(2*np.pi*1.5*f*t) + 
                    0.25 * np.sin(2*np.pi*2.0*f*t)) * 0.40
        else:
            harm = (np.sin(2*np.pi*f*t) + 
                    0.40 * np.sin(2*np.pi*1.002*f*t)) * 0.50
        wave_out += harm
    env = _envelope(n, 0.04, 0.08, sr)
    return wave_out * env

# Full Multi-Track Sound Configuration Matrix
TRACK_CONFIGS = {
    # --- IShowSpeed (4 Tracks) ---
    "speed_brazilian_phonk": {
        "bpm": 138, "chord_type": "phonk",
        "chords": [[110.0, 164.81, 220.0, 261.63], [98.0, 146.83, 196.0, 246.94], [116.54, 174.61, 233.08, 293.66], [87.31, 130.81, 174.61, 220.0]],
        "bass_notes": [55.0, 49.0, 58.27, 43.65],
        "kick_pattern": [0, 1.5, 2, 3], "snare_pattern": [1, 3], "hat_div": 4
    },
    "speed_persona_surprise": {
        "bpm": 130, "chord_type": "acid_jazz",
        "chords": [[146.83, 185.0, 220.0, 277.18], [123.47, 155.56, 185.0, 233.08], [164.81, 196.0, 246.94, 293.66], [110.0, 138.59, 164.81, 207.65]],
        "bass_notes": [73.42, 61.74, 82.41, 55.0],
        "kick_pattern": [0, 1.25, 2.5], "snare_pattern": [1, 3], "hat_div": 4
    },
    "speed_streambeats_moonwalk": {
        "bpm": 132, "chord_type": "synthwave",
        "chords": [[146.83, 220.0, 293.66, 349.23], [116.54, 174.61, 233.08, 293.66], [174.61, 220.0, 261.63, 349.23], [130.81, 196.0, 261.63, 329.63]],
        "bass_notes": [73.42, 58.27, 87.31, 65.41],
        "kick_pattern": [0, 1, 2, 3], "snare_pattern": [1, 3], "hat_div": 4
    },
    "speed_streambeats_slaps": {
        "bpm": 124, "chord_type": "warm",
        "chords": [[130.81, 164.81, 196.0, 246.94], [110.0, 146.83, 174.61, 220.0]],
        "bass_notes": [65.41, 55.0],
        "kick_pattern": [0, 2], "snare_pattern": [1, 3], "hat_div": 4
    },

    # --- Kai Cenat (4 Tracks) ---
    "kai_mamp_bouncy_trap": {
        "bpm": 118, "chord_type": "warm",
        "chords": [[261.63, 329.63, 392.0, 493.88], [220.0, 261.63, 329.63, 392.0], [174.61, 220.0, 261.63, 329.63], [196.0, 246.94, 293.66, 392.0]],
        "bass_notes": [65.41, 55.0, 43.65, 49.0],
        "kick_pattern": [0, 1.75, 2.5], "snare_pattern": [2], "hat_div": 4
    },
    "kai_do_you_mind_nostalgia": {
        "bpm": 124, "chord_type": "warm",
        "chords": [[174.61, 220.0, 261.63, 329.63], [196.0, 246.94, 293.66, 392.0], [146.83, 174.61, 220.0, 261.63], [164.81, 196.0, 246.94, 329.63]],
        "bass_notes": [43.65, 49.0, 36.71, 41.2],
        "kick_pattern": [0, 2.5], "snare_pattern": [1, 3], "hat_div": 4
    },
    "kai_streambeats_prime": {
        "bpm": 112, "chord_type": "phonk",
        "chords": [[110.0, 164.81, 220.0], [130.81, 196.0, 261.63], [146.83, 220.0, 293.66]],
        "bass_notes": [55.0, 65.41, 73.42],
        "kick_pattern": [0, 1.5, 2.5], "snare_pattern": [2], "hat_div": 4
    },
    "kai_streambeats_groovy": {
        "bpm": 94, "chord_type": "warm",
        "chords": [[220.0, 261.63, 329.63, 392.0], [174.61, 220.0, 261.63, 329.63]],
        "bass_notes": [55.0, 43.65],
        "kick_pattern": [0, 2.5], "snare_pattern": [2], "hat_div": 2
    },

    # --- Jynxzi (4 Tracks) ---
    "jynxzi_tactical_phonk": {
        "bpm": 142, "chord_type": "phonk",
        "chords": [[146.83, 220.0, 293.66, 349.23], [130.81, 196.0, 261.63, 311.13], [110.0, 164.81, 220.0, 261.63], [123.47, 185.0, 246.94, 293.66]],
        "bass_notes": [73.42, 65.41, 55.0, 61.74],
        "kick_pattern": [0, 1.25, 2.5, 3.25], "snare_pattern": [1, 3], "hat_div": 4
    },
    "jynxzi_streambeats_recon": {
        "bpm": 126, "chord_type": "synthwave",
        "chords": [[110.0, 146.83, 164.81], [98.0, 130.81, 146.83]],
        "bass_notes": [55.0, 49.0],
        "kick_pattern": [0, 2], "snare_pattern": [2], "hat_div": 2
    },
    "jynxzi_streambeats_slaps": {
        "bpm": 135, "chord_type": "phonk",
        "chords": [[110.0, 164.81, 220.0], [98.0, 146.83, 196.0]],
        "bass_notes": [55.0, 49.0],
        "kick_pattern": [0, 1.5, 3], "snare_pattern": [1, 3], "hat_div": 4
    },
    "jynxzi_brazilian_powerful": {
        "bpm": 130, "chord_type": "phonk",
        "chords": [[146.83, 196.0, 246.94], [130.81, 174.61, 220.0]],
        "bass_notes": [73.42, 65.41],
        "kick_pattern": [0, 1.5, 2, 3], "snare_pattern": [1, 3], "hat_div": 4
    },

    # --- CaseOh (4 Tracks) ---
    "caseoh_hypnotic_trap": {
        "bpm": 82, "chord_type": "warm",
        "chords": [[220.0, 261.63, 329.63, 392.0], [174.61, 220.0, 261.63, 329.63], [130.81, 164.81, 196.0, 246.94], [146.83, 174.61, 220.0, 261.63]],
        "bass_notes": [55.0, 43.65, 32.7, 36.71],
        "kick_pattern": [0, 2.5], "snare_pattern": [2], "hat_div": 2
    },
    "caseoh_streambeats_arcade": {
        "bpm": 108, "chord_type": "pizzicato",
        "chords": [[261.63, 329.63, 392.0, 523.25], [220.0, 261.63, 329.63, 440.0], [174.61, 220.0, 261.63, 349.23], [196.0, 246.94, 293.66, 392.0]],
        "bass_notes": [65.41, 55.0, 43.65, 49.0],
        "kick_pattern": [0, 1.5, 2.5], "snare_pattern": [2], "hat_div": 4
    },
    "caseoh_streambeats_midnight": {
        "bpm": 96, "chord_type": "synthwave",
        "chords": [[130.81, 164.81, 196.0], [116.54, 146.83, 174.61]],
        "bass_notes": [65.41, 58.27],
        "kick_pattern": [0, 2], "snare_pattern": [2], "hat_div": 2
    },
    "caseoh_quirky_ban_rant": {
        "bpm": 115, "chord_type": "pizzicato",
        "chords": [[261.63, 329.63, 392.0], [220.0, 261.63, 329.63], [174.61, 220.0, 261.63], [196.0, 246.94, 293.66]],
        "bass_notes": [65.41, 55.0, 43.65, 49.0],
        "kick_pattern": [0, 2], "snare_pattern": [1, 3], "hat_div": 2
    },

    # --- Generic & Other Streamers ---
    "xqc_cyber_speed": {
        "bpm": 138, "chord_type": "synthwave",
        "chords": [[130.81, 196.0, 261.63, 329.63], [116.54, 174.61, 233.08, 293.66], [103.83, 155.56, 207.65, 261.63]],
        "bass_notes": [65.41, 58.27, 51.91],
        "kick_pattern": [0, 1, 2, 3], "snare_pattern": [1, 3], "hat_div": 4
    },
    "adin_lofi_trap": {
        "bpm": 92, "chord_type": "warm",
        "chords": [[220.0, 261.63, 329.63, 392.0], [174.61, 220.0, 261.63, 329.63]],
        "bass_notes": [55.0, 43.65],
        "kick_pattern": [0, 2.5], "snare_pattern": [2], "hat_div": 2
    },
    "viral_shorts_lofi_bounce": {
        "bpm": 110, "chord_type": "warm",
        "chords": [[261.63, 329.63, 392.0, 493.88], [220.0, 261.63, 329.63, 392.0]],
        "bass_notes": [65.41, 55.0],
        "kick_pattern": [0, 1.5, 2.5], "snare_pattern": [2], "hat_div": 4
    }
}

def synthesize_streamer_track(style_key: str, out_wav_path: str, duration: float = 75.0):
    """Procedurally synthesize a complete 75-second BGM track for any style key."""
    os.makedirs(os.path.dirname(os.path.abspath(out_wav_path)), exist_ok=True)
    cfg = TRACK_CONFIGS.get(style_key, TRACK_CONFIGS["speed_brazilian_phonk"])

    bpm = cfg["bpm"]
    beat_sec = 60.0 / bpm
    bar_sec = beat_sec * 4.0

    total_bars = int(np.ceil(duration / bar_sec)) + 1
    total_samples = int(duration * SR)
    mix = np.zeros(total_samples, dtype=np.float32)

    kick = _generate_808_kick(dur=min(0.4, beat_sec * 0.9), sr=SR)
    snare = _generate_snare(dur=min(0.25, beat_sec * 0.7), sr=SR)
    hat = _generate_hihat(dur=0.06, sr=SR)

    for bar in range(total_bars):
        bar_start_sample = int(bar * bar_sec * SR)
        chord_idx = bar % len(cfg["chords"])
        chord_freqs = cfg["chords"][chord_idx]
        chord_audio = _generate_chord(chord_freqs, dur=bar_sec * 0.96, chord_type=cfg["chord_type"], sr=SR)

        end_s = min(total_samples, bar_start_sample + len(chord_audio))
        len_to_copy = end_s - bar_start_sample
        if len_to_copy > 0:
            mix[bar_start_sample:end_s] += chord_audio[:len_to_copy] * 0.38

        # Bass Root
        bass_f = cfg["bass_notes"][chord_idx % len(cfg["bass_notes"])]
        bass_n = int(bar_sec * 0.85 * SR)
        bt = np.linspace(0, bar_sec * 0.85, bass_n, endpoint=False, dtype=np.float32)
        bass_audio = np.sin(2 * np.pi * bass_f * bt) * np.exp(-bt * 1.5) * 0.32
        bend_s = min(total_samples, bar_start_sample + bass_n)
        blen = bend_s - bar_start_sample
        if blen > 0:
            mix[bar_start_sample:bend_s] += bass_audio[:blen]

        # Kick
        for beat_pos in cfg["kick_pattern"]:
            ks = bar_start_sample + int(beat_pos * beat_sec * SR)
            ke = min(total_samples, ks + len(kick))
            if 0 <= ks < total_samples and ke > ks:
                mix[ks:ke] += kick[:ke - ks] * 0.55

        # Snare
        for beat_pos in cfg["snare_pattern"]:
            ss = bar_start_sample + int(beat_pos * beat_sec * SR)
            se = min(total_samples, ss + len(snare))
            if 0 <= ss < total_samples and se > ss:
                mix[ss:se] += snare[:se - ss] * 0.40

        # Hi-Hats
        hat_steps = 4 * cfg["hat_div"]
        step_sec = bar_sec / hat_steps
        for step in range(hat_steps):
            hs = bar_start_sample + int(step * step_sec * SR)
            he = min(total_samples, hs + len(hat))
            if 0 <= hs < total_samples and he > hs:
                vol = 0.32 if step % 2 == 0 else 0.20
                mix[hs:he] += hat[:he - hs] * vol

    # Fast vectorized smoothing filter
    kernel = np.array([0.15, 0.70, 0.15], dtype=np.float32)
    mix = np.convolve(mix, kernel, mode="same")

    peak = np.max(np.abs(mix))
    if peak > 0:
        mix = mix / peak * 0.82

    # Fade in / fade out
    fi = int(0.5 * SR)
    fo = int(1.0 * SR)
    mix[:fi] *= np.linspace(0.0, 1.0, fi, dtype=np.float32)
    mix[-fo:] *= np.linspace(1.0, 0.0, fo, dtype=np.float32)

    pcm = (np.clip(mix, -1.0, 1.0) * 32767).astype(np.int16)
    stereo_pcm = np.stack([pcm, pcm], axis=1)

    with wave.open(out_wav_path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo_pcm.tobytes())

    return out_wav_path

def get_streamer_bgm(track_or_creator_key: str = "speed", out_dir: str = None) -> str:
    """Retrieve or synthesize the royalty-free BGM track."""
    track_or_creator_key = (track_or_creator_key or "speed").lower().strip()

    # Direct match in track configs
    if track_or_creator_key in TRACK_CONFIGS:
        style_key = track_or_creator_key
    else:
        from .creators import get_creator_profile
        profile = get_creator_profile(track_or_creator_key)
        # Default to first dedicated track or music style
        style_key = profile.get("tracks", [{}])[0].get("id", profile["music"]["style"])

    out_dir = out_dir or os.path.join(media_dir(), "bgm")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"bgm_{style_key}.wav")

    if os.path.exists(out_file) and os.path.getsize(out_file) > 10000:
        return out_file

    print(f"[Music Synthesizer] Generating 100% royalty-free track: {style_key}...")
    synthesize_streamer_track(style_key, out_file, duration=75.0)
    return out_file

def make_bgm(profile=None, out_path=None):
    profile = profile or {}
    key = profile.get("track_id") or profile.get("style") or profile.get("creator", "speed")
    return get_streamer_bgm(key)