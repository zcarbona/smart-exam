"""
Quick test script to verify face detection works with the live camera.
Run with: python test_face_detection.py
Press 'q' to quit the window.
"""
import cv2

from camera_capture import CameraCapture
from face_detector import FaceDetector


def main():
    print("Starting face detection test... press 'q' in the window to quit.")

    detector = FaceDetector(min_detection_confidence=0.5, model_selection=0)

    with CameraCapture(camera_index=0) as camera:
        while True:
            success, frame = camera.read()

            if not success:
                print("Failed to read frame from camera.")
                break

            faces = detector.detect(frame)

            for face in faces:
                x1, y1, x2, y2 = face["bbox"]
                confidence = face["confidence"]

                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

                label = f"{confidence:.2f}"
                cv2.putText(
                    frame, label, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2,
                )

                for name, (kx, ky) in face["keypoints"].items():
                    cv2.circle(frame, (int(kx), int(ky)), 3, (0, 0, 255), -1)

            cv2.putText(
                frame, f"Faces detected: {len(faces)}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2,
            )

            cv2.imshow("Face Detection Test - Press 'q' to quit", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    detector.close()
    cv2.destroyAllWindows()
    print("Test complete.")


if __name__ == "__main__":
    main()