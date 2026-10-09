import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Enum,
    Float,
    Text,
)
from sqlalchemy.orm import relationship, DeclarativeBase


def utcnow() -> datetime:
    """Naive UTC timestamp, matching the existing column semantics."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    INVIGILATOR = "invigilator"

    # Legacy alias. `Enum(UserRole)` persists the *member name*, so rows written
    # by earlier versions hold "PROCTOR". Mapping it onto INVIGILATOR keeps that
    # historical data valid while the application only ever issues the two roles
    # above. Remove once the legacy rows have been migrated.
    PROCTOR = "invigilator"


class ExamStatus(str, enum.Enum):
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.INVIGILATOR, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, server_default="1")
    full_name = Column(String(100), nullable=True)

    # Optional room assignment. When set, every exam/camera/event query this
    # user can reach is constrained to that room.
    assigned_room_id = Column(
        Integer, ForeignKey("exam_rooms.id", ondelete="SET NULL"), nullable=True, index=True
    )

    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    refresh_token = Column(String(512), nullable=True, index=True)
    refresh_token_expires = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    assigned_room = relationship("ExamRoom", back_populates="invigilators")


class ExamRoom(Base):
    __tablename__ = "exam_rooms"

    id = Column(Integer, primary_key=True, index=True)
    room_code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    building = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, server_default="1")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    invigilators = relationship("User", back_populates="assigned_room")
    exam_sessions = relationship("ExamSession", back_populates="room")
    cameras = relationship("CameraDevice", back_populates="room")


class CameraDevice(Base):
    """A physical camera feed attached to a room.

    `is_online` is refreshed only by an authenticated device heartbeat from the
    AI pipeline, so a configured-but-silent camera is never reported as online.
    """

    __tablename__ = "camera_devices"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("exam_rooms.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    device_code = Column(String(50), unique=True, index=True, nullable=False)
    status = Column(String(50), default="unknown", nullable=False)  # unknown|online|offline
    last_seen_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    room = relationship("ExamRoom", back_populates="cameras")


class RobotDevice(Base):
    """Robot / edge device identity.

    Authentication for this device is intentionally separate from invigilator
    login: it is a device code plus a pre-shared key, never a user account.
    """

    __tablename__ = "robot_devices"

    id = Column(Integer, primary_key=True, index=True)
    device_code = Column(String(50), unique=True, default="ROBOT-01")
    api_key_hash = Column(String(255), nullable=True)
    status = Column(String(50), default="idle")  # idle, inspecting, charging, offline
    battery_level = Column(Float, default=95.0)
    current_zone = Column(String(50), default="Aisle 1")
    last_ping = Column(DateTime, default=utcnow)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class ExamSession(Base):
    __tablename__ = "exam_sessions"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("exam_rooms.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(100), default="Final Exam")
    room_name = Column(String(50), default="Hall 101")
    status = Column(Enum(ExamStatus), default=ExamStatus.RUNNING)
    pause_reason = Column(String(100), nullable=True)
    student_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    room = relationship("ExamRoom", back_populates="exam_sessions")
    students = relationship("StudentTrack", back_populates="exam_session", cascade="all, delete-orphan")
    events = relationship("ViolationEvent", back_populates="exam_session", cascade="all, delete-orphan")


class StudentTrack(Base):
    __tablename__ = "student_tracks"

    id = Column(Integer, primary_key=True, index=True)
    exam_session_id = Column(Integer, ForeignKey("exam_sessions.id"), nullable=False)
    track_id = Column(Integer, index=True, nullable=False)
    student_college_id = Column(String(50), nullable=True)
    student_name = Column(String(100), nullable=True)
    score = Column(Float, default=0.0)
    is_suspicious = Column(Boolean, default=False)
    presence_state = Column(String(50), default="present")
    head_yaw = Column(Float, default=0.0)
    head_pitch = Column(Float, default=0.0)
    gaze_direction = Column(String(50), default="Eyes Center")
    zone_status = Column(String(50), default="safe")
    last_seen = Column(DateTime, default=utcnow)
    created_at = Column(DateTime, default=utcnow)

    exam_session = relationship("ExamSession", back_populates="students")
    events = relationship("ViolationEvent", back_populates="student_track", cascade="all, delete-orphan")


class ViolationEvent(Base):
    __tablename__ = "violation_events"

    id = Column(Integer, primary_key=True, index=True)
    exam_session_id = Column(Integer, ForeignKey("exam_sessions.id"), nullable=False)
    student_track_id = Column(Integer, ForeignKey("student_tracks.id"), nullable=True)
    track_id = Column(Integer, nullable=True)
    event_uid = Column(String(64), unique=True, nullable=True, index=True)
    event_type = Column(String(100), nullable=False)
    points = Column(Float, default=0.0)
    evidence_path = Column(String(255), nullable=True)
    timestamp = Column(DateTime, default=utcnow)

    exam_session = relationship("ExamSession", back_populates="events")
    student_track = relationship("StudentTrack", back_populates="events")
