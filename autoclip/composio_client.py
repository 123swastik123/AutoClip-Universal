"""Composio MCP & YouTube Integration Client.

Enables:
1. Search & discover YouTube videos using authenticated Composio account (@askwhatt)
2. Retrieve channel details, playlists, and video metadata
3. Upload rendered 9:16 Shorts directly to YouTube
"""
import os, sys, json, urllib.request, urllib.error
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from . import config

COMPOSIO_URL = os.environ.get("COMPOSIO_MCP_URL", "https://connect.composio.dev/mcp")
COMPOSIO_KEY = os.environ.get("COMPOSIO_API_KEY", "")

def _call_mcp(method, params=None, timeout=25):
    """Execute JSON-RPC call against Composio MCP endpoint (SSE stream)."""
    headers = {
        "Authorization": f"Bearer {COMPOSIO_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "id": 1
    }
    if params:
        payload["params"] = params
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(COMPOSIO_URL, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", errors="ignore")
    
    # Parse all SSE data lines and return the last one with a result
    results = []
    for line in raw.split("\n"):
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                if "result" in data:
                    results.append(data["result"])
                elif "error" in data:
                    results.append({"error": data["error"]})
            except Exception:
                pass
    
    # Return the last successful result
    if results:
        return results[-1]
    return {}

def execute_tool(slug, arguments=None, timeout=30, account=None):
    """Execute a single Composio tool via COMPOSIO_MULTI_EXECUTE_TOOL."""
    tool_entry = {
        "tool_slug": slug,
        "arguments": arguments or {}
    }
    if account:
        tool_entry["account"] = account
    elif slug.startswith("TWITCH_"):
        tool_entry["account"] = "twitch_yapp-gifted"

    res = _call_mcp("tools/call", {
        "name": "COMPOSIO_MULTI_EXECUTE_TOOL",
        "arguments": {
            "sync_response_to_workbench": False,
            "tools": [tool_entry]
        }
    }, timeout=timeout)
    content = res.get("content", [])
    if content:
        txt = content[0].get("text", "{}")
        try:
            parsed = json.loads(txt)
            results = parsed.get("data", {}).get("results", [])
            if results:
                return results[0].get("response", {}).get("data", {})
        except Exception:
            return txt
    return {}

def get_twitch_clips(broadcaster_id: str, first: int = 5):
    """Retrieve top clips for a Twitch broadcaster via Composio."""
    try:
        data = execute_tool("TWITCH_GET_CLIPS", {"broadcaster_id": broadcaster_id, "first": first})
        return data.get("data", [])
    except Exception as e:
        print(f"[Composio Twitch] Error fetching clips: {e}")
        return []

def get_twitch_videos(user_id: str, first: int = 3):
    """Retrieve published videos/VODs for a Twitch user via Composio."""
    try:
        data = execute_tool("TWITCH_GET_VIDEOS", {"user_id": user_id, "first": first, "type": "archive"})
        return data.get("data", [])
    except Exception as e:
        print(f"[Composio Twitch] Error fetching videos: {e}")
        return []

def get_twitch_user(login_name: str):
    """Retrieve Twitch user profile by login name via Composio."""
    try:
        data = execute_tool("TWITCH_GET_USERS", {"login": [login_name]})
        users = data.get("data", [])
        return users[0] if users else None
    except Exception as e:
        print(f"[Composio Twitch] Error fetching user {login_name}: {e}")
        return None

def get_channel_info():
    """Retrieve connected YouTube channel details."""
    res = _call_mcp("tools/call", {
        "name": "COMPOSIO_SEARCH_TOOLS",
        "arguments": {
            "query": "youtube"
        }
    })
    content = res.get("content", [])
    if content:
        txt = content[0].get("text", "{}")
        try:
            parsed = json.loads(txt)
            statuses = parsed.get("data", {}).get("toolkit_connection_statuses", [])
            for st in statuses:
                if st.get("toolkit") == "youtube" and st.get("has_active_connection"):
                    accs = st.get("accounts", [])
                    if accs:
                        items = accs[0].get("user_info", {}).get("items", [])
                        if items:
                            snip = items[0].get("snippet", {})
                            return {
                                "connected": True,
                                "channel_id": items[0].get("id"),
                                "title": snip.get("title"),
                                "custom_url": snip.get("customUrl"),
                                "account_id": accs[0].get("id")
                            }
        except Exception:
            pass
    return {"connected": False}

def search_youtube(query, max_results=5):
    """Search YouTube videos using the connected Composio account."""
    data = execute_tool("YOUTUBE_SEARCH_YOU_TUBE", {
        "q": query,
        "maxResults": max_results
    })
    items = data.get("items", [])
    out = []
    for it in items:
        vid_id = it.get("id", {}).get("videoId")
        if vid_id:
            snip = it.get("snippet", {})
            out.append({
                "id": vid_id,
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "title": snip.get("title"),
                "channel": snip.get("channelTitle"),
                "description": snip.get("description", "")[:120],
                "published_at": snip.get("publishedAt")
            })
    return out

def get_channel_videos(channel_id=None, max_results=10):
    """Retrieve videos from the user's connected YouTube channel."""
    if not channel_id:
        info = get_channel_info()
        channel_id = info.get("channel_id", "UCBaLUH8LwQQ2KMkxq7wNfCA")
    data = execute_tool("YOUTUBE_LIST_CHANNEL_VIDEOS", {
        "channelId": channel_id
    })
    items = data.get("items", []) if isinstance(data, dict) else []
    out = []
    for it in items:
        vid_id = it.get("snippet", {}).get("resourceId", {}).get("videoId") or it.get("id", {}).get("videoId")
        if vid_id:
            snip = it.get("snippet", {})
            out.append({
                "id": vid_id,
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "title": snip.get("title", ""),
                "description": snip.get("description", "")[:120],
                "published_at": snip.get("publishedAt", "")
            })
    return out

def get_presigned_upload_url(timeout=30):
    """Obtain a presigned upload URL and S3 storage key from Composio."""
    code = """
import os, requests, json, sys
backend_url = os.environ.get("BACKEND_URL", "https://backend.composio.dev")
access_key = os.environ.get("COMPOSIO_WORKBENCH_ACCESS_KEY", "")
presigned_url = backend_url + "/api/v3/tool_router/internal/presigned_url"
req_headers = {
    "x-session-access-key": access_key,
    "Content-Type": "application/json",
}
payload = {"operation": "upload"}
try:
    response = requests.post(presigned_url, json=payload, headers=req_headers, timeout=20)
    print("PRESIGNED_RES:" + response.text)
except Exception as e:
    print("PRESIGNED_ERR:" + str(e))
"""
    try:
        res = _call_mcp("tools/call", {
            "name": "COMPOSIO_REMOTE_WORKBENCH",
            "arguments": {"code_to_execute": code}
        }, timeout=timeout)
        content = res.get("content", [])
        if content:
            txt = content[0].get("text", "")
            try:
                parsed = json.loads(txt)
                stdout = parsed.get("data", {}).get("stdout", "")
                stderr = parsed.get("data", {}).get("stderr", "")
                print(f"[Presigned URL] stdout={stdout[:300]} stderr={stderr[:200]}")
                if "PRESIGNED_RES:" in stdout:
                    raw_json = stdout.split("PRESIGNED_RES:", 1)[1].strip()
                    pdata = json.loads(raw_json)
                    u = pdata.get("upload_url") or pdata.get("url")
                    k = pdata.get("key") or pdata.get("s3key")
                    if u and k:
                        return u, k
                    print(f"[Presigned URL] Got response but missing url/key: {pdata}")
                elif "PRESIGNED_ERR:" in stdout:
                    print(f"[Presigned URL] Remote error: {stdout}")
            except Exception as pe:
                print(f"[Presigned URL] Parse error: {pe} | raw txt: {txt[:300]}")
    except Exception as e:
        print(f"[Presigned URL] Call failed: {e}")
    return None, None

def upload_video_to_youtube(video_path, title, description="", tags=None, privacy="public", publish_at=None, creator=None, account_id=None, thumbnail_path=None, pinned_comment=None):
    """Upload a rendered short video to the connected YouTube channel via Composio MCP or Studio.

    Strict Creator/Niche Routing:
    - IShowSpeed -> Channel 1 (Speed Clips Daily, youtube_rigid-easing)
    - CaseOh     -> Channel 2 (CaseOh Clips, youtube_bout-unfine)
    - Jynxzi     -> Channel 3 (Jynxzi Clips, youtube_teredo-jolly)
    - AI/Tech    -> Channel 4 (TechPulse Daily, youtube_begin-manner)
    """
    video_path = os.path.abspath(video_path)
    if not os.path.exists(video_path):
        return {"ok": False, "error": f"File does not exist: {video_path}"}

    file_size = os.path.getsize(video_path)
    if file_size == 0:
        return {"ok": False, "error": f"Video file is empty: {video_path}"}

    print(f"[AutoClip Upload] Starting upload: {os.path.basename(video_path)} ({file_size // 1024}KB)")

    # Resolve target account from creator routing table with STRICT ZERO CROSS-UPLOAD GUARANTEE
    from . import channel_routing
    target_account = account_id
    target_channel_name = None

    if not creator and not target_account:
        err_msg = "⛔ UPLOAD BLOCKED: No creator specified. Refusing to upload to prevent cross-channel contamination."
        print(f"[AutoClip Upload] {err_msg}")
        return {"ok": False, "error": err_msg}

    route = None
    if creator:
        try:
            route = channel_routing.get_route(creator)
            expected_acc = route["composio_account_id"]
            if target_account and target_account != expected_acc:
                err_msg = f"⛔ UPLOAD BLOCKED: Account '{target_account}' does not match route for '{creator}' ({expected_acc}). Refusing cross-upload."
                print(f"[AutoClip Upload] {err_msg}")
                return {"ok": False, "error": err_msg}
            target_account = expected_acc
            target_channel_name = f"{route['target_name']} ({route['channel_id']})"
            print(f"[AutoClip Route] Routing '{title}' -> {target_channel_name} via {target_account}")
        except Exception as re:
            err_msg = f"⛔ UPLOAD BLOCKED: No verified YouTube channel route for creator '{creator}': {re}. Refusing cross-upload."
            print(f"[AutoClip Route] {err_msg}")
            return {"ok": False, "error": err_msg}

    if not target_account:
        err_msg = f"⛔ UPLOAD BLOCKED: No destination channel account resolved for creator '{creator}'. Refusing cross-upload."
        print(f"[AutoClip Route] {err_msg}")
        return {"ok": False, "error": err_msg}

    filename = os.path.basename(video_path)
    clean_title = (title or "AutoClip Viral Short").strip()
    if "#shorts" not in clean_title.lower():
        clean_title += " #shorts"

    tags_list = tags or ["shorts", "viral", "trending", "funny"]
    if isinstance(tags_list, str):
        tags_list = [t.strip().lstrip("#") for t in tags_list.split(",") if t.strip()]

    desc_text = (description or f"{clean_title}\n\n#shorts #viral").strip()
    privacy_status = "private" if publish_at else (privacy or "public")
    creator_key = str(creator).strip().lower() if creator else "speed"

    # Check if automated Studio browser session is authenticated for this creator (UNLIMITED ZERO-QUOTA)
    try:
        from . import studio_uploader
        if studio_uploader.is_session_authenticated(creator_key):
            print(f"[AutoClip Upload] Found authenticated YouTube Studio session for '{creator_key}'. Using automated zero-quota browser uploader...")
            studio_res = studio_uploader.upload_short_via_studio(
                video_path=video_path,
                title=clean_title,
                description=desc_text,
                tags=tags_list,
                schedule_dt=publish_at,
                creator_key=creator_key,
                headless=True,
                thumbnail_path=thumbnail_path,
                pinned_comment=pinned_comment
            )
            if studio_res.get("ok"):
                if publish_at:
                    try:
                        from . import creators
                        creators.record_scheduled_slot(creator_key, publish_at)
                    except Exception as sce:
                        print(f"[AutoClip Route] Could not record scheduled slot: {sce}")
                try:
                    from . import excel_tracker
                    excel_tracker.log_upload(
                        creator=creator_key,
                        title=clean_title,
                        video_id=studio_res.get("video_id", ""),
                        url=studio_res.get("url", ""),
                        scheduled_slot=str(publish_at) if publish_at else "Immediate Peak",
                        notes=f"AutoClip Short for {creator_key.title()}"
                    )
                except Exception as ee:
                    print(f"[Excel Tracker] Note on upload log: {ee}")
                return studio_res
            print(f"[AutoClip Upload] Studio uploader note for '{creator_key}': {studio_res.get('error')}. Gracefully falling back to Composio YouTube API...")
        else:
            print(f"[AutoClip Upload] No authenticated YouTube Studio session for '{creator_key}'. Using Composio YouTube API...")
    except Exception as se:
        print(f"[AutoClip Upload] Studio uploader check note: {se}")

    # Step 1: Request presigned S3 upload URL
    print(f"[AutoClip Upload] Fetching presigned S3 URL...")
    upload_url, s3key = get_presigned_upload_url()
    if not upload_url or not s3key:
        from . import studio_uploader
        c_name = studio_uploader.CREATOR_CHANNELS.get(creator_key, {}).get("name", creator_key.title())
        return {"ok": False, "error": (
            f"⛔ YouTube Data API upload unavailable (Composio storage unreachable).\n\n"
            f"💡 **Recommended: Enable 100% Automated YouTube Studio Uploads (Zero Quota Limit)**\n"
            f"Run this one-time command in your terminal to log in to **{c_name}**:\n"
            f"```powershell\n"
            f"& \"C:\\Users\\swastik\\Desktop\\AutoClip\\.venv\\Scripts\\python.exe\" -m autoclip.studio_uploader --login {creator_key}\n"
            f"```\n"
            f"Once logged in, all uploads and scheduling are completely automated with NO limits!"
        ), "needs_login": True, "creator": creator_key}

    # Step 2: Stream video bytes directly to Cloudflare R2 / S3
    print(f"[AutoClip Upload] Uploading {file_size // 1024}KB to staging storage (s3key={s3key[:20]}...)...")
    try:
        # Stream upload in chunks to avoid memory blowup on large files
        def file_iter():
            with open(video_path, "rb") as f:
                while True:
                    chunk = f.read(4*1024*1024)
                    if not chunk:
                        break
                    yield chunk
        # Build request with chunked encoding
        put_req = urllib.request.Request(
            upload_url,
            data=file_iter(),
            headers={"Content-Type": "video/mp4", "Content-Length": str(file_size)},
            method="PUT"
        )
        with urllib.request.urlopen(put_req, timeout=120) as put_res:
            if put_res.status not in (200, 204):
                return {"ok": False, "error": f"Staging storage upload failed: HTTP {put_res.status}"}
        print(f"[AutoClip Upload] Staged to S3 successfully.")
    except Exception as e:
        return {"ok": False, "error": f"Staging storage upload failed: {e}"}

    # Step 3: Trigger YouTube Multipart Upload tool via Composio
    yt_args = {
        "title": clean_title,
        "description": desc_text,
        "tags": tags_list,
        "categoryId": "24",
        "privacyStatus": privacy_status,
        "videoFile": {
            "name": filename,
            "mimetype": "video/mp4",
            "s3key": s3key
        }
    }
    if publish_at:
        if hasattr(publish_at, "isoformat"):
            yt_args["publishAt"] = publish_at.isoformat()
        else:
            yt_args["publishAt"] = str(publish_at)

    tool_entry = {
        "tool_slug": "YOUTUBE_MULTIPART_UPLOAD_VIDEO",
        "arguments": yt_args
    }
    if target_account:
        tool_entry["account"] = target_account

    # Use longer timeout for YouTube upload (can take 2+ minutes)
    yt_res = _call_mcp("tools/call", {
        "name": "COMPOSIO_MULTI_EXECUTE_TOOL",
        "arguments": {
            "tools": [tool_entry]
        }
    }, timeout=300)

    content = yt_res.get("content", [])
    if not content:
        return {"ok": False, "error": "No response received from Composio MCP upload tool."}

    # Handle multiple content items - find the one with actual results
    txt = ""
    for item in content:
        item_text = item.get("text", "")
        if item_text and len(item_text) > len(txt):
            txt = item_text

    if not txt:
        return {"ok": False, "error": "Empty response from Composio MCP upload tool."}

    try:
        data_outer = json.loads(txt)
        data_inner = data_outer.get("data", {})
        results = data_inner.get("results", [])
        if results:
            first_res = results[0]
            resp_block = first_res.get("response", {})
            is_success = resp_block.get("successful", False)
            resp_data = resp_block.get("data", {})

            if is_success:
                vid_id = (
                    resp_data.get("id") or
                    (resp_data.get("video", {}) if isinstance(resp_data.get("video"), dict) else {}).get("id")
                )
                yt_url = f"https://www.youtube.com/watch?v={vid_id}" if vid_id else ""
                if publish_at:
                    try:
                        from . import creators
                        creators.record_scheduled_slot(creator_key, publish_at)
                    except Exception as sce:
                        print(f"[AutoClip Route] Could not record scheduled slot: {sce}")
                try:
                    from . import excel_tracker
                    excel_tracker.log_upload(
                        creator=creator_key,
                        title=clean_title,
                        video_id=vid_id or "",
                        url=yt_url,
                        scheduled_slot=str(publish_at) if publish_at else "Immediate Peak",
                        notes=f"AutoClip Short for {creator_key.title()}"
                    )
                except Exception as ee:
                    print(f"[Excel Tracker] Note on upload log: {ee}")
                return {
                    "ok": True,
                    "video_id": vid_id,
                    "url": yt_url,
                    "title": clean_title,
                    "privacy": privacy_status,
                    "response": resp_data
                }
            else:
                # Dig into all possible nested error locations
                err_msg = (
                    resp_block.get("error")
                    or (resp_data.get("error", {}).get("message") if isinstance(resp_data.get("error"), dict) else None)
                    or resp_data.get("message")
                    or resp_data.get("error")
                    or first_res.get("error")
                    or data_inner.get("error")
                )
                # Log full raw response for debugging
                raw_dump = json.dumps(first_res, indent=2)[:800]
                print(f"[Upload Debug] Full Composio response:\n{raw_dump}")

                if not err_msg or str(err_msg) in ("{}", "None", ""):
                    raw_lower = raw_dump.lower()
                    if "quotaexceeded" in raw_lower or "quota" in raw_lower or "403" in raw_lower or "429" in raw_lower:
                        err_msg = "YouTube API Quota Exceeded"
                    elif "401" in raw_lower or "unauthorized" in raw_lower:
                        err_msg = "YouTube API Authorization Error — OAuth token may have expired. Re-connect the account in Composio."
                    elif "400" in raw_lower or "invalid" in raw_lower:
                        err_msg = "YouTube API Bad Request — video metadata or format may be invalid."
                    else:
                        err_msg = f"Upload failed (no error detail returned). Debug: {raw_dump[:300]}"

                err_str = str(err_msg)
                if any(k in err_str.lower() for k in ["quota", "quotaexceeded", "ratelimit", "429", "rateLimitExceeded"]):
                    c_key = creator or "jynxzi"
                    err_clean = (
                        "⛔ YouTube API Quota Exceeded on shared Composio connection (~6 uploads/day limit reached).\n"
                        "🤖 **Hands-Free Automated Studio Uploader is now ready!**\n"
                        f"Run this one-time command in your terminal to authenticate '{c_key}':\n"
                        f"`python -m autoclip.studio_uploader --login {c_key}`\n"
                        "Once signed in, AutoClip will upload and schedule all future clips 100% hands-free in the background without any daily limits!"
                    )
                    return {"ok": False, "error": err_clean, "raw_error": err_str}

                return {"ok": False, "error": f"YouTube API Error: {err_str}"}

        # No results at all
        print(f"[Upload Debug] No results in response: {json.dumps(data_outer)[:600]}")
        error_msg = data_outer.get("error") or "Composio returned no results. The upload tool may have timed out."
        return {"ok": False, "error": error_msg}
    except Exception as e:
        return {"ok": False, "error": f"Failed parsing upload response: {e}\n{txt[:500]}"}


