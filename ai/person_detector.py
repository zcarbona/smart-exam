import cv2
import numpy as np
from ultralytics import YOLO
import mediapipe as mp


class PersonDetector:
    """
    Wrapper around YOLOv8 for detecting people (students) in the frame.
    Uses the standard COCO-pretrained model, filtering for the "person" class only.
    """

    PERSON_CLASS_ID = 0  # "person" class index in the COCO dataset

    def __init__(self, model_path: str = "yolov8n.pt", confidence_threshold: float = 0.5):
        """
        model_path: "yolov8n.pt" (nano) is the smallest/fastest variant — good for
        CPU-only machines like a MacBook without a dedicated GPU. Ultralytics will
        auto-download this the first time it's used.
        """
        self.model = YOLO(model_path)
        self.confidence_threshold = confidence_threshold

    def detect(self, frame):
        """
        Run person detection on a single BGR frame.

        Returns a list of dicts, one per detected person:
            {
                "bbox": (x1, y1, x2, y2),  # pixel coordinates
                "confidence": float,
            }
        """
        results = self.model(frame, verbose=False)[0]

        people = []
        for box in results.boxes:
            class_id = int(box.cls[0])
            confidence = float(box.conf[0])

            if class_id == self.PERSON_CLASS_ID and confidence >= self.confidence_threshold:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                people.append({
                    "bbox": (x1, y1, x2, y2),
                    "confidence": confidence,
                })

        return people


class PoseEstimator:
    """
    Wrapper around MediaPipe Pose for body keypoint detection
    (shoulders, hips, spine alignment, etc).

    Used to determine posture: standing/sitting, leaning, body orientation —
    independent of head direction.
    """

    # Key landmark indices in MediaPipe's 33-point pose model
    KEY_LANDMARKS = {
        "left_shoulder": 11,
        "right_shoulder": 12,
        "left_hip": 23,
        "right_hip": 24,
        "nose": 0,
    }

    def __init__(self, min_detection_confidence: float = 0.5, min_tracking_confidence: float = 0.5):
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,  # 0=lite/fast, 1=full/balanced, 2=heavy/accurate
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def estimate(self, frame):
        """
        Run pose estimation on a single BGR frame.

        NOTE: MediaPipe Pose detects ONE person per call by design. For multiple
        students, crop each person's bounding box (from PersonDetector) and run
        this on each crop separately — see estimate_in_region() below.

        Returns a dict (or None if no pose detected):
            {
                "shoulder_center": (x, y),
                "hip_center": (x, y),
                "shoulder_width": float,       # used for scale normalization
                "torso_length": float,         # distance(shoulder_center, hip_center)
                "spine_tilt_degrees": float,   # 0 = perfectly upright, +/- = leaning
                "landmarks": {name: (x, y), ...}  # raw key points, pixel coords
            }
        """
        height, width = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.pose.process(rgb_frame)

        if not results.pose_landmarks:
            return None

        return self._compute_pose_metrics(results.pose_landmarks, width, height)

    def estimate_in_region(self, frame, bbox):
        """
        Crop the frame to a person's bounding box and run pose estimation
        only within that region. Returns coordinates translated back to
        the full frame's coordinate space.
        """
        x1, y1, x2, y2 = bbox
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)

        if x2 <= x1 or y2 <= y1:
            return None

        crop = frame[y1:y2, x1:x2]
        pose_result = self.estimate(crop)

        if pose_result is None:
            return None

        # Translate all coordinates from crop-space back to full-frame-space
        offset = np.array([x1, y1])
        pose_result["shoulder_center"] = tuple(np.array(pose_result["shoulder_center"]) + offset)
        pose_result["hip_center"] = tuple(np.array(pose_result["hip_center"]) + offset)
        for name in pose_result["landmarks"]:
            pose_result["landmarks"][name] = tuple(np.array(pose_result["landmarks"][name]) + offset)

        return pose_result

    def _compute_pose_metrics(self, pose_landmarks, width, height):
        landmarks = pose_landmarks.landmark

        def to_px(idx):
            return np.array([landmarks[idx].x * width, landmarks[idx].y * height])

        named_points = {
            name: to_px(idx) for name, idx in self.KEY_LANDMARKS.items()
        }

        shoulder_center = (named_points["left_shoulder"] + named_points["right_shoulder"]) / 2
        hip_center = (named_points["left_hip"] + named_points["right_hip"]) / 2

        shoulder_width = float(np.linalg.norm(named_points["left_shoulder"] - named_points["right_shoulder"]))
        torso_length = float(np.linalg.norm(shoulder_center - hip_center))

        # Spine tilt: angle of the shoulder-hip vector relative to vertical
        spine_vector = shoulder_center - hip_center
        # atan2(dx, dy) where dy is "up" — 0 degrees means perfectly vertical
        spine_tilt_degrees = float(np.degrees(np.arctan2(spine_vector[0], -spine_vector[1])))

        return {
            "shoulder_center": tuple(shoulder_center),
            "hip_center": tuple(hip_center),
            "shoulder_width": shoulder_width,
            "torso_length": torso_length,
            "spine_tilt_degrees": spine_tilt_degrees,
            "landmarks": {name: tuple(pt) for name, pt in named_points.items()},
        }

    def close(self):
        self.pose.close()