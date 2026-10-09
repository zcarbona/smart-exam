import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum, Float, Text
from sqlalchemy.orm import relationship, DeclarativeBase

class Base(DeclarativeBase):
    pass

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    PROCTOR = "proctor"

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
    role = Column(Enum(UserRole), default=UserRole.PROCTOR, nullable=False)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    refresh_token = Column(String(512), nullable=True, index=True)
    refresh_token_expires = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ExamSession(Base):
    __tablename__ = "exam_sessions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), default="Final Exam")
    room_name = Column(String(50), default="Hall 101")
    status = Column(Enum(ExamStatus), default=ExamStatus.RUNNING)
    pause_reason = Column(String(100), nullable=True)
    student_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    last_seen = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    exam_session = relationship("ExamSession", back_populates="students")
    events = relationship("ViolationEvent", back_populates="student_track", cascade="all, delete-orphan")

class ViolationEvent(Base):
    __tablename__ = "violation_events"

    id = Column(Integer, primary_key=True, index=True)
    exam_session_id = Column(Integer, ForeignKey("exam_sessions.id"), nullable=False)
    student_track_id = Column(Integer, ForeignKey("student_tracks.id"), nullable=True)
    track_id = Column(Integer, nullable=True)
    event_type = Column(String(100), nullable=False)
    points = Column(Float, default=0.0)
    evidence_path = Column(String(255), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    exam_session = relationship("ExamSession", back_populates="events")
    student_track = relationship("StudentTrack", back_populates="events")

class RobotDevice(Base):
    """Stubbed model ready for future Robot / MQTT integration"""
    __tablename__ = "robot_devices"

    id = Column(Integer, primary_key=True, index=True)
    device_code = Column(String(50), unique=True, default="ROBOT-01")
    status = Column(String(50), default="idle")  # idle, inspecting, charging, offline
    battery_level = Column(Float, default=95.0)
    current_zone = Column(String(50), default="Aisle 1")
    last_ping = Column(DateTime, default=datetime.utcnow)
