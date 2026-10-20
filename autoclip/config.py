import os

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_dotenv(env_path=None):
    """Simple zero-dependency .env loader."""
    if env_path is None:
        env_path = os.path.join(PROJECT, ".env")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass

load_dotenv()

# Media/cache lives outside the repo by default so nothing heavy is ever committed.
DEFAULT_MEDIA_DIR = os.path.join(os.environ.get("TEMP", os.environ.get("TMPDIR", "/tmp")), "opencode", "autoclip")

def media_dir():
    d = os.environ.get("AUTOCLIP_MEDIA", DEFAULT_MEDIA_DIR)
    os.makedirs(d, exist_ok=True)
    return d

DATA = os.path.join(PROJECT, "data")
DOWNLOADS_DIR = os.path.join(DATA, "downloads")
SHORTS_DIR = os.path.join(DATA, "shorts")
RESEARCH = os.path.join(DATA, "research")
STATE = os.path.join(DATA, "state")
TEMPLATES = os.path.join(PROJECT, "templates")
DOCS = os.path.join(PROJECT, "docs")

FPS_OUT = 30
W_OUT, H_OUT = 1080, 1920

# YouTube section download needs JS runtime to solve signatures (PO tokens / n-challenge).
DENO_DIR = os.path.expanduser(r"~/.deno/bin")
if os.path.exists(DENO_DIR) and DENO_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = DENO_DIR + os.pathsep + os.environ.get("PATH", "")

YTDLP_JS_RUNTIME = "deno" if (os.path.exists(os.path.join(DENO_DIR, "deno.exe")) or os.path.exists(os.path.join(DENO_DIR, "deno"))) else "node"

PYTHON = "python"

from enum import Enum
class CaptionAnimation(str, Enum):
    PHRASE_POP = "phrase_pop"
    WORD_POP = "word_pop"
    PHRASE_REVEAL = "phrase_reveal"
    HIGHLIGHT_SWEEP = "highlight_sweep"
    SINGLE_WORD_POP = "single_word_pop"

    @classmethod
    def valid_styles(cls):
        return tuple(m.value for m in cls)