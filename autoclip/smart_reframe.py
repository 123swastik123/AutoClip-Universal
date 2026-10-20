"""Smart Multi-Speaker & Dynamic Face-Tracking 9:16 Reframe Engine.

Features:
1. Multi-face & profile detection via OpenCV (alt2 + profileface + upperbody)
2. Automatic Two-Person Conversation Detection -> Stacked 9:16 Split Screen
   (Person 1 top 1080x960, Person 2 bottom 1080x960, with subtle divider)
3. Dynamic Active Speaker Tracking for Solo Creators (Speed, Kai, etc.)
   - Anchor memory (never snaps to 0.5 when looking down/screaming)
   - Deadband & Exponential Moving Average (EMA) camera smoothing
   - Keeps the creator centered and 100% in frame across reactions
"""
import os, sys, json, math, subprocess
import cv2
import numpy as np

CASCADE_DIR = cv2.data.haarcascades
FRONTAL_ALT2 = os.path.join(CASCADE_DIR, "haarcascade_frontalface_alt2.xml")
FRONTAL_DEF = os.path.join(CASCADE_DIR, "haarcascade_frontalface_default.xml")
PROFILE = os.path.join(CASCADE_DIR, "haarcascade_profileface.xml")

_clf_alt2 = cv2.CascadeClassifier(FRONTAL_ALT2)
_clf_def = cv2.CascadeClassifier(FRONTAL_DEF)
_clf_prof = cv2.CascadeClassifier(PROFILE)

YUNET_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models", "face_detection_yunet_2023mar.onnx")
BLAZEFACE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models", "blaze_face_short_range.tflite")

_yunet_detector = None
if os.path.exists(YUNET_PATH):
    try:
        _yunet_detector = cv2.FaceDetectorYN.create(YUNET_PATH, "", (320, 180), score_threshold=0.45, nms_threshold=0.3)
    except Exception as e:
        print(f"[Smart Reframe Warning] YuNet init error: {e}")

_mp_detector = None
if os.path.exists(BLAZEFACE_PATH):
    try:
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision
        import mediapipe as mp
        _base_opts = mp_python.BaseOptions(model_asset_path=BLAZEFACE_PATH)
        _opts = mp_vision.FaceDetectorOptions(base_options=_base_opts)
        _mp_detector = mp_vision.FaceDetector.create_from_options(_opts)
    except Exception as e:
        print(f"[Smart Reframe Warning] MediaPipe init error: {e}")

