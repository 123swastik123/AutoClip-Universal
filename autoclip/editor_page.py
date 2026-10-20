"""AutoClip Visual Studio Editor (Modern React + TS + Vite CapCut Studio)."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def render_editor_html(clip_data: dict) -> str:
    """Serve the modern React CapCut Editor SPA."""
    dist_html = PROJECT_ROOT / "frontend" / "dist" / "index.html"
    if dist_html.exists():
        with open(dist_html, "r", encoding="utf-8") as f:
            return f.read()

    # Fallback redirect to /editor
    return """<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="refresh" content="0; url=/editor" />
    <title>Redirecting to CapCut Studio...</title>
</head>
<body style="background:#0e0e10;color:#e8e8ea;font-family:sans-serif;padding:2rem;">
    <h2>Loading CapCut Studio...</h2>
</body>
</html>"""
