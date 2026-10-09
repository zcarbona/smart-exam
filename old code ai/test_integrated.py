"""
Integrated test: combines ALL detection modules with the scoring system.

Pipeline per frame:
    Camera -> Brightness Enhancement
           -> Person Detection (YOLO) -> Pose Estimation (MediaPipe)
           -> Face Detection -> Head Pose -> Eye Gaze
           -> Object Detection (mobile) -> Leaning Analysis
           -> Desk Zone Check -> Scoring Engine -> HUD display

Run with: python test_integrated.py
Press 'q' to quit.

Setup phase (~1 sec): sit still, system learns your desk zone.
Monitoring phase: all violations tracked + scored live.

TIPS:
- Keep your head centered for the first few seconds after setup so the
  gaze baseline can calibrate (watch the "Baseline" line on screen).
- Good lighting improves detection accuracy significantly. The code
  applies a brightness boost automatically, but natural or desk light helps.
- Head pose detection may fail at very extreme angles (>60 deg yaw) --
  those are logged as "detection_lost" events automatically.
"""
import cv2
import time

from camera_capture import CameraCapture
from face_detector import FaceDetector, HeadPoseEstimator
from eye_gaze import EyeGazeEstimator
from person_detector import PersonDetector, PoseEstimator
from boundary_zones import DeskZoneManager, BoundaryZoneAnalyzer, ZoneThresholds
from object_detector import ObjectDetector
from scoring_system import StudentScoringEngine, ScoringRules

# ── Constants ────────────────────────────────────────────────────────────────
STUDENT_ID = 1

# Brightness / contrast boost for dim environments.
# alpha: contrast multiplier (1.0 = no change, 1.3 = 30% more contrast)
# beta:  brightness additive  (0 = no change, 20 = noticeably brighter)
BRIGHTNESS_ALPHA = 1.3
BRIGHTNESS_BETA = 20

STATUS_COLORS = {
    "safe":      (0, 255, 0),
    "warning":   (0, 255, 255),
    "violation": (0, 0, 255),
}

PRESENCE_COLORS = {
    "present":              (0, 255, 0),
    "temporarily_missing":  (0, 255, 255),
    "warning_missing":      (0, 165, 255),
    "exited":               (0, 0, 255),
}

GAZE_COLORS = {
    "Eyes Left":   (0, 0, 255),
    "Eyes Right":  (0, 0, 255),
    "Eyes Up":     (0, 255, 255),
    "Eyes Down":   (0, 255, 255),
    "Eyes Center": (0, 255, 0),
    "N/A":         (100, 100, 100),
}


# ── HUD Drawing ──────────────────────────────────────────────────────────────

