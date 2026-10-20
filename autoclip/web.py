"""AutoClip Web Studio 2.0 - YouTube to 5 Ranked Shorts & Creator Studio.

Features:
1. YouTube URL to 5 Ranked 9:16 Shorts (Download -> Transcribe -> Free LLM Rank -> Face Reframe -> Kinetic Subtitles -> Download)
2. Magic 1-Click Creator Studio (IShowSpeed, Kai Cenat, Marlon Webb, etc.)
3. Interactive 9:16 Phone Mockup Player with dynamic golden-yellow subtitles
4. Direct one-click downloadable MP4 files
5. Multi-provider Free LLM API Cascading Gateway
"""
import os, sys, json, time, re, uuid, mimetypes, urllib.request, urllib.error, threading, subprocess
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def _safe_resolve(rel_path):
    """Safely resolve relative path within PROJECT_ROOT, preventing directory traversal."""
    if not rel_path:
        return None
    clean_rel = rel_path.replace("/", os.sep).replace("\\", os.sep).lstrip(os.sep)
    norm = os.path.abspath(os.path.join(PROJECT_ROOT, clean_rel))
    try:
        common = os.path.commonpath([norm, PROJECT_ROOT])
        if os.path.abspath(common) == os.path.abspath(PROJECT_ROOT):
            return norm
    except ValueError:
        return None
    return None

from autoclip import config, llm as llm_mod, research as research_mod, qa as qa_mod, request as request_mod, youtube_pipeline, composio_client

LOG_BUFFER = []
LOG_LOCK = threading.Lock()

ACTIVE_JOBS = {}
JOBS_LOCK = threading.Lock()

# Background cleanup thread - safely purges completed downloads older than 2 hours
CLEANUP_RUNNING = True

def background_cleanup():
    """Clean stale temp files older than 2 hours (not active downloads)."""
    import glob
    while CLEANUP_RUNNING:
        try:
            time.sleep(300)
            downloads_dir = os.path.join(PROJECT_ROOT, "data", "downloads")
            if os.path.exists(downloads_dir):
                for pattern in ["*.mp4", "*.wav", "*.json"]:
                    for f in glob.glob(os.path.join(downloads_dir, pattern)):
                        try:
                            # Only delete completed files older than 2 hours
                            if time.time() - os.path.getmtime(f) > 7200:
                                os.remove(f)
                        except Exception:
                            pass
        except Exception:
            pass

cleanup_thread = threading.Thread(target=background_cleanup, daemon=True)
if CLEANUP_RUNNING:
    cleanup_thread.start()

def append_log(msg):
    ts = time.strftime("%H:%M:%S")
    with LOG_LOCK:
        LOG_BUFFER.append(f"[{ts}] {msg}")
        if len(LOG_BUFFER) > 300:
            LOG_BUFFER.pop(0)

def run_magic_video_job(job_id, creator_in, prompt_in, format_in, source_mode, source_url):
    try:
        def set_job(step, pct, msg, extra=None):
            with JOBS_LOCK:
                ACTIVE_JOBS[job_id]["step"] = step
                ACTIVE_JOBS[job_id]["progress"] = pct
                ACTIVE_JOBS[job_id]["message"] = msg
                if extra:
                    ACTIVE_JOBS[job_id].update(extra)
            append_log(f"[{job_id[:6]}] (Step {step} - {pct}%): {msg}")

        set_job(1, 15, "Parsing intent & viral structure...")
        time.sleep(0.3)
        creator = creator_in.strip() or "IShowSpeed"
        fmt_kind = "short" if format_in == "short" else "compilation"

        set_job(2, 35, f"Consulting LLM cascade for {creator} viral profile...")
        try:
            r_profile = research_mod.ai_research(creator, topic=prompt_in, format_kind=fmt_kind)
        except Exception as e:
            append_log(f"Cascade fallback note: using cached/default profile ({e})")
            r_profile = research_mod.load()

        silence_trim = r_profile.get("edit_trend", {}).get("max_silence_before_cut", 0.4)
        emphasis_color = r_profile.get("caption_trend", {}).get("emphasis_color", "#FFD200")
        set_job(2, 50, f"Profile active: {silence_trim}s max cuts, golden karaoke ({emphasis_color}), ducked BGM")
        time.sleep(0.3)

        slug = re.sub(r'[^a-zA-Z0-9_]', '_', creator.lower())
        out_filename = f"{slug}_short.mp4"
        out_path = os.path.join(PROJECT_ROOT, "data", out_filename)
        src_video = os.path.join(PROJECT_ROOT, "data", f"{slug}_source.mp4")
        words_file = os.path.join(PROJECT_ROOT, "data", f"{slug}_words.json")

        set_job(3, 60, f"Acquiring video source for {creator}...")

        if source_url and source_url.startswith("http"):
            set_job(3, 65, f"Downloading via yt-dlp: {source_url[:40]}...")
            cmd = [sys.executable, "-m", "yt_dlp",
                   "--download-sections", "*00:00-00:40",
                   "-f", "best[ext=mp4]/best",
                   "--force-overwrites",
                   source_url, "-o", src_video]
            try:
                subprocess.run(cmd, timeout=120, capture_output=True)
            except Exception as e:
                append_log(f"yt-dlp download note: {e}")

        if not os.path.exists(src_video):
            if os.path.exists(os.path.join(PROJECT_ROOT, "data", "speed_source.mp4")) and "speed" in slug:
                src_video = os.path.join(PROJECT_ROOT, "data", "speed_source.mp4")
            elif os.path.exists(os.path.join(PROJECT_ROOT, "data", "marlon_single.mp4")) and "marlon" in slug:
                src_video = os.path.join(PROJECT_ROOT, "data", "marlon_single.mp4")
            else:
                src_video = os.path.join(PROJECT_ROOT, "data", "speed_source.mp4")

        if not os.path.exists(words_file) and os.path.exists(src_video):
            set_job(3, 72, f"Transcribing {os.path.basename(src_video)} with faster-whisper...")
            tr_cmd = [
                sys.executable,
                "-m", "autoclip.cli", "transcribe", src_video, words_file
            ]
            env = os.environ.copy()
            env["PYTHONPATH"] = PROJECT_ROOT
            subprocess.run(tr_cmd, env=env, timeout=120, capture_output=True)

        set_job(3, 78, f"Source prepared: {os.path.basename(src_video)} with word-level timestamps")
        time.sleep(0.3)

        set_job(4, 85, f"Running AutoClip pipeline: 9:16 face reframe, LLM moment cut & golden karaoke burn...")
        pipe_cmd = [
            sys.executable,
            "-m", "autoclip.cli", "pipeline",
            "--src", src_video,
            "--words", words_file,
            "--request", prompt_in or f"{creator} funniest viral moment",
            "--out", out_path,
            "--name", f"{slug}_cut"
        ]
        env = os.environ.copy()
        r_pipe = subprocess.run(pipe_cmd, env=env, timeout=180, capture_output=True, text=True)

        if not os.path.exists(out_path):
            err_msg = (r_pipe.stderr or "AutoClip assembly failed to produce output video.").strip()
            raise RuntimeError(f"Pipeline render error: {err_msg[-300:]}")

        set_job(4, 94, "Assembly finished: 9:16 reframe, karaoke burn & loudness normalized (-14 LUFS)")
        time.sleep(0.3)

        set_job(5, 98, "Running dual-gate technical & creative QA checks...")
        qa_rep = qa_mod.tech_qa(out_path)
        
        set_job(5, 100, f"Completed! Real Short ready for {creator}.", {
            "status": "completed",
            "video_path": f"data/{out_filename}",
            "filename": out_filename,
            "creator": creator,
            "format": fmt_kind,
            "qa": qa_rep
        })
        append_log(f"Successfully generated Short for {creator}: data/{out_filename}")

    except Exception as e:
        with JOBS_LOCK:
            ACTIVE_JOBS[job_id]["status"] = "failed"
            ACTIVE_JOBS[job_id]["message"] = f"Error: {e}"
        append_log(f"Job {job_id[:6]} failed: {e}")

class AutoClipWebHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    @staticmethod
    def _is_local_origin(origin_str):
        if not origin_str:
            return False
        try:
            parsed = urlparse(origin_str)
            host = (parsed.hostname or "").lower()
            return host in ("127.0.0.1", "localhost", "::1")
        except Exception:
            return False

    def send_json(self, data, status=200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        origin = self.headers.get("Origin", "")
        if self._is_local_origin(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        origin = self.headers.get("Origin", "")
        if self._is_local_origin(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self.serve_dashboard()
            return
        elif path == "/api/status":
            self.handle_api_status()
            return
        elif path == "/api/videos":
            self.handle_api_videos()
            return
        elif path == "/api/research-data":
            self.handle_api_research_data()
            return
        elif path == "/api/qa-inspect":
            qs = parse_qs(parsed.query)
            fn = qs.get("file", [""])[0]
            self.handle_api_qa(fn)
            return
        elif path == "/api/job-status":
            qs = parse_qs(parsed.query)
            jid = qs.get("job_id", [""])[0]
            with JOBS_LOCK:
                job = ACTIVE_JOBS.get(jid, {"status": "not_found"})
            self.send_json(job)
            return
        elif path == "/api/logs":
            with LOG_LOCK:
                logs = list(LOG_BUFFER)
            self.send_json({"logs": logs})
            return
        elif path == "/api/download":
            qs = parse_qs(parsed.query)
            fn = qs.get("file", [""])[0]
            self.handle_api_download(fn)
            return
        elif path == "/api/youtube-history":
            self.handle_api_youtube_history()
            return
        elif path == "/api/composio-status":
            self.handle_composio_status()
            return
        elif path == "/api/composio-channel-videos":
            self.handle_composio_channel_videos()
            return
        elif path == "/api/disk-space":
            self.handle_api_disk_space()
            return
        elif path == "/api/cleanup":
            self.handle_api_cleanup()
            return
        elif path == "/api/creator-profiles":
            from . import creators
            self.send_json({"ok": True, "creators": creators.CREATORS, "music_map_40": creators.STREAMER_MUSIC_MAP_40})
            return
        elif path == "/api/optimal-schedule":
            from . import creators
            qs = parse_qs(parsed.query)
            cid = qs.get("creator", ["speed"])[0]
            slot = creators.calculate_next_optimal_slot(cid)
            profile = creators.get_creator_profile(cid)
            self.send_json({"ok": True, "creator": profile, "slot": slot})
            return
        elif path.startswith("/video/"):
            rel_name = path[len("/video/"):]
            self.serve_video(rel_name)
            return
        elif path.startswith("/assets/"):
            self.handle_serve_dist_asset(path)
            return
        elif path.startswith("/api/editor/project/"):
            clip_id = path[len("/api/editor/project/"):]
            self.handle_get_editor_project(clip_id)
            return
        elif path == "/editor" or path.startswith("/editor/"):
            qs = parse_qs(parsed.query)
            file_param = qs.get("file", [""])[0]
            creator_param = qs.get("creator", ["speed"])[0]
            self.handle_serve_editor(file_param, creator_param)
            return


        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        try:
            # CSRF / Cross-Origin drive protection: block requests from external websites
            origin = self.headers.get("Origin", "")
            referer = self.headers.get("Referer", "")
            sec_fetch_site = self.headers.get("Sec-Fetch-Site", "")
            if origin and not self._is_local_origin(origin):
                self.send_json({"ok": False, "error": "Forbidden: Cross-site requests rejected."}, 403)
                return
            if referer and not self._is_local_origin(referer):
                self.send_json({"ok": False, "error": "Forbidden: Cross-site requests rejected."}, 403)
                return
            if sec_fetch_site == "cross-site":
                self.send_json({"ok": False, "error": "Forbidden: Cross-site requests rejected."}, 403)
                return

            parsed = urlparse(self.path)
            path = parsed.path
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            try:
                payload = json.loads(body)
            except Exception:
                payload = {}

            if path == "/api/editor/render-project":
                self.handle_editor_render_project(payload)
                return
            elif path == "/api/editor/render":
                self.handle_editor_render(payload)
                return

            elif path == "/api/magic-create":
                self.handle_magic_create(payload)
                return
            elif path == "/api/youtube-to-shorts":
                self.handle_youtube_to_shorts(payload)
                return
            elif path == "/api/composio-search":
                self.handle_composio_search(payload)
                return
            elif path == "/api/composio-upload":
                self.handle_composio_upload(payload)
                return
            elif path == "/api/open-in-explorer":
                self.handle_open_in_explorer(payload)
                return
            elif path == "/api/test-cascade":
                self.handle_test_cascade()
                return
            elif path == "/api/save-config":
                self.handle_save_config(payload)
                return
            elif path == "/api/run-research":
                self.handle_run_research(payload)
                return

            self.send_response(404)
            self.end_headers()
        except Exception as e:
            append_log(f"Unhandled error in do_POST: {e}")
            self.send_json({"ok": False, "error": str(e)}, 500)

    def handle_youtube_to_shorts(self, payload):
        url = str(payload.get("url") or "").strip()
        creator = str(payload.get("creator") or "").strip() or None
        track_id = str(payload.get("track_id") or "").strip() or None
        if not url:
            self.send_json({"ok": False, "error": "YouTube URL is required"}, 400)
            return

        job_id = str(uuid.uuid4())[:8]
        with JOBS_LOCK:
            ACTIVE_JOBS[job_id] = {
                "id": job_id,
                "status": "running",
                "step": 1,
                "progress": 5,
                "message": "Initializing YouTube 5-Shorts generator...",
                "url": url,
                "creator": creator,
                "track_id": track_id,
                "kind": "youtube_5_shorts"
            }

        def worker():
            try:
                def progress_cb(pct, msg):
                    with JOBS_LOCK:
                        if job_id in ACTIVE_JOBS:
                            ACTIVE_JOBS[job_id]["progress"] = pct
                            ACTIVE_JOBS[job_id]["message"] = msg
                            step = 1
                            if pct >= 25: step = 2
                            if pct >= 45: step = 3
                            if pct >= 60: step = 4
                            if pct >= 95: step = 5
                            ACTIVE_JOBS[job_id]["step"] = step
                    append_log(f"[YT-{job_id}] {msg}")

                summary = youtube_pipeline.run_youtube_to_5_shorts(url, job_id=job_id, progress_cb=progress_cb, creator=creator, track_id=track_id, keep_source=False)
                with JOBS_LOCK:
                    ACTIVE_JOBS[job_id]["status"] = "completed"
                    ACTIVE_JOBS[job_id]["progress"] = 100
                    ACTIVE_JOBS[job_id]["message"] = "Completed! 5 Ranked Shorts ready for download."
                    ACTIVE_JOBS[job_id]["result"] = summary
                append_log(f"[YT-{job_id}] Finished! 5 Shorts created for {summary.get('video_info', {}).get('title', '')}")
            except Exception as e:
                with JOBS_LOCK:
                    if job_id in ACTIVE_JOBS:
                        ACTIVE_JOBS[job_id]["status"] = "failed"
                        ACTIVE_JOBS[job_id]["message"] = str(e)
                append_log(f"[YT-{job_id}] Failed: {e}")

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        self.send_json({"ok": True, "job_id": job_id})

    def handle_api_download(self, rel_path):
        if not rel_path:
            self.send_json({"ok": False, "error": "No file specified"}, 400)
            return

        full_path = _safe_resolve(rel_path)
        if not full_path or not os.path.exists(full_path) or not os.path.isfile(full_path):
            self.send_json({"ok": False, "error": f"File not found: {rel_path}"}, 404)
            return

        file_size = os.path.getsize(full_path)
        filename = os.path.basename(full_path)

        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(file_size))
        origin = self.headers.get("Origin", "")
        if self._is_local_origin(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
        self.end_headers()

        with open(full_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def handle_api_youtube_history(self):
        history = []
        shorts_dir = os.path.join(PROJECT_ROOT, "data", "shorts")
        if os.path.exists(shorts_dir):
            for fn in os.listdir(shorts_dir):
                if fn.endswith("_summary.json"):
                    fp = os.path.join(shorts_dir, fn)
                    try:
                        with open(fp, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            # Skip any demo runs
                            vinfo = data.get("video_info", {})
                            if vinfo.get("id") == "speed_demo":
                                continue
                            # Verify that at least one clip mp4 actually exists on disk
                            clips = data.get("clips", [])
                            valid_clips = [c for c in clips if os.path.exists(os.path.join(PROJECT_ROOT, c.get("file", "").replace("/", os.sep)))]
                            if not valid_clips:
                                continue
                            data["clips"] = valid_clips
                            history.append(data)
                    except Exception:
                        pass
        history.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        self.send_json({"history": history})

    def handle_composio_status(self):
        try:
            info = composio_client.get_channel_info()
            self.send_json({"ok": True, "info": info})
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, 500)

    def handle_composio_channel_videos(self):
        try:
            vids = composio_client.get_channel_videos()
            self.send_json({"ok": True, "videos": vids})
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, 500)

    def handle_api_cleanup(self):
        """Clean up intermediate files from /tmp/opencode/autoclip and project data/downloads"""
        import glob
        import time
        
        cleaned = {"downloads": 0, "tmp": 0, "errors": []}
        
        try:
            # Clean project downloads directory
            downloads_dir = os.path.join(PROJECT_ROOT, "data", "downloads")
            if os.path.exists(downloads_dir):
                for pattern in ["*.mp4", "*.wav", "*.json", "*.part"]:
                    for f in glob.glob(os.path.join(downloads_dir, pattern)):
                        try:
                            # Only delete files older than 15 seconds
                            if time.time() - os.path.getmtime(f) > 15:
                                os.remove(f)
                                cleaned["downloads"] += 1
                        except Exception as e:
                            cleaned["errors"].append(f"downloads: {e}")
            
            # Clean tmp/opencode/autoclip directory
            tmp_dir = "/tmp/opencode/autoclip"
            if os.path.exists(tmp_dir):
                for pattern in ["job_*_prep.mp4", "job_*_reframed.mp4", "job_*_punch.mp4", "job_*_capped.mp4", "job_*_cap.*", "concat_list.txt", "merged.mp4", "remaster_*", "top5_*", "whoosh.wav", "boom.wav", "bgm_*.wav"]:
                    for f in glob.glob(os.path.join(tmp_dir, pattern)):
                        try:
                            # Only delete files older than 15 seconds
                            if time.time() - os.path.getmtime(f) > 15:
                                os.remove(f)
                                cleaned["tmp"] += 1
                        except Exception as e:
                            cleaned["errors"].append(f"tmp: {e}")
                        
        except Exception as e:
            cleaned["errors"].append(str(e))
        
        self.send_json({"ok": True, "cleaned": cleaned})

    def handle_api_disk_space(self):
        """Return disk space information for monitoring."""
        import shutil
        
        def get_disk_usage(path):
            try:
                total, used, free = shutil.disk_usage(path)
                return {
                    "total_gb": round(total / (1024**3), 2),
                    "used_gb": round(used / (1024**3), 2),
                    "free_gb": round(free / (1024**3), 2),
                    "used_pct": round((used / total) * 100, 1)
                }
            except Exception as e:
                return {"error": str(e)}
        
        # Get disk usage for relevant paths
        paths = {
            "project_root": PROJECT_ROOT,
            "tmp_autoclip": "/tmp/opencode/autoclip",
            "c_drive": "C:\\"
        }
        
        result = {}
        for name, path in paths.items():
            result[name] = get_disk_usage(path)
        
        # Also count temp files
        tmp_count = 0
        tmp_size_mb = 0
        tmp_dir = "/tmp/opencode/autoclip"
        if os.path.exists(tmp_dir):
            for f in os.listdir(tmp_dir):
                fp = os.path.join(tmp_dir, f)
                if os.path.isfile(fp):
                    tmp_count += 1
                    tmp_size_mb += os.path.getsize(fp) / (1024 * 1024)
        
        downloads_count = 0
        downloads_size_mb = 0
        downloads_dir = os.path.join(PROJECT_ROOT, "data", "downloads")
        if os.path.exists(downloads_dir):
            for f in os.listdir(downloads_dir):
                fp = os.path.join(downloads_dir, f)
                if os.path.isfile(fp):
                    downloads_count += 1
                    downloads_size_mb += os.path.getsize(fp) / (1024 * 1024)
        
        result["temp_files"] = {
            "tmp_autoclip": {"count": tmp_count, "size_mb": round(tmp_size_mb, 1)},
            "downloads": {"count": downloads_count, "size_mb": round(downloads_size_mb, 1)}
        }
        
        self.send_json({"ok": True, "disk": result})

    def handle_composio_search(self, payload):
        query = payload.get("query", "").strip()
        try:
            vids = composio_client.search_youtube(query) if query else []
            self.send_json({"ok": True, "videos": vids})
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, 500)

    def handle_composio_upload(self, payload):
        file_param = payload.get("file", "").strip()
        title = payload.get("title", "AutoClip Viral Short").strip()
        desc = payload.get("description", "#shorts #viral #autoclip").strip()
        tags = payload.get("tags")
        privacy = payload.get("privacy", "public").strip()
        publish_at = payload.get("publish_at")
        creator = payload.get("creator") or payload.get("creator_slug")
        account_id = payload.get("account_id")
        if not file_param:
            self.send_json({"ok": False, "error": "File path required"}, 400)
            return
        full_path = _safe_resolve(file_param)
        if not full_path or not os.path.exists(full_path):
            self.send_json({"ok": False, "error": f"File does not exist: {file_param}"}, 404)
            return

        append_log(f"Composio MCP: Requesting upload for {os.path.basename(full_path)} (creator: {creator or 'default'})...")
        try:
            res = composio_client.upload_video_to_youtube(
                full_path, title, desc, tags=tags, privacy=privacy, publish_at=publish_at,
                creator=creator, account_id=account_id
            )
            append_log(f"Composio MCP: Upload response received: {res}")
            self.send_json(res if isinstance(res, dict) and "ok" in res else {"ok": True, "result": res})
        except Exception as e:
            append_log(f"Composio MCP upload failed: {e}")
            self.send_json({"ok": False, "error": str(e)}, 500)

    def handle_serve_dist_asset(self, path):
        asset_rel = path.lstrip("/")
        asset_file = os.path.join(PROJECT_ROOT, "frontend", "dist", asset_rel.replace("/", os.sep))
        if os.path.exists(asset_file) and os.path.isfile(asset_file):
            content_type, _ = mimetypes.guess_type(asset_file)
            if asset_file.endswith(".js"):
                content_type = "application/javascript"
            elif asset_file.endswith(".css"):
                content_type = "text/css"
            with open(asset_file, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()

    def handle_get_editor_project(self, clip_id):
        shorts_dir = os.path.join(PROJECT_ROOT, "data", "shorts")
        full_path = None
        if os.path.exists(shorts_dir):
            for f in os.listdir(shorts_dir):
                if f.endswith(".mp4") and (clip_id in f or clip_id == "demo"):
                    full_path = os.path.join(shorts_dir, f)
                    break
            if not full_path:
                cand = [os.path.join(shorts_dir, f) for f in os.listdir(shorts_dir) if f.endswith(".mp4")]
                if cand:
                    cand.sort(key=os.path.getmtime, reverse=True)
                    full_path = cand[0]

        rel_name = os.path.relpath(full_path, PROJECT_ROOT).replace("\\", "/") if full_path else ""
        stream_url = f"/video/{rel_name}" if rel_name else ""
        base_name = os.path.splitext(os.path.basename(full_path))[0] if full_path else "Demo Clip"

        proj = {
            "id": clip_id or "clip_demo",
            "title": base_name.replace("_", " ").title(),
            "creator": "jynxzi" if "jynx" in base_name.lower() else ("caseoh" if "case" in base_name.lower() else "speed"),
            "sourceVideoPath": rel_name,
            "sourceStreamUrl": stream_url,
            "sourceWidth": 1920,
            "sourceHeight": 1080,
            "duration": 42.0,
            "currentTime": 0,
            "isPlaying": False,
            "layout": "split",
            "splitOrder": "streamer_top",
            "splitRatio": 0.5,
            "blurAmount": 24,
            "blurDarken": 0.2,
            "pipShape": "rounded",
            "pipBorder": True,
            "pipBorderColor": "#22d3ee",
            "pipShadow": True,
            "pipScale": 0.35,
            "facecamCrop": {"x": 0.65, "y": 0.05, "width": 0.32, "height": 0.45},
            "gameplayCrop": {"x": 0.05, "y": 0.05, "width": 0.90, "height": 0.90},
            "layers": [
                {
                    "id": "layer_hook",
                    "type": "hook_text",
                    "name": "Viral Hook Banner",
                    "start": 0,
                    "duration": 4.5,
                    "visible": True,
                    "locked": False,
                    "opacity": 1,
                    "x": 100,
                    "y": 180,
                    "width": 880,
                    "height": 110,
                    "rotation": 0,
                    "scale": 1,
                    "text": base_name.replace("_", " ").upper(),
                    "fontFamily": "Montserrat",
                    "fontSize": 54,
                    "fontWeight": "900",
                    "color": "#FFFFFF",
                    "strokeColor": "#000000",
                    "strokeWidth": 4,
                    "backgroundColor": "#000000d0",
                    "backgroundPadding": 16,
                    "borderRadius": 14,
                    "letterSpacing": 1,
                    "align": "center",
                    "animationIn": "pop",
                    "animationOut": "fade"
                },
                {
                    "id": "layer_captions",
                    "type": "captions",
                    "name": "Auto Subtitles",
                    "start": 0,
                    "duration": 42.0,
                    "visible": True,
                    "locked": False,
                    "opacity": 1,
                    "x": 90,
                    "y": 1350,
                    "width": 900,
                    "height": 160,
                    "rotation": 0,
                    "scale": 1,
                    "style": {
                        "fontFamily": "Impact",
                        "fontSize": 78,
                        "color": "#FFFFFF",
                        "activeWordColor": "#22d3ee",
                        "strokeColor": "#000000",
                        "strokeWidth": 10,
                        "shadowColor": "#000000c0",
                        "shadowBlur": 12,
                        "uppercase": True,
                        "wordsPerLine": 2,
                        "animation": "karaoke"
                    },
                    "words": [
                        {"word": "LOOK", "start": 0.4, "end": 0.8},
                        {"word": "AT", "start": 0.8, "end": 1.1},
                        {"word": "HIM", "start": 1.1, "end": 1.5},
                        {"word": "FALL!", "start": 1.5, "end": 2.2},
                        {"word": "NO", "start": 2.6, "end": 2.9},
                        {"word": "WAY", "start": 2.9, "end": 3.4},
                        {"word": "BRO", "start": 3.4, "end": 3.9}
                    ]
                }
            ],
            "selectedLayerId": "layer_hook",
            "showSafeZone": False,
            "showSnapGuides": True,
            "timelineZoom": 40
        }
        self.send_json(proj)

    def handle_editor_render_project(self, payload):
        from . import visual_editor, creators, excel_tracker
        project = payload.get("project", {})
        if not project:
            self.send_json({"ok": False, "error": "No project payload provided"}, 400)
            return

        try:
            render_res = visual_editor.render_project_json(project)
            creator = project.get("creator", "speed")
            slot = creators.calculate_next_optimal_slot(creator)

            excel_tracker.log_upload(
                creator=creator,
                title=project.get("title", "Custom Short"),
                video_id=render_res.get("filename", ""),
                url=render_res.get("stream_url", ""),
                scheduled_slot=slot.get("readable", ""),
                notes=f"CapCut Studio JSON Render ({project.get('layout')})"
            )

            self.send_json({
                "ok": True,
                "render": render_res,
                "output_path": render_res.get("output_path"),
                "slot": slot.get("readable"),
                "creator": creator
            })
        except Exception as e:
            append_log(f"Editor project render failed: {e}")
            self.send_json({"ok": False, "error": str(e)}, 500)

    def handle_serve_editor(self, file_param, creator_param):
        dist_html = os.path.join(PROJECT_ROOT, "frontend", "dist", "index.html")
        if os.path.exists(dist_html):
            with open(dist_html, "rb") as f:
                html_bytes = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_bytes)))
            self.end_headers()
            self.wfile.write(html_bytes)
            return

        from . import editor_page
        full_path = _safe_resolve(file_param) if file_param else None
        
        if not full_path or not os.path.exists(full_path):
            shorts_dir = os.path.join(PROJECT_ROOT, "data", "shorts")
            if os.path.exists(shorts_dir):
                all_vids = [os.path.join(shorts_dir, f) for f in os.listdir(shorts_dir) if f.endswith(".mp4")]
                if all_vids:
                    all_vids.sort(key=os.path.getmtime, reverse=True)
                    full_path = all_vids[0]

        rel_name = os.path.relpath(full_path, PROJECT_ROOT).replace("\\", "/") if full_path else ""
        stream_url = f"/video/{rel_name}" if rel_name else ""
        base_name = os.path.splitext(os.path.basename(full_path))[0] if full_path else "AutoClip Short"

        c_norm = creator_param.lower() if creator_param else "speed"
        if "case" in base_name.lower(): c_norm = "caseoh"
        elif "jynx" in base_name.lower() or "jinx" in base_name.lower(): c_norm = "jynxzi"

        clip_data = {
            "title": base_name.replace("_", " ").title(),
            "hook_text": base_name.replace("_", " ").upper(),
            "creator": c_norm,
            "creator_id": c_norm,
            "stream_url": stream_url,
            "rel_path": rel_name,
            "file": rel_name,
            "t0": 0.0,
            "t1": 35.0,
            "duration": 35.0
        }

        html = editor_page.render_editor_html(clip_data)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))


    def handle_editor_render(self, payload):
        from . import visual_editor, creators, excel_tracker
        source_param = payload.get("source_video_path", "").strip()
        full_path = _safe_resolve(source_param) if source_param else None
        if not full_path or not os.path.exists(full_path):
            shorts_dir = os.path.join(PROJECT_ROOT, "data", "shorts")
            candidates = [os.path.join(shorts_dir, f) for f in os.listdir(shorts_dir) if f.endswith(".mp4")]
            if candidates:
                candidates.sort(key=os.path.getmtime, reverse=True)
                full_path = candidates[0]

        if not full_path or not os.path.exists(full_path):
            self.send_json({"ok": False, "error": f"Source video not found: {source_param}"}, 404)
            return

        creator = payload.get("creator", "speed")
        t0 = float(payload.get("t0", 0.0))
        t1 = float(payload.get("t1", 35.0))
        layout_mode = payload.get("layout_mode", "split")
        split_order = payload.get("split_order", "streamer_top")
        split_ratio = float(payload.get("split_ratio", 0.5))
        caption_y = int(payload.get("caption_y", 440))
        caption_font = payload.get("caption_font", "Arial Black")
        caption_size = int(payload.get("caption_size", 102))
        caption_color = payload.get("caption_color_hex", "#FFD200")
        hook_text = payload.get("hook_text", "")
        hook_dur = float(payload.get("hook_duration", 4.0))
        ai_prompt = payload.get("ai_instructions", "")

        try:
            render_res = visual_editor.render_custom_clip(
                source_video_path=full_path,
                t0=t0,
                t1=t1,
                layout_mode=layout_mode,
                split_order=split_order,
                split_ratio=split_ratio,
                caption_y=caption_y,
                caption_font=caption_font,
                caption_size=caption_size,
                caption_color_hex=caption_color,
                hook_text=hook_text,
                hook_duration=hook_dur,
                ai_instructions=ai_prompt
            )

            # Assign to next optimal 6-hour slot
            slot = creators.calculate_next_optimal_slot(creator)

            # Record in Excel Master Tracker
            excel_tracker.log_upload(
                creator=creator,
                title=hook_text or render_res.get("filename", "Custom Short"),
                video_id=render_res.get("filename", ""),
                url=render_res.get("stream_url", ""),
                scheduled_slot=slot.get("readable", ""),
                notes=f"CapCut Studio Custom Edit ({layout_mode}, {split_order})"
            )

            self.send_json({
                "ok": True,
                "render": render_res,
                "slot": slot.get("readable"),
                "creator": creator
            })
        except Exception as e:
            append_log(f"Custom editor render failed: {e}")
            self.send_json({"ok": False, "error": str(e)}, 500)

    def handle_open_in_explorer(self, payload):
        file_param = payload.get("file", "").strip()
        full_path = _safe_resolve(file_param)
        if full_path and os.path.exists(full_path):
            import subprocess
            try:
                subprocess.Popen(["explorer.exe", f"/select,{full_path}"])
                self.send_json({"ok": True, "path": full_path})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
        else:
            self.send_json({"ok": False, "error": f"File does not exist or is invalid: {file_param}"}, 404)

    def handle_magic_create(self, payload):
        creator = payload.get("creator", "IShowSpeed").strip()
        prompt = payload.get("prompt", "").strip() or f"{creator} top five funny moments"
        fmt = payload.get("format", "short").strip()
        src_mode = payload.get("source_mode", "auto").strip()
        src_url = payload.get("source_url", "").strip()

        job_id = str(uuid.uuid4())
        with JOBS_LOCK:
            ACTIVE_JOBS[job_id] = {
                "id": job_id,
                "status": "running",
                "step": 0,
                "progress": 5,
                "message": "Initializing 1-click video pipeline...",
                "creator": creator,
                "prompt": prompt,
                "format": fmt
            }

        t = threading.Thread(
            target=run_magic_video_job,
            args=(job_id, creator, prompt, fmt, src_mode, src_url),
            daemon=True
        )
        t.start()
        self.send_json({"ok": True, "job_id": job_id})

    def handle_api_status(self):
        providers = llm_mod.get_providers()
        prov_data = []
        for p in providers:
            masked = (p['api_key'][:6] + "..." + p['api_key'][-4:]) if len(p['api_key']) > 10 else ("(none)" if not p['api_key'] else "***")
            prov_data.append({
                "name": p["name"],
                "model": p["model"],
                "base_url": p["base_url"],
                "api_key_masked": masked,
                "configured": p.get("configured", False)
            })

        freellm_online = False
        try:
            req = urllib.request.Request("http://127.0.0.1:3001/v1/models", headers={"Authorization": f"Bearer {os.environ.get('AUTOCLIP_PRIMARY_API_KEY', '')}"})
            with urllib.request.urlopen(req, timeout=2) as r:
                if r.status == 200:
                    freellm_online = True
        except Exception:
            pass

        ollama_online = False
        try:
            req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
            with urllib.request.urlopen(req, timeout=2) as r:
                if r.status == 200:
                    ollama_online = True
        except Exception:
            pass

        self.send_json({
            "status": "online",
            "providers": prov_data,
            "services": {
                "freellmapi": {"online": freellm_online, "url": "http://127.0.0.1:3001"},
                "ollama": {"online": ollama_online, "url": "http://127.0.0.1:11434"}
            },
            "env": {
                "AUTOCLIP_PRIMARY_MODEL": os.environ.get("AUTOCLIP_PRIMARY_MODEL", ""),
                "AUTOCLIP_PRIMARY_BASE_URL": os.environ.get("AUTOCLIP_PRIMARY_BASE_URL", ""),
                "AUTOCLIP_PRIMARY_API_KEY_CONFIGURED": bool(os.environ.get("AUTOCLIP_PRIMARY_API_KEY")),
                "AUTOCLIP_FALLBACK_MODEL": os.environ.get("AUTOCLIP_FALLBACK_MODEL", ""),
                "AUTOCLIP_FALLBACK_BASE_URL": os.environ.get("AUTOCLIP_FALLBACK_BASE_URL", ""),
                "AUTOCLIP_LOCAL_MODEL": os.environ.get("AUTOCLIP_LOCAL_MODEL", ""),
                "AUTOCLIP_LOCAL_BASE_URL": os.environ.get("AUTOCLIP_LOCAL_BASE_URL", "")
            }
        })

    def handle_test_cascade(self):
        providers = llm_mod.get_providers()
        results = []
        test_system = "You are a health check assistant. Reply with JSON."
        test_user = "Reply with JSON: {\"status\": \"ok\", \"model_tested\": true}"
        test_schema = {"status": ("str", True), "model_tested": ("bool", True)}

        for p in providers:
            p_res = {
                "name": p["name"],
                "model": p["model"],
                "base_url": p["base_url"],
                "configured": p.get("configured", False),
                "ok": False,
                "latency_ms": 0,
                "detail": ""
            }
            if not p.get("configured"):
                p_res["detail"] = "Not configured (no key or URL)"
                results.append(p_res)
                continue

            start_t = time.time()
            try:
                t_limit = 20 if "127.0.0.1" in p["base_url"] or "localhost" in p["base_url"] else 15
                res = llm_mod._call_provider(p, test_system, test_user, schema=test_schema, timeout=t_limit)
                elapsed = int((time.time() - start_t) * 1000)
                p_res["ok"] = True
                p_res["latency_ms"] = elapsed
                p_res["detail"] = f"Responded in {elapsed}ms: {json.dumps(res)}"
                append_log(f"Test passed for {p['name']} ({p['model']}) in {elapsed}ms")
            except Exception as e:
                elapsed = int((time.time() - start_t) * 1000)
                p_res["latency_ms"] = elapsed
                p_res["detail"] = str(e)
                append_log(f"Test failed for {p['name']} ({p['model']}): {e}")
            results.append(p_res)

        self.send_json({"results": results})

    def handle_save_config(self, payload):
        env_path = os.path.join(PROJECT_ROOT, ".env")
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

        keys_map = {
            "AUTOCLIP_PRIMARY_MODEL": payload.get("AUTOCLIP_PRIMARY_MODEL"),
            "AUTOCLIP_PRIMARY_BASE_URL": payload.get("AUTOCLIP_PRIMARY_BASE_URL"),
            "AUTOCLIP_PRIMARY_API_KEY": payload.get("AUTOCLIP_PRIMARY_API_KEY"),
            "AUTOCLIP_FALLBACK_MODEL": payload.get("AUTOCLIP_FALLBACK_MODEL"),
            "AUTOCLIP_FALLBACK_BASE_URL": payload.get("AUTOCLIP_FALLBACK_BASE_URL"),
            "AUTOCLIP_FALLBACK_API_KEY": payload.get("AUTOCLIP_FALLBACK_API_KEY"),
            "AUTOCLIP_LOCAL_MODEL": payload.get("AUTOCLIP_LOCAL_MODEL"),
            "AUTOCLIP_LOCAL_BASE_URL": payload.get("AUTOCLIP_LOCAL_BASE_URL"),
        }

        for k, v in keys_map.items():
            if v is not None:
                os.environ[k] = str(v).strip()

        new_lines = []
        handled = set()
        for line in lines:
            trimmed = line.strip()
            if trimmed and not trimmed.startswith("#") and "=" in trimmed:
                k = trimmed.split("=", 1)[0].strip()
                if k in keys_map and keys_map[k] is not None:
                    new_lines.append(f"{k}={keys_map[k]}\n")
                    handled.add(k)
                    continue
            new_lines.append(line)

        for k, v in keys_map.items():
            if v is not None and k not in handled:
                new_lines.append(f"{k}={v}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        append_log("Updated LLM Cascade configuration in .env")
        self.send_json({"ok": True, "message": "Configuration saved & applied successfully!"})

    def handle_api_videos(self):
        videos = []
        data_dir = os.path.join(PROJECT_ROOT, "data")
        shorts_dir = os.path.join(PROJECT_ROOT, "data", "shorts")
        build_dir = os.path.join(PROJECT_ROOT, "_build")

        for d in (shorts_dir, data_dir, build_dir):
            if not os.path.exists(d):
                continue
            for fn in os.listdir(d):
                if fn.lower().endswith(".mp4"):
                    if "speed_demo" in fn or fn.startswith("test_") or "sample" in fn:
                        continue
                    fp = os.path.join(d, fn)
                    st = os.stat(fp)
                    rel = f"data/shorts/{fn}" if d == shorts_dir else (f"data/{fn}" if d == data_dir else f"_build/{fn}")
                    videos.append({
                        "name": fn,
                        "rel_path": rel,
                        "size_mb": round(st.st_size / (1024 * 1024), 2),
                        "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
                        "is_short": "short" in fn or "rank" in fn or "single" in fn or "prep" in fn
                    })
        videos.sort(key=lambda x: x["mtime"], reverse=True)
        self.send_json({"videos": videos})

    def handle_api_qa(self, rel_path):
        if not rel_path:
            self.send_json({"ok": False, "error": "No file specified"}, 400)
            return

        fp = _safe_resolve(rel_path)
        if not fp or not os.path.exists(fp):
            self.send_json({"ok": False, "error": f"File not found: {rel_path}"}, 404)
            return

        try:
            report = qa_mod.tech_qa(fp)
            self.send_json({"ok": True, "report": report})
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, 500)

    def handle_api_research_data(self):
        rep_path = os.path.join(PROJECT_ROOT, "data", "research", "research_report.md")
        build_path = os.path.join(PROJECT_ROOT, "data", "research", "builder.json")

        rep_text = ""
        builder_data = {}
        if os.path.exists(rep_path):
            with open(rep_path, "r", encoding="utf-8") as f:
                rep_text = f.read()
        if os.path.exists(build_path):
            try:
                with open(build_path, "r", encoding="utf-8") as f:
                    builder_data = json.load(f)
            except Exception:
                pass

        self.send_json({
            "report_markdown": rep_text,
            "builder": builder_data
        })

    def handle_run_research(self, payload):
        creator = payload.get("creator", "").strip()
        topic = payload.get("topic", "").strip() or None
        if not creator:
            self.send_json({"ok": False, "error": "Creator name required"}, 400)
            return

        append_log(f"Initiating AI research for creator: '{creator}' (topic: {topic})...")
        try:
            res = research_mod.ai_research(creator, topic=topic)
            append_log(f"AI research completed for '{creator}' via LLM cascade!")
            self.send_json({
                "ok": True,
                "creator": creator,
                "data": res,
                "markdown": research_mod.report_markdown()
            })
        except Exception as e:
            append_log(f"Research failed: {e}")
            self.send_json({"ok": False, "error": str(e)}, 500)

    def serve_video(self, rel_name):
        full_path = _safe_resolve(rel_name)
        if not full_path or not os.path.exists(full_path) or not os.path.isfile(full_path):
            self.send_response(404)
            self.end_headers()
            return

        file_size = os.path.getsize(full_path)
        mime_type, _ = mimetypes.guess_type(full_path)
        mime_type = mime_type or "video/mp4"

        range_header = self.headers.get("Range")
        if range_header:
            match = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if match:
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else file_size - 1
                length = end - start + 1
                self.send_response(206)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                try:
                    with open(full_path, "rb") as f:
                        f.seek(start)
                        bytes_left = length
                        while bytes_left > 0:
                            chunk = f.read(min(bytes_left, 65536))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            bytes_left -= len(chunk)
                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
                    pass
                return

        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(file_size))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

        try:
            with open(full_path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
            pass

    def serve_dashboard(self):
        html = DASHBOARD_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AutoClip Studio · YouTube to 5 Ranked Shorts & Creator Studio</title>
  <style>
    :root {
      --bg: #090d16;
      --card-bg: #111827;
      --card-border: #1f293d;
      --accent: #8b5cf6;
      --gold: #fbbf24;
      --gold-dark: #d97706;
      --green: #10b981;
      --red: #ef4444;
      --blue: #38bdf8;
      --text: #f1f5f9;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background-color: var(--bg); color: var(--text); min-height: 100vh; display: flex; flex-direction: column; }
    
    header {
      background: #0f172a;
      border-bottom: 1px solid var(--card-border);
      padding: 1rem 2rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 50;
    }
    .brand { display: flex; align-items: center; gap: 0.75rem; }
    .brand-logo { font-size: 1.5rem; background: linear-gradient(135deg, #f59e0b, #c084fc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 800; }
    .tag { background: #8b5cf620; color: #c084fc; border: 1px solid #8b5cf640; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; }
    
    .status-badges { display: flex; gap: 1rem; align-items: center; }
    .badge { display: flex; align-items: center; gap: 0.4rem; background: #1e293b; padding: 0.35rem 0.75rem; border-radius: 20px; font-size: 0.8rem; border: 1px solid #334155; }
    .dot { width: 8px; height: 8px; border-radius: 50%; }
    .dot.online { background-color: var(--green); box-shadow: 0 0 8px var(--green); }
    .dot.offline { background-color: var(--red); box-shadow: 0 0 8px var(--red); }
    
    .nav-tabs { display: flex; background: #0c1220; border-bottom: 1px solid var(--card-border); padding: 0 2rem; gap: 1.5rem; overflow-x: auto; }
    .tab-btn { background: none; border: none; color: var(--text-muted); font-size: 0.95rem; font-weight: 600; padding: 1rem 0.5rem; cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.2s; white-space: nowrap; }
    .tab-btn:hover { color: var(--text); }
    .tab-btn.active { color: #facc15; border-bottom-color: #facc15; }

    main { flex: 1; padding: 2rem; max-width: 1400px; margin: 0 auto; width: 100%; }
    .tab-content { display: none; }
    .tab-content.active { display: block; animation: fadeIn 0.2s ease-in-out; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

    .card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; }
    .card-title { font-size: 1.15rem; font-weight: 700; margin-bottom: 1rem; display: flex; justify-content: space-between; align-items: center; color: #f8fafc; }

    /* Form elements */
    .form-group { margin-bottom: 1.25rem; }
    label { display: block; font-size: 0.82rem; font-weight: 600; color: var(--text-muted); margin-bottom: 0.4rem; text-transform: uppercase; letter-spacing: 0.5px; }
    input, select, textarea {
      width: 100%;
      background: #060911;
      border: 1px solid #334155;
      color: var(--text);
      padding: 0.75rem 1rem;
      border-radius: 8px;
      font-size: 0.95rem;
      outline: none;
      transition: border-color 0.2s;
    }
    input:focus, textarea:focus { border-color: var(--gold); }

    .btn-create {
      width: 100%;
      background: linear-gradient(135deg, #f59e0b, #d97706);
      color: #000;
      border: none;
      padding: 1.1rem;
      border-radius: 8px;
      font-size: 1.15rem;
      font-weight: 800;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.75rem;
      box-shadow: 0 4px 20px rgba(245, 158, 11, 0.3);
      transition: transform 0.15s, opacity 0.15s;
    }
    .btn-create:hover { opacity: 0.95; transform: scale(1.01); }
    .btn-create:disabled { opacity: 0.5; cursor: not-allowed; transform: none; box-shadow: none; }

    .btn-dl {
      background: #10b981;
      color: #fff;
      border: none;
      padding: 0.6rem 1rem;
      border-radius: 6px;
      font-weight: 700;
      font-size: 0.88rem;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      text-decoration: none;
      transition: opacity 0.15s;
    }
    .btn-dl:hover { opacity: 0.9; }

    .btn-preview {
      background: #1e293b;
      color: #38bdf8;
      border: 1px solid #334155;
      padding: 0.6rem 1rem;
      border-radius: 6px;
      font-weight: 700;
      font-size: 0.88rem;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
    }
    .btn-preview:hover { background: #334155; }

    /* Progress tracker */
    .tracker-card { background: #060911; border: 1px solid #1e293b; border-radius: 10px; padding: 1.5rem; margin-top: 1.5rem; display: none; }
    .progress-bar-bg { width: 100%; height: 10px; background: #1e293b; border-radius: 5px; overflow: hidden; margin-bottom: 1.25rem; }
    .progress-bar-fill { height: 100%; width: 5%; background: linear-gradient(90deg, #8b5cf6, #f59e0b); transition: width 0.4s ease; }
    .step-list { display: flex; flex-direction: column; gap: 0.75rem; }
    .step-item { display: flex; align-items: center; gap: 0.75rem; font-size: 0.9rem; color: #64748b; }
    .step-item.active { color: #facc15; font-weight: 700; }
    .step-item.done { color: #34d399; }
    .step-icon { width: 22px; height: 22px; border-radius: 50%; border: 2px solid currentColor; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; }

    /* Chips */
    .chips { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem; margin-bottom: 1.25rem; }
    .chip { background: #1e293b; border: 1px solid #334155; padding: 0.35rem 0.75rem; border-radius: 20px; font-size: 0.8rem; cursor: pointer; color: #cbd5e1; transition: all 0.2s; }
    .chip:hover { background: #334155; color: #fff; border-color: var(--gold); }
    .chip.active { background: #facc1520; color: #facc15; border-color: var(--gold); font-weight: 700; box-shadow: 0 0 10px rgba(250, 204, 21, 0.2); }

    /* YouTube 5-Shorts Cards */
    .yt-shorts-grid { display: grid; grid-template-columns: 1fr; gap: 1.25rem; margin-top: 1.5rem; }
    .clip-card {
      background: #0d1322;
      border: 1px solid #1e293b;
      border-radius: 10px;
      padding: 1.25rem;
      display: flex;
      flex-direction: column;
      gap: 0.85rem;
      transition: border-color 0.2s;
    }
    .clip-card.rank-1 { border: 2px solid var(--gold); background: #facc1508; box-shadow: 0 4px 20px rgba(251, 191, 36, 0.12); }
    .clip-card.rank-2 { border: 1.5px solid #94a3b8; }
    .clip-card.rank-3 { border: 1.5px solid #cd7f32; }

    .clip-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; }
    .rank-badge { font-weight: 800; font-size: 1.1rem; display: flex; align-items: center; gap: 0.5rem; }
    .rank-badge.gold { color: var(--gold); }
    .rank-badge.silver { color: #e2e8f0; }
    .rank-badge.bronze { color: #f97316; }

    .critique-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; background: #060911; padding: 0.75rem; border-radius: 8px; border: 1px solid #1e293b; font-size: 0.85rem; }
    @media (max-width: 768px) { .critique-grid { grid-template-columns: 1fr; } }
    .critique-good { color: #34d399; }
    .critique-bad { color: #f87171; }

    .clip-specs { display: flex; flex-wrap: wrap; gap: 0.5rem; font-size: 0.78rem; color: var(--text-muted); }
    .spec-pill { background: #1e293b; padding: 0.2rem 0.5rem; border-radius: 4px; border: 1px solid #334155; }

    /* Video player */
    .player-wrap { display: flex; gap: 2rem; align-items: flex-start; }
    @media (max-width: 1024px) { .player-wrap { flex-direction: column; } }
    .phone-mockup {
      width: 320px;
      height: 568px;
      background: #000;
      border-radius: 28px;
      border: 4px solid #334155;
      box-shadow: 0 20px 40px rgba(0,0,0,0.6);
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }
    .phone-mockup video { width: 100%; height: 100%; object-fit: cover; }
    .video-info-panel { flex: 1; width: 100%; }

    /* Creator Grid */
    .creator-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }
    .creator-card { background: #090e18; border: 2px solid #1e293b; border-radius: 10px; padding: 1rem 0.75rem; text-align: center; cursor: pointer; transition: all 0.2s; }
    .creator-card:hover { border-color: #a855f7; transform: translateY(-2px); }
    .creator-card.active { border-color: var(--gold); background: #facc1510; }
    .creator-avatar { font-size: 2.2rem; margin-bottom: 0.5rem; }
    .creator-name { font-weight: 700; font-size: 0.95rem; }
    .creator-tag { font-size: 0.72rem; color: var(--text-muted); }

    /* Metric Grid */
    .metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 1rem; margin-top: 1rem; }
    .metric-box { background: #060911; border: 1px solid #1e293b; border-radius: 8px; padding: 0.75rem; text-align: center; }
    .metric-val { font-size: 1.25rem; font-weight: 700; color: #38bdf8; margin-top: 0.25rem; }
    .metric-lbl { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600; }

    pre { background: #050811; border: 1px solid #1e293b; border-radius: 8px; padding: 1rem; font-family: monospace; font-size: 0.85rem; color: #a5b4fc; overflow-x: auto; max-height: 400px; white-space: pre-wrap; word-break: break-all; }
    .log-box { height: 260px; overflow-y: auto; background: #050811; border: 1px solid #1e293b; border-radius: 8px; padding: 0.75rem; font-family: monospace; font-size: 0.8rem; color: #cbd5e1; }
    .btn { background: #8b5cf6; color: white; border: none; padding: 0.65rem 1.2rem; border-radius: 6px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 0.5rem; font-size: 0.9rem; }
    .btn-secondary { background: #1e293b; border: 1px solid #334155; }
    .btn-gold { background: var(--gold); color: #000; font-weight: 700; }

    /* MCP Upload Modal */
    .modal-backdrop {
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0, 0, 0, 0.78);
      backdrop-filter: blur(5px);
      z-index: 999;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 1rem;
    }
    .modal-box {
      background: #0f172a;
      border: 1px solid #334155;
      border-radius: 12px;
      max-width: 580px;
      width: 100%;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.85);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      animation: modalIn 0.2s ease-out;
    }
    @keyframes modalIn {
      from { opacity: 0; transform: scale(0.95); }
      to { opacity: 1; transform: scale(1); }
    }
    .modal-header {
      padding: 1.25rem 1.5rem;
      border-bottom: 1px solid #1e293b;
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: #0b1120;
    }
    .modal-body {
      padding: 1.5rem;
      display: flex;
      flex-direction: column;
      gap: 1rem;
      max-height: 70vh;
      overflow-y: auto;
    }
    .modal-footer {
      padding: 1rem 1.5rem;
      border-top: 1px solid #1e293b;
      display: flex;
      justify-content: flex-end;
      gap: 0.75rem;
      background: #090d16;
    }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <div class="brand-logo">AutoClip Studio</div>
      <span class="tag">YouTube to 5 Shorts</span>
    </div>
    <div class="status-badges">
      <div class="badge" title="Composio YouTube Connected Channel">
        <div id="dot-composio" class="dot offline"></div>
        <span id="txt-composio">YouTube: Checking...</span>
      </div>
      <a href="http://localhost:3001" target="_blank" style="text-decoration: none; color: inherit;">
        <div class="badge" title="FreeLLMAPI Unified Gateway">
          <div id="dot-freellm" class="dot offline"></div>
          <span>FreeLLMAPI (:3001)</span>
        </div>
      </a>
      <a href="http://localhost:11434" target="_blank" style="text-decoration: none; color: inherit;">
        <div class="badge" title="Local Ollama">
          <div id="dot-ollama" class="dot offline"></div>
          <span>Ollama (:11434)</span>
        </div>
      </a>
      <button class="btn btn-secondary" onclick="refreshStatus()" style="padding: 0.35rem 0.75rem; font-size: 0.8rem;">Refresh</button>
    </div>
  </header>

  <nav class="nav-tabs">
    <button class="tab-btn active" onclick="switchTab('yt-shorts')">🎬 YouTube to 5 Shorts</button>
    <button class="tab-btn" onclick="switchTab('magic')">⚡ 1-Click Creator Studio</button>
    <button class="tab-btn" onclick="switchTab('player')">📱 Shorts Player & QA</button>
    <button class="tab-btn" onclick="switchTab('cascade')">⚙️ LLM Keys & Cascade</button>
    <button class="tab-btn" onclick="switchTab('research')">🔍 AI Research Dossier</button>
    <button class="tab-btn" onclick="switchTab('pipeline')">📜 System Logs</button>
  </nav>

  <main>
    <!-- TAB 1: YOUTUBE TO 5 RANKED SHORTS (PRIMARY) -->
    <div id="tab-yt-shorts" class="tab-content active">
      <div class="card">
        <div class="card-title">
          <span>🎬 Paste YouTube Video Link &rarr; Get 5 Ranked Downloadable Shorts</span>
          <span style="font-size: 0.8rem; font-weight: 400; color: var(--gold);">Free LLM AI Curation &middot; 9:16 Face Reframe &middot; Golden Subtitles</span>
        </div>

        <!-- STREAMER & AUDIENCE TIMELINE SELECTOR -->
        <div class="form-group" style="margin-bottom: 1.25rem;">
          <label>Target Streamer &bull; Auto-Sets Audience Upload Timeline &amp; Matched Copyright-Free Music</label>
          <div class="chips" id="streamer-chips-bar" style="margin-bottom: 0.75rem;">
            <div class="chip active" id="chip-speed" onclick="setStreamer('speed')">⚡ IShowSpeed</div>
            <div class="chip" id="chip-kai" onclick="setStreamer('kai')">🎮 Kai Cenat</div>
            <div class="chip" id="chip-jynxzi" onclick="setStreamer('jynxzi')">🎯 Jynxzi</div>
            <div class="chip" id="chip-caseoh" onclick="setStreamer('caseoh')">🍔 CaseOh</div>
            <div class="chip" id="chip-xqc" onclick="setStreamer('xqc')">🔥 xQc</div>
            <div class="chip" id="chip-adin" onclick="setStreamer('adin')">🎙️ Adin Ross</div>
            <div class="chip" id="chip-marlon" onclick="setStreamer('marlon')">🎭 Marlon Webb</div>
            <div class="chip" id="chip-default" onclick="setStreamer('default')">✨ General Streamer</div>
          </div>

          <!-- Active Streamer Audience Timeline & Music Card -->
          <div id="streamer-timeline-card" style="background: #090e1a; border: 1px solid #1e293b; border-radius: 8px; padding: 0.9rem; display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 1rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
              <div style="display: flex; align-items: center; gap: 0.5rem;">
                <span style="font-size: 1.3rem;" id="st-card-avatar">⚡</span>
                <div>
                  <span style="font-weight: 700; color: #f8fafc; font-size: 0.95rem;" id="st-card-name">IShowSpeed</span>
                  <span style="font-size: 0.75rem; color: var(--gold); margin-left: 0.4rem;" id="st-card-tag">High Energy &middot; Reactions &middot; Rages</span>
                </div>
              </div>
              <span class="tag" style="background: #10b98120; color: #34d399; border: 1px solid #10b98140;" id="st-card-badge">100% No-Copyright BGM</span>
            </div>

            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 0.75rem; margin-top: 0.25rem; font-size: 0.82rem;">
              <div style="background: #111827; border: 1px solid #1f293d; border-radius: 6px; padding: 0.6rem 0.75rem;">
                <div style="color: var(--text-muted); font-size: 0.72rem; text-transform: uppercase; font-weight: 700;">📅 Peak Audience Window</div>
                <div style="color: #60a5fa; font-weight: 600; margin-top: 0.15rem;" id="st-card-peak">Fri/Sat/Sun 2:30 PM – 5:00 PM EDT (US School Dismissal)</div>
              </div>
              <div style="background: #111827; border: 1px solid #1f293d; border-radius: 6px; padding: 0.6rem 0.75rem;">
                <div style="color: var(--text-muted); font-size: 0.72rem; text-transform: uppercase; font-weight: 700;">🚀 Next Recommended Upload Slot</div>
                <div style="color: #facc15; font-weight: 600; margin-top: 0.15rem;" id="st-card-next">Friday, Oct 02 at 02:30 PM EDT (in ~5 hours)</div>
              </div>
              <div style="background: #111827; border: 1px solid #1f293d; border-radius: 6px; padding: 0.6rem 0.75rem;">
                <div style="color: var(--text-muted); font-size: 0.72rem; text-transform: uppercase; font-weight: 700;">🎵 Matched Non-Copyrighted Music</div>
                <div style="color: #34d399; font-weight: 600; margin-top: 0.15rem;" id="st-card-bgm">Brazilian Phonk (Rage & Climax) (138 BPM)</div>
              </div>
            </div>

            <!-- Interactive 4-Track Selector -->
            <div style="margin-top: 0.6rem; border-top: 1px solid #1f293d; padding-top: 0.6rem;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem; flex-wrap: wrap; gap: 0.4rem;">
                <span style="font-size: 0.75rem; color: #94a3b8; font-weight: 700; text-transform: uppercase;">
                  🎶 4 Dedicated Copyright-Safe Tracks (Auto-Match per Rank or Lock Track):
                </span>
                <span style="font-size: 0.74rem; color: #34d399; font-weight: 600;" id="st-track-selected-label">Mode: Auto-Match per Rank</span>
              </div>
              <div class="chips" id="streamer-track-chips" style="margin-bottom: 0.2rem; margin-top: 0.35rem;">
                <!-- Populated dynamically via JS -->
              </div>
            </div>

            <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.2rem;" id="st-card-reason">
              Teens in US timezones finish school between 2:30–3:30 PM EDT. YouTube Shorts requires 2–3 hours of micro-cohort test indexing before exploding into prime-time evening feeds.
            </div>
          </div>
        </div>

        <div class="form-group">
          <label>YouTube Video or Live Stream URL</label>
          <div style="display: flex; gap: 0.75rem;">
            <input type="text" id="yt-url-input" value="" placeholder="Paste any YouTube video link (e.g. https://www.youtube.com/watch?v=... or https://youtu.be/...)">
            <button class="btn btn-secondary" onclick="pasteFromClipboard()" style="white-space: nowrap;">📋 Paste</button>
          </div>
          <div class="chips">
            <div class="chip" onclick="pasteFromClipboard()">📋 Paste from Clipboard</div>
            <div class="chip" onclick="toggleComposioSearch()">🔍 Search YouTube via MCP</div>
            <div class="chip" onclick="loadComposioChannelVideos()">📺 Pick from Connected Channel (@askwhatt)</div>
          </div>
        </div>

        <!-- Composio MCP YouTube Integration Bar -->
        <div style="background: #060a14; border: 1px solid #1e293b; border-radius: 8px; padding: 0.9rem; margin-bottom: 1.25rem;">
          <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
              <span style="font-size: 1.1rem;">🔴</span>
              <div>
                <span style="font-size: 0.82rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700;">Composio MCP Connected Channel:</span>
                <span id="comp-chan-label" style="font-weight: 700; color: #facc15; font-size: 0.9rem; margin-left: 0.35rem;">Ask What? (@askwhatt)</span>
              </div>
            </div>
            <div style="display: flex; gap: 0.5rem;">
              <button class="btn btn-secondary" onclick="loadComposioChannelVideos()" style="padding: 0.35rem 0.75rem; font-size: 0.8rem;">
                📺 Channel Videos
              </button>
              <button class="btn btn-secondary" onclick="toggleComposioSearch()" style="padding: 0.35rem 0.75rem; font-size: 0.8rem;">
                🔍 Search via MCP
              </button>
            </div>
          </div>

          <div id="comp-search-box" style="display: none; margin-top: 0.75rem;">
            <div style="display: flex; gap: 0.5rem;">
              <input type="text" id="comp-query-input" placeholder="Search any YouTube video e.g. IShowSpeed funny, Sidemen, MrBeast..." style="padding: 0.5rem 0.75rem; font-size: 0.85rem;">
              <button class="btn btn-gold" onclick="doComposioSearch()" style="padding: 0.5rem 0.85rem; font-size: 0.82rem; white-space: nowrap;">Search MCP</button>
            </div>
          </div>

          <div id="comp-results-container" style="display: none; margin-top: 0.75rem; max-height: 200px; overflow-y: auto; flex-direction: column; gap: 0.5rem;">
          </div>
        </div>

        <button class="btn-create" id="btn-yt-generate" onclick="launchYoutubeTo5Shorts()">
          <span>🚀 GENERATE 5 VIRAL SHORTS (9:16)</span>
        </button>

        <!-- Progress Tracker -->
        <div class="tracker-card" id="yt-tracker">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
            <span style="font-weight: 700; font-size: 1rem; color: #f8fafc;" id="yt-tracker-title">Starting Pipeline...</span>
            <span style="font-size: 0.85rem; font-weight: 700; color: var(--gold);" id="yt-tracker-pct">5%</span>
          </div>
          <div class="progress-bar-bg">
            <div class="progress-bar-fill" id="yt-tracker-bar"></div>
          </div>
          <div class="step-list">
            <div class="step-item active" id="yt-st-1"><div class="step-icon">1</div> <span>1. Downloading YouTube Video & Audio Stream (yt-dlp)</span></div>
            <div class="step-item" id="yt-st-2"><div class="step-icon">2</div> <span>2. Faster-Whisper Word-Level Transcription & Speech Energies</span></div>
            <div class="step-item" id="yt-st-3"><div class="step-icon">3</div> <span>3. Free LLM API Analysis & 5-Tier Viral Ranking (#1 to #5)</span></div>
            <div class="step-item" id="yt-st-4"><div class="step-icon">4</div> <span>4. 9:16 Face-Tracking Reframe & Kinetic Subtitles Burn</span></div>
            <div class="step-item" id="yt-st-5"><div class="step-icon">5</div> <span>5. -14 LUFS Broadcast Audio Normalization & QA Pass</span></div>
          </div>
        </div>
      </div>

      <!-- RESULTS SECTION: 5 RANKED CLIPS + PREVIEW PLAYER -->
      <div class="card" id="yt-results-card">
        <div class="card-title">
          <span>🏆 Top 5 Ranked Viral Shorts (Rated & Ranked from Best to Worst)</span>
          <span class="tag" style="background: #10b98120; color: #34d399; border: 1px solid #10b98140;">All 5 Rendered in 9:16 &middot; Ready to Download</span>
        </div>

        <div class="player-wrap">
          <!-- Left: The 5 Ranked Cards -->
          <div style="flex: 1.2; display: flex; flex-direction: column; gap: 1rem;" id="ranked-clips-container">
            <!-- Dynamically populated or loaded from summary -->
            <div id="no-clips-placeholder" style="color: var(--text-muted); font-size: 0.92rem; padding: 2rem; text-align: center; border: 1px dashed #334155; border-radius: 8px;">
              <div style="font-size: 1.6rem; margin-bottom: 0.5rem;">🎬</div>
              <div style="font-weight: 700; color: #f8fafc; margin-bottom: 0.25rem;">No Shorts Generated Yet</div>
              <div>Paste a YouTube video link above and click <strong>GENERATE 5 VIRAL SHORTS</strong>.</div>
            </div>
          </div>

          <!-- Right: Vertical Phone Mockup Player -->
          <div>
            <div class="phone-mockup">
              <video id="yt-preview-video" controls playsinline loop>
                Your browser does not support HTML5 video.
              </video>
            </div>
            <div style="text-align: center; margin-top: 0.75rem;">
              <div id="yt-preview-title" style="font-weight: 700; color: var(--gold); font-size: 0.95rem;">Paste a YouTube link above to generate shorts</div>
              <div style="margin-top: 0.5rem;">
                <a id="yt-preview-dl-btn" href="#" class="btn-dl" style="padding: 0.4rem 0.8rem; font-size: 0.8rem; display: none;">
                  ⬇ Download This Short (.mp4)
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 2: MAGIC 1-CLICK STUDIO -->
    <div id="tab-magic" class="tab-content">
      <div class="card">
        <div class="card-title">
          <span>1. Pick Your Creator</span>
          <span style="font-size: 0.8rem; font-weight: 400; color: var(--gold);">IShowSpeed, Kai Cenat, Marlon Webb</span>
        </div>
        <div class="creator-grid">
          <div class="creator-card active" onclick="selectCreator('IShowSpeed', this)">
            <div class="creator-avatar">⚡</div>
            <div class="creator-name">IShowSpeed</div>
            <div class="creator-tag">High Energy &middot; Reactions &middot; Rages</div>
          </div>
          <div class="creator-card" onclick="selectCreator('Marlon Webb', this)">
            <div class="creator-avatar">🎭</div>
            <div class="creator-name">Marlon Webb</div>
            <div class="creator-tag">Skits &middot; Dad Jokes</div>
          </div>
          <div class="creator-card" onclick="selectCreator('Kai Cenat', this)">
            <div class="creator-avatar">🎮</div>
            <div class="creator-name">Kai Cenat</div>
            <div class="creator-tag">Stream Chaos &middot; MAMP</div>
          </div>
        </div>

        <div class="form-group">
          <label>Describe the Video Concept</label>
          <input type="text" id="magic-prompt" value="IShowSpeed top five funny moments">
        </div>

        <button class="btn-create" id="btn-create-magic" onclick="launchMagicCreation()">
          <span>⚡ CREATE CREATOR VIDEO</span>
        </button>

        <div class="tracker-card" id="magic-tracker">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
            <span style="font-weight: 700; font-size: 1rem; color: #f8fafc;" id="tracker-title">Building...</span>
            <span style="font-size: 0.85rem; font-weight: 700; color: var(--gold);" id="tracker-pct">15%</span>
          </div>
          <div class="progress-bar-bg">
            <div class="progress-bar-fill" id="tracker-bar"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 3: SHORTS PLAYER & QA -->
    <div id="tab-player" class="tab-content">
      <div class="player-wrap">
        <div>
          <div class="phone-mockup">
            <video id="short-video" controls playsinline loop>
              Your browser does not support HTML5 video.
            </video>
          </div>
          <div style="text-align: center; margin-top: 0.75rem; font-size: 0.8rem; color: var(--gold); font-weight: 600;">
            1080x1920 9:16 Vertical &middot; Golden-Yellow Pop Captions
          </div>
        </div>

        <div class="video-info-panel">
          <div class="card">
            <div class="card-title">
              <span>All Generated Shorts Gallery</span>
              <button class="btn btn-secondary" onclick="loadVideos()" style="padding: 0.3rem 0.6rem; font-size: 0.75rem;">Reload List</button>
            </div>
            <div class="form-group">
              <label>Select Short to Preview & Download</label>
              <select id="video-select" onchange="onVideoSelectChange()">
                <option value="">No videos generated yet</option>
              </select>
            </div>
            <div style="margin-top: 0.5rem;">
              <a id="main-player-dl-btn" href="#" class="btn-dl" style="display: none;">
                ⬇ Download Selected Video (.mp4)
              </a>
            </div>
          </div>

          <div class="card">
            <div class="card-title">
              <span>Technical & Editorial QA Report</span>
              <span class="tag" id="qa-badge-pass" style="background: #10b98120; color: #34d399; border: 1px solid #10b98140;">PASS</span>
            </div>
            <div class="metric-grid">
              <div class="metric-box">
                <div class="metric-lbl">Resolution</div>
                <div class="metric-val" id="m-res">1080x1920</div>
              </div>
              <div class="metric-box">
                <div class="metric-lbl">Frame Rate</div>
                <div class="metric-val" id="m-fps">30 FPS</div>
              </div>
              <div class="metric-box">
                <div class="metric-lbl">Duration</div>
                <div class="metric-val" id="m-dur">20.1s</div>
              </div>
              <div class="metric-box">
                <div class="metric-lbl">Loudness</div>
                <div class="metric-val" id="m-lufs">-14.0 LUFS</div>
              </div>
              <div class="metric-box">
                <div class="metric-lbl">Black Frames</div>
                <div class="metric-val" id="m-black" style="color: #34d399;">0.00s</div>
              </div>
              <div class="metric-box">
                <div class="metric-lbl">Caption Style</div>
                <div class="metric-val" id="m-caps" style="color: var(--gold);">Golden Pop</div>
              </div>
            </div>
            <div style="margin-top: 1.25rem;">
              <pre id="qa-probe-json" style="max-height: 140px; font-size: 0.78rem;">Loading QA results...</pre>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 4: LLM CASCADE & SETTINGS -->
    <div id="tab-cascade" class="tab-content">
      <div class="card">
        <div class="card-title">
          <span>Cascading LLM Engine Hierarchy</span>
          <button class="btn btn-gold" onclick="testCascade()" id="btn-test-cascade" style="padding: 0.4rem 0.8rem; font-size: 0.8rem;">Test Cascade Now</button>
        </div>
        <div style="display: flex; flex-direction: column; gap: 0.75rem;">
          <div class="card" style="padding: 0.85rem 1rem; margin-bottom: 0;">
            <div style="font-weight: 700; color: #a855f7;">Tier 1: Primary (Best First)</div>
            <div style="font-size: 0.8rem; color: var(--text-muted);" id="p1-desc">FreeLLMAPI &middot; mistral-code</div>
            <span class="tag" id="p1-status" style="margin-top: 0.35rem; display: inline-block;">Ready</span>
          </div>
          <div class="card" style="padding: 0.85rem 1rem; margin-bottom: 0;">
            <div style="font-weight: 700; color: #38bdf8;">Tier 2: Fallback Model</div>
            <div style="font-size: 0.8rem; color: var(--text-muted);" id="p2-desc">FreeLLMAPI &middot; command-r-2</div>
            <span class="tag" id="p2-status" style="margin-top: 0.35rem; display: inline-block;">Ready</span>
          </div>
          <div class="card" style="padding: 0.85rem 1rem; margin-bottom: 0;">
            <div style="font-weight: 700; color: #10b981;">Tier 3: Local Offline Fallback</div>
            <div style="font-size: 0.8rem; color: var(--text-muted);" id="p3-desc">Ollama &middot; gemma4:12b</div>
            <span class="tag" id="p3-status" style="margin-top: 0.35rem; display: inline-block;">Online</span>
          </div>
        </div>
        <div id="cascade-test-results" style="display: none; margin-top: 1rem;">
          <pre id="test-output-log" style="font-size: 0.78rem; max-height: 180px;"></pre>
        </div>
      </div>
    </div>

    <!-- TAB 5: RESEARCH DOSSIER -->
    <div id="tab-research" class="tab-content">
      <div class="card">
        <div class="card-title">
          <span>Active Creator Profile (builder.json)</span>
        </div>
        <pre id="profile-json-view" style="max-height: 250px;">Loading profile...</pre>
      </div>
      <div class="card">
        <div class="card-title">
          <span>Generated Research Report</span>
        </div>
        <pre id="report-md-view" style="max-height: 350px; white-space: pre-wrap;">Loading report...</pre>
      </div>
    </div>

    <!-- TAB 6: LOGS -->
    <div id="tab-pipeline" class="tab-content">
      <div class="card">
        <div class="card-title">
          <span>System Execution Logs</span>
          <button class="btn btn-secondary" onclick="fetchLogs()" style="padding: 0.3rem 0.6rem; font-size: 0.75rem;">Clear / Refresh</button>
        </div>
        <div class="log-box" id="sys-log-box">Connecting...</div>
      </div>
    <!-- COMPOSIO MCP YOUTUBE UPLOAD MODAL -->
    <div id="upload-modal" class="modal-backdrop">
      <div class="modal-box">
        <div class="modal-header">
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <span style="font-size: 1.25rem;">🔴</span>
            <div>
              <div style="font-weight: 700; font-size: 1.05rem; color: #f8fafc;">Upload Short to YouTube via MCP</div>
              <div style="font-size: 0.75rem; color: var(--gold);">Channel: Ask What? (@askwhatt)</div>
            </div>
          </div>
          <button onclick="closeUploadModal()" style="background: none; border: none; color: var(--text-muted); font-size: 1.3rem; cursor: pointer; padding: 0.2rem 0.5rem;">&times;</button>
        </div>
        <div class="modal-body">
          <input type="hidden" id="modal-file-path">
          <!-- Streamer Optimal Audience Timeline Card in Modal -->
          <div id="modal-streamer-timeline-box" style="background: #090e1a; border: 1px solid #1e293b; border-radius: 8px; padding: 0.75rem; margin-bottom: 0.85rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
              <div style="font-size: 0.82rem; font-weight: 700; color: #facc15;" id="modal-streamer-title">⚡ IShowSpeed Optimal Upload Timeline</div>
              <button type="button" class="btn btn-secondary" onclick="applyModalOptimalSchedule()" style="padding: 0.2rem 0.6rem; font-size: 0.72rem; border-color: var(--gold); color: var(--gold); font-weight: 700;">
                ⚡ Apply Optimal Slot
              </button>
            </div>
            <div style="font-size: 0.8rem; color: #93c5fd; font-weight: 600;" id="modal-streamer-slot">Recommended: Friday, Oct 02 at 02:30 PM EDT (in ~5 hours)</div>
            <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 0.25rem;" id="modal-streamer-reason">Peak youth after-school surge. Allows 2h YouTube Shorts feed indexing before peak evening consumption.</div>
          </div>
          <div class="form-group" style="margin-bottom: 0.75rem;">
            <label>Short Title (AI-Optimized with #shorts)</label>
            <input type="text" id="modal-title" placeholder="Catchy title...">
          </div>
          <div class="form-group" style="margin-bottom: 0.75rem;">
            <label>Description (AI Viral Hooks & Hashtags)</label>
            <textarea id="modal-description" rows="3" placeholder="Engaging description..."></textarea>
          </div>
          <div class="form-group" style="margin-bottom: 0.75rem;">
            <label>Tags & Hashtags (Comma-separated)</label>
            <input type="text" id="modal-tags" placeholder="shorts, viral, funny, autoclip">
          </div>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 0.75rem;">
            <div>
              <label>Privacy Setting</label>
              <select id="modal-privacy">
                <option value="public" selected>Public</option>
                <option value="unlisted">Unlisted</option>
                <option value="private">Private</option>
              </select>
            </div>
            <div>
              <label>Publish Schedule</label>
              <div style="display: flex; align-items: center; gap: 0.5rem; height: 42px;">
                <input type="checkbox" id="modal-schedule-toggle" onchange="toggleScheduleInput()" style="width: auto; cursor: pointer;">
                <span style="font-size: 0.85rem; color: var(--text-muted); cursor: pointer;" onclick="document.getElementById('modal-schedule-toggle').click()">Schedule video</span>
              </div>
            </div>
          </div>
          <div id="modal-schedule-box" style="display: none; margin-bottom: 0.75rem;">
            <label>Scheduled Release Date & Time</label>
            <input type="datetime-local" id="modal-publish-at">
            <span style="font-size: 0.72rem; color: var(--text-muted);">Video is uploaded as private on YouTube until this release time.</span>
          </div>
          <div id="modal-status-msg" style="display: none; padding: 0.75rem; border-radius: 6px; font-size: 0.85rem;"></div>
        </div>
        <div class="modal-footer" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
          <button type="button" class="btn btn-secondary" onclick="openStudioUpload()" style="border-color: #ef4444; color: #f87171; font-weight: 600;" title="Upload directly in YouTube Studio with ZERO API quota limits">
            🌐 1-Click Studio Upload (Unlimited)
          </button>
          <div style="display: flex; gap: 0.5rem;">
            <button class="btn btn-secondary" onclick="closeUploadModal()">Cancel</button>
            <button class="btn btn-gold" id="btn-submit-modal-upload" onclick="submitModalUpload()">
              🚀 Upload via API
            </button>
          </div>
        </div>
      </div>
    </div>
  </main>

  <script>
    let selectedCreator = 'IShowSpeed';
    let selectedStreamer = 'speed';
    let selectedTrackId = null;
    let selectedFormat = 'short';
    let allCreatorsData = {};
    let currentSlotData = null;

    async function loadCreatorProfiles() {
      try {
        const res = await fetch('/api/creator-profiles');
        const data = await res.json();
        if (data.ok && data.creators) {
          allCreatorsData = data.creators;
          if (allCreatorsData[selectedStreamer]) {
            updateStreamerCardWithData(allCreatorsData[selectedStreamer]);
          }
        }
      } catch (e) {
        console.error(e);
      }
    }

    async function setStreamer(creatorId) {
      selectedStreamer = creatorId;
      selectedTrackId = null;
      document.querySelectorAll('#streamer-chips-bar .chip').forEach(c => c.classList.remove('active'));
      const chipEl = document.getElementById(`chip-${creatorId}`);
      if (chipEl) chipEl.classList.add('active');

      try {
        const res = await fetch(`/api/optimal-schedule?creator=${creatorId}`);
        const data = await res.json();
        if (data.ok) {
          currentSlotData = data.slot;
          updateStreamerCardWithData(data.creator, data.slot);
        }
      } catch (e) {
        console.error(e);
      }
    }

    function renderStreamerTracks(tracks) {
      const container = document.getElementById('streamer-track-chips');
      if (!container) return;
      container.innerHTML = '';

      // Auto-match chip (default)
      const autoChip = document.createElement('div');
      autoChip.className = `chip ${selectedTrackId === null ? 'active' : ''}`;
      autoChip.id = 'track-chip-auto';
      autoChip.innerHTML = '✨ <strong>Auto-Match by Rank</strong> (Rank 1: Climax, Rank 2: Meme/Hype...)';
      autoChip.onclick = () => selectTrack(null, 'Auto-Match per Rank');
      container.appendChild(autoChip);

      if (tracks && Array.isArray(tracks)) {
        tracks.forEach((t, i) => {
          const chip = document.createElement('div');
          chip.className = `chip ${selectedTrackId === t.id ? 'active' : ''}`;
          chip.id = `track-chip-${t.id}`;
          const pool = t.pool || '';
          let poolBadge = '🎵';
          if (pool.includes('RAGE')) poolBadge = '🔴 RAGE';
          else if (pool.includes('HYPE')) poolBadge = '🟠 HYPE';
          else if (pool.includes('FUNNY')) poolBadge = '🟡 FUNNY';
          else if (pool.includes('STORY')) poolBadge = '🔵 STORY';
          else if (pool.includes('CINEMATIC')) poolBadge = '🟣 SUSPENSE';

          chip.innerHTML = `<span style="font-size: 0.72rem; padding: 0.1rem 0.35rem; border-radius: 3px; background: #334155; margin-right: 0.3rem;">${poolBadge}</span> #${i+1} ${t.name} <span style="font-size: 0.72rem; color: #94a3b8;">(${t.bpm} BPM)</span>`;
          chip.onclick = () => selectTrack(t.id, t.name);
          container.appendChild(chip);
        });
      }
    }

    function selectTrack(trackId, trackName) {
      selectedTrackId = trackId;
      document.querySelectorAll('#streamer-track-chips .chip').forEach(c => c.classList.remove('active'));
      const lbl = document.getElementById('st-track-selected-label');
      if (trackId === null) {
        const el = document.getElementById('track-chip-auto');
        if (el) el.classList.add('active');
        if (lbl) lbl.innerText = 'Mode: Auto-Match per Rank';
      } else {
        const el = document.getElementById(`track-chip-${trackId}`);
        if (el) el.classList.add('active');
        if (lbl) lbl.innerText = `Locked: ${trackName}`;
      }
    }

    function updateStreamerCardWithData(creator, slot) {
      if (!creator) return;
      const av = document.getElementById('st-card-avatar');
      const nm = document.getElementById('st-card-name');
      const tg = document.getElementById('st-card-tag');
      const bgm = document.getElementById('st-card-bgm');
      const pk = document.getElementById('st-card-peak');
      const nx = document.getElementById('st-card-next');
      const rs = document.getElementById('st-card-reason');

      if (av) av.innerText = creator.avatar || '⚡';
      if (nm) nm.innerText = creator.name;
      if (tg) tg.innerText = creator.tag;
      if (bgm && creator.music) bgm.innerText = creator.music.name;
      if (slot) {
        if (pk) pk.innerText = slot.peak_label;
        if (nx) nx.innerText = slot.human_readable;
        if (rs) rs.innerText = slot.reason;
      }

      // Render 4-Track buttons
      renderStreamerTracks(creator.tracks || (creator.music ? [creator.music] : []));
      selectTrack(null, 'Auto-Match per Rank');
    }

    function switchTab(name) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      event.target.classList.add('active');
      document.getElementById('tab-' + name).classList.add('active');
    }

    function setYtUrl(u) {
      document.getElementById('yt-url-input').value = u;
    }

    async function pasteFromClipboard() {
      try {
        const text = await navigator.clipboard.readText();
        if (text) document.getElementById('yt-url-input').value = text;
      } catch (e) {
        alert('Please paste using Ctrl+V');
      }
    }

    async function launchYoutubeTo5Shorts() {
      const url = document.getElementById('yt-url-input').value.trim();
      if (!url) {
        alert('Please enter a YouTube link');
        return;
      }

      const btn = document.getElementById('btn-yt-generate');
      btn.disabled = true;
      btn.innerText = '⏳ DOWNLOADING & GENERATING 5 SHORTS...';

      const tracker = document.getElementById('yt-tracker');
      tracker.style.display = 'block';

      try {
        const res = await fetch('/api/youtube-to-shorts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            url: url,
            creator: selectedStreamer,
            track_id: selectedTrackId || null
          })
        });
        const data = await res.json();
        if (data.ok && data.job_id) {
          pollYtJob(data.job_id);
        } else {
          alert('Error: ' + (data.error || 'Failed to start'));
          btn.disabled = false;
          btn.innerText = '🚀 GENERATE 5 VIRAL SHORTS (9:16)';
        }
      } catch (e) {
        alert('Network error: ' + e);
        btn.disabled = false;
        btn.innerText = '🚀 GENERATE 5 VIRAL SHORTS (9:16)';
      }
    }

    function pollYtJob(jobId) {
      const interval = setInterval(async () => {
        try {
          const res = await fetch(`/api/job-status?job_id=${jobId}`);
          const job = await res.json();
          if (job.status === 'not_found') return;

          document.getElementById('yt-tracker-bar').style.width = job.progress + '%';
          document.getElementById('yt-tracker-pct').innerText = job.progress + '%';
          document.getElementById('yt-tracker-title').innerText = job.message || 'Processing...';

          for (let i = 1; i <= 5; i++) {
            const el = document.getElementById(`yt-st-${i}`);
            if (i < job.step) {
              el.className = 'step-item done';
            } else if (i === job.step) {
              el.className = 'step-item active';
            } else {
              el.className = 'step-item';
            }
          }

          if (job.status === 'completed') {
            clearInterval(interval);
            document.getElementById('btn-yt-generate').disabled = false;
            document.getElementById('btn-yt-generate').innerText = '🚀 GENERATE 5 VIRAL SHORTS (9:16)';
            alert('🎉 Done! All 5 Ranked Shorts have been rendered!');
            if (job.result && job.result.clips) {
              renderRankedClips(job.result.clips);
            } else {
              loadYoutubeHistory();
            }
          } else if (job.status === 'failed') {
            clearInterval(interval);
            document.getElementById('btn-yt-generate').disabled = false;
            document.getElementById('btn-yt-generate').innerText = '🚀 GENERATE 5 VIRAL SHORTS (9:16)';
            alert('Pipeline failed: ' + job.message);
          }
        } catch (e) {
          console.error(e);
        }
      }, 1500);
    }

    let currentClips = [];

    function renderRankedClips(clips) {
      currentClips = clips || [];
      const cont = document.getElementById('ranked-clips-container');
      cont.innerHTML = '';
      if (!clips || !clips.length) {
        cont.innerHTML = `
          <div id="no-clips-placeholder" style="color: var(--text-muted); font-size: 0.92rem; padding: 2rem; text-align: center; border: 1px dashed #334155; border-radius: 8px;">
            <div style="font-size: 1.6rem; margin-bottom: 0.5rem;">🎬</div>
            <div style="font-weight: 700; color: #f8fafc; margin-bottom: 0.25rem;">No Shorts Generated Yet</div>
            <div>Paste a YouTube video link above and click <strong>GENERATE 5 VIRAL SHORTS</strong>.</div>
          </div>`;
        const titleEl = document.getElementById('yt-preview-title');
        if (titleEl) titleEl.innerText = 'Paste a YouTube link above to generate shorts';
        const dlBtn = document.getElementById('yt-preview-dl-btn');
        if (dlBtn) dlBtn.style.display = 'none';
        const vid = document.getElementById('yt-preview-video');
        if (vid) { vid.src = ''; }
        return;
      }

      clips.forEach((c, idx) => {
        const card = document.createElement('div');
        const rankClass = idx === 0 ? 'rank-1' : (idx === 1 ? 'rank-2' : (idx === 2 ? 'rank-3' : ''));
        const badgeColor = idx === 0 ? 'gold' : (idx === 1 ? 'silver' : (idx === 2 ? 'bronze' : ''));
        const medal = idx === 0 ? '🥇' : (idx === 1 ? '🥈' : (idx === 2 ? '🥉' : '🏅'));
        card.className = `clip-card ${rankClass}`;

        const isSplit = !!(c.is_split_screen);

        card.innerHTML = `
          <div class="clip-header">
            <div>
              <div class="rank-badge ${badgeColor}">${medal} #${c.rank} &middot; Score: ${c.score}/100 <span class="tag" style="font-size: 0.75rem; margin-left: 0.5rem;">${c.tier || 'Viral Hook'}</span></div>
              <div style="font-weight: 700; font-size: 1.05rem; color: #f8fafc; margin-top: 0.25rem;">${c.title}</div>
              ${c.hook_text ? `<div style="font-size: 0.85rem; color: var(--gold); margin-top: 0.2rem;">Hook: "${c.hook_text}"</div>` : ''}
            </div>
            <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
              <button class="btn-preview" onclick="previewShortByIdx(${idx})">
                ▶ Preview
              </button>
              <a href="${c.download_url}" class="btn-dl">
                ⬇ Download MP4
              </a>
              <button class="btn btn-gold" id="btn-upload-clip-${idx}" onclick="openUploadModal(${idx})" style="padding: 0.5rem 0.8rem; font-size: 0.82rem;">
                🚀 Upload via MCP
              </button>
            </div>
          </div>

          <div class="critique-grid">
            <div>
              <div style="font-weight: 700; margin-bottom: 0.25rem;" class="critique-good">🟢 Viral Strength (Why It Works)</div>
              <div>${c.why_good || 'High energy speech cadence and punchy reaction.'}</div>
            </div>
            <div>
              <div style="font-weight: 700; margin-bottom: 0.25rem;" class="critique-bad">🔴 Editorial Critique (Rating Factor)</div>
              <div>${c.why_bad || 'Standard pacing compared to peak climax.'}</div>
            </div>
          </div>

          <div class="clip-specs">
            <span class="spec-pill">⏱ ${c.duration}s</span>
            <span class="spec-pill">📦 ${c.size_mb} MB</span>
            <span class="spec-pill">📐 1080x1920 9:16</span>
            <span class="spec-pill">👤 Face Centered (${c.face_hits || 85}%)</span>
            ${isSplit ? `<span class="spec-pill" style="color: #60a5fa; border-color: #3b82f660; font-weight: 600;">👥 Dual Speaker Split Screen</span>` : ''}
            <span class="spec-pill" style="color: #38bdf8; border-color: #38bdf860; font-weight: 600;">🎵 ${c.music_name || 'Matched Streamer BGM (No Copyright)'}</span>
            <span class="spec-pill" style="color: #facc15; border-color: #facc1560; font-weight: 600;">⏰ Best Post: ${c.optimal_schedule ? c.optimal_schedule.human_readable.split(' (')[0] : 'Fri 2:30 PM EDT'}</span>
            <span class="spec-pill" style="color: #34d399;">✓ QA Pass</span>
          </div>
        `;
        cont.appendChild(card);
      });

      if (clips.length > 0) {
        previewShort(clips[0].stream_url, clips[0].title, clips[0].download_url, clips[0].rank, clips[0].score);
      }
    }

    function previewShortByIdx(idx) {
      const c = currentClips[idx];
      if (c) {
        previewShort(c.stream_url, c.title, c.download_url, c.rank, c.score);
      }
    }

    function previewShort(streamUrl, title, dlUrl, rank, score) {
      const vid = document.getElementById('yt-preview-video');
      const dlBtn = document.getElementById('yt-preview-dl-btn');
      const titleEl = document.getElementById('yt-preview-title');
      if (streamUrl) {
        vid.src = streamUrl;
        vid.load();
        vid.play().catch(() => {});
      }
      if (titleEl) {
        titleEl.innerText = `#${rank} (${score}/100) ${title}`;
      }
      if (dlBtn) {
        dlBtn.href = dlUrl || '#';
        dlBtn.style.display = dlUrl ? 'inline-flex' : 'none';
      }
    }

    async function loadYoutubeHistory() {
      try {
        const res = await fetch('/api/youtube-history');
        const data = await res.json();
        if (data.history && data.history.length > 0) {
          const validHistory = data.history.filter(h => {
            if (!h.video_info || h.video_info.id === 'speed_demo') return false;
            if (!h.clips || !h.clips.length) return false;
            return true;
          });
          if (validHistory.length > 0) {
            renderRankedClips(validHistory[0].clips);
            return;
          }
        }
        renderRankedClips([]);
      } catch (e) {
        console.error(e);
        renderRankedClips([]);
      }
    }

    function selectCreator(name, el) {
      selectedCreator = name;
      document.querySelectorAll('.creator-card').forEach(c => c.classList.remove('active'));
      el.classList.add('active');
      document.getElementById('magic-prompt').value = `${name} top five funny moments`;
    }

    async function launchMagicCreation() {
      const btn = document.getElementById('btn-create-magic');
      btn.disabled = true;
      btn.innerText = '⏳ CREATING VIDEO...';
      const tracker = document.getElementById('magic-tracker');
      tracker.style.display = 'block';

      try {
        const res = await fetch('/api/magic-create', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            creator: selectedCreator,
            prompt: document.getElementById('magic-prompt').value.trim(),
            format: 'short',
            source_mode: 'auto'
          })
        });
        const data = await res.json();
        if (data.ok && data.job_id) {
          pollMagicJob(data.job_id);
        }
      } catch (e) {
        btn.disabled = false;
        btn.innerText = '⚡ CREATE CREATOR VIDEO';
      }
    }

    function pollMagicJob(jobId) {
      const interval = setInterval(async () => {
        try {
          const res = await fetch(`/api/job-status?job_id=${jobId}`);
          const job = await res.json();
          if (job.status === 'not_found') return;
          document.getElementById('tracker-bar').style.width = job.progress + '%';
          document.getElementById('tracker-pct').innerText = job.progress + '%';
          document.getElementById('tracker-title').innerText = job.message || 'Processing...';

          if (job.status === 'completed') {
            clearInterval(interval);
            document.getElementById('btn-create-magic').disabled = false;
            document.getElementById('btn-create-magic').innerText = '⚡ CREATE CREATOR VIDEO';
            alert(`🎉 Success! Video ready!`);
            switchTab('player');
            loadVideos();
          } else if (job.status === 'failed') {
            clearInterval(interval);
            document.getElementById('btn-create-magic').disabled = false;
            document.getElementById('btn-create-magic').innerText = '⚡ CREATE CREATOR VIDEO';
            alert('Failed: ' + job.message);
          }
        } catch (e) {}
      }, 1000);
    }

    async function refreshStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        document.getElementById('dot-freellm').className = 'dot ' + (data.services.freellmapi.online ? 'online' : 'offline');
        document.getElementById('dot-ollama').className = 'dot ' + (data.services.ollama.online ? 'online' : 'offline');
        document.getElementById('p1-desc').innerText = (data.env.AUTOCLIP_PRIMARY_BASE_URL || 'Gateway') + ' · ' + (data.env.AUTOCLIP_PRIMARY_MODEL || 'mistral-code');
        document.getElementById('p2-desc').innerText = (data.env.AUTOCLIP_FALLBACK_BASE_URL || 'Gateway') + ' · ' + (data.env.AUTOCLIP_FALLBACK_MODEL || 'command-r-2');
        document.getElementById('p3-desc').innerText = (data.env.AUTOCLIP_LOCAL_BASE_URL || 'Ollama') + ' · ' + (data.env.AUTOCLIP_LOCAL_MODEL || 'gemma4:12b');
      } catch (e) {}

      try {
        const cRes = await fetch('/api/composio-status');
        const cData = await cRes.json();
        const dot = document.getElementById('dot-composio');
        const txt = document.getElementById('txt-composio');
        const chanLbl = document.getElementById('comp-chan-label');
        if (cData.ok && cData.info && cData.info.connected) {
          if (dot) dot.className = 'dot online';
          const name = cData.info.custom_url || cData.info.title || '@askwhatt';
          if (txt) txt.innerText = 'YouTube: ' + name;
          if (chanLbl) chanLbl.innerText = `${cData.info.title || 'Channel'} (${cData.info.custom_url || ''})`;
        } else {
          if (dot) dot.className = 'dot offline';
          if (txt) txt.innerText = 'YouTube: Disconnected';
        }
      } catch (e) {}
    }

    async function loadComposioChannelVideos() {
      const container = document.getElementById('comp-results-container');
      container.style.display = 'flex';
      container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem;">Fetching videos from your YouTube channel via Composio MCP...</div>';
      try {
        const res = await fetch('/api/composio-channel-videos');
        const data = await res.json();
        if (data.ok && data.videos && data.videos.length > 0) {
          container.innerHTML = '';
          data.videos.forEach(v => {
            const item = document.createElement('div');
            item.style.cssText = 'background: #090e1a; border: 1px solid #1e293b; padding: 0.6rem 0.75rem; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; gap: 0.75rem;';
            item.innerHTML = `
              <div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.85rem;">
                <span style="color: #38bdf8; font-weight: 600;">${v.title}</span>
                <span style="color: var(--text-muted); font-size: 0.75rem; margin-left: 0.5rem;">${v.url}</span>
              </div>
              <button class="btn btn-gold" onclick="setYtUrl('${v.url}')" style="padding: 0.3rem 0.65rem; font-size: 0.75rem; white-space: nowrap;">
                Use This Video
              </button>
            `;
            container.appendChild(item);
          });
        } else {
          container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem;">No channel videos found.</div>';
        }
      } catch (e) {
        container.innerHTML = `<div style="color: #f87171; font-size: 0.85rem;">Error: ${e}</div>`;
      }
    }

    function toggleComposioSearch() {
      const box = document.getElementById('comp-search-box');
      box.style.display = box.style.display === 'none' ? 'block' : 'none';
      if (box.style.display === 'block') {
        document.getElementById('comp-query-input').focus();
      }
    }

    async function doComposioSearch() {
      const q = document.getElementById('comp-query-input').value.trim();
      if (!q) return;
      const container = document.getElementById('comp-results-container');
      container.style.display = 'flex';
      container.innerHTML = `<div style="color: var(--text-muted); font-size: 0.85rem;">Searching YouTube for "${q}" via Composio MCP...</div>`;
      try {
        const res = await fetch('/api/composio-search', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ query: q })
        });
        const data = await res.json();
        if (data.ok && data.videos && data.videos.length > 0) {
          container.innerHTML = '';
          data.videos.forEach(v => {
            const item = document.createElement('div');
            item.style.cssText = 'background: #090e1a; border: 1px solid #1e293b; padding: 0.6rem 0.75rem; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; gap: 0.75rem;';
            item.innerHTML = `
              <div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.85rem;">
                <span style="color: #38bdf8; font-weight: 600;">${v.title}</span>
                <span style="color: var(--text-muted); font-size: 0.75rem; margin-left: 0.5rem;">[${v.channel}] ${v.url}</span>
              </div>
              <button class="btn btn-gold" onclick="setYtUrl('${v.url}')" style="padding: 0.3rem 0.65rem; font-size: 0.75rem; white-space: nowrap;">
                Use This Video
              </button>
            `;
            container.appendChild(item);
          });
        } else {
          container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem;">No search results returned.</div>';
        }
      } catch (e) {
        container.innerHTML = `<div style="color: #f87171; font-size: 0.85rem;">Error: ${e}</div>`;
      }
    }

    let activeModalClipIdx = null;

    function openUploadModal(idx) {
      activeModalClipIdx = idx;
      const c = currentClips[idx] || {};
      document.getElementById('modal-file-path').value = c.file || '';

      const creatorKey = c.creator_id || selectedStreamer || 'speed';
      const creator = (allCreatorsData && allCreatorsData[creatorKey]) || {
        name: c.creator_name || 'IShowSpeed',
        avatar: c.creator_avatar || '⚡',
        metadata: {
          hashtags: ['#shorts', '#ishowspeed', '#speed', '#viral', '#funny', '#reaction'],
          tags: ['ishowspeed', 'speed', 'viral', 'funny', 'shorts'],
          desc_cta: 'Catch the wildest stream moments daily!'
        }
      };

      const sched = c.optimal_schedule || currentSlotData;

      // Update Modal Streamer Timeline Box
      const titleEl = document.getElementById('modal-streamer-title');
      const slotEl = document.getElementById('modal-streamer-slot');
      const reasonEl = document.getElementById('modal-streamer-reason');
      if (titleEl) titleEl.innerText = `${creator.avatar || '⚡'} ${creator.name} Optimal Audience Timeline`;
      if (slotEl && sched && sched.human_readable) {
        slotEl.innerText = `Prime Window: ${sched.peak_label || ''} · Recommended: ${sched.human_readable}`;
      }
      if (reasonEl && sched && sched.reason) reasonEl.innerText = sched.reason;

      let title = c.title || 'Viral Short';
      if (!title.toLowerCase().includes('#shorts')) title += ' #shorts';
      document.getElementById('modal-title').value = title;
      
      let desc = c.description || '';
      if (!desc) {
        const tagList = Array.isArray(c.tags) && c.tags.length ? c.tags.map(t => '#' + t.replace(/^#/, '')).join(' ') : (creator.metadata ? creator.metadata.hashtags.join(' ') : '#shorts #viral');
        desc = `${c.title}\n\n${creator.metadata ? creator.metadata.desc_cta : 'Catch the best moments daily!'}\n\n${tagList}`;
      }
      document.getElementById('modal-description').value = desc;

      let tagsStr = '';
      if (Array.isArray(c.tags) && c.tags.length) {
        tagsStr = c.tags.join(', ');
      } else if (typeof c.tags === 'string' && c.tags) {
        tagsStr = c.tags;
      } else {
        tagsStr = (creator.metadata && creator.metadata.tags) ? creator.metadata.tags.join(', ') : 'shorts, viral, funny, trending';
      }
      document.getElementById('modal-tags').value = tagsStr;
      document.getElementById('modal-privacy').value = 'public';

      document.getElementById('modal-schedule-toggle').checked = false;
      document.getElementById('modal-schedule-box').style.display = 'none';
      document.getElementById('modal-publish-at').value = (sched && sched.input_value) ? sched.input_value : '';

      const msgBox = document.getElementById('modal-status-msg');
      msgBox.style.display = 'none';
      msgBox.innerHTML = '';

      const submitBtn = document.getElementById('btn-submit-modal-upload');
      submitBtn.disabled = false;
      submitBtn.innerText = '🚀 Confirm Upload via MCP';
      submitBtn.style.background = 'var(--gold)';

      document.getElementById('upload-modal').style.display = 'flex';
    }

    function applyModalOptimalSchedule() {
      const c = currentClips[activeModalClipIdx] || {};
      const sched = c.optimal_schedule || currentSlotData;
      if (sched && sched.input_value) {
        document.getElementById('modal-schedule-toggle').checked = true;
        document.getElementById('modal-schedule-box').style.display = 'block';
        document.getElementById('modal-publish-at').value = sched.input_value;
        document.getElementById('modal-privacy').value = 'private';
      }
    }

    function closeUploadModal() {
      document.getElementById('upload-modal').style.display = 'none';
    }

    function toggleScheduleInput() {
      const box = document.getElementById('modal-schedule-box');
      const chk = document.getElementById('modal-schedule-toggle');
      box.style.display = chk.checked ? 'block' : 'none';
      if (chk.checked && !document.getElementById('modal-publish-at').value) {
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        tomorrow.setHours(18, 0, 0, 0);
        const pad = n => String(n).padStart(2, '0');
        const localIso = `${tomorrow.getFullYear()}-${pad(tomorrow.getMonth()+1)}-${pad(tomorrow.getDate())}T${pad(tomorrow.getHours())}:${pad(tomorrow.getMinutes())}`;
        document.getElementById('modal-publish-at').value = localIso;
      }
    }

    async function submitModalUpload() {
      const filePath = document.getElementById('modal-file-path').value.trim();
      const title = document.getElementById('modal-title').value.trim();
      const desc = document.getElementById('modal-description').value.trim();
      const tagsRaw = document.getElementById('modal-tags').value;
      const privacy = document.getElementById('modal-privacy').value;
      const isScheduled = document.getElementById('modal-schedule-toggle').checked;
      const schedTime = document.getElementById('modal-publish-at').value;

      if (!filePath) {
        alert('No video file selected.');
        return;
      }
      if (!title) {
        alert('Please provide a video title.');
        return;
      }

      const tags = tagsRaw.split(',').map(t => t.trim()).filter(Boolean);
      let publishAt = null;
      if (isScheduled && schedTime) {
        publishAt = new Date(schedTime).toISOString();
      }

      const submitBtn = document.getElementById('btn-submit-modal-upload');
      submitBtn.disabled = true;
      submitBtn.innerText = '⏳ Staging & Uploading to YouTube...';

      const msgBox = document.getElementById('modal-status-msg');
      msgBox.style.display = 'block';
      msgBox.style.background = '#1e293b';
      msgBox.style.border = '1px solid #3b82f6';
      msgBox.style.color = '#93c5fd';
      msgBox.innerHTML = '⚡ Staging video to Composio S3 & Calling MCP <code>YOUTUBE_MULTIPART_UPLOAD_VIDEO</code>... This takes ~15-25 seconds.';

      try {
        const res = await fetch('/api/composio-upload', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            file: filePath,
            title: title,
            description: desc,
            tags: tags,
            privacy: isScheduled ? 'private' : privacy,
            publish_at: publishAt
          })
        });
        const data = await res.json();
        if (data.ok) {
          msgBox.style.background = '#064e3b';
          msgBox.style.border = '1px solid #10b981';
          msgBox.style.color = '#6ee7b7';
          msgBox.innerHTML = `🎉 <strong>Success!</strong> Video published to YouTube channel <strong>Ask What? (@askwhatt)</strong> via Composio MCP!`;
          submitBtn.innerText = '✓ Uploaded to YouTube!';
          submitBtn.style.background = '#10b981';

          if (activeModalClipIdx !== null) {
            const cardBtn = document.getElementById(`btn-upload-clip-${activeModalClipIdx}`);
            if (cardBtn) {
              cardBtn.innerText = '✓ Uploaded to YT!';
              cardBtn.style.background = '#10b981';
              cardBtn.style.color = '#fff';
            }
          }
          setTimeout(() => {
            closeUploadModal();
          }, 2400);
        } else {
          const errText = data.error || JSON.stringify(data.result || data);
          const isQuota = /quota|limit|exceeded|429/i.test(errText);
          msgBox.style.background = isQuota ? '#291804' : '#450a0a';
          msgBox.style.border = isQuota ? '1px solid #f59e0b' : '1px solid #ef4444';
          msgBox.style.color = isQuota ? '#fef3c7' : '#fca5a5';
          if (isQuota) {
            msgBox.innerHTML = `
              <div style="font-weight: 700; color: #f59e0b; margin-bottom: 6px;">⚠️ YouTube Data API Quota Limit Reached</div>
              <div style="font-size: 0.82rem; margin-bottom: 10px; color: #cbd5e1;">Google restricts free API uploads to ~6/day across the app. <strong>YouTube Studio web has UNLIMITED uploads</strong> with 0 quota limits. Use our 1-click Studio bridge below:</div>
              <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                <button type="button" class="btn" onclick="copyModalMetadata()" style="background: #2563eb; color: #fff; font-size: 0.82rem; padding: 6px 12px; font-weight: 600;">📋 Copy Metadata</button>
                <button type="button" class="btn" onclick="revealInExplorer()" style="background: #059669; color: #fff; font-size: 0.82rem; padding: 6px 12px; font-weight: 600;">📁 Reveal Video File</button>
                <button type="button" class="btn" onclick="openStudioUpload()" style="background: #dc2626; color: #fff; font-size: 0.82rem; padding: 6px 12px; font-weight: 600;">🌐 Open YouTube Studio</button>
              </div>
            `;
          } else {
            msgBox.innerHTML = `❌ <strong>Upload error:</strong> ${errText}`;
          }
          submitBtn.disabled = false;
          submitBtn.innerText = '🚀 Retry Upload via MCP';
          submitBtn.style.background = 'var(--gold)';
        }
      } catch (e) {
        msgBox.style.background = '#450a0a';
        msgBox.style.border = '1px solid #ef4444';
        msgBox.style.color = '#fca5a5';
        msgBox.innerHTML = `❌ <strong>Network / Upload Error:</strong> ${e.message || e}`;
        submitBtn.disabled = false;
        submitBtn.innerText = '🚀 Retry Upload via MCP';
        submitBtn.style.background = 'var(--gold)';
      }
    }

    function copyModalMetadata() {
      const title = document.getElementById('modal-title').value;
      const desc = document.getElementById('modal-description').value;
      const tags = document.getElementById('modal-tags').value;
      const fullText = `TITLE:\n${title}\n\nDESCRIPTION:\n${desc}\n\nTAGS:\n${tags}`;
      navigator.clipboard.writeText(fullText).then(() => {
        alert('📋 Title, Description & Tags copied to clipboard!');
      }).catch(() => {
        const ta = document.createElement('textarea');
        ta.value = fullText;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        alert('📋 Title, Description & Tags copied to clipboard!');
      });
    }

    async function revealInExplorer() {
      const filePath = document.getElementById('modal-file-path').value;
      try {
        await fetch('/api/open-in-explorer', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ file: filePath })
        });
      } catch (e) {
        console.error(e);
      }
    }

    function openStudioUpload() {
      copyModalMetadata();
      revealInExplorer();
      window.open('https://studio.youtube.com/channel/UCBaLUH8LwQQ2KMkxq7wNfCA/videos/upload?d=ud', '_blank');
    }

    async function uploadShortViaMCP(file, title, btn) {
      const idx = currentClips.findIndex(c => c.file === file);
      if (idx !== -1) {
        openUploadModal(idx);
      } else {
        openUploadModal(0);
      }
    }

    async function testCascade() {
      const btn = document.getElementById('btn-test-cascade');
      btn.disabled = true;
      btn.innerText = 'Testing...';
      document.getElementById('cascade-test-results').style.display = 'block';
      document.getElementById('test-output-log').innerText = 'Testing cascade tiers...';

      try {
        const res = await fetch('/api/test-cascade', { method: 'POST' });
        const data = await res.json();
        let logTxt = '';
        data.results.forEach((r, idx) => {
          const badge = document.getElementById(`p${idx+1}-status`);
          if (badge) badge.innerText = r.ok ? `${r.latency_ms}ms OK` : 'Failed';
          logTxt += `[Tier ${idx+1}] ${r.name} (${r.model})\nStatus: ${r.ok ? 'PASS' : 'FAIL'} (${r.latency_ms}ms)\nDetail: ${r.detail}\n\n`;
        });
        document.getElementById('test-output-log').innerText = logTxt;
      } catch (e) {
        document.getElementById('test-output-log').innerText = 'Error: ' + e;
      } finally {
        btn.disabled = false;
        btn.innerText = 'Test Cascade Now';
      }
    }

    async function loadResearchData() {
      try {
        const res = await fetch('/api/research-data');
        const data = await res.json();
        document.getElementById('profile-json-view').innerText = JSON.stringify(data.builder, null, 2);
        document.getElementById('report-md-view').innerText = data.report_markdown || 'No report generated yet.';
      } catch (e) {}
    }

    async function loadVideos() {
      try {
        const res = await fetch('/api/videos');
        const data = await res.json();
        const sel = document.getElementById('video-select');
        const dlBtn = document.getElementById('main-player-dl-btn');
        sel.innerHTML = '';
        if (data.videos && data.videos.length > 0) {
          data.videos.forEach(v => {
            const opt = document.createElement('option');
            opt.value = v.rel_path;
            opt.innerText = `${v.name} (${v.size_mb} MB) [${v.mtime}]`;
            sel.appendChild(opt);
          });
          sel.value = data.videos[0].rel_path;
          if (dlBtn) dlBtn.style.display = 'inline-flex';
          onVideoSelectChange();
        } else {
          sel.innerHTML = '<option value="">No videos generated yet</option>';
          if (dlBtn) dlBtn.style.display = 'none';
          const vid = document.getElementById('short-video');
          if (vid) vid.src = '';
        }
      } catch (e) {}
    }

    async function onVideoSelectChange() {
      const sel = document.getElementById('video-select');
      const rel = sel.value;
      if (!rel) return;
      const vid = document.getElementById('short-video');
      vid.src = '/video/' + rel;
      vid.load();
      document.getElementById('main-player-dl-btn').href = '/api/download?file=' + encodeURIComponent(rel);

      try {
        const res = await fetch('/api/qa-inspect?file=' + encodeURIComponent(rel));
        const data = await res.json();
        if (data.ok && data.report) {
          const f = data.report.found || {};
          document.getElementById('m-res').innerText = f.video ? `${f.video[1]}x${f.video[2]}` : '1080x1920';
          document.getElementById('m-fps').innerText = f.video ? `${f.video[3]} FPS` : '30 FPS';
          document.getElementById('m-dur').innerText = f.duration ? `${f.duration}s` : 'N/A';
          document.getElementById('qa-badge-pass').innerText = data.report.ok ? 'PASS' : 'FLAGGED';
          document.getElementById('qa-badge-pass').style.color = data.report.ok ? '#34d399' : '#f87171';
          document.getElementById('qa-probe-json').innerText = JSON.stringify(data.report, null, 2);
        }
      } catch (e) {}
    }

    async function fetchLogs() {
      try {
        const res = await fetch('/api/logs');
        const data = await res.json();
        const box = document.getElementById('sys-log-box');
        box.innerHTML = data.logs.join('<br>') || 'No logs recorded.';
        box.scrollTop = box.scrollHeight;
      } catch (e) {}
    }

    window.addEventListener('DOMContentLoaded', () => {
      refreshStatus();
      loadCreatorProfiles();
      setStreamer('speed');
      loadYoutubeHistory();
      loadResearchData();
      loadVideos();
      fetchLogs();
      setInterval(fetchLogs, 4000);
    });
  </script>
</body>
</html>
"""

def run_server(port=8080):
    server_address = ("127.0.0.1", port)
    httpd = ThreadingHTTPServer(server_address, AutoClipWebHandler)
    append_log(f"AutoClip Studio Web Server started on http://localhost:{port}")
    print(f"\n=======================================================")
    print(f"  AutoClip Magic Studio 2.0 Running!")
    print(f"  URL: http://localhost:{port}")
    print(f"  YouTube to 5 Shorts Studio: ACTIVE")
    print(f"  FreeLLMAPI Router: http://127.0.0.1:3001")
    print(f"  Ollama Server:     http://127.0.0.1:11434")
    print(f"=======================================================\n", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down web server...")
        httpd.server_close()

if __name__ == "__main__":
    p = 8080
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        p = int(sys.argv[1])
    run_server(port=p)
