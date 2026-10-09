import base64
import os
import time
import uuid
from typing import Optional

import cv2
import requests

BACKEND_URL_ENV = "BACKEND_URL"
ROBOT_DEVICE_CODE_ENV = "ROBOT_DEVICE_CODE"
ROBOT_DEVICE_KEY_ENV = "ROBOT_DEVICE_KEY"


class EventGenerator:
    """Dispatches violation events and periodic status heartbeats from the AI
    Pipeline to the Backend FastAPI server via HTTP POST.

    Every call is authenticated as a *machine device* using
    `X-Device-Code` / `X-Device-Key`. This is deliberately separate from
    invigilator login: the pipeline never holds a user account, and possession
    of the device key grants event ingestion only — no dashboard or user access.
    """

    def __init__(
        self,
        backend_url: str = "http://localhost:8000",
        device_code: Optional[str] = None,
        device_key: Optional[str] = None,
        heartbeat_interval: float = 10.0,
    ):
        self.backend_url = backend_url.rstrip("/")
        self.device_code = device_code or os.environ.get(ROBOT_DEVICE_CODE_ENV, "ROBOT-01")
        self.device_key = device_key or os.environ.get(ROBOT_DEVICE_KEY_ENV, "Robot-Dev-Key-2026!")
        self.events_endpoint = f"{self.backend_url}/api/events/ai"
        self.sync_endpoint = f"{self.backend_url}/api/events/sync"
        self.heartbeat_endpoint = f"{self.backend_url}/api/events/device/heartbeat"
        self.last_sync_time = 0.0
        self.heartbeat_interval = heartbeat_interval
        self.last_heartbeat_time = 0.0

    @property
    def _headers(self) -> dict:
        return {
            "X-Device-Code": self.device_code,
            "X-Device-Key": self.device_key,
        }

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
        """Sends an alert event to the backend.

        Each event carries a unique `event_uid`, so if the POST times out the
        same event can be safely re-sent without creating a duplicate alert on
        the dashboard.
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
            "event_uid": f"{self.device_code}-{track_id}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}",
        }

        try:
            resp = requests.post(
                self.events_endpoint, json=payload, headers=self._headers, timeout=2.0
            )
            if resp.status_code == 401:
                print("[EventGenerator] Device credentials rejected — check ROBOT_DEVICE_KEY.")
            return resp.status_code == 201
        except Exception as e:
            # Non-blocking log if backend server is temporarily unreachable
            print(f"[EventGenerator] Warning: Could not post event to backend: {e}")
            return False

    def sync_status(self, live_student_count: int, fps: int, tracks: list) -> bool:
        """Throttled status sync every 1 second."""
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
            resp = requests.post(
                self.sync_endpoint, json=payload, headers=self._headers, timeout=1.0
            )
            return resp.status_code == 200
        except Exception:
            return False

    def send_heartbeat(self, camera_codes: Optional[list] = None, detail: Optional[str] = None) -> bool:
        """Report that this device and its cameras are alive.

        This is what moves a registered camera from `unknown` to `online` on the
        dashboard — a camera is never assumed to be online just because it is
        configured.
        """
        now = time.time()
        if now - self.last_heartbeat_time < self.heartbeat_interval:
            return False
        self.last_heartbeat_time = now

        payload = {
            "device_code": self.device_code,
            "status": "online",
            "detail": detail,
            "camera_codes": camera_codes or [],
        }
        try:
            resp = requests.post(
                self.heartbeat_endpoint, json=payload, headers=self._headers, timeout=2.0
            )
            return resp.status_code == 200
        except Exception:
            return False
