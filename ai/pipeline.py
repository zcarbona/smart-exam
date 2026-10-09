"""
AI Pipeline Runner:
Captures camera frames, runs multi-modal CV detection:
- Person detection (YOLOv8) + Centroid tracking
- MediaPipe Pose (Spine tilt & Desk boundary zones)
- MediaPipe FaceMesh (Head yaw/pitch + Gaze ratios with personal baseline)
- YOLOv8 Object detection (Mobile phone)
- Dispatches AI events to Backend FastAPI via EventGenerator
"""
import os
import time
import cv2
import numpy as np

from ai.camera_capture import CameraCapture, list_available_cameras
from ai.face_detector import FaceDetector, HeadPoseEstimator
from ai.eye_gaze import EyeGazeEstimator
from ai.person_detector import PersonDetector, PoseEstimator
from ai.boundary_zones import DeskZoneManager, BoundaryZoneAnalyzer, ZoneThresholds
from ai.object_detector import ObjectDetector
from ai.scoring_system import StudentScoringEngine, ScoringRules
from ai.event_generator import EventGenerator

CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "0"))
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
BRIGHTNESS_ALPHA = 1.3
BRIGHTNESS_BETA = 20
DISPLAY_GUI = os.environ.get("DISPLAY_GUI", "true").lower() == "true"

class CentroidTracker:
    def __init__(self, max_disappeared: int = 30):
        self.next_id = 0
        self.tracks: dict[int, np.ndarray] = {}
        self.disappeared: dict[int, int] = {}
        self.max_disappeared = max_disappeared

    def _centroid(self, bbox):
        x1, y1, x2, y2 = bbox
        return np.array([(x1 + x2) / 2, (y1 + y2) / 2], dtype=float)

    def update(self, bboxes: list) -> dict[int, tuple]:
        if not bboxes:
            for tid in list(self.disappeared):
                self.disappeared[tid] += 1
                if self.disappeared[tid] > self.max_disappeared:
                    del self.tracks[tid]
                    del self.disappeared[tid]
            return {}

        new_cents = [self._centroid(b) for b in bboxes]

        if not self.tracks:
            for c, b in zip(new_cents, bboxes):
                self.tracks[self.next_id] = c
                self.disappeared[self.next_id] = 0
                self.next_id += 1
            return {tid: bboxes[i] for i, tid in enumerate(self.tracks)}

        track_ids = list(self.tracks.keys())
        old_cents = [self.tracks[tid] for tid in track_ids]

        D = np.linalg.norm(np.array(old_cents)[:, None] - np.array(new_cents)[None, :], axis=2)

        matched_old, matched_new, assignments = set(), set(), {}
        for row in D.min(axis=1).argsort():
            col = D[row].argmin()
            if row in matched_old or col in matched_new:
                continue
            if D[row, col] > 150:
                continue
            tid = track_ids[row]
            assignments[tid] = col
            self.tracks[tid] = new_cents[col]
            self.disappeared[tid] = 0
            matched_old.add(row)
            matched_new.add(col)

        for i, tid in enumerate(track_ids):
            if i not in matched_old:
                self.disappeared[tid] += 1
                if self.disappeared[tid] > self.max_disappeared:
                    del self.tracks[tid]
                    del self.disappeared[tid]

        for j, (c, b) in enumerate(zip(new_cents, bboxes)):
            if j not in matched_new:
                self.tracks[self.next_id] = c
                self.disappeared[self.next_id] = 0
                assignments[self.next_id] = j
                self.next_id += 1

        return {tid: bboxes[col] for tid, col in assignments.items() if tid in self.tracks}