def detect_faces_in_frame(frame_or_gray):
    """Detect all prominent faces using YuNet / MediaPipe neural models with Haar fallback."""
    if len(frame_or_gray.shape) == 2:
        gray = frame_or_gray
        bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    else:
        bgr = frame_or_gray
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    h, w = bgr.shape[:2]
    out = []

    # 1. Primary Neural Engine: OpenCV YuNet (Deep CNN with 5 facial landmarks)
    if _yunet_detector is not None:
        try:
            _yunet_detector.setInputSize((w, h))
            _, faces = _yunet_detector.detect(bgr)
            if faces is not None and len(faces) > 0:
                for f in faces:
                    x, y, fw, fh = float(f[0]), float(f[1]), float(f[2]), float(f[3])
                    score = float(f[-1])
                    cx = (x + fw / 2.0) / float(w)
                    cy = (y + fh / 2.0) / float(h)
                    area = (fw * fh) / float(w * h)
                    out.append({
                        "cx": max(0.0, min(1.0, cx)),
                        "cy": max(0.0, min(1.0, cy)),
                        "w": fw / float(w),
                        "h": fh / float(h),
                        "area": area,
                        "score": score,
                        "box": (int(x), int(y), int(fw), int(fh)),
                        "detector": "yunet_neural"
                    })
                out.sort(key=lambda item: item["area"], reverse=True)
                return out
        except Exception as e:
            pass

    # 2. Secondary Neural Engine: Google MediaPipe BlazeFace
    if _mp_detector is not None:
        try:
            import mediapipe as mp
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            res = _mp_detector.detect(mp_img)
            if res.detections:
                for d in res.detections:
                    box = d.bounding_box
                    score = d.categories[0].score if d.categories else 0.8
                    x, y, fw, fh = float(box.origin_x), float(box.origin_y), float(box.width), float(box.height)
                    cx = (x + fw / 2.0) / float(w)
                    cy = (y + fh / 2.0) / float(h)
                    area = (fw * fh) / float(w * h)
                    out.append({
                        "cx": max(0.0, min(1.0, cx)),
                        "cy": max(0.0, min(1.0, cy)),
                        "w": fw / float(w),
                        "h": fh / float(h),
                        "area": area,
                        "score": score,
                        "box": (int(x), int(y), int(fw), int(fh)),
                        "detector": "mediapipe_neural"
                    })
                out.sort(key=lambda item: item["area"], reverse=True)
                return out
        except Exception as e:
            pass

    # 3. Fallback: Classical Haar Cascades (frontalface_alt2 + profileface)
    min_size = (max(16, int(w * 0.04)), max(16, int(h * 0.04)))
    faces = list(_clf_alt2.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=min_size))
    if len(faces) < 2:
        profs = list(_clf_prof.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=4, minSize=min_size))
        for (px, py, pw, ph) in profs:
            overlap = False
            for (fx, fy, fw, fh) in faces:
                if abs((px + pw/2) - (fx + fw/2)) < (fw * 0.7) and abs((py + ph/2) - (fy + fh/2)) < (fh * 0.7):
                    overlap = True
                    break
            if not overlap:
                faces.append((px, py, pw, ph))

    if not len(faces):
        faces = list(_clf_def.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=min_size))

    for (x, y, fw, fh) in faces:
        cx = (x + fw / 2.0) / float(w)
        cy = (y + fh / 2.0) / float(h)
        area = (fw * fh) / float(w * h)
        out.append({
            "cx": cx,
            "cy": cy,
            "w": fw / float(w),
            "h": fh / float(h),
            "area": area,
            "score": 0.5,
            "box": (x, y, fw, fh),
            "detector": "haar_cascade"
        })
    out.sort(key=lambda f: f["area"], reverse=True)
    return out

