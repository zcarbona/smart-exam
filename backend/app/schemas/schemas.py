from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: str
    is_active: bool = True
    full_name: Optional[str] = None
    assigned_room_id: Optional[int] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LogoutResponse(BaseModel):
    ok: bool = True


# --- Invigilator management (admin only) --------------------------------------
# Note: there is deliberately no `role` field on any of these schemas. The server
# assigns `invigilator` itself, so a client can never request elevation.

class InvigilatorCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=12, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=100)
    email: Optional[str] = Field(default=None, max_length=100)
    assigned_room_id: Optional[int] = None


class InvigilatorUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=100)
    email: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None
    assigned_room_id: Optional[int] = None
    password: Optional[str] = Field(default=None, min_length=12, max_length=128)


# --- Exam rooms --------------------------------------------------------------

class RoomCreate(BaseModel):
    room_code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    building: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None


class RoomUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    building: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None


class CameraCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    device_code: str = Field(min_length=1, max_length=50)


class RoomOut(BaseModel):
    id: int
    room_code: str
    name: str
    building: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


class CameraOut(BaseModel):
    id: int
    room_id: int
    name: str
    device_code: str
    status: str
    last_seen_at: Optional[datetime] = None
    last_error: Optional[str] = None

    class Config:
        from_attributes = True


class RoomDetailOut(RoomOut):
    cameras: List[CameraOut] = []


# --- Events from AI Pipeline -------------------------------------------------

class AIEventCreate(BaseModel):
    track_id: int
    event_type: str
    points: float
    evidence_base64: Optional[str] = None
    head_yaw: Optional[float] = 0.0
    head_pitch: Optional[float] = 0.0
    gaze_direction: Optional[str] = "Eyes Center"
    zone_status: Optional[str] = "safe"
    presence_state: Optional[str] = "present"
    current_score: Optional[float] = None
    # Client-generated unique id. Lets the pipeline retry safely and lets the
    # backend drop replayed submissions.
    event_uid: Optional[str] = Field(default=None, max_length=64)


class AITrackState(BaseModel):
    track_id: int
    head_yaw: float = 0.0
    head_pitch: float = 0.0
    gaze_direction: str = "Eyes Center"
    gaze_baseline_h: float = 0.5
    zone_status: str = "safe"
    score: float = 0.0
    presence_state: str = "present"


class AIStatusSync(BaseModel):
    live_student_count: int
    fps: int
    tracks: List[AITrackState] = []


class DeviceHeartbeat(BaseModel):
    device_code: Optional[str] = Field(default=None, max_length=50)
    status: str = "online"
    detail: Optional[str] = Field(default=None, max_length=255)
    # Which registered cameras this device is currently feeding. A device can
    # own several; listing them makes the mapping explicit instead of guessed.
    camera_codes: List[str] = Field(default_factory=list)


class ViolationEventOut(BaseModel):
    id: int
    track_id: Optional[int] = None
    student_name: Optional[str] = None
    student_college_id: Optional[str] = None
    event_type: str
    points: float
    total_score: Optional[float] = None
    is_suspicious: Optional[bool] = None
    evidence_url: Optional[str] = None
    timestamp: datetime

    class Config:
        from_attributes = True

    @field_validator("student_name", "student_college_id", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        # An unnamed track renders as "Unknown" in the UI rather than as a
        # fabricated placeholder such as "Student 3".
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v


class StudentAssignRequest(BaseModel):
    track_id: int
    student_college_id: str
    student_name: str


class StudentTrackOut(BaseModel):
    track_id: int
    student_college_id: Optional[str] = None
    student_name: Optional[str] = None
    score: float
    is_suspicious: bool
    presence_state: str
    head_yaw: float
    head_pitch: float
    gaze_direction: str
    zone_status: str
    events: List[ViolationEventOut] = []

    class Config:
        from_attributes = True


class ExamStatusOut(BaseModel):
    id: int
    title: str
    room_name: str
    room_id: Optional[int] = None
    status: str
    pause_reason: Optional[str] = None
    student_count: int

    class Config:
        from_attributes = True


class ExamStartRequest(BaseModel):
    title: str = Field(default="Proctored Exam", max_length=100)
    room_id: Optional[int] = None
    room_name: Optional[str] = Field(default=None, max_length=50)


class DashboardStatsOut(BaseModel):
    """Every figure here is computed from persisted rows; nothing is constant."""

    active_exams: int
    paused_exams: int
    tracked_students: int
    suspicious_students: int
    total_events: int
    events_last_hour: int
    events_today: int
    cameras_total: int
    cameras_online: int
    cameras_offline: int
    cameras_unknown: int
    robots_total: int
    robots_online: int
    event_type_breakdown: List[dict] = []


class RobotStatusOut(BaseModel):
    device_code: str
    status: str
    battery_level: float
    current_zone: str
    last_ping: datetime

    class Config:
        from_attributes = True


class RobotDeviceCreate(BaseModel):
    device_code: str = Field(min_length=1, max_length=50)
    device_key: str = Field(min_length=12, max_length=128)


class RobotDispatchCommand(BaseModel):
    target_track_id: int
    reason: str = "Proctor manual dispatch"
