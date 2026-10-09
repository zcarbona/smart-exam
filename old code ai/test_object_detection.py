"""
Test script to verify mobile phone detection works with the live camera.
Run with: python test_object_detection.py
Press 'q' to quit the window.

Hold a phone up in frame to test detection.
"""
import cv2

from camera_capture import CameraCapture
from object_detector import ObjectDetector


def main():
    print("Starting object detection test... press 'q' in the window to quit.")
    print("Hold a phone up to test detection.")

    object_detector = ObjectDetector(model_path="yolov8n.pt", confidence_threshold=0.4)

    with CameraCapture(camera_index=0) as camera:
        while True:
            success, frame = camera.read()
            if not success:
                print("Failed to read frame from camera.")
                break

            objects = object_detector.detect(frame)

            for obj in objects:
                x1, y1, x2, y2 = obj["bbox"]
                label = obj["label"]
                confidence = obj["confidence"]

                # Red box — this is a "violation" object by nature
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)

                text = f"{label}: {confidence:.2f}"
                cv2.putText(frame, text, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

            # Summary overlay
            cv2.putText(frame, f"Objects detected: {len(objects)}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

            if objects:
                cv2.putText(frame, "ALERT: Prohibited object detected!", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            cv2.imshow("Object Detection Test - Press 'q' to quit", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cv2.destroyAllWindows()
    print("Test complete.")


if __name__ == "__main__":
    main()