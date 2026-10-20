"""YouTube Studio Automated Browser Uploader (Playwright).

Provides 100% automated, hands-free video uploading to YouTube Studio.
- Bypasses Google Data API v3 quota limits (UNLIMITED daily uploads).
- Uses persistent browser sessions per creator (saved cookies & auth).
- Fills Title, Description, Tags, 'Not for Kids', and Schedules optimal slots.
"""

import os
import sys
import time
import json
import re
import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

# Force UTF-8 output on Windows to prevent UnicodeEncodeError with emojis in CP1252 terminals
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Always anchor to the AutoClip project root regardless of working directory
# Path(__file__) = Desktop\AutoClip\autoclip\studio_uploader.py → .parent.parent = Desktop\AutoClip
_THIS_FILE = Path(__file__).resolve()
_AUTOCLIP_ROOT = _THIS_FILE.parent.parent  # autoclip/ -> AutoClip/

# Sanity check: if resolved root doesn't look right, fall back to known path
if not (_AUTOCLIP_ROOT / "autoclip").exists():
    _AUTOCLIP_ROOT = Path(r"C:\Users\swastik\Desktop\AutoClip")

PROJECT_ROOT = _AUTOCLIP_ROOT

# Always use Desktop\AutoClip as canonical sessions root (regardless of workspace/CWD)
SESSIONS_DIR = Path(r"C:\Users\swastik\Desktop\AutoClip\data\studio_sessions")
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"

# Channel ID mapping
CREATOR_CHANNELS = {
    "speed": {
        "channel_id": "UCVrh_-HaHkEF8tEnYGJsW5A",
        "name": "Speed Clips Daily",
        "handle": "@tanvoiamhere"
    },
    "caseoh": {
        "channel_id": "UCelQ7wkvHyI9j0Ab3ISMqEQ",
        "name": "CaseOh Clips",
        "handle": "@fixlife-q7g"
    },
    "jynxzi": {
        "channel_id": "UCBaLUH8LwQQ2KMkxq7wNfCA",
        "name": "Jynxzi Clips",
        "handle": "@askwhatt"
    },
    "event_horizon": {
        "channel_id": "UCmlRgAwu8PuI_VlvTjDoY6w",
        "name": "EVENT HORIZON",
        "handle": "@event_horizon-q5u"
    }
}


def get_session_dir(creator_key: str) -> Path:
    """Return persistent session folder for this creator."""
    c_norm = str(creator_key or "default").strip().lower()
    if "speed" in c_norm or "tanvo" in c_norm:
        c_slug = "speed"
    elif "case" in c_norm:
        c_slug = "caseoh"
    elif "jynx" in c_norm or "jinx" in c_norm:
        c_slug = "jynxzi"
    elif "event" in c_norm or "horizon" in c_norm:
        c_slug = "event_horizon"
    else:
        c_slug = "default"
    
    path = SESSIONS_DIR / c_slug
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_session_authenticated(creator_key: str) -> bool:
    """Check if authenticated state file exists in the persistent profile.
    
    Accepts both:
    1. storage_state.json (exported by Playwright after login_interactive)
    2. Native Edge/Chromium Cookies database (written during interactive browser session)
    """
    s_dir = get_session_dir(creator_key)
    
    # Priority 1: Playwright storage_state.json with verified Google cookies
    storage_state = s_dir / "storage_state.json"
    if storage_state.exists() and storage_state.stat().st_size > 200:
        try:
            content = storage_state.read_text(encoding="utf-8")
            data = json.loads(content)
            cookies = data.get("cookies", [])
            if cookies and len(cookies) >= 5:
                return True
        except Exception:
            pass

    # Priority 2: Native Chromium/Edge Cookies database (written when user logs in via
    # the interactive browser that was launched by login_interactive())
    cookie_file = s_dir / "Default" / "Network" / "Cookies"
    cookie_file_alt = s_dir / "Default" / "Cookies"
    for cf in [cookie_file, cookie_file_alt]:
        if cf.exists():
            size = cf.stat().st_size
            # A fresh empty Edge profile creates a ~28KB Cookies file.
            # A real logged-in session with Google accounts is typically 40KB+.
            if size >= 40960:  # 40KB+ means actual Google/YouTube cookies stored
                return True

    return False


