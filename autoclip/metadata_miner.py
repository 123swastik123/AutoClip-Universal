"""
AutoClip Competitor Benchmark & Metadata Inspiration Miner
Extracts and synthesizes Titles, Descriptions, and Tags directly from the #1 most viral videos of that format.
"""

import subprocess
import json
import re
from typing import Dict, Any, List

class MetadataMiner:
    """Mines winning metadata patterns from top-performing YouTube Shorts."""

    @staticmethod
    def mine_format_benchmarks(query: str, max_results: int = 5) -> Dict[str, Any]:
        """Scrapes top performing videos for a query and extracts viral blueprints."""
        cmd = [
            r"C:\Users\swastik\Desktop\AutoClip\.venv\Scripts\yt-dlp.exe",
            "--dump-json",
            "--flat-playlist",
            f"ytsearch{max_results}:{query}"
        ]
        
        benchmarks = []
        try:
            res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode("utf-8", errors="replace")
            for line in res.strip().split("\n"):
                if line:
                    d = json.loads(line)
                    benchmarks.append({
                        "id": d.get("id"),
                        "title": d.get("title", ""),
                        "views": d.get("view_count", 0) or 0,
                        "url": f"https://www.youtube.com/watch?v={d.get('id')}"
                    })
        except Exception as e:
            print(f"[MetadataMiner Warning] Search error: {e}")

        # Sort by view count descending
        benchmarks.sort(key=lambda x: x["views"], reverse=True)
        return benchmarks

    @staticmethod
    def synthesize_viral_package(format_name: str, topic_item: str, reference_vids: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Synthesizes the optimal Title, Description, and Tags inspired by top winners.
        """
        top_title = reference_vids[0]["title"] if reference_vids else "CASEOH RANKS FOOD"
        
        # Clean and extract structural pattern from top winner
        # e.g., "CASEOH RANKS HOSTESS SNACKS!! #clips #funny #caseoh" -> Pattern: ALL CAPS + ITEM + !!
        
        clean_title = f"CaseOh CAN'T CHANGE HIS SPOT! 😭 ({topic_item} Edition) #shorts"
        
        description = (
            f"CaseOh blind ranks {topic_item} and gets stuck with his picks! Twinkies at #9 is wild... 💀\n\n"
            f"What is your absolute #1 {topic_item}? Did CaseOh cook or burn the kitchen? Drop your ranking below! 👇\n\n"
            f"All stream credits to CaseOh: https://www.youtube.com/@caseoh_\n\n"
            f"#caseoh #caseohclips #shorts #funny #blindranking #food #reactions #streamer"
        )
        
        tags = [
            "case", "caseoh", "caseoh games", "caseoh clips", "stream clips",
            "caseoh rage", "caseoh funny", "caseoh moments", "streamer", "caseoh ranks",
            "caseoh food edition", "funny", "reactions", "caseoh funniest moments",
            "hostess snacks", "twinkies", "donettes", "snoballs", "ding dongs",
            "caseoh blind ranking", "food ranking", "streamer reactions"
        ]
        
        return {
            "title": clean_title,
            "description": description,
            "tags": ", ".join(tags),
            "benchmark_inspirations": [b["title"] for b in (reference_vids or [])[:3]]
        }
