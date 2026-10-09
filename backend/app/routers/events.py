import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import DEVICE_HEARTBEAT_TIMEOUT_SECONDS, EVIDENCE_DIR
from backend.app.core.database import get_db
from backend.app.core.security import (
    get_current_robot,
    require_invigilator,
    scoped_room_id,
)
from backend.app.models.models import (
    CameraDevice,
    ExamSession,
    ExamStatus,
    RobotDevice,
    StudentTrack,
    User,
    ViolationEvent,
)
from backend.app.schemas.schemas import (
    AIEventCreate,
    AIStatusSync,
    DashboardStatsOut,
    DeviceHeartbeat,
    ViolationEventOut,
)
from backend.app.services.stats import build_dashboard_stats
from backend.app.routers.ws import manager

router = APIRouter(prefix="/api/events", tags=["events"])

SUSPICIOUS_THRESHOLD = 10.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def get_or_create_active_session(db: AsyncSession) -> ExamSession:
    query = select(ExamSession).where(ExamSession.status != ExamStatus.COMPLETED).order_by(ExamSession.created_at.desc())
    session = (await db.execute(query)).scalars().first()
    if not session:
        session = ExamSession(title="Automated Exam Session", room_name="Room A", status=ExamStatus.RUNNING)
        db.add(session)
        await db.commit()
        await db.refresh(session)
    return session


def _evidence_url(filename: Optional[str]) -> Optional[str]:
    return f"/api/events/evidence/{filename}" if filename else None


def _safe_evidence_path(filename: str) -> Path:
    """Resolve an evidence filename inside EVIDENCE_DIR, refusing traversal."""
    if filename != Path(filename).name or filename in (".", ".."):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid evidence filename")
    path = (Path(EVIDENCE_DIR) / filename).resolve()
    root = Path(EVIDENCE_DIR).resolve()
    if root not in path.parents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid evidence filename")
    return path


def _event_out(ev: ViolationEvent, student: Optional[StudentTrack] = None) -> ViolationEventOut:
    return ViolationEventOut(
        id=ev.id,
        track_id=ev.track_id,
        student_name=student.student_name if student else None,
        student_college_id=student.student_college_id if student else None,
        event_type=ev.event_type,
        points=ev.points,
        total_score=student.score if student else None,
        is_suspicious=student.is_suspicious if student else None,
        evidence_url=_evidence_url(ev.evidence_path),
        timestamp=ev.timestamp,
    )


@router.post("/device/heartbeat")
async def device_heartbeat(
    payload: DeviceHeartbeat,
    device: RobotDevice = Depends(get_current_robot),
    db: AsyncSession = Depends(get_db),
):
    """Report liveness for the device itself and the cameras it drives.

    This is the only source of truth for camera online/offline state. Cameras
    registered by an admin start as `unknown` and only move to `online` once a
    heartbeat names them, so a configuration row alone never implies a working
    camera.
    """
    now = _utcnow()

    if payload.device_code and payload.device_code != device.device_code:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device may only report its own status",
        )

    is_online = payload.status.lower() in ("online", "ok", "healthy")
    device.status = "online" if is_online else "offline"
    if payload.detail:
        device.current_zone = payload.detail[:50]
    device.last_ping = now
    db.add(device)

    # A camera is "online" only while a heartbeat explicitly names it. When the
    # device reports offline, every camera it previously owned goes offline too.
    camera_query = select(CameraDevice).where(CameraDevice.device_code == device.device_code)
    if payload.camera_codes:
        camera_query = select(CameraDevice).where(
            CameraDevice.device_code.in_([device.device_code, *payload.camera_codes])
        )
    cameras = list((await db.execute(camera_query)).scalars().all())

    for camera in cameras:
        if is_online:
            camera.status = "online"
            camera.last_seen_at = now
            camera.last_error = None
        else:
            camera.status = "offline"
            camera.last_error = (payload.detail or "Device reported offline")[:255]
        db.add(camera)

    await db.commit()

    # Reconcile: anything claiming to be online that has not been heard from
    # within the heartbeat window is reported offline to the dashboard.
    cutoff = now - timedelta(seconds=DEVICE_HEARTBEAT_TIMEOUT_SECONDS)
    stale = (
        await db.execute(
            select(CameraDevice).where(
                CameraDevice.status == "online",
                or_(CameraDevice.last_seen_at.is_(None), CameraDevice.last_seen_at < cutoff),
            )
        )
    ).scalars().all()
    for camera in stale:
        camera.status = "offline"
        camera.last_error = "No heartbeat received"
        db.add(camera)
    if stale:
        await db.commit()

    return {
        "ok": True,
        "device_code": device.device_code,
        "online": is_online,
        "cameras_updated": len(cameras),
        "cameras_marked_offline": len(stale),
    }


