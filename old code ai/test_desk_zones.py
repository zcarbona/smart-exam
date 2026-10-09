"""
Test script for the desk-zone system: a setup phase that learns each
student's seat position, followed by a monitoring phase that flags
students who move outside their own assigned zone.

Run with: python test_desk_zones.py
Press 'q' to quit the window.

HOW TO TEST:
1. When the window opens, stay in your seat position for ~1 second
   (the "SETTING UP" phase collects 30 frames).
2. Once setup completes, the zone (circle) is drawn around your seat.
3. Lean far to one side or move far from your spot to trigger Warning/Violation.
"""
import cv2

from camera_capture import CameraCapture
from person_detector import PersonDetector, PoseEstimator
from boundary_zones import DeskZoneManager, BoundaryZoneAnalyzer, ZoneThresholds


STATUS_COLORS = {
    "safe": (0, 255, 0),         # green
    "warning": (0, 255, 255),    # yellow
    "violation": (0, 0, 255),    # red
    "unassigned": (128, 128, 128),  # gray
}


def main():
    print("Starting desk zone test... press 'q' in the window to quit.")
    print("Stay still in your seat for the first ~1 second (setup phase).")

    person_detector = PersonDetector(model_path="yolov8n.pt", confidence_threshold=0.5)
    pose_estimator = PoseEstimator()
    thresholds = ZoneThresholds()
    zone_manager = DeskZoneManager(thresholds=thresholds, setup_frames=30)
    leaning_analyzer = BoundaryZoneAnalyzer(thresholds=thresholds)

    with CameraCapture(camera_index=0) as camera:
        while True:
            success, frame = camera.read()
            if not success:
                print("Failed to read frame from camera.")
                break

            # --- Detect people + estimate pose ---
            people = person_detector.detect(frame)
            people_with_pose = []
            for person in people:
                pose = pose_estimator.estimate_in_region(frame, person["bbox"])
                people_with_pose.append({"bbox": person["bbox"], "pose": pose})

            if not zone_manager.is_setup_complete:
                # --- SETUP PHASE ---
                zone_manager.setup_frame(people_with_pose)

                # Draw current detections in white during setup
                for person in people_with_pose:
                    if person["pose"] is None:
                        continue
                    x1, y1, x2, y2 = person["bbox"]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 255), 2)

                progress = min(zone_manager._frames_seen, zone_manager.setup_frames)
                cv2.putText(frame, f"SETTING UP ZONES... {progress}/{zone_manager.setup_frames}",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
                cv2.putText(frame, "Stay in your seat position", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

            else:
                # --- MONITORING PHASE ---
                zone_results = zone_manager.check_zones(people_with_pose)
                leaning_results = leaning_analyzer.analyze_leaning(people_with_pose)

                # Draw the fixed zone circles (drawn once per frame, same position every time)
                for zone_id, zone in zone_manager.zones.items():
                    cx, cy = map(int, zone["center"])
                    cv2.circle(frame, (cx, cy), int(zone["safe_radius"]), (0, 200, 0), 1)
                    cv2.circle(frame, (cx, cy), int(zone["violation_radius"]), (0, 0, 200), 1)
                    cv2.putText(frame, f"Seat {zone_id}", (cx - 20, cy - int(zone["safe_radius"]) - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 0), 1)

                # Draw each detected person with their zone status
                for zr in zone_results:
                    x1, y1, x2, y2 = zr["person_bbox"]
                    status = zr["status"]
                    color = STATUS_COLORS[status]

                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                    if zr["normalized_distance"] is not None:
                        label = f"Seat {zr['zone_id']} | {zr['normalized_distance']:.2f}x [{status.upper()}]"
                    else:
                        label = f"[{status.upper()}]"
                    cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                    # Line from current position to assigned zone center
                    if zr["zone_center"] is not None:
                        cx, cy = map(int, zr["current_center"])
                        zx, zy = map(int, zr["zone_center"])
                        cv2.line(frame, (cx, cy), (zx, zy), color, 1)

                # Draw leaning status under each box
                for lr in leaning_results:
                    x1, y1, x2, y2 = lr["person_bbox"]
                    tilt = lr["spine_tilt_degrees"]
                    status = lr["leaning_status"]
                    color = STATUS_COLORS[status]
                    cv2.putText(frame, f"Tilt: {tilt:.1f} deg [{status.upper()}]",
                                (x1, y2 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

                # Summary counters
                violations = sum(1 for zr in zone_results if zr["status"] == "violation")
                violations += sum(1 for lr in leaning_results if lr["leaning_status"] == "violation")
                cv2.putText(frame, f"Seats: {len(zone_manager.zones)}  Violations: {violations}",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

            cv2.imshow("Desk Zone Test - Press 'q' to quit", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    pose_estimator.close()
    cv2.destroyAllWindows()
    print("Test complete.")


if __name__ == "__main__":
    main()