def run_pipeline(display_gui: bool = DISPLAY_GUI):
    print("=" * 60)
    print("Starting Smart Exam AI Pipeline...")
    print(f"Backend Event Target: {BACKEND_URL}")
    print(f"Camera index: {CAMERA_INDEX}")
    print("=" * 60)

    # Initialize modules
    face_detector = FaceDetector()
    head_pose_est = HeadPoseEstimator()
    gaze_est = EyeGazeEstimator()
    person_detector = PersonDetector(confidence_threshold=0.5)
    body_pose_est = PoseEstimator()
    object_detector = ObjectDetector(confidence_threshold=0.4)
    thresholds = ZoneThresholds()
    zone_manager = DeskZoneManager(thresholds=thresholds, setup_frames=30)
    leaning_analyzer = BoundaryZoneAnalyzer(thresholds=thresholds)
    scoring_engine = StudentScoringEngine(ScoringRules())
    tracker = CentroidTracker(max_disappeared=30)
    event_gen = EventGenerator(backend_url=BACKEND_URL)

    last_event_counts: dict[int, int] = {}
    fps_counter, fps_timer, current_fps, frame_count = 0, time.time(), 0, 0

    with CameraCapture(camera_index=CAMERA_INDEX) as camera:
        print("[AI Pipeline] Camera successfully opened. Processing frames...")

        while True:
            success, frame = camera.read()
            if not success:
                time.sleep(0.05)
                continue

            frame = cv2.convertScaleAbs(frame, alpha=BRIGHTNESS_ALPHA, beta=BRIGHTNESS_BETA)
            frame_count += 1
            fps_counter += 1
            if time.time() - fps_timer >= 1.0:
                current_fps = fps_counter
                fps_counter = 0
                fps_timer = time.time()

            # 1. Person detection & tracking
            people = person_detector.detect(frame)
            bboxes = [p["bbox"] for p in people]
            id_to_bbox = tracker.update(bboxes)
            live_count = len(id_to_bbox)

            people_with_pose = []
            for tid, bbox in id_to_bbox.items():
                pose = body_pose_est.estimate_in_region(frame, bbox)
                people_with_pose.append({"id": tid, "bbox": bbox, "pose": pose})

            # Setup phase: calibrate seat zones
            if not zone_manager.is_setup_complete:
                zone_manager.setup_frame(people_with_pose)
                progress = (
                    min(zone_manager._frames_seen, zone_manager.setup_frames),
                    zone_manager.setup_frames,
                )
                if display_gui:
                    display = frame.copy()
                    cv2.putText(display, f"SETTING UP ZONES... {progress[0]}/{progress[1]}",
                                (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
                    cv2.imshow("Smart Exam - AI Pipeline (q to quit)", display)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                continue

            # 2. Desk zones
            zone_results = zone_manager.check_zones(people_with_pose)
            zone_by_id: dict[int, str] = {}
            for zr in zone_results:
                if zr["current_center"] is None:
                    continue
                zrx, zry = zr["current_center"]
                best_tid, best_dist = None, float("inf")
                for p in people_with_pose:
                    if p["pose"] is None:
                        continue
                    sc = p["pose"]["shoulder_center"]
                    d = ((sc[0] - zrx) ** 2 + (sc[1] - zry) ** 2) ** 0.5
                    if d < best_dist:
                        best_dist, best_tid = d, p["id"]
                if best_tid is not None:
                    zone_by_id[best_tid] = zr["status"]

            # 3. Full-frame detections
            faces = face_detector.detect(frame)
            head_poses = head_pose_est.estimate(frame)
            gazes = gaze_est.estimate(frame)
            objects = object_detector.detect(frame)

            # Spatial mapping: link head poses & gazes to the corresponding person
            # Fixes the multi-student gaze assignment bug identified in situation.md
            track_sync_list = []

            for p in people_with_pose:
                tid = p["id"]
                bx1, by1, bx2, by2 = p["bbox"]
                person_cx = (bx1 + bx2) / 2
                person_cy = (by1 + by2) / 2

                scoring_engine.update_presence(tid, is_detected=True)

                # Find nearest head pose inside or near person bounding box
                yaw, pitch, head_pose_ok = 0.0, 0.0, False
                matched_hp_idx = None
                if head_poses:
                    distances = [
                        ((hp["nose_2d"][0] - person_cx) ** 2 + (hp["nose_2d"][1] - person_cy) ** 2) ** 0.5
                        for hp in head_poses
                    ]
                    best_idx = int(np.argmin(distances))
                    if distances[best_idx] < 300:
                        yaw = head_poses[best_idx]["yaw"]
                        pitch = head_poses[best_idx]["pitch"]
                        head_pose_ok = True
                        matched_hp_idx = best_idx

                # Match gaze to corresponding face
                gaze_dir, gaze_h_ratio = None, None
                if gazes and matched_hp_idx is not None and matched_hp_idx < len(gazes):
                    gaze_dir = gazes[matched_hp_idx]["gaze_direction"]
                    gaze_h_ratio = gazes[matched_hp_idx]["horizontal_ratio"]
                elif gazes:
                    gaze_dir = gazes[0]["gaze_direction"]
                    gaze_h_ratio = gazes[0]["horizontal_ratio"]

                faces_here = [
                    f for f in faces
                    if bx1 <= (f["bbox"][0] + f["bbox"][2]) / 2 <= bx2
                    and by1 <= (f["bbox"][1] + f["bbox"][3]) / 2 <= by2
                ]

                # Scoring triggers
                if len(faces_here) > 1:
                    scoring_engine.report_another_face(tid)
                elif not head_pose_ok and len(faces_here) > 0:
                    scoring_engine.report_detection_failure(tid)

                scoring_engine.update_head_pose(tid, yaw, pitch, gaze_dir, gaze_h_ratio)

                for obj in objects:
                    ox1, oy1, ox2, oy2 = obj["bbox"]
                    obj_cx = (ox1 + ox2) / 2
                    obj_cy = (oy1 + oy2) / 2
                    if bx1 <= obj_cx <= bx2 and by1 <= obj_cy <= by2:
                        scoring_engine.report_mobile_detected(tid)

                for lr in leaning_analyzer.analyze_leaning([p]):
                    if lr["leaning_status"] == "violation":
                        scoring_engine.report_leaning_violation(tid)

                zone_status = zone_by_id.get(tid, "safe")
                if zone_status == "violation":
                    scoring_engine.report_desk_zone_violation(tid)

                # Check if new violation was logged -> send to backend via EventGenerator
                record = scoring_engine.get_record(tid)
                last_n = last_event_counts.get(tid, 0)
                if len(record.event_log) > last_n:
                    new_events = record.event_log[last_n:]
                    for ts, evt, pts, _ in new_events:
                        event_gen.send_violation(
                            track_id=tid,
                            event_type=evt,
                            points=pts,
                            frame=frame,
                            head_yaw=yaw,
                            head_pitch=pitch,
                            gaze_direction=gaze_dir or "Eyes Center",
                            zone_status=zone_status,
                            presence_state=record.presence_state.value,
                            current_score=record.score,
                        )
                    last_event_counts[tid] = len(record.event_log)

                track_sync_list.append({
                    "track_id": tid,
                    "head_yaw": round(yaw, 1),
                    "head_pitch": round(pitch, 1),
                    "gaze_direction": gaze_dir or "Eyes Center",
                    "gaze_baseline_h": round(record.gaze_baseline_h, 3),
                    "zone_status": zone_status,
                    "score": round(record.score, 0),
                    "presence_state": record.presence_state.value,
                })

            # Send periodic telemetry heartbeat to backend
            event_gen.sync_status(live_student_count=live_count, fps=current_fps, tracks=track_sync_list)

            if display_gui:
                display = frame.copy()
                for p in people_with_pose:
                    tid = p["id"]
                    x1, y1, x2, y2 = p["bbox"]
                    rec = scoring_engine.get_record(tid)
                    color = (0, 0, 255) if rec.score >= 10 else (0, 255, 0)
                    cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(display, f"ID {tid} | {rec.score:.0f}pts", (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                cv2.putText(display, f"FPS: {current_fps} | Students: {live_count}",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.imshow("Smart Exam - AI Pipeline (q to quit)", display)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        cv2.destroyAllWindows()

if __name__ == "__main__":
    run_pipeline()