def analyze_speaker_tracking(video_path, sample_step=0.35):
    """Scan video and determine whether it's a Two-Person Conversation or Single Speaker."""
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    dur = total_frames / fps if total_frames > 0 else 10.0
    
    in_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920)
    in_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1080)

    step = max(1, int(round(fps * sample_step)))
    
    samples = []  # list of {"t": t, "faces": [...]}
    i = 0

    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if i % step == 0:
            t = i / fps
            scale = 360.0 / in_w if in_w > 360 else 1.0
            small_w = int(in_w * scale)
            small_h = int(in_h * scale)
            small_fr = cv2.resize(fr, (small_w, small_h), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small_fr, cv2.COLOR_BGR2GRAY)
            faces = detect_faces_in_frame(small_fr)
            samples.append({"t": t, "faces": faces})
        i += 1
    cap.release()

    if not samples:
        return {
            "mode": "single_track",
            "in_w": in_w, "in_h": in_h, "dur": dur,
            "is_two_people": False,
            "hits": 0.0,
            "cx_default": 0.5,
            "trajectory": [(0.0, 0.5), (dur, 0.5)]
        }

    # Evaluate whether 2 distinct people are present
    two_face_hits = 0
    person1_points = []
    person2_points = []
    all_single_points = []

    for s in samples:
        fcs = s["faces"]
        if len(fcs) >= 2:
            # Check horizontal distance between top 2 faces
            f1, f2 = fcs[0], fcs[1]
            dist = abs(f1["cx"] - f2["cx"])
            if dist >= 0.18:
                two_face_hits += 1
                left_f = f1 if f1["cx"] < f2["cx"] else f2
                right_f = f2 if f1["cx"] < f2["cx"] else f1
                person1_points.append(left_f)
                person2_points.append(right_f)
        if len(fcs) >= 1:
            all_single_points.append((s["t"], fcs[0]))

    ratio_two = two_face_hits / float(len(samples))
    is_two_people = (ratio_two >= 0.22 and len(person1_points) >= 4)

    if is_two_people:
        # Two-Person Mode (Split Screen)
        p1_cx = float(np.median([p["cx"] for p in person1_points]))
        p1_cy = float(np.median([p["cy"] for p in person1_points]))
        p2_cx = float(np.median([p["cx"] for p in person2_points]))
        p2_cy = float(np.median([p["cy"] for p in person2_points]))

        return {
            "mode": "split_two",
            "in_w": in_w, "in_h": in_h, "dur": dur,
            "is_two_people": True,
            "ratio_two": round(ratio_two, 2),
            "person1": {"cx": round(p1_cx, 3), "cy": round(p1_cy, 3)},
            "person2": {"cx": round(p2_cx, 3), "cy": round(p2_cy, 3)},
            "hits": round((len(person1_points) + len(all_single_points)) / (2.0 * len(samples)), 2)
        }

    # Single-Speaker Dynamic Tracking Mode
    # Compute robust trajectory with anchor memory & EMA smoothing
    raw_trajectory = []
    last_known_cx = 0.5
    if all_single_points:
        # Initial anchor is median of top confident detections
        last_known_cx = float(np.median([p[1]["cx"] for p in all_single_points[:max(5, len(all_single_points)//2)]]))

    for s in samples:
        t = s["t"]
        if s["faces"]:
            # Pick face closest to last known position to prevent jumping
            best_face = min(s["faces"], key=lambda f: abs(f["cx"] - last_known_cx))
            cx = best_face["cx"]
            last_known_cx = cx
            raw_trajectory.append((t, cx, True))
        else:
            # Hold last known position (Anchor Memory)
            raw_trajectory.append((t, last_known_cx, False))

    # Apply Exponential Moving Average (EMA) and deadband
    smooth_traj = []
    current_smoothed = raw_trajectory[0][1] if raw_trajectory else 0.5
    deadband = 0.035  # don't jitter for micro-movements < 3.5%
    alpha = 0.28      # smoothing factor

    for (t, cx, is_hit) in raw_trajectory:
        diff = cx - current_smoothed
        if abs(diff) > deadband:
            current_smoothed += alpha * diff
        smooth_traj.append((round(t, 2), round(float(current_smoothed), 3)))

    hits_count = len(all_single_points)
    hit_rate = round(hits_count / float(len(samples)), 2)

    face_cx = 0.18
    face_cy = 0.72
    if all_single_points:
        face_cx = float(np.median([p[1]["cx"] for p in all_single_points]))
        face_cy = float(np.median([p[1]["cy"] for p in all_single_points]))
    elif person1_points:
        face_cx = float(np.median([p["cx"] for p in person1_points]))
        face_cy = float(np.median([p["cy"] for p in person1_points]))

    return {
        "mode": "single_track",
        "in_w": in_w, "in_h": in_h, "dur": dur,
        "is_two_people": False,
        "hits": hit_rate,
        "face_box": {"cx": round(face_cx, 3), "cy": round(face_cy, 3)},
        "cx_anchor": round(last_known_cx, 3),
        "trajectory": smooth_traj
    }

def generate_reframe_filter(tracking_info):
    """Generate the FFmpeg video filter for 1080x1920 9:16 vertical reframe."""
    in_w = tracking_info["in_w"]
    in_h = tracking_info["in_h"]
    creator = (tracking_info.get("creator") or "").lower()
    mode = tracking_info.get("mode")
    force_split = bool(tracking_info.get("force_split", False))
    is_gaming = bool(tracking_info.get("is_gaming", False) or creator in ["jynxzi", "caseoh"])

    # Mode 1: Explicit or Speed creator blur_fill (MrBeast cinematic style)
    # Scales the main 16:9 clip into center with blurred, extended, darkened video behind it
    if mode == "blur_fill" or (creator == "speed" and not force_split and not tracking_info.get("is_two_people")):
        filter_str = (
            f"[0:v]split=2[v_bg][v_fg];"
            f"[v_bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=32,eq=brightness=-0.16[bg];"
            f"[v_fg]scale=1080:-2:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p"
        )
        return filter_str, {"split_screen": False, "mode": "blur_fill"}

    # Mode 2: Two-person conversation split screen (Person 1 Top, Person 2 Bottom)
    if tracking_info.get("is_two_people") and not is_gaming:
        p1 = tracking_info.get("person1", {"cx": 0.30, "cy": 0.50})
        p2 = tracking_info.get("person2", {"cx": 0.70, "cy": 0.50})
        
        # Crop 9:8 aspect ratio for each speaker (half vertical height)
        crop_h = int(round(in_h * 0.85))
        crop_w = int(round(crop_h * 9.0 / 8.0))
        if crop_w % 2 != 0: crop_w -= 1
        if crop_h % 2 != 0: crop_h -= 1
        crop_w = min(crop_w, in_w)
        crop_h = min(crop_h, in_h)

        x_p1 = max(0, min(in_w - crop_w, int(p1["cx"] * in_w - crop_w / 2.0)))
        y_p1 = max(0, min(in_h - crop_h, int(p1["cy"] * in_h - crop_h * 0.45)))

        x_p2 = max(0, min(in_w - crop_w, int(p2["cx"] * in_w - crop_w / 2.0)))
        y_p2 = max(0, min(in_h - crop_h, int(p2["cy"] * in_h - crop_h * 0.45)))

        filter_str = (
            f"[0:v]split=2[in_p1][in_p2];"
            f"[in_p1]crop={crop_w}:{crop_h}:{x_p1}:{y_p1},scale=1080:960:flags=lanczos[top_p1];"
            f"[in_p2]crop={crop_w}:{crop_h}:{x_p2}:{y_p2},scale=1080:960:flags=lanczos[bot_p2];"
            f"[top_p1][bot_p2]vstack=inputs=2[stacked];"
            f"[stacked]drawbox=x=0:y=958:w=1080:h=4:color=0xFFD200@0.90:t=fill,format=yuv420p"
        )
        return filter_str, {"split_screen": True, "mode": "split_two_speakers"}

    # Mode 3: Streamer Gameplay + Facecam Split Screen
    if force_split or (tracking_info.get("mode") == "split_two" and is_gaming) or (is_gaming and tracking_info.get("hits", 0) > 0.20):
        face_info = tracking_info.get("face_box") or tracking_info.get("person1") or {}
        face_cx = face_info.get("cx", tracking_info.get("cx_anchor", 0.18))
        face_cy = face_info.get("cy", 0.72)

        # 1. Creator Facecam (Bottom Half):
        face_crop_h = int(round(in_h * 0.36))
        face_crop_w = int(round(face_crop_h * 9.0 / 8.0))
        if face_crop_w % 2 != 0: face_crop_w -= 1
        if face_crop_h % 2 != 0: face_crop_h -= 1
        face_crop_w = min(face_crop_w, in_w)
        face_crop_h = min(face_crop_h, in_h)

        x_face = max(0, min(in_w - face_crop_w, int(face_cx * in_w - face_crop_w / 2.0)))
        y_face = max(0, min(in_h - face_crop_h, int(face_cy * in_h - face_crop_h * 0.42)))

        # 2. Gameplay Action (Top Half):
        game_crop_h = in_h
        game_crop_w = int(round(game_crop_h * 9.0 / 8.0))
        if game_crop_w % 2 != 0: game_crop_w -= 1
        if game_crop_h % 2 != 0: game_crop_h -= 1
        game_crop_w = min(game_crop_w, in_w)
        game_crop_h = min(game_crop_h, in_h)

        # Position gameplay away from facecam
        if face_cx < 0.45:
            x_game = max(0, in_w - game_crop_w)
        elif face_cx > 0.55:
            x_game = 0
        else:
            x_game = max(0, min(in_w - game_crop_w, int((in_w - game_crop_w) / 2.0)))
        y_game = 0

        filter_str = (
            f"[0:v]split=2[in_g][in_f];"
            f"[in_g]crop={game_crop_w}:{game_crop_h}:{x_game}:{y_game},scale=1080:960:flags=lanczos,setsar=1[top_game];"
            f"[in_f]crop={face_crop_w}:{face_crop_h}:{x_face}:{y_face},scale=1080:960:flags=lanczos,setsar=1[bot_face];"
            f"[top_game][bot_face]vstack=inputs=2[stacked_raw];"
            f"[stacked_raw]drawbox=x=0:y=958:w=1080:h=4:color=0xFFD200@0.90:t=fill,setsar=1,setdar=9/16[reframe_out]"
        )
        return filter_str, {"split_screen": True, "face_cx": face_cx, "face_cy": face_cy}

    else:
        # Single-Speaker Dynamic Tracking (9:16 Portrait)
        # If face detection rate is too low (< 15%), automatically use blurred fill background to prevent cutting off crucial action
        if tracking_info.get("hits", 0) < 0.15 and not tracking_info.get("force_crop"):
            filter_str = (
                f"[0:v]split=2[v_bg][v_fg];"
                f"[v_bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=30,eq=brightness=-0.12[bg];"
                f"[v_fg]scale=1080:-2:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p"
            )
            return filter_str, {"split_screen": False, "mode": "blur_fill"}

        crop_h = in_h
        crop_w = int(round(in_h * 9.0 / 16.0))
        if crop_w % 2 != 0: crop_w -= 1
        max_x = max(0, in_w - crop_w)

        traj = tracking_info.get("trajectory", [])
        if not traj:
            cx_anchor = tracking_info.get("cx_anchor", 0.5)
            x_static = int(round(max(0, min(max_x, cx_anchor * in_w - crop_w / 2.0))))
            return f"crop={crop_w}:{crop_h}:{x_static}:0,scale=1080:1920:flags=lanczos,format=yuv420p", {"split_screen": False}

        # Build smooth time-based piecewise expression:
        keyframes = [traj[0]]
        for pt in traj[1:]:
            if pt[0] - keyframes[-1][0] >= 1.0 or abs(pt[1] - keyframes[-1][1]) >= 0.08:
                keyframes.append(pt)
        if traj[-1][0] > keyframes[-1][0]:
            keyframes.append(traj[-1])

        if len(keyframes) == 1:
            cx = keyframes[0][1]
            x_pos = int(round(max(0, min(max_x, cx * in_w - crop_w / 2.0))))
            return f"crop={crop_w}:{crop_h}:{x_pos}:0,scale=1080:1920:flags=lanczos,format=yuv420p", {"split_screen": False}

        expr = f"{keyframes[-1][1]:.3f}"
        for idx in range(len(keyframes) - 1, 0, -1):
            t_prev, cx_prev = keyframes[idx - 1]
            t_curr, cx_curr = keyframes[idx]
            dt = max(0.01, t_curr - t_prev)
            segment_expr = f"({cx_prev:.3f}+({cx_curr - cx_prev:.3f})*(t-{t_prev:.2f})/{dt:.2f})"
            expr = f"if(lt(t,{t_curr:.2f}),{segment_expr},{expr})"

        xc_expr = f"min({max_x},max(0,({expr})*{in_w}-{crop_w / 2.0:.1f}))"
        filter_str = f"crop={crop_w}:{crop_h}:'{xc_expr}':0,scale=1080:1920:flags=lanczos,format=yuv420p"
        return filter_str, {"split_screen": False, "keyframes": len(keyframes)}
