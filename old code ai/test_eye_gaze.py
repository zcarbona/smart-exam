"""
Test script to verify eye gaze estimation works with the live camera.
Run with: python test_eye_gaze.py
Press 'q' to quit the window.
"""
import cv2

from camera_capture import CameraCapture
from eye_gaze import EyeGazeEstimator


def main():
    print("Starting eye gaze test... press 'q' in the window to quit.")

    gaze_estimator = EyeGazeEstimator()

    with CameraCapture(camera_index=0) as camera:
        while True:
            success, frame = camera.read()
            if not success:
                print("Failed to read frame from camera.")
                break

            gazes = gaze_estimator.estimate(frame)

            for gaze in gazes:
                h_ratio = gaze["horizontal_ratio"]
                v_ratio = gaze["vertical_ratio"]
                direction = gaze["gaze_direction"]

                text = f"H: {h_ratio:.2f}  V: {v_ratio:.2f}"
                cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.putText(frame, direction, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)

            cv2.imshow("Eye Gaze Test - Press 'q' to quit", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    gaze_estimator.close()
    cv2.destroyAllWindows()
    print("Test complete.")


if __name__ == "__main__":
    main()