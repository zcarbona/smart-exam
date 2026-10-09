"""
Test script to verify face detection + head pose estimation work together live.
Run with: python test_head_pose.py
Press 'q' to quit the window.
"""
import cv2

from camera_capture import CameraCapture
from face_detector import FaceDetector, HeadPoseEstimator


def classify_direction(yaw, pitch):
    """Simple human-readable label based on yaw/pitch thresholds."""
    if yaw > 20:
        return "Looking Right"
    elif yaw < -20:
        return "Looking Left"
    elif pitch < -15:
        return "Looking Down"
    elif pitch > 15:
        return "Looking Up"
    else:
        return "Looking Forward"


def main():
    print("Starting head pose test... press 'q' in the window to quit.")

    face_detector = FaceDetector(min_detection_confidence=0.5, model_selection=0)
    pose_estimator = HeadPoseEstimator()

    with CameraCapture(camera_index=0) as camera:
        while True:
            success, frame = camera.read()
            if not success:
                print("Failed to read frame from camera.")
                break

            # Draw face bounding boxes
            faces = face_detector.detect(frame)
            for face in faces:
                x1, y1, x2, y2 = face["bbox"]
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # Compute and draw head pose
            poses = pose_estimator.estimate(frame)
            for pose in poses:
                yaw, pitch, roll = pose["yaw"], pose["pitch"], pose["roll"]
                nose_x, nose_y = int(pose["nose_2d"][0]), int(pose["nose_2d"][1])

                direction = classify_direction(yaw, pitch)

                # Draw a line showing where the nose is pointing
                line_length = 100
                end_x = int(nose_x + line_length * (yaw / 90))
                end_y = int(nose_y - line_length * (pitch / 90))
                cv2.line(frame, (nose_x, nose_y), (end_x, end_y), (255, 0, 0), 3)

                text = f"Yaw: {yaw:.1f}  Pitch: {pitch:.1f}  Roll: {roll:.1f}"
                cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.putText(frame, direction, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)

            cv2.imshow("Head Pose Test - Press 'q' to quit", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    face_detector.close()
    pose_estimator.close()
    cv2.destroyAllWindows()
    print("Test complete.")


if __name__ == "__main__":
    main()