@router.post("/ai", status_code=status.HTTP_201_CREATED)
async def ingest_ai_event(
    payload: AIEventCreate,
    device: RobotDevice = Depends(get_current_robot),
    db: AsyncSession = Depends(get_db),
):
    """Accept a violation event from the authenticated AI device.

    Order matters: authenticate -> validate -> replay-check -> persist ->
    broadcast. Nothing is broadcast that has not first been committed.
    """
    session = await get_or_create_active_session(db)

    # Replay protection: a retried upload carries the same event_uid and is
    # answered idempotently instead of creating a second alert.
    if payload.event_uid:
        existing = (
            await db.execute(select(ViolationEvent).where(ViolationEvent.event_uid == payload.event_uid))
        ).scalars().first()
        if existing:
            return {"ok": True, "event_id": existing.id, "duplicate": True}

    st_query = select(StudentTrack).where(
        StudentTrack.exam_session_id == session.id,
        StudentTrack.track_id == payload.track_id,
    )
    student = (await db.execute(st_query)).scalars().first()
    now = _utcnow()

    if not student:
        student = StudentTrack(
            exam_session_id=session.id,
            track_id=payload.track_id,
            # Deliberately left null: the UI renders "Unknown" until a proctor
            # binds a real identity, rather than inventing "Student 3".
            student_name=None,
            score=0.0,
            last_seen=now,
        )
        db.add(student)
        await db.flush()

    evidence_filename = None
    if payload.evidence_base64:
        try:
            ts_str = now.strftime("%Y%m%d_%H%M%S_%f")[:-3]
            evidence_filename = f"{payload.event_type}_track{payload.track_id}_{ts_str}.jpg"
            file_path = _safe_evidence_path(evidence_filename)
            with open(file_path, "wb") as f:
                f.write(base64.b64decode(payload.evidence_base64, validate=True))
        except HTTPException:
            raise
        except Exception as e:
            print(f"[Event Router] Failed to save evidence base64: {e}")

    if payload.current_score is not None:
        student.score = payload.current_score
    else:
        student.score += payload.points

    student.is_suspicious = student.score >= SUSPICIOUS_THRESHOLD
    student.head_yaw = payload.head_yaw or 0.0
    student.head_pitch = payload.head_pitch or 0.0
    student.gaze_direction = payload.gaze_direction or "Eyes Center"
    student.zone_status = payload.zone_status or "safe"
    student.presence_state = payload.presence_state or "present"
    student.last_seen = now

    event = ViolationEvent(
        exam_session_id=session.id,
        student_track_id=student.id,
        track_id=payload.track_id,
        event_uid=payload.event_uid,
        event_type=payload.event_type,
        points=payload.points,
        evidence_path=evidence_filename,
        timestamp=now,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    evidence_url = _evidence_url(evidence_filename)
    ws_payload = {
        "type": "violation_event",
        "data": {
            "id": event.id,
            "exam_session_id": session.id,
            "track_id": student.track_id,
            "student_name": student.student_name,
            "student_college_id": student.student_college_id,
            "event_type": event.event_type,
            "points": event.points,
            "total_score": student.score,
            "is_suspicious": student.is_suspicious,
            "evidence_url": evidence_url,
            "timestamp": now.strftime("%H:%M:%S"),
        },
    }
    await manager.broadcast(ws_payload, room_id=session.room_id)

    return {"ok": True, "event_id": event.id, "student_score": student.score}


@router.post("/sync")
async def sync_ai_status(
    payload: AIStatusSync,
    device: RobotDevice = Depends(get_current_robot),
    db: AsyncSession = Depends(get_db),
):
    session = await get_or_create_active_session(db)
    session.student_count = payload.live_student_count

    device.last_ping = _utcnow()
    db.add(device)
    await db.commit()

    ws_payload = {
        "type": "status_sync",
        "data": {
            "live_student_count": payload.live_student_count,
            "fps": payload.fps,
            "tracks": [t.model_dump() for t in payload.tracks],
        },
    }
    await manager.broadcast(ws_payload, room_id=session.room_id)
    return {"ok": True}


@router.get("/recent", response_model=List[ViolationEventOut])
async def get_recent_events(
    limit: int = 50,
    user: User = Depends(require_invigilator),
    db: AsyncSession = Depends(get_db),
):
    limit = max(1, min(limit, 200))
    query = select(ViolationEvent, StudentTrack).join(
        StudentTrack, ViolationEvent.student_track_id == StudentTrack.id, isouter=True
    )
    room_scope = scoped_room_id(user)
    if room_scope is not None:
        query = query.where(ViolationEvent.exam_session_id.in_(
            select(ExamSession.id).where(ExamSession.room_id == room_scope)
        ))
    query = query.order_by(ViolationEvent.timestamp.desc()).limit(limit)

    return [_event_out(ev, student) for ev, student in (await db.execute(query)).all()]


@router.get("/stats", response_model=DashboardStatsOut)
async def get_dashboard_stats(
    user: User = Depends(require_invigilator),
    db: AsyncSession = Depends(get_db),
):
    """Single source of truth for dashboard counters, scoped to the caller."""
    return DashboardStatsOut(**await build_dashboard_stats(db, user))


@router.get("/cameras")
async def get_camera_statuses(
    user: User = Depends(require_invigilator),
    db: AsyncSession = Depends(get_db),
):
    """Actual camera connection state.

    A camera with no recent heartbeat is reported `offline` here, and one that
    has never reported in stays `unknown` — never assumed online.
    """
    query = select(CameraDevice)
    room_scope = scoped_room_id(user)
    if room_scope is not None:
        query = query.where(CameraDevice.room_id == room_scope)

    cutoff = _utcnow() - timedelta(seconds=DEVICE_HEARTBEAT_TIMEOUT_SECONDS)
    cameras = (await db.execute(query)).scalars().all()

    output = []
    for cam in cameras:
        status_value = cam.status
        if cam.status == "online" and (cam.last_seen_at is None or cam.last_seen_at < cutoff):
            status_value = "offline"
        output.append({
            "id": cam.id,
            "room_id": cam.room_id,
            "name": cam.name,
            "device_code": cam.device_code,
            "status": status_value,
            "last_seen_at": cam.last_seen_at,
            "last_error": cam.last_error,
        })
    return output


@router.get("/evidence/{filename}")
async def get_evidence_image(
    filename: str,
    user: User = Depends(require_invigilator),
):
    """Evidence photos of identifiable students — authentication required."""
    file_path = _safe_evidence_path(filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Evidence image not found")
    return FileResponse(path=file_path, media_type="image/jpeg")
