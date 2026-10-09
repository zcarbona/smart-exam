"""
Test script to verify leaning (spine tilt) analysis works for multiple people.
Combines: PersonDetector (YOLOv8) + PoseEstimator (MediaPipe Pose) + BoundaryZoneAnalyzer.

NOTE: This test only checks individual leaning/posture per student.
For position-relative-to-seat checks (desk zones), see test_desk_zones.py instead.

Run with: python test_boundary.py
Press 'q' to quit the window.
"""
import cv2

from camera_capture import CameraCapture
from person_detector import PersonDetector, PoseEstimator
from boundary_zones import BoundaryZoneAnalyzer, ZoneThresholds


# Colors for each status (BGR format for OpenCV)
STATUS_COLORS = {
    "safe": (0, 255, 0),       # green
    "warning": (0, 255, 255),  # yellow
    "violation": (0, 0, 255),  # red
}


def main():
    print("Starting leaning analysis test... press 'q' in the window to quit.")

    person_detector = PersonDetector(model_path="yolov8n.pt", confidence_threshold=0.5)
    pose_estimator = PoseEstimator()
    leaning_analyzer = BoundaryZoneAnalyzer(ZoneThresholds())

    with CameraCapture(camera_index=0) as camera:
        while True:
            success, frame = camera.read()
            if not success:
                print("Failed to read frame from camera.")
                break

            # --- Step 1: Detect people ---
            people = person_detector.detect(frame)

            # --- Step 2: Estimate pose for each person ---
            people_with_pose = []
            for person in people:
                pose = pose_estimator.estimate_in_region(frame, person["bbox"])
                people_with_pose.append({
                    "bbox": person["bbox"],
                    "pose": pose,
                })

            # --- Step 3: Run leaning analysis ---
            leaning_results = leaning_analyzer.analyze_leaning(people_with_pose)

            # --- Draw bounding boxes + leaning status ---
            for lr in leaning_results:
                x1, y1, x2, y2 = lr["person_bbox"]
                status = lr["leaning_status"]
                tilt = lr["spine_tilt_degrees"]
                color = STATUS_COLORS[status]

                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                label = f"Tilt: {tilt:.1f} deg [{status.upper()}]"
                cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            # Draw people with no pose detected (grayed out)
            people_with_pose_bboxes = {p["bbox"] for p in people_with_pose if p["pose"] is not None}
            for person in people_with_pose:
                if person["pose"] is None:
                    x1, y1, x2, y2 = person["bbox"]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (128, 128, 128), 2)
                    cv2.putText(frame, "no pose", (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (128, 128, 128), 2)

            # --- Summary overlay ---
            cv2.putText(frame, f"People: {len(people_with_pose)}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

            violation_count = sum(1 for lr in leaning_results if lr["leaning_status"] == "violation")
            cv2.putText(frame, f"Leaning violations: {violation_count}", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            cv2.imshow("Leaning Analysis Test - Press 'q' to quit", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    pose_estimator.close()
    cv2.destroyAllWindows()
    print("Test complete.")


if __name__ == "__main__":
    main()