from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field

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

    class Config:
        from_attributes = True

# Events from AI Pipeline
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

class ViolationEventOut(BaseModel):
    id: int
    track_id: Optional[int] = None
    event_type: str
    points: float
    evidence_url: Optional[str] = None
    timestamp: datetime

    class Config:
        from_attributes = True

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
    status: str
    pause_reason: Optional[str] = None
    student_count: int

    class Config:
        from_attributes = True

class RobotStatusOut(BaseModel):
    device_code: str
    status: str
    battery_level: float
    current_zone: str
    last_ping: datetime

    class Config:
        from_attributes = True

class RobotDispatchCommand(BaseModel):
    target_track_id: int
    reason: str = "Proctor manual dispatch"
