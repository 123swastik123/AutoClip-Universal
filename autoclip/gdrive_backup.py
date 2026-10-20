"""Automated Cloud Backup & Archiving to Google Drive (Mayur Desai account).

Backs up final rendered Shorts and thumbnails to Google Drive folder 'AutoClip_Master_Archive'
and purges bulky source downloads to free up local PC disk space.
"""

import os
import sys
import json
import urllib.request
from pathlib import Path
from typing import Dict, Any, Optional

PROJECT_ROOT = Path(r"C:\Users\swastik\Desktop\AutoClip")
ARCHIVE_FOLDER_ID = "1GV5cGIsLqAUPEPe4JRSNCsfKhu7U8nxD"  # AutoClip_Master_Archive in swastiksachit@gmail.com
GDRIVE_ACCOUNT_ID = "googledrive_lohan-anigh"             # swastiksachit@gmail.com (5 TB Account)

def backup_short_to_gdrive(
    video_path: str,
    thumbnail_path: Optional[str] = None,
    folder_id: str = ARCHIVE_FOLDER_ID,
    account_id: str = GDRIVE_ACCOUNT_ID
) -> Dict[str, Any]:
    """Upload rendered short mp4 and thumbnail jpg to Google Drive archive."""
    from . import composio_client

    results = {"video_uploaded": False, "thumb_uploaded": False, "files": []}

    # Helper to stage and upload one file
    def upload_one(file_path: str, mimetype: str) -> Optional[Dict[str, Any]]:
        if not file_path or not os.path.exists(file_path):
            return None
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            return None

        fname = os.path.basename(file_path)
        print(f"[GDrive Archive] Staging '{fname}' ({file_size // 1024}KB)...")

        # Step 1: Request presigned S3 upload URL
        upload_url, s3key = composio_client.get_presigned_upload_url()
        if not upload_url or not s3key:
            print(f"[GDrive Archive] Could not get presigned upload URL")
            return None

        # Step 2: Stream bytes to staging storage
        try:
            with open(file_path, "rb") as f:
                data = f.read()
            req = urllib.request.Request(
                upload_url,
                data=data,
                headers={"Content-Type": mimetype, "Content-Length": str(len(data))},
                method="PUT"
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                if resp.status not in (200, 204):
                    print(f"[GDrive Archive] Staging upload failed: HTTP {resp.status}")
                    return None
        except Exception as e:
            print(f"[GDrive Archive] Staging upload failed: {e}")
            return None

        # Step 3: Call Composio Google Drive tool
        tool_slug = "GOOGLEDRIVE_RESUMABLE_UPLOAD" if file_size > 5 * 1024 * 1024 else "GOOGLEDRIVE_UPLOAD_FILE"
        tool_args = {
            "folder_to_upload_to": folder_id,
            "file_to_upload": {
                "name": fname,
                "mimetype": mimetype,
                "s3key": s3key
            }
        }
        try:
            mcp_res = composio_client.execute_tool(tool_slug, tool_args, account=account_id)
            print(f"[GDrive Archive] Upload result for '{fname}': {str(mcp_res)[:200]}")
            return mcp_res
        except Exception as te:
            print(f"[GDrive Archive] GDrive tool call error: {te}")
            return None

    # Upload video
    if video_path and os.path.exists(video_path):
        v_res = upload_one(video_path, "video/mp4")
        if v_res:
            results["video_uploaded"] = True
            results["files"].append(os.path.basename(video_path))

    # Upload thumbnail
    if thumbnail_path and os.path.exists(thumbnail_path):
        t_res = upload_one(thumbnail_path, "image/jpeg")
        if t_res:
            results["thumb_uploaded"] = True
            results["files"].append(os.path.basename(thumbnail_path))

    return results

def purge_raw_source_video(video_id: str) -> int:
    """Purge heavy raw source .mp4 and .wav files from local disk to reclaim space."""
    downloads_dir = PROJECT_ROOT / "data" / "downloads"
    freed_bytes = 0
    if not downloads_dir.exists() or not video_id:
        return 0

    patterns = [f"{video_id}_source*.mp4", f"{video_id}*.wav"]
    for pat in patterns:
        for f in downloads_dir.glob(pat):
            try:
                sz = f.stat().st_size
                f.unlink(missing_ok=True)
                freed_bytes += sz
                print(f"[Disk Cleanup] Purged '{f.name}' ({sz // (1024*1024)}MB freed)")
            except Exception as e:
                print(f"[Disk Cleanup] Note on {f.name}: {e}")

    return freed_bytes
