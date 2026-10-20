"""AutoClip 30-Day Master Tracker & Excel Analytics Engine.

Maintains the authoritative C:/Users/swastik/Desktop/AutoClip/data/AutoClip_30_Day_Master_Tracker.xlsx
workbook for tracking all 30 days of uploads across:
1. Speed Clips Daily (@tanvoiamhere)
2. CaseOh Clips (@fixlife-q7g)
3. Jynxzi Clips (@askwhatt)

Also pulls YouTube analytics and formats weekly DM summaries.
"""

import os
import sys
import json
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    openpyxl = None

PROJECT_ROOT = Path(r"C:\Users\swastik\Desktop\AutoClip")
DATA_DIR = PROJECT_ROOT / "data"
EXCEL_PATH = DATA_DIR / "AutoClip_30_Day_Master_Tracker.xlsx"
JSON_LOG_PATH = DATA_DIR / "uploads_master_log.json"

START_DATE = datetime.date(2026, 10, 7)  # Day 1 start date

def _get_day_number(dt: datetime.datetime = None) -> int:
    """Calculate the project day number (Day 1 = Oct 7, 2026)."""
    if dt is None:
        dt = datetime.datetime.now()
    delta = (dt.date() - START_DATE).days
    return max(1, delta + 1)

def load_json_log() -> List[Dict[str, Any]]:
    """Load JSON log of all uploads."""
    if JSON_LOG_PATH.exists():
        try:
            with open(JSON_LOG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_json_log(entries: List[Dict[str, Any]]):
    """Save JSON log."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(JSON_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

def log_upload(
    creator: str,
    title: str,
    video_id: str,
    url: str,
    rank: int = 1,
    scheduled_slot: str = "",
    channel_name: str = "",
    notes: str = ""
) -> Dict[str, Any]:
    """Record an upload to the JSON master log and update the Excel spreadsheet."""
    entries = load_json_log()
    now = datetime.datetime.now()
    day_num = _get_day_number(now)

    # Deduplicate by video_id
    existing = next((e for e in entries if e.get("video_id") == video_id and video_id), None)
    if existing:
        existing.update({
            "title": title,
            "url": url,
            "scheduled_slot": scheduled_slot or existing.get("scheduled_slot", ""),
            "notes": notes or existing.get("notes", "")
        })
        entry = existing
    else:
        entry = {
            "day": f"Day {day_num}",
            "date_ist": now.strftime("%Y-%m-%d %I:%M %p IST"),
            "date_iso": now.isoformat(),
            "creator": creator.lower(),
            "channel_name": channel_name or f"{creator.title()} Clips",
            "rank": rank,
            "title": title,
            "video_id": video_id,
            "url": url or (f"https://youtu.be/{video_id}" if video_id else ""),
            "scheduled_slot": scheduled_slot,
            "status": "Live / Scheduled",
            "views": "-",
            "likes": "-",
            "comments": "-",
            "retention_pct": "-",
            "notes": notes or "AutoClip Viral 9:16 Short"
        }
        entries.append(entry)

    save_json_log(entries)
    try:
        generate_excel_tracker()
    except Exception as e:
        print(f"[Excel Tracker] Note during excel sync: {e}")
    return entry

def generate_excel_tracker() -> str:
    """Generate or update the beautiful master Excel tracker spreadsheet."""
    if not openpyxl:
        return ""

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()

    # Define Theme Colors and Styles
    c_header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid") # Slate 900
    c_header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    
    font_title = Font(name="Calibri", size=15, bold=True, color="0F172A")
    font_sub = Font(name="Calibri", size=10, italic=True, color="64748B")
    font_body = Font(name="Calibri", size=10, color="1E293B")
    font_bold = Font(name="Calibri", size=10, bold=True, color="0F172A")
    font_link = Font(name="Calibri", size=10, color="2563EB", underline="single")

    border_thin = Border(
        left=Side(style='thin', color='E2E8F0'),
        right=Side(style='thin', color='E2E8F0'),
        top=Side(style='thin', color='E2E8F0'),
        bottom=Side(style='thin', color='E2E8F0')
    )

    fill_alt = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid") # Slate 50
    fill_speed = PatternFill(start_color="FEF2F2", end_color="FEF2F2", fill_type="solid") # Red 50
    fill_caseoh = PatternFill(start_color="FFFBEB", end_color="FFFBEB", fill_type="solid") # Amber 50
    fill_jynxzi = PatternFill(start_color="F0FDF4", end_color="F0FDF4", fill_type="solid") # Green 50

    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    # -------------------------------------------------------------
    # SHEET 1: 30-Day Upload Log
    # -------------------------------------------------------------
    ws1 = wb.active
    ws1.title = "30-Day Upload Log"
    ws1.views.sheetView[0].showGridLines = True

    # Title block
    ws1["A1"] = "AutoClip 30-Day Master Production & Upload Tracker"
    ws1["A1"].font = font_title
    ws1["A2"] = "Tracking 3 Channels • 6-Hour Spacing Timeline • October 7, 2026 – November 6, 2026"
    ws1["A2"].font = font_sub

    headers1 = [
        "Day #", "Upload Date (IST)", "Channel / Streamer", "Rank",
        "Short Title", "YouTube URL", "Scheduled Window", "Status",
        "Views", "Likes", "Comments", "Retention %", "Notes & Tags"
    ]

    row_num = 4
    for col_num, h_text in enumerate(headers1, 1):
        cell = ws1.cell(row=row_num, column=col_num, value=h_text)
        cell.fill = c_header_fill
        cell.font = c_header_font
        cell.alignment = align_center
        cell.border = border_thin

    entries = load_json_log()
    row_num = 5
    for idx, e in enumerate(entries):
        creator = e.get("creator", "").lower()
        if "speed" in creator:
            row_fill = fill_speed
        elif "case" in creator:
            row_fill = fill_caseoh
        elif "jynx" in creator:
            row_fill = fill_jynxzi
        else:
            row_fill = fill_alt if idx % 2 == 1 else None

        row_data = [
            (e.get("day", "Day 1"), align_center, font_bold),
            (e.get("date_ist", ""), align_center, font_body),
            (e.get("channel_name", ""), align_left, font_bold),
            (f"Rank #{e.get('rank', 1)}", align_center, font_body),
            (e.get("title", ""), align_left, font_body),
            (e.get("url", ""), align_left, font_link),
            (e.get("scheduled_slot", "Immediate / Peak"), align_center, font_body),
            (e.get("status", "Live"), align_center, font_bold),
            (e.get("views", "-"), align_center, font_body),
            (e.get("likes", "-"), align_center, font_body),
            (e.get("comments", "-"), align_center, font_body),
            (e.get("retention_pct", "-"), align_center, font_body),
            (e.get("notes", ""), align_left, font_body)
        ]

        for col_idx, (val, al, fnt) in enumerate(row_data, 1):
            c = ws1.cell(row=row_num, column=col_idx, value=val)
            c.font = fnt
            c.alignment = al
            c.border = border_thin
            if row_fill:
                c.fill = row_fill
            if col_idx == 6 and val.startswith("http"):
                c.hyperlink = val

        row_num += 1

    # Auto-fit column widths
    for col in ws1.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for c in col:
            val_str = str(c.value or "")
            if len(val_str) > max_len and c.row > 2:
                max_len = len(val_str)
        ws1.column_dimensions[col_letter].width = max(max_len + 3, 12)
    ws1.column_dimensions["E"].width = 38 # Title column
    ws1.column_dimensions["F"].width = 28 # URL column
    ws1.column_dimensions["G"].width = 32 # Scheduled slot column

    # -------------------------------------------------------------
    # SHEET 2: Weekly Performance Summary
    # -------------------------------------------------------------
    ws2 = wb.create_sheet(title="Weekly Analytics & DM Reports")
    ws2.views.sheetView[0].showGridLines = True

    ws2["A1"] = "Weekly Channel Performance & DM Audit Reports"
    ws2["A1"].font = font_title
    ws2["A2"] = "Automated Weekly Direct Message Reports for Swastik • 7-Day Performance Audits"
    ws2["A2"].font = font_sub

    headers2 = [
        "Report #", "Date Window", "Channel", "Total Shorts",
        "Total Views", "Total Likes", "Top Performing Short",
        "Avg Duration", "Virality Notes / Takeaways"
    ]

    row_num = 4
    for col_num, h_text in enumerate(headers2, 1):
        cell = ws2.cell(row=row_num, column=col_num, value=h_text)
        cell.fill = c_header_fill
        cell.font = c_header_font
        cell.alignment = align_center
        cell.border = border_thin

    # Template rows for Weeks 1 to 4
    weeks_meta = [
        ("Week 1 DM Report", "Oct 7 – Oct 14, 2026", "Speed Clips Daily", "In Progress", "-", "-", "Pending 7-Day Run", "-", "First seed window testing"),
        ("Week 1 DM Report", "Oct 7 – Oct 14, 2026", "CaseOh Clips", "In Progress", "-", "-", "Pending 7-Day Run", "-", "Horror jumpscare retention check"),
        ("Week 1 DM Report", "Oct 7 – Oct 14, 2026", "Jynxzi Clips", "In Progress", "-", "-", "Pending 7-Day Run", "-", "Minecraft vs R6 clutch benchmark"),
        ("Week 2 DM Report", "Oct 14 – Oct 21, 2026", "All Channels", "Scheduled", "-", "-", "-", "-", "Cadence consistency evaluation"),
        ("Week 3 DM Report", "Oct 21 – Oct 28, 2026", "All Channels", "Scheduled", "-", "-", "-", "-", "Mid-month velocity check"),
        ("Week 4 DM Report", "Oct 28 – Nov 4, 2026", "All Channels", "Scheduled", "-", "-", "-", "-", "Pre-review milestone audit"),
        ("Month 1 Retrospective", "Oct 7 – Nov 6, 2026", "All Channels", "Final Review", "-", "-", "-", "-", "Complete 30-day analytics retrospective")
    ]

    row_num = 5
    for idx, w in enumerate(weeks_meta):
        for col_idx, val in enumerate(w, 1):
            c = ws2.cell(row=row_num, column=col_idx, value=val)
            c.font = font_bold if col_idx in [1, 3] else font_body
            c.alignment = align_center if col_idx in [1, 2, 4, 5, 6, 8] else align_left
            c.border = border_thin
            if idx % 2 == 1:
                c.fill = fill_alt
        row_num += 1

    for col in ws2.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for c in col:
            val_str = str(c.value or "")
            if len(val_str) > max_len and c.row > 2:
                max_len = len(val_str)
        ws2.column_dimensions[col_letter].width = max(max_len + 3, 14)

    # -------------------------------------------------------------
    # SHEET 3: Channel Configuration & Rules
    # -------------------------------------------------------------
    ws3 = wb.create_sheet(title="Channel Setup & Peak Windows")
    ws3.views.sheetView[0].showGridLines = True

    ws3["A1"] = "Channel Registry & 6-Hour Timeline Specification"
    ws3["A1"].font = font_title
    ws3["A2"] = "Strict 1-to-1 Mapping • Zero Cross-Contamination • Optimal Algorithm Upload Slots"
    ws3["A2"].font = font_sub

    headers3 = ["Channel Key", "Display Name", "Handle", "YouTube Channel ID", "Composio Account", "Optimal Peak Windows (IST)", "Niche Focus"]
    row_num = 4
    for col_num, h_text in enumerate(headers3, 1):
        cell = ws3.cell(row=row_num, column=col_num, value=h_text)
        cell.fill = c_header_fill
        cell.font = c_header_font
        cell.alignment = align_center
        cell.border = border_thin

    channel_specs = [
        ("speed", "Speed Clips Daily", "@tanvoiamhere", "UCVrh_-HaHkEF8tEnYGJsW5A", "youtube_begin-manner", "1:00 AM, 7:00 AM, 3:30 PM, 9:30 PM", "High Energy · Reactions · Rage"),
        ("caseoh", "CaseOh Clips", "@fixlife-q7g", "UCelQ7wkvHyI9j0Ab3ISMqEQ", "youtube_bout-unfine", "2:00 AM, 8:30 AM, 4:30 PM, 10:30 PM", "Horror Games · Jumpscares · Comedy"),
        ("jynxzi", "Jynxzi Clips", "@askwhatt", "UCBaLUH8LwQQ2KMkxq7wNfCA", "youtube_teredo-jolly", "7:30 AM, 2:30 PM, 9:30 PM, 3:30 AM", "Minecraft · R6 Clutches · Chaos")
    ]

    row_num = 5
    for c_spec in channel_specs:
        for col_idx, val in enumerate(c_spec, 1):
            c = ws3.cell(row=row_num, column=col_idx, value=val)
            c.font = font_bold if col_idx in [1, 2] else font_body
            c.alignment = align_center if col_idx in [1, 3, 4, 5] else align_left
            c.border = border_thin
        row_num += 1

    for col in ws3.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for c in col:
            val_str = str(c.value or "")
            if len(val_str) > max_len and c.row > 2:
                max_len = len(val_str)
        ws3.column_dimensions[col_letter].width = max(max_len + 3, 15)

    wb.save(EXCEL_PATH)
    print(f"[Excel Tracker] Master spreadsheet successfully generated: {EXCEL_PATH}")
    return str(EXCEL_PATH)


def sync_day1_uploads():
    """Seed Day 1 with all 10 verified uploads."""
    day1_videos = [
        # Speed Clips Daily
        {
            "creator": "speed",
            "title": "Speed Blames Controller For Losing 🎮 💀 #shorts",
            "video_id": "UZgqcMSEl7s",
            "url": "https://youtu.be/UZgqcMSEl7s",
            "rank": 1,
            "channel_name": "Speed Clips Daily",
            "scheduled_slot": "Uploaded Day 1 (11:11 PM IST)",
            "notes": "IShowSpeed FC24 / Gaming rage moment"
        },
        {
            "creator": "speed",
            "title": "Speed Panics Over Ronaldo Retiring 🇵🇹 💀 #shorts",
            "video_id": "KhuTMsYVtT4",
            "url": "https://youtu.be/KhuTMsYVtT4",
            "rank": 2,
            "channel_name": "Speed Clips Daily",
            "scheduled_slot": "Uploaded Day 1 (11:07 PM IST)",
            "notes": "IShowSpeed viral Ronaldo reaction"
        },
        {
            "creator": "speed",
            "title": "😂 BRO LOST IT 😂 💀 #shorts",
            "video_id": "ADu36_yciUA",
            "url": "https://youtu.be/ADu36_yciUA",
            "rank": 3,
            "channel_name": "Speed Clips Daily",
            "scheduled_slot": "Uploaded Day 1 (10:53 PM IST)",
            "notes": "IShowSpeed laughing freakout clip"
        },
        # CaseOh Clips
        {
            "creator": "caseoh",
            "title": "CaseOh Defends His Junk Food 🍕 💀 #shorts",
            "video_id": "J8uxNHoFVWU",
            "url": "https://youtu.be/J8uxNHoFVWU",
            "rank": 1,
            "channel_name": "CaseOh Clips",
            "scheduled_slot": "Uploaded Day 1 (11:56 PM IST)",
            "notes": "CaseOh food defense / chat ban comedy"
        },
        {
            "creator": "caseoh",
            "title": "\"Look here buddy i just got...\" 😱 #shorts",
            "video_id": "bCStgG34r0I",
            "url": "https://youtu.be/bCStgG34r0I",
            "rank": 2,
            "channel_name": "CaseOh Clips",
            "scheduled_slot": "Uploaded Day 1 (9:41 PM IST)",
            "notes": "CaseOh 60 Seconds / Simulator reaction"
        },
        {
            "creator": "caseoh",
            "title": "\"How you doing not today cooper...\" 😱 #shorts",
            "video_id": "qvtzrorOQHA",
            "url": "https://youtu.be/qvtzrorOQHA",
            "rank": 3,
            "channel_name": "CaseOh Clips",
            "scheduled_slot": "Uploaded Day 1 (11:51 AM IST)",
            "notes": "CaseOh horror game interaction"
        },
        # Jynxzi Clips
        {
            "creator": "jynxzi",
            "title": "Minecraft Sex Offender Allegations 💀 #shorts",
            "video_id": "qD6SskmaYvk",
            "url": "https://youtu.be/qD6SskmaYvk",
            "rank": 1,
            "channel_name": "Jynxzi Clips",
            "scheduled_slot": "Uploaded Day 1 (11:47 PM IST)",
            "notes": "Hardcore Minecraft Day 1 dialogue highlight"
        },
        {
            "creator": "jynxzi",
            "title": "Jynxzi Loses It Over Creeper 💥 💀 #shorts",
            "video_id": "6sz37YC_9kw",
            "url": "https://youtu.be/6sz37YC_9kw",
            "rank": 2,
            "channel_name": "Jynxzi Clips",
            "scheduled_slot": "Uploaded Day 1 (11:41 PM IST)",
            "notes": "Hardcore Minecraft Creeper explosion freakout"
        },
        {
            "creator": "jynxzi",
            "title": "Jynxzi Pushes Friend Off Cliff 🎮 💀 #shorts",
            "video_id": "A1dW_a0RsPE",
            "url": "https://youtu.be/A1dW_a0RsPE",
            "rank": 3,
            "channel_name": "Jynxzi Clips",
            "scheduled_slot": "Uploaded Day 1 (10:54 PM IST)",
            "notes": "Minecraft Cliff betrayal comedy moment"
        },
        {
            "creator": "jynxzi",
            "title": "Caught On My Brother In Water 🌊 💀 #shorts",
            "video_id": "mv2wxnX27Q4",
            "url": "https://youtu.be/mv2wxnX27Q4",
            "rank": 4,
            "channel_name": "Jynxzi Clips",
            "scheduled_slot": "Uploaded Day 1 (9:55 PM IST)",
            "notes": "Minecraft Drowning water trap moment"
        }
    ]

    for item in day1_videos:
        log_upload(
            creator=item["creator"],
            title=item["title"],
            video_id=item["video_id"],
            url=item["url"],
            rank=item["rank"],
            scheduled_slot=item["scheduled_slot"],
            channel_name=item["channel_name"],
            notes=item["notes"]
        )
    print(f"[Excel Tracker] Seeded Day 1 with {len(day1_videos)} verified uploads.")


def update_live_metrics_from_youtube() -> List[Dict[str, Any]]:
    """Query YouTube Data API for actual view counts, likes, and comments for all tracked videos."""
    from . import composio_client, channel_routing
    entries = load_json_log()
    if not entries:
        return []

    # Group by creator account
    creator_videos = {}
    for e in entries:
        c = e.get("creator", "speed")
        v_id = e.get("video_id")
        if v_id:
            creator_videos.setdefault(c, []).append(e)

    for c, v_entries in creator_videos.items():
        try:
            route = channel_routing.get_route(c)
            acc = route["composio_account_id"]
            v_ids = [ve["video_id"] for ve in v_entries if ve.get("video_id")]
            if not v_ids:
                continue
            
            res = composio_client.execute_tool('YOUTUBE_GET_VIDEO_DETAILS_BATCH', {
                'id': v_ids,
                'parts': ['statistics', 'snippet']
            }, account=acc)

            items = []
            if isinstance(res, dict):
                data = res.get('data', res)
                if 'items' in data:
                    items = data['items']
                elif 'results' in data and data['results']:
                    items = data['results'][0].get('response', {}).get('data', {}).get('items', [])
            
            stats_by_id = {}
            for item in items:
                v_id = item.get('id')
                stats = item.get('statistics', {})
                if v_id:
                    stats_by_id[v_id] = stats

            for ve in v_entries:
                v_id = ve.get("video_id")
                if v_id in stats_by_id:
                    st = stats_by_id[v_id]
                    ve["views"] = int(st.get("viewCount", 0))
                    ve["likes"] = int(st.get("likeCount", 0))
                    ve["comments"] = int(st.get("commentCount", 0))
        except Exception as err:
            print(f"[Excel Tracker] Could not fetch stats for {c}: {err}")

    save_json_log(entries)
    generate_excel_tracker()
    return entries


if __name__ == "__main__":
    sync_day1_uploads()
    update_live_metrics_from_youtube()
    generate_excel_tracker()

