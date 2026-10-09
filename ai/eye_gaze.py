import cv2
import numpy as np
import mediapipe as mp


class EyeGazeEstimator:
    """
    Wrapper around MediaPipe Face Mesh (with iris refinement) to estimate
    where the eyes are looking, independent of head rotation.

    Uses MediaPipe's official landmark indices:
        LEFT_IRIS  = [468, 469, 470, 471, 472]  (center = 468)
        RIGHT_IRIS = [473, 474, 475, 476, 477]  (center = 473)
        LEFT_EYE_CORNERS  = [33, 133]
        RIGHT_EYE_CORNERS = [362, 263]
        LEFT_EYE_LIDS  (top, bottom) = [159, 145]
        RIGHT_EYE_LIDS (top, bottom) = [386, 374]

    horizontal_ratio:
        0.0 -> iris near first corner index
        1.0 -> iris near second corner index
        0.5 -> centered
    """

    # (corner_1, corner_2) — order doesn't matter for ratio math, just be consistent
    LEFT_EYE_CORNERS = (33, 133)
    RIGHT_EYE_CORNERS = (362, 263)

    LEFT_EYE_VERTICAL = (159, 145)    # (top, bottom)
    RIGHT_EYE_VERTICAL = (386, 374)   # (top, bottom)

    LEFT_IRIS_CENTER = 468
    RIGHT_IRIS_CENTER = 473

    def __init__(self, min_detection_confidence: float = 0.5, min_tracking_confidence: float = 0.5, debug: bool = False):
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=5,
            refine_landmarks=True,  # required for iris landmarks (468-477)
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self.debug = debug

    def estimate(self, frame):
        height, width = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb_frame)

        gazes = []
        if results.multi_face_landmarks:
            for face_landmarks in results.multi_face_landmarks:
                gaze = self._compute_gaze(face_landmarks, width, height)
                if gaze is not None:
                    gazes.append(gaze)

        return gazes

    def _compute_gaze(self, face_landmarks, width, height):
        landmarks = face_landmarks.landmark

        def to_px(idx):
            return np.array([landmarks[idx].x * width, landmarks[idx].y * height])

        def eye_ratios(corners, vertical, iris_idx):
            c1 = to_px(corners[0])
            c2 = to_px(corners[1])
            top = to_px(vertical[0])
            bottom = to_px(vertical[1])
            iris = to_px(iris_idx)

            eye_width = np.linalg.norm(c2 - c1)
            eye_height = np.linalg.norm(bottom - top)

            h_ratio = np.linalg.norm(iris - c1) / eye_width if eye_width > 1e-6 else 0.5
            v_ratio = np.linalg.norm(iris - top) / eye_height if eye_height > 1e-6 else 0.5

            h_ratio = float(np.clip(h_ratio, 0.0, 1.0))
            v_ratio = float(np.clip(v_ratio, 0.0, 1.0))

            return h_ratio, v_ratio

        left_h, left_v = eye_ratios(self.LEFT_EYE_CORNERS, self.LEFT_EYE_VERTICAL, self.LEFT_IRIS_CENTER)
        right_h, right_v = eye_ratios(self.RIGHT_EYE_CORNERS, self.RIGHT_EYE_VERTICAL, self.RIGHT_IRIS_CENTER)

        horizontal_ratio = (left_h + right_h) / 2
        vertical_ratio = (left_v + right_v) / 2

        if self.debug:
            print(
                f"[DEBUG] L_h={left_h:.3f} R_h={right_h:.3f} -> avg_h={horizontal_ratio:.3f}  "
                f"L_v={left_v:.3f} R_v={right_v:.3f} -> avg_v={vertical_ratio:.3f}"
            )

        gaze_direction = self._classify_gaze(horizontal_ratio, vertical_ratio)

        return {
            "horizontal_ratio": horizontal_ratio,
            "vertical_ratio": vertical_ratio,
            "gaze_direction": gaze_direction,
            "left_eye_ratio": left_h,
            "right_eye_ratio": right_h,
        }

    @staticmethod
    def _classify_gaze(h_ratio, v_ratio):
        """
        Thresholds are starting points — calibrate using debug=True output.
        """
        if h_ratio < 0.35:
            return "Eyes Left"
        elif h_ratio > 0.65:
            return "Eyes Right"
        elif v_ratio < 0.35:
            return "Eyes Up"
        elif v_ratio > 0.65:
            return "Eyes Down"
        else:
            return "Eyes Center"

    def close(self):
        self.face_mesh.close()