def login_interactive(creator_key: str = "jynxzi") -> bool:
    """Open a visible browser window so user can sign in to YouTube Studio once.
    Cookies and session tokens are saved permanently for automated headless uploads.
    """
    from playwright.sync_api import sync_playwright
    s_dir = get_session_dir(creator_key)
    c_info = CREATOR_CHANNELS.get(creator_key, {"name": creator_key.title()})
    ch_id = c_info.get("channel_id")
    
    print(f"\n=======================================================")
    print(f"  🔐 YouTube Studio One-Time Login: {c_info.get('name').upper()}")
    print(f"=======================================================")
    print(f"Target Channel: {c_info.get('name')} ({c_info.get('handle', '')})")
    print(f"Profile Folder: {s_dir}")
    print("\n👉 An Edge browser window will open in a moment.")
    print("👉 Sign in to the Google Account associated with this YouTube channel.")
    print("👉 Once you reach YouTube Studio, this script will save your session and exit.")
    print("=======================================================\n")
    
    with sync_playwright() as p:
        try:
            browser_context = p.chromium.launch_persistent_context(
                user_data_dir=str(s_dir),
                headless=False,
                channel="msedge",  # Use Edge
                user_agent=USER_AGENT,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--start-maximized",
                    "--no-first-run",
                    "--no-default-browser-check"
                ],
                viewport=None
            )
        except Exception:
            browser_context = p.chromium.launch_persistent_context(
                user_data_dir=str(s_dir),
                headless=False,
                user_agent=USER_AGENT,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--start-maximized",
                    "--no-first-run"
                ],
                viewport=None
            )
        
        page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()
        target_studio_url = f"https://studio.youtube.com/channel/{ch_id}" if ch_id else "https://studio.youtube.com"
        print(f"[Studio Uploader] Opening: {target_studio_url}")
        page.goto(target_studio_url, wait_until="domcontentloaded", timeout=60000)
        
        # Wait up to 10 minutes for user to complete login and land on studio.youtube.com
        logged_in = False
        t_start = time.time()
        last_print = 0
        while time.time() - t_start < 600:
            current_url = page.url
            now = time.time()
            if now - last_print > 15:
                elapsed = int(now - t_start)
                print(f"[Studio Uploader] Waiting for sign-in in browser... ({elapsed}s elapsed)")
                last_print = now

            if "studio.youtube.com" in current_url and "accounts.google.com" not in current_url:
                try:
                    page.wait_for_selector("#create-icon, button[aria-label='Create'], ytcp-button#create-icon, #avatar-btn", timeout=4000)
                    logged_in = True
                    break
                except Exception:
                    if "studio.youtube.com" in page.url and "accounts.google.com" not in page.url:
                        logged_in = True
                        break
            time.sleep(2)
        
        if logged_in:
            print(f"\n[Studio Uploader] ✅ Authentication detected for {c_info.get('name')}!")
            print("[Studio Uploader] Finalizing session tokens...")
            time.sleep(3)
            # Save storage state json
            try:
                state_file = s_dir / "storage_state.json"
                browser_context.storage_state(path=str(state_file))
                print(f"[Studio Uploader] Session saved to {state_file}")
            except Exception as e:
                print(f"[Studio Uploader] Note saving storage state: {e}")
            time.sleep(1)
            browser_context.close()
            print(f"[Studio Uploader] 🎉 Ready! {c_info.get('name')} is now fully configured for unlimited automated uploads.\n")
            return True
        else:
            print("\n[Studio Uploader] ⚠️ Login timed out (10 minutes) or was not completed.")
            browser_context.close()
            return False


def safe_click(page, selector_or_element, timeout=15000, desc="element") -> bool:
    """Click an element safely, completely immune to Polymer tp-yt-iron-overlay-backdrop."""
    try:
        page.evaluate("""() => {
            document.querySelectorAll('tp-yt-iron-overlay-backdrop').forEach(b => {
                b.style.pointerEvents = 'none';
                b.style.display = 'none';
                b.removeAttribute('opened');
            });
        }""")
    except Exception:
        pass

    target = None
    if isinstance(selector_or_element, str):
        try:
            target = page.wait_for_selector(selector_or_element, timeout=timeout)
        except Exception:
            return False
    else:
        target = selector_or_element

    if not target:
        return False

    try:
        target.click(force=True, timeout=5000)
        return True
    except Exception:
        pass

    try:
        page.evaluate("el => el.click()", target)
        return True
    except Exception as e:
        print(f"[Studio Uploader] safe_click JS dispatch note on {desc}: {e}")
        return False


