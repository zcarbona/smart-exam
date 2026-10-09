"""
Test script to verify person detection (YOLOv8) + pose estimation work together.
Run with: python test_person_pose.py
Press 'q' to quit the window.

NOTE: First run will download the yolov8n.pt model automatically (~6MB).
"""
import cv2

from camera_capture import CameraCapture
from person_detector import PersonDetector, PoseEstimator


def main():
    print("Starting person + pose test... press 'q' in the window to quit.")
    print("(First run downloads the YOLOv8 model — may take a few seconds)")

    person_detector = PersonDetector(model_path="yolov8n.pt", confidence_threshold=0.5)
    pose_estimator = PoseEstimator()

    with CameraCapture(camera_index=0) as camera:
        while True:
            success, frame = camera.read()
            if not success:
                print("Failed to read frame from camera.")
                break

            people = person_detector.detect(frame)

            for i, person in enumerate(people):
                x1, y1, x2, y2 = person["bbox"]
                confidence = person["confidence"]

                # Draw person bounding box
                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 165, 0), 2)
                cv2.putText(
                    frame, f"Person {i+1}: {confidence:.2f}", (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 165, 0), 2,
                )

                # Run pose estimation within this person's bounding box
                pose = pose_estimator.estimate_in_region(frame, person["bbox"])

                if pose is not None:
                    # Draw shoulder and hip center points
                    sx, sy = int(pose["shoulder_center"][0]), int(pose["shoulder_center"][1])
                    hx, hy = int(pose["hip_center"][0]), int(pose["hip_center"][1])

                    cv2.circle(frame, (sx, sy), 6, (0, 255, 0), -1)   # shoulder center
                    cv2.circle(frame, (hx, hy), 6, (0, 0, 255), -1)   # hip center
                    cv2.line(frame, (sx, sy), (hx, hy), (255, 255, 0), 2)  # spine line

                    tilt_text = f"Tilt: {pose['spine_tilt_degrees']:.1f} deg"
                    torso_text = f"Torso: {pose['torso_length']:.0f}px"
                    cv2.putText(frame, tilt_text, (x1, y2 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                    cv2.putText(frame, torso_text, (x1, y2 + 45), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

            cv2.putText(
                frame, f"People detected: {len(people)}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2,
            )

            cv2.imshow("Person + Pose Test - Press 'q' to quit", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    pose_estimator.close()
    cv2.destroyAllWindows()
    print("Test complete.")


if __name__ == "__main__":
    main()