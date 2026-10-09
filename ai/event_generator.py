import time
import base64
import requests
import cv2
from typing import Optional

class EventGenerator:
    """
    Dispatches violation events and periodic status heartbeats
    from the AI Pipeline to the Backend FastAPI server via HTTP POST.
    """
    def __init__(self, backend_url: str = "http://localhost:8000"):
        self.backend_url = backend_url.rstrip("/")
        self.events_endpoint = f"{self.backend_url}/api/events/ai"
        self.sync_endpoint = f"{self.backend_url}/api/events/sync"
        self.last_sync_time = 0.0

    def send_violation(
        self,
        track_id: int,
        event_type: str,
        points: float,
        frame=None,
        head_yaw: float = 0.0,
        head_pitch: float = 0.0,
        gaze_direction: str = "Eyes Center",
        zone_status: str = "safe",
        presence_state: str = "present",
        current_score: Optional[float] = None,
    ) -> bool:
        """
        Sends an alert event to the backend. Encodes the current frame as base64 JPEG evidence.
        """
        evidence_b64 = None
        if frame is not None:
            try:
                success, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if success:
                    evidence_b64 = base64.b64encode(buffer).decode("utf-8")
            except Exception as e:
                print(f"[EventGenerator] Failed to encode frame evidence: {e}")

        payload = {
            "track_id": track_id,
            "event_type": event_type,
            "points": points,
            "evidence_base64": evidence_b64,
            "head_yaw": head_yaw,
            "head_pitch": head_pitch,
            "gaze_direction": gaze_direction,
            "zone_status": zone_status,
            "presence_state": presence_state,
            "current_score": current_score,
        }

        try:
            resp = requests.post(self.events_endpoint, json=payload, timeout=2.0)
            return resp.status_code == 201
        except Exception as e:
            # Non-blocking log if backend server is temporarily unreachable
            print(f"[EventGenerator] Warning: Could not post event to backend: {e}")
            return False

    def sync_status(self, live_student_count: int, fps: int, tracks: list) -> bool:
        """
        Throttled status sync every 1 second.
        """
        now = time.time()
        if now - self.last_sync_time < 1.0:
            return False
        self.last_sync_time = now

        payload = {
            "live_student_count": live_student_count,
            "fps": fps,
            "tracks": tracks,
        }

        try:
            resp = requests.post(self.sync_endpoint, json=payload, timeout=1.0)
            return resp.status_code == 200
        except Exception:
            return False