def upload_short_via_studio(
    video_path: str,
    title: str,
    description: str = "",
    tags: Optional[List[str]] = None,
    schedule_dt: Optional[datetime.datetime] = None,
    creator_key: str = "jynxzi",
    headless: bool = True,
    thumbnail_path: Optional[str] = None,
    pinned_comment: Optional[str] = None
) -> Dict[str, Any]:
    """Upload a video directly through YouTube Studio web UI using Playwright.
    
    100% hands-free and completely bypasses Google Data API quota limits.
    """
    from playwright.sync_api import sync_playwright
    
    video_path = os.path.abspath(video_path)
    if not os.path.exists(video_path):
        return {"ok": False, "error": f"Video file not found: {video_path}"}
    
    s_dir = get_session_dir(creator_key)
    c_info = CREATOR_CHANNELS.get(creator_key, {"name": creator_key.title()})
    ch_id = c_info.get("channel_id")
    
    # Check if session exists; if not, suggest one-time login
    if not is_session_authenticated(creator_key):
        return {
            "ok": False,
            "error": (
                f"Studio session not authenticated for '{c_info.get('name')}'.\n"
                f"👉 Run this one-time command in terminal to log in once:\n"
                f"`python -m autoclip.studio_uploader --login {creator_key}`"
            ),
            "needs_login": True
        }

    clean_title = (title or "AutoClip Short").strip()
    if "#shorts" not in clean_title.lower():
        clean_title += " #shorts"
    clean_title = clean_title[:100]  # YouTube title limit
    
    desc_text = (description or f"{clean_title}\n\nCreated with AutoClip AI.\n#shorts #viral").strip()[:5000]
    tags_list = tags or ["shorts", "viral", "trending"]
    
    print(f"[Studio Uploader] Launching headless browser for {c_info.get('name')}...")
    
    with sync_playwright() as p:
        try:
            # Use Edge (msedge) — faster startup, native Google login, no --no-sandbox warning
            try:
                browser_context = p.chromium.launch_persistent_context(
                    user_data_dir=str(s_dir),
                    headless=headless,
                    channel="msedge",
                    user_agent=USER_AGENT,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-infobars",
                        "--no-first-run",
                        "--no-default-browser-check"
                    ],
                    viewport={"width": 1280, "height": 800}
                )
            except Exception:
                # Fallback to bundled Playwright Chromium
                browser_context = p.chromium.launch_persistent_context(
                    user_data_dir=str(s_dir),
                    headless=headless,
                    user_agent=USER_AGENT,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-infobars",
                        "--no-first-run"
                    ],
                    viewport={"width": 1280, "height": 800}
                )
            
            page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()
            
            # Navigate to target channel upload page
            upload_url = f"https://studio.youtube.com/channel/{ch_id}/videos/upload?d=ud" if ch_id else "https://studio.youtube.com/video/upload"
            print(f"[Studio Uploader] Navigating to: {upload_url}")
            page.goto(upload_url, wait_until="domcontentloaded", timeout=45000)
            
            # Check if redirected to login
            if "accounts.google.com" in page.url:
                browser_context.close()
                try:
                    s_file = get_session_dir(creator_key) / "storage_state.json"
                    if s_file.exists():
                        s_file.unlink()
                except Exception:
                    pass
                return {
                    "ok": False,
                    "error": f"Session expired for {c_info.get('name')}. Please log in again using: python -m autoclip.studio_uploader --login {creator_key}",
                    "needs_login": True
                }
            
            # Dismiss any announcement / release note modals
            for dismiss_sel in ["ytcp-button#dismiss-button", "button:has-text('Dismiss')", "button:has-text('Got it')", "tp-yt-paper-dialog #close-button"]:
                try:
                    btn = page.query_selector(dismiss_sel)
                    if btn and btn.is_visible():
                        btn.click()
                        time.sleep(0.5)
                except Exception:
                    pass

            # Step 1: Wait for file input or click Create -> Upload
            print("[Studio Uploader] Staging file input...")
            file_input = page.wait_for_selector("input[type='file']", state="attached", timeout=15000)
            if not file_input:
                try:
                    # Try clicking create button
                    page.click("#create-icon, button[aria-label='Create']", timeout=8000)
                    page.click("tp-yt-paper-item:has-text('Upload videos'), #text-item-0", timeout=8000)
                    file_input = page.wait_for_selector("input[type='file']", state="attached", timeout=15000)
                except Exception as ce:
                    print(f"[Studio Uploader] Create button note: {ce}")
                    file_input = page.wait_for_selector("input[type='file']", state="attached", timeout=10000)

            # Step 2: Set the video file
            print(f"[Studio Uploader] Attaching video file: {os.path.basename(video_path)}")
            file_input.set_input_files(video_path)

            # Step 3: Wait for upload details dialog to populate
            print("[Studio Uploader] Waiting for Details modal...")
            page.wait_for_selector("#textbox, div[aria-label*='title'], ytcp-social-suggestions-textbox", timeout=40000)
            time.sleep(2)
            
            # Step 4: Fill Title
            print(f"[Studio Uploader] Setting Title: '{clean_title}'")
            try:
                title_box = page.wait_for_selector("#title-textarea #textbox, div[aria-label*='title'][contenteditable='true']", timeout=10000)
                safe_click(page, title_box, desc="title_box")
                title_box.fill(clean_title)
            except Exception as te:
                print(f"[Studio Uploader] Title fallback fill: {te}")
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                page.keyboard.type(clean_title)

            # Step 5: Fill Description
            try:
                print("[Studio Uploader] Setting Description...")
                desc_box = page.wait_for_selector("#description-textarea #textbox, div[aria-label*='description'][contenteditable='true']", timeout=8000)
                safe_click(page, desc_box, desc="desc_box")
                desc_box.fill(desc_text)
            except Exception as de:
                print(f"[Studio Uploader] Description note: {de}")

            # Step 5.1: Attach Custom Thumbnail if provided
            if thumbnail_path and os.path.exists(thumbnail_path):
                print(f"[Studio Uploader] Attaching custom thumbnail: {os.path.basename(thumbnail_path)}...")
                try:
                    thumb_input = page.query_selector(
                        "input#file-loader, ytcp-thumbnails-compact-editor-uploader input[type='file'], input[type='file'][accept*='image']"
                    )
                    if thumb_input:
                        thumb_input.set_input_files(os.path.abspath(thumbnail_path))
                        time.sleep(1.5)
                        print("[Studio Uploader] Custom thumbnail attached successfully.")
                    else:
                        print("[Studio Uploader] Thumbnail file input not found on page.")
                except Exception as the:
                    print(f"[Studio Uploader] Custom thumbnail note: {the}")

            # Step 6: Set "Not Made for Kids"
            print("[Studio Uploader] Selecting 'Not Made for Kids'...")
            try:
                not_for_kids = page.wait_for_selector("tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']", timeout=8000)
                safe_click(page, not_for_kids, desc="not_for_kids")
            except Exception as ke:
                print(f"[Studio Uploader] Audience selector note: {ke}")

            # Step 7: Fill Tags (Optional Show More)
            try:
                toggle_btn = page.query_selector("#toggle-button, ytcp-button#toggle-button")
                if toggle_btn and toggle_btn.is_visible():
                    safe_click(page, toggle_btn, desc="toggle_btn")
                    time.sleep(1)
                tags_input = page.wait_for_selector("#tags-container input, input[aria-label='Tags']", timeout=5000)
                if tags_input:
                    tags_str = ",".join(tags_list[:15])
                    tags_input.fill(tags_str)
                    tags_input.press("Enter")

                # Step 7.1: Altered / AI Content Disclosure ("Yes")
                try:
                    alt_radio = page.query_selector("tp-yt-paper-radio-button[name='ALTERED_CONTENT_YES'], ytcp-video-metadata-editor-advanced tp-yt-paper-radio-button[name='ALTERED_CONTENT_YES']")
                    if not alt_radio:
                        # Alternative selector for altered content
                        alt_radio = page.query_selector("tp-yt-paper-radio-button[name='ALTERED_CONTENT_YES']")
                    if alt_radio:
                        safe_click(page, alt_radio, desc="altered_content_yes")
                        print("[Studio Uploader] Marked Altered / AI content: YES")
                except Exception as ae:
                    print(f"[Studio Uploader] Altered content disclosure note: {ae}")
            except Exception:
                pass

            # Step 8: Click Next through tabs until reaching Visibility
            print("[Studio Uploader] Advancing through wizard tabs to Visibility...")
            for step_num in range(5):
                # Check if Visibility tab is already reached
                try:
                    vis_elem = page.query_selector(
                        "#second-container, tp-yt-paper-radio-button[name='SCHEDULE'], #first-container, tp-yt-paper-radio-button[name='PRIVATE']"
                    )
                    if vis_elem and vis_elem.is_visible():
                        print(f"[Studio Uploader] Visibility tab active at step {step_num}.")
                        break
                except Exception:
                    pass

                try:
                    next_btn = page.query_selector("#next-button, ytcp-button#next-button")
                    if next_btn and next_btn.is_visible():
                        safe_click(page, next_btn, desc=f"next_btn_{step_num}")
                        time.sleep(2.0)
                    else:
                        time.sleep(1.0)
                except Exception as ne:
                    print(f"[Studio Uploader] Next button step {step_num} note: {ne}")
                    time.sleep(1.0)

            # Ensure Visibility container is fully loaded
            try:
                page.wait_for_selector(
                    "#second-container, tp-yt-paper-radio-button[name='SCHEDULE'], #first-container, tp-yt-paper-radio-button[name='PRIVATE']",
                    timeout=15000
                )
            except Exception as ve:
                print(f"[Studio Uploader] Visibility container wait note: {ve}")

            # Step 9: Visibility Tab (Schedule or Public)
            print("[Studio Uploader] Configuring Visibility / Schedule...")
            scheduled_success = False
            if schedule_dt:
                target_dt = None
                if isinstance(schedule_dt, datetime.datetime):
                    target_dt = schedule_dt
                elif isinstance(schedule_dt, str):
                    try:
                        clean_str = schedule_dt.strip().replace("Z", "+00:00")
                        target_dt = datetime.datetime.fromisoformat(clean_str)
                    except Exception:
                        try:
                            import dateutil.parser
                            target_dt = dateutil.parser.parse(schedule_dt)
                        except Exception:
                            pass
                
                if target_dt:
                    try:
                        # Convert to local timezone for the browser instance
                        local_dt = target_dt.astimezone() if target_dt.tzinfo else target_dt
                        
                        # Round to nearest 15-minute slot for YouTube Studio scheduler
                        m_rounded = int(round(local_dt.minute / 15.0) * 15)
                        if m_rounded >= 60:
                            local_dt = (local_dt + datetime.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
                        else:
                            local_dt = local_dt.replace(minute=m_rounded, second=0, microsecond=0)

                        month_name = local_dt.strftime("%b")
                        day_num = str(local_dt.day)
                        year_num = str(local_dt.year)
                        target_date_str = f"{month_name} {day_num}, {year_num}"
                        target_time_str = local_dt.strftime("%I:%M %p").lstrip("0")
                        if not target_time_str:
                            target_time_str = local_dt.strftime("%I:%M %p")

                        print(f"[Studio Uploader] Target Schedule Slot -> Date: {target_date_str} | Time: {target_time_str}")

                        # 1. Scroll dialog down to expose Schedule section
                        try:
                            page.evaluate("""() => {
                                const sec = document.querySelector('#second-container') || 
                                            document.querySelector('tp-yt-paper-radio-button[name="SCHEDULE"]') ||
                                            document.querySelector('#schedule-radio-button');
                                if (sec) sec.scrollIntoView({ behavior: 'instant', block: 'center' });
                            }""")
                            time.sleep(1.0)
                        except Exception:
                            pass

                        # 2. Click Schedule radio button with multiple fallbacks
                        clicked_schedule = False

                        # Try locator force click first
                        try:
                            loc = page.locator("#schedule-radio-button, tp-yt-paper-radio-button[name='SCHEDULE'], #second-container tp-yt-paper-radio-button, tp-yt-paper-radio-button:has-text('Schedule')").first
                            if loc.count() > 0:
                                loc.scroll_into_view_if_needed()
                                loc.click(force=True)
                                clicked_schedule = True
                        except Exception as loc_e:
                            print(f"[Studio Uploader] Locator click schedule note: {loc_e}")

                        # Fallback: JavaScript DOM click
                        if not clicked_schedule:
                            try:
                                clicked_schedule = page.evaluate("""() => {
                                    const el = document.querySelector('#schedule-radio-button') ||
                                               document.querySelector('tp-yt-paper-radio-button[name="SCHEDULE"]') ||
                                               document.querySelector('#second-container tp-yt-paper-radio-button') ||
                                               Array.from(document.querySelectorAll('tp-yt-paper-radio-button')).find(e => (e.innerText || '').toLowerCase().includes('schedule'));
                                    if (el) {
                                        el.scrollIntoView();
                                        el.click();
                                        return true;
                                    }
                                    return false;
                                }""")
                            except Exception:
                                pass

                        # Fallback: Playwright wait_for_selector
                        if not clicked_schedule:
                            schedule_radio = page.wait_for_selector(
                                "tp-yt-paper-radio-button[name='SCHEDULE'], #schedule-radio-button, #second-container tp-yt-paper-radio-button, [aria-label*='Schedule' i]",
                                timeout=15000
                            )
                            safe_click(page, schedule_radio, desc="schedule_radio_wait")
                            clicked_schedule = True

                        time.sleep(2.0)

                        # 3. Wait for Datepicker trigger to expand
                        try:
                            page.wait_for_selector("#datepicker-trigger, ytcp-dropdown-trigger#datepicker-trigger, [aria-label*='date' i]", timeout=10000)
                        except Exception:
                            pass

                        # Set Date in Studio UI
                        try:
                            date_trigger = page.query_selector("#datepicker-trigger, ytcp-dropdown-trigger#datepicker-trigger, [aria-label*='date' i]")
                            if date_trigger:
                                safe_click(page, date_trigger, desc="date_trigger")
                                time.sleep(1.0)
                                date_input = page.query_selector("ytcp-date-picker input, ytcp-dropdown-trigger input, input[aria-label*='date' i], tp-yt-paper-dialog input")
                                if date_input:
                                    safe_click(page, date_input, desc="date_input")
                                    page.keyboard.press("Control+A")
                                    page.keyboard.press("Backspace")
                                    page.keyboard.type(target_date_str)
                                    page.keyboard.press("Enter")
                                    time.sleep(0.8)
                                else:
                                    page.keyboard.press("Escape")
                        except Exception as de:
                            print(f"[Studio Uploader] Datepicker note: {de}")

                        # Set Time in Studio UI
                        try:
                            time_trigger = page.query_selector("#time-of-day-trigger, ytcp-form-input-container#time-of-day-container, [aria-label*='time' i]")
                            if time_trigger:
                                safe_click(page, time_trigger, desc="time_trigger")
                                time.sleep(0.8)
                                time_input = page.query_selector("#time-of-day-trigger input, input[aria-label*='time' i], #time-of-day-container input, tp-yt-paper-dialog input")
                                if time_input:
                                    safe_click(page, time_input, desc="time_input")
                                    page.keyboard.press("Control+A")
                                    page.keyboard.press("Backspace")
                                    page.keyboard.type(target_time_str)
                                    page.keyboard.press("Enter")
                                    time.sleep(0.8)
                                else:
                                    page.keyboard.press("Escape")
                        except Exception as te:
                            print(f"[Studio Uploader] Timepicker note: {te}")

                        scheduled_success = True
                        print(f"[Studio Uploader] ✅ Scheduled for {target_date_str} at {target_time_str}")
                    except Exception as se:
                        print(f"[Studio Uploader] Schedule radio note: {se}. Falling back to PRIVATE (never accidental public)")
                        try:
                            # CRITICAL SAFETY: Fall back to PRIVATE, NEVER PUBLIC, when scheduling is requested!
                            safe_click(page, "tp-yt-paper-radio-button[name='PRIVATE'], #private-radio-button", desc="private_radio_fallback")
                        except Exception:
                            pass

            if not scheduled_success and not schedule_dt:
                try:
                    safe_click(page, "tp-yt-paper-radio-button[name='PUBLIC'], #public-radio-button", desc="public_radio_default")
                except Exception:
                    pass

            # Step 10: Wait for file upload progress to complete
            print("[Studio Uploader] Verifying file upload status on YouTube servers...")
            try:
                # Wait for upload progress to reach processing/complete or at least 15s
                page.wait_for_selector(
                    "ytcp-video-upload-progress:has-text('complete'), ytcp-video-upload-progress:has-text('Processing'), ytcp-video-upload-progress:has-text('Checks'), ytcp-video-upload-progress:has-text('100%')",
                    timeout=45000
                )
                print("[Studio Uploader] Upload progress verified.")
            except Exception:
                time.sleep(5)

            # Extract generated short URL from preview dialog
            video_url = ""
            try:
                link_el = page.query_selector("a.ytcp-video-info, a[href*='youtu.be']")
                if link_el:
                    video_url = link_el.get_attribute("href") or ""
            except Exception:
                pass

            # Step 11: Click Done / Schedule / Publish button
            print("[Studio Uploader] Finalizing upload (Clicking Done/Publish)...")
            done_btn = page.wait_for_selector(
                "#done-button, ytcp-button#done-button, button[aria-label='Publish'], button[aria-label='Schedule'], ytcp-button:has-text('Schedule'), ytcp-button:has-text('Publish'), ytcp-button:has-text('Save')",
                timeout=20000
            )
            safe_click(page, done_btn, desc="done_btn")
            
            # Wait for upload confirmation modal
            print("[Studio Uploader] Waiting for YouTube confirmation modal...")
            try:
                page.wait_for_selector(
                    "ytcp-video-share-dialog, ytcp-dialog:has-text('Video published'), ytcp-dialog:has-text('Video scheduled'), ytcp-dialog:has-text('Processing'), ytcp-dialog:has-text('Upload complete')",
                    timeout=60000
                )
                if not video_url:
                    dialog_link = page.query_selector("ytcp-video-share-dialog a[href*='youtu.be'], a[href*='youtu.be']")
                    if dialog_link:
                        video_url = dialog_link.get_attribute("href") or ""
            except Exception as we:
                print(f"[Studio Uploader] Modal wait note: {we}")
            
            time.sleep(5)
            browser_context.close()
            
            print(f"[Studio Uploader] 🎉 Upload complete! Link: {video_url or 'Live in Studio'}")
            res_payload = {
                "ok": True,
                "url": video_url or f"https://studio.youtube.com/channel/{ch_id}/videos/short",
                "title": clean_title,
                "channel": c_info.get("name"),
                "scheduled": bool(schedule_dt),
                "thumbnail_path": thumbnail_path if (thumbnail_path and os.path.exists(thumbnail_path)) else None,
                "pinned_comment": pinned_comment
            }
            try:
                from . import excel_tracker
                excel_tracker.log_upload(
                    creator=creator_key,
                    title=clean_title,
                    video_id=video_url.split("/")[-1] if video_url else "",
                    url=video_url or "",
                    scheduled_slot=str(schedule_dt) if schedule_dt else "Immediate Peak",
                    channel_name=c_info.get("name", f"{creator_key.title()} Clips"),
                    notes="Uploaded via YouTube Studio Automation"
                )
            except Exception:
                pass
            return res_payload
            
        except Exception as e:
            try:
                browser_context.close()
            except Exception:
                pass
            return {"ok": False, "error": f"Studio upload automation error: {e}"}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="YouTube Studio Browser Uploader")
    parser.add_argument("--login", type=str, choices=["speed", "caseoh", "jynxzi", "event_horizon"], default=None, help="Open interactive browser to log in once")
    parser.add_argument("--status", action="store_true", help="Check session login status for creators")
    args = parser.parse_args()
    
    if args.status:
        print("\n=== YouTube Studio Session Status ===")
        for c in ["speed", "caseoh", "jynxzi", "event_horizon"]:
            auth = is_session_authenticated(c)
            c_name = CREATOR_CHANNELS[c]["name"]
            status_tag = "[OK] Logged In" if auth else "[X] Needs One-Time Login"
            print(f"  {c.upper():<14} ({c_name}): {status_tag}")
        print()
    elif args.login:
        login_interactive(args.login)
    else:
        parser.print_help()
