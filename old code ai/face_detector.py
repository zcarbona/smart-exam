import cv2
import numpy as np
import mediapipe as mp


class FaceDetector:
    """
    Wrapper around MediaPipe Face Detection.
    Fast, lightweight detection — used for finding faces and basic bounding boxes.
    """

    def __init__(self, min_detection_confidence: float = 0.5, model_selection: int = 0):
        self.mp_face_detection = mp.solutions.face_detection
        self.detector = self.mp_face_detection.FaceDetection(
            min_detection_confidence=min_detection_confidence,
            model_selection=model_selection,
        )

    def detect(self, frame):
        height, width = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.detector.process(rgb_frame)

        faces = []
        if results.detections:
            for detection in results.detections:
                bbox_rel = detection.location_data.relative_bounding_box

                x1 = int(bbox_rel.xmin * width)
                y1 = int(bbox_rel.ymin * height)
                box_w = int(bbox_rel.width * width)
                box_h = int(bbox_rel.height * height)

                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(width, x1 + box_w)
                y2 = min(height, y1 + box_h)

                keypoints = {}
                key_names = [
                    "right_eye", "left_eye", "nose_tip",
                    "mouth_center", "right_ear", "left_ear",
                ]
                for name, kp in zip(key_names, detection.location_data.relative_keypoints):
                    keypoints[name] = (kp.x * width, kp.y * height)

                faces.append({
                    "bbox": (x1, y1, x2, y2),
                    "confidence": detection.score[0],
                    "keypoints": keypoints,
                })

        return faces

    def close(self):
        self.detector.close()


class HeadPoseEstimator:
    """
    Wrapper around MediaPipe Face Mesh + OpenCV solvePnP.
    Estimates head orientation (Yaw, Pitch, Roll) in degrees.
    """

    LANDMARK_IDS = {
        "nose_tip": 1,
        "chin": 152,
        "left_eye_corner": 263,
        "right_eye_corner": 33,
        "left_mouth_corner": 287,
        "right_mouth_corner": 57,
    }

    MODEL_POINTS_3D = np.array([
        (0.0, 0.0, 0.0),
        (0.0, -63.6, -12.5),
        (-43.3, 32.7, -26.0),
        (43.3, 32.7, -26.0),
        (-28.9, -28.9, -24.1),
        (28.9, -28.9, -24.1),
    ], dtype=np.float64)

    def __init__(self, min_detection_confidence: float = 0.5, min_tracking_confidence: float = 0.5):
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=5,
            refine_landmarks=False,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def estimate(self, frame):
        height, width = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb_frame)

        poses = []
        if results.multi_face_landmarks:
            for face_landmarks in results.multi_face_landmarks:
                pose = self._compute_pose(face_landmarks, width, height)
                if pose is not None:
                    poses.append(pose)

        return poses

    def _compute_pose(self, face_landmarks, width, height):
        image_points_2d = []
        for name, idx in self.LANDMARK_IDS.items():
            lm = face_landmarks.landmark[idx]
            image_points_2d.append((lm.x * width, lm.y * height))
        image_points_2d = np.array(image_points_2d, dtype=np.float64)

        focal_length = width
        center = (width / 2, height / 2)
        camera_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1],
        ], dtype=np.float64)

        dist_coeffs = np.zeros((4, 1))

        success, rotation_vector, translation_vector = cv2.solvePnP(
            self.MODEL_POINTS_3D, image_points_2d, camera_matrix, dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )

        if not success:
            return None

        rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
        yaw, pitch, roll = self._rotation_matrix_to_euler_angles(rotation_matrix)

        nose_tip_2d = tuple(image_points_2d[0])

        return {
            "yaw": yaw,
            "pitch": pitch,
            "roll": roll,
            "nose_2d": nose_tip_2d,
        }

    @staticmethod
    def _rotation_matrix_to_euler_angles(R):
        sy = np.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
        singular = sy < 1e-6

        if not singular:
            pitch = np.arctan2(-R[2, 0], sy)
            yaw = np.arctan2(R[1, 0], R[0, 0])
            roll = np.arctan2(R[2, 1], R[2, 2])
        else:
            pitch = np.arctan2(-R[2, 0], sy)
            yaw = 0
            roll = np.arctan2(-R[1, 2], R[1, 1])

        return np.degrees(yaw), np.degrees(pitch), np.degrees(roll)

    def close(self):
        self.face_mesh.close()