def draw_hud(frame, record, gaze_dir, gaze_h_ratio,
             yaw, pitch, zone_status, objects, faces_count,
             head_pose_ok, current_fps):
    h, w = frame.shape[:2]

    # ── FPS (top right corner) ───────────────────────────────────────────
    fps_color = (0, 255, 0) if current_fps >= 15 else (0, 165, 255) if current_fps >= 8 else (0, 0, 255)
    cv2.putText(frame, f"FPS: {current_fps}", (w - 120, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, fps_color, 2)

    # ── Score (top left) ────────────────────────────────────────────────
    score_color = (0, 0, 255) if record.score >= 10 else (0, 255, 255)
    cv2.putText(frame, f"Score: {record.score:.0f} / 10",
                (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.9, score_color, 2)

    # Score progress bar
    bar_w = 200
    filled = int(min(record.score / 10, 1.0) * bar_w)
    cv2.rectangle(frame, (10, 45), (10 + bar_w, 58), (50, 50, 50), -1)
    cv2.rectangle(frame, (10, 45), (10 + filled, 58), score_color, -1)

    # Suspicious banner
    if record.score >= 10:
        cv2.rectangle(frame, (0, 62), (w, 88), (0, 0, 180), -1)
        cv2.putText(frame, "!! SUSPICIOUS STUDENT !!",
                    (w // 2 - 160, 82),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    y = 105

    # ── Presence state ───────────────────────────────────────────────────
    presence_color = PRESENCE_COLORS.get(record.presence_state.value, (255, 255, 255))
    cv2.putText(frame, f"State : {record.presence_state.value.replace('_', ' ').upper()}",
                (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, presence_color, 2)
    y += 25

    # ── Head pose (or failure indicator) ────────────────────────────────
    if head_pose_ok:
        yaw_color = (0, 0, 255) if abs(yaw) > 20 else (200, 200, 200)
        pitch_color = (0, 0, 255) if pitch < -15 else (200, 200, 200)
        cv2.putText(frame, f"Yaw   : {yaw:+.1f} deg",
                    (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, yaw_color, 2)
        y += 22
        cv2.putText(frame, f"Pitch : {pitch:+.1f} deg",
                    (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, pitch_color, 2)
    else:
        cv2.putText(frame, "Pose  : DETECTION FAILED",
                    (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 100, 255), 2)
        y += 22
        cv2.putText(frame, "(extreme angle or poor lighting)",
                    (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 100, 100), 1)
    y += 25

    # ── Eye gaze ─────────────────────────────────────────────────────────
    gaze_color = GAZE_COLORS.get(gaze_dir, (200, 200, 200))
    cv2.putText(frame, f"Gaze  : {gaze_dir}",
                (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, gaze_color, 2)
    y += 22

    # ── Gaze baseline calibration status ─────────────────────────────────
    if record.gaze_baseline_samples > 0:
        baseline_text = (
            f"Baseline H: {record.gaze_baseline_h:.2f} "
            f"(n={record.gaze_baseline_samples})"
        )
        # Green once we have enough samples to be reliable (~30+)
        baseline_color = (0, 255, 0) if record.gaze_baseline_samples > 30 else (0, 255, 255)
    else:
        baseline_text = "Baseline: calibrating... keep head centered"
        baseline_color = (0, 165, 255)
    cv2.putText(frame, baseline_text, (10, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, baseline_color, 1)
    y += 25

    # ── Combined sideways alert ──────────────────────────────────────────
    if head_pose_ok and abs(yaw) > 20:
        direction = "RIGHT" if yaw > 0 else "LEFT"
        cv2.putText(frame, f"!! LOOKING {direction} !!",
                    (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        y += 25

    # ── Zone status ──────────────────────────────────────────────────────
    if zone_status:
        zcolor = STATUS_COLORS.get(zone_status, (200, 200, 200))
        cv2.putText(frame, f"Zone  : {zone_status.upper()}",
                    (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, zcolor, 2)
        y += 25

    # ── Multiple faces ───────────────────────────────────────────────────
    if faces_count > 1:
        cv2.putText(frame, f"!! {faces_count} FACES DETECTED !!",
                    (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        y += 25

    # ── Mobile / object alerts ───────────────────────────────────────────
    for obj in objects:
        cv2.putText(frame, f"!! {obj['label'].upper()} DETECTED !!",
                    (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        y += 25

    # ── Recent events (right side) ───────────────────────────────────────
    cv2.putText(frame, "Recent Events:", (w - 340, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1)

    recent = record.event_log[-6:]
    for i, (ts, evt, pts, _) in enumerate(reversed(recent)):
        age = time.time() - ts
        color = (100, 255, 100) if age < 3 else (150, 150, 150)
        label = f"{evt.replace('_', ' ')}  +{pts}  ({age:.0f}s)"
        cv2.putText(frame, label, (w - 340, 52 + i * 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

    # ── Total event count (bottom left) ──────────────────────────────────
    cv2.putText(frame, f"Total events: {len(record.event_log)}",
                (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Starting integrated test... press 'q' to quit.")
    print("Sit still during the setup phase (~1 second).")
    print("After setup, keep head centered briefly so gaze baseline calibrates.")

    # ── Init all modules ────────────────────────────────────────────────
    face_detector = FaceDetector()
    head_pose_estimator = HeadPoseEstimator()
    gaze_estimator = EyeGazeEstimator()
    person_detector = PersonDetector(confidence_threshold=0.5)
    body_pose_estimator = PoseEstimator()
    thresholds = ZoneThresholds()
    zone_manager = DeskZoneManager(thresholds=thresholds, setup_frames=30)
    leaning_analyzer = BoundaryZoneAnalyzer(thresholds=thresholds)
    object_detector = ObjectDetector(confidence_threshold=0.4)
    scoring_engine = StudentScoringEngine(ScoringRules())

    # FPS tracking
    fps_counter = 0
    fps_timer = time.time()
    current_fps = 0

    with CameraCapture(camera_index=0) as camera:
        while True:
            success, frame = camera.read()
            if not success:
                print("Failed to read frame.")
                break

            # ── Brightness enhancement for dim environments ───────────────
            frame = cv2.convertScaleAbs(frame, alpha=BRIGHTNESS_ALPHA, beta=BRIGHTNESS_BETA)

            # ── FPS counter ──────────────────────────────────────────────
            fps_counter += 1
            if time.time() - fps_timer >= 1.0:
                current_fps = fps_counter
                fps_counter = 0
                fps_timer = time.time()

            # ── 1. Person detection + body pose ─────────────────────────
            people = person_detector.detect(frame)
            people_with_pose = []
            for p in people:
                pose = body_pose_estimator.estimate_in_region(frame, p["bbox"])
                people_with_pose.append({"bbox": p["bbox"], "pose": pose})
            person_detected = len(people) > 0

            # ── 2. Setup phase ───────────────────────────────────────────
            if not zone_manager.is_setup_complete:
                zone_manager.setup_frame(people_with_pose)
                progress = min(zone_manager._frames_seen, zone_manager.setup_frames)

                for p in people_with_pose:
                    if p["pose"] is None:
                        continue
                    x1, y1, x2, y2 = p["bbox"]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 255), 2)

                cv2.rectangle(frame, (0, 0), (frame.shape[1], 70), (30, 30, 30), -1)
                cv2.putText(
                    frame,
                    f"SETTING UP DESK ZONES...  {progress} / {zone_manager.setup_frames}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2,
                )
                cv2.putText(
                    frame, "Sit still in your seat position",
                    (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1,
                )

                cv2.imshow("Integrated Test - Press 'q' to quit", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue

            # ── 3. Desk zone monitoring ──────────────────────────────────
            zone_status = None
            zone_results = zone_manager.check_zones(people_with_pose)

            for zone_id, zone in zone_manager.zones.items():
                cx, cy = map(int, zone["center"])
                cv2.circle(frame, (cx, cy), int(zone["safe_radius"]), (0, 180, 0), 1)
                cv2.circle(frame, (cx, cy), int(zone["violation_radius"]), (0, 0, 180), 1)
                cv2.putText(
                    frame, f"Seat {zone_id}",
                    (cx - 20, cy - int(zone["safe_radius"]) - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 180, 0), 1,
                )

            if zone_results:
                zone_status = zone_results[0]["status"]
                zr = zone_results[0]
                if zr["zone_center"] is not None:
                    cx_p, cy_p = map(int, zr["current_center"])
                    cx_z, cy_z = map(int, zr["zone_center"])
                    cv2.line(frame, (cx_p, cy_p), (cx_z, cy_z),
                             STATUS_COLORS.get(zone_status, (200, 200, 200)), 1)

            # ── 4. Face detection ────────────────────────────────────────
            faces = face_detector.detect(frame)
            face_count = len(faces)
            face_detected = face_count > 0

            for face in faces:
                x1, y1, x2, y2 = face["bbox"]
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            if face_count > 1:
                scoring_engine.report_another_face(STUDENT_ID)

            # ── 5. Head pose ─────────────────────────────────────────────
            yaw, pitch = 0.0, 0.0
            head_pose_ok = False
            head_poses = head_pose_estimator.estimate(frame)

            if head_poses:
                head_pose_ok = True
                yaw = head_poses[0]["yaw"]
                pitch = head_poses[0]["pitch"]

                nose_x, nose_y = map(int, head_poses[0]["nose_2d"])
                end_x = int(nose_x + 80 * (yaw / 90))
                end_y = int(nose_y - 80 * (pitch / 90))
                cv2.line(frame, (nose_x, nose_y), (end_x, end_y), (255, 100, 0), 3)
            else:
                # Pose detection failed while face IS in frame — suspicious
                if face_detected:
                    scoring_engine.report_detection_failure(STUDENT_ID)

            # ── 6. Eye gaze ──────────────────────────────────────────────
            gaze_dir = "N/A"
            gaze_h_ratio = None
            gazes = gaze_estimator.estimate(frame)
            if gazes:
                gaze_dir = gazes[0]["gaze_direction"]
                gaze_h_ratio = gazes[0]["horizontal_ratio"]

            # ── 7. Head pose + gaze combined scoring (personal baseline) ─
            scoring_engine.update_head_pose(
                STUDENT_ID, yaw, pitch, gaze_dir, gaze_h_ratio
            )

            # ── 8. Object detection (mobile phone) ───────────────────────
            objects = object_detector.detect(frame)
            if objects:
                scoring_engine.report_mobile_detected(STUDENT_ID)
                for obj in objects:
                    ox1, oy1, ox2, oy2 = obj["bbox"]
                    cv2.rectangle(frame, (ox1, oy1), (ox2, oy2), (0, 0, 255), 2)
                    cv2.putText(
                        frame, f"{obj['label']} {obj['confidence']:.2f}",
                        (ox1, oy1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2,
                    )

            # ── 9. Leaning analysis ──────────────────────────────────────
            leaning_results = leaning_analyzer.analyze_leaning(people_with_pose)
            for lr in leaning_results:
                if lr["leaning_status"] == "violation":
                    scoring_engine.report_leaning_violation(STUDENT_ID)

                x1, y1, x2, y2 = lr["person_bbox"]
                lean_color = STATUS_COLORS.get(lr["leaning_status"], (200, 200, 200))
                cv2.rectangle(frame, (x1, y1), (x2, y2), lean_color, 2)
                cv2.putText(
                    frame,
                    f"Tilt: {lr['spine_tilt_degrees']:.1f} [{lr['leaning_status'].upper()}]",
                    (x1, y2 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, lean_color, 1,
                )

            # ── 10. Desk zone violation scoring ──────────────────────────
            if zone_status == "violation":
                scoring_engine.report_desk_zone_violation(STUDENT_ID)

            # ── 11. Presence state machine ───────────────────────────────
            is_detected = face_detected or person_detected
            scoring_engine.update_presence(STUDENT_ID, is_detected)
            record = scoring_engine.get_record(STUDENT_ID)

            # ── 12. Draw HUD ─────────────────────────────────────────────
            draw_hud(
                frame, record,
                gaze_dir, gaze_h_ratio,
                yaw, pitch,
                zone_status, objects, face_count,
                head_pose_ok, current_fps,
            )

            cv2.imshow("Integrated Test - Press 'q' to quit", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    # ── Cleanup ──────────────────────────────────────────────────────────
    face_detector.close()
    head_pose_estimator.close()
    gaze_estimator.close()
    body_pose_estimator.close()
    cv2.destroyAllWindows()

    # ── Final report ─────────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("FINAL REPORT")
    print("=" * 55)
    for r in scoring_engine.get_all_records():
        status = "SUSPICIOUS" if r.score >= 10 else "CLEAN"
        print(f"\nStudent {r.student_id}:  Score={r.score:.0f}  [{status}]")
        print(f"  Final state   : {r.presence_state.value}")
        print(
            f"  Gaze baseline : {r.gaze_baseline_h:.3f} "
            f"(from {r.gaze_baseline_samples} samples)"
        )
        if r.event_log:
            print("  Events:")
            for ts, evt, pts, _ in r.event_log:
                t = time.strftime("%H:%M:%S", time.localtime(ts))
                print(f"    [{t}]  {evt:<35} +{pts}")
        else:
            print("  No violations recorded.")
    print("=" * 55)


if __name__ == "__main__":
    main()