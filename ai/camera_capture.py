import cv2


def list_available_cameras(max_check: int = 5) -> list[int]:
    """
    Scan camera indices 0..max_check-1 and return those that open successfully.
    Run this once to find your iPhone camera index.
    Usage in terminal:
        python3 -c "from camera_capture import list_available_cameras; print(list_available_cameras())"
    """
    available = []
    for i in range(max_check):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            available.append(i)
            cap.release()
    return available


class CameraCapture:
    """
    Wrapper class for reading frames from a webcam or iPhone (Continuity Camera).

    To use iPhone camera on Mac:
        1. Make sure iPhone and Mac are on the same WiFi and same Apple ID,
           and Bluetooth is ON on both devices (Continuity Camera needs BT
           even though video goes over WiFi).
        2. macOS Ventura+ detects iPhone automatically as a virtual camera
           ONLY once the iPhone is unlocked, near the Mac, and not already
           in use by another app (FaceTime, Camera app, etc).
        3. Run list_available_cameras() to find the correct index — it is
           usually NOT 0 (built-in webcam is normally 0). Try 1, then 2.
        4. Pass that index here: CameraCapture(camera_index=1)

    If the iPhone doesn't show up in list_available_cameras() at all:
        - Open the Camera app (or FaceTime) on Mac first — System Settings >
          Video sometimes needs the iPhone selected there once before OpenCV
          can see it as an index.
        - Lock and unlock the iPhone, keep it within ~10m of the Mac.
        - Reboot Continuity Camera: turn iPhone Wi-Fi off/on.

    Alternatively, use DroidCam or EpocCam app on any phone — same approach,
    just pick the virtual camera index it creates.
    """

    def __init__(self,
                 camera_index: int = 0,
                 width: int = 1280,
                 height: int = 720,
                 fps: int = 30):
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.fps = fps
        self.cap = None

    def start(self):
        """Open the camera and configure resolution + FPS."""
        self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            available = list_available_cameras()
            raise RuntimeError(
                f"Could not open camera at index {self.camera_index}.\n"
                f"Available camera indices on this machine: {available}\n"
                "Check camera permissions: System Settings > Privacy & Security > Camera.\n"
                "For iPhone: make sure Continuity Camera is enabled on both devices, "
                "iPhone is unlocked and nearby, and Bluetooth is on."
            )
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        # Auto-exposure — helps in dim environments
        self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)

        # Log what we actually got (camera may not honour the request exactly)
        actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = int(self.cap.get(cv2.CAP_PROP_FPS))
        print(
            f"[CameraCapture] Opened index {self.camera_index} — "
            f"{actual_w}x{actual_h} @ {actual_fps}fps"
        )
        return self

    def read(self):
        """
        Read a single frame from the camera.
        Returns (success: bool, frame: np.ndarray or None)
        """
        if self.cap is None:
            raise RuntimeError("Camera not started. Call start() first.")
        success, frame = self.cap.read()
        return success, frame

    def is_opened(self) -> bool:
        return self.cap is not None and self.cap.isOpened()

    def release(self):
        """Release the camera resource."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()