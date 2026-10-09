import os
import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import EVIDENCE_DIR
from backend.app.core.database import get_db
from backend.app.models.models import ExamSession, ExamStatus, StudentTrack, ViolationEvent
from backend.app.schemas.schemas import AIEventCreate, AIStatusSync, ViolationEventOut
from backend.app.routers.ws import manager

router = APIRouter(prefix="/api/events", tags=["events"])

async def get_or_create_active_session(db: AsyncSession) -> ExamSession:
    query = select(ExamSession).where(ExamSession.status != ExamStatus.COMPLETED).order_by(ExamSession.created_at.desc())
    session = (await db.execute(query)).scalars().first()
    if not session:
        session = ExamSession(title="Automated Exam Session", room_name="Room A", status=ExamStatus.RUNNING)
        db.add(session)
        await db.commit()
        await db.refresh(session)
    return session

@router.post("/ai", status_code=status.HTTP_201_CREATED)
async def ingest_ai_event(payload: AIEventCreate, db: AsyncSession = Depends(get_db)):
    session = await get_or_create_active_session(db)

    st_query = select(StudentTrack).where(
        StudentTrack.exam_session_id == session.id,
        StudentTrack.track_id == payload.track_id,
    )
    student = (await db.execute(st_query)).scalars().first()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if not student:
        student = StudentTrack(
            exam_session_id=session.id,
            track_id=payload.track_id,
            student_name=f"Student {payload.track_id}",
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
            file_path = Path(EVIDENCE_DIR) / evidence_filename
            with open(file_path, "wb") as f:
                f.write(base64.b64decode(payload.evidence_base64))
        except Exception as e:
            print(f"[Event Router] Failed to save evidence base64: {e}")

    if payload.current_score is not None:
        student.score = payload.current_score
    else:
        student.score += payload.points

    student.is_suspicious = student.score >= 10.0
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
        event_type=payload.event_type,
        points=payload.points,
        evidence_path=evidence_filename,
        timestamp=now,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    evidence_url = f"/api/events/evidence/{evidence_filename}" if evidence_filename else None
    ws_payload = {
        "type": "violation_event",
        "data": {
            "id": event.id,
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
    await manager.broadcast(ws_payload)

    return {"ok": True, "event_id": event.id, "student_score": student.score}

@router.post("/sync")
async def sync_ai_status(payload: AIStatusSync, db: AsyncSession = Depends(get_db)):
    session = await get_or_create_active_session(db)
    session.student_count = payload.live_student_count
    await db.commit()

    ws_payload = {
        "type": "status_sync",
        "data": {
            "live_student_count": payload.live_student_count,
            "fps": payload.fps,
            "tracks": [t.model_dump() for t in payload.tracks],
        },
    }
    await manager.broadcast(ws_payload)
    return {"ok": True}

@router.get("/recent", response_model=List[ViolationEventOut])
async def get_recent_events(limit: int = 50, db: AsyncSession = Depends(get_db)):
    query = select(ViolationEvent).order_by(ViolationEvent.timestamp.desc()).limit(limit)
    results = (await db.execute(query)).scalars().all()
    events_out = []
    for ev in results:
        ev_url = f"/api/events/evidence/{ev.evidence_path}" if ev.evidence_path else None
        events_out.append(
            ViolationEventOut(
                id=ev.id,
                track_id=ev.track_id,
                event_type=ev.event_type,
                points=ev.points,
                evidence_url=ev_url,
                timestamp=ev.timestamp,
            )
        )
    return events_out

@router.get("/evidence/{filename}")
async def get_evidence_image(filename: str):
    file_path = Path(EVIDENCE_DIR) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Evidence image not found")
    return FileResponse(path=file_path, media_type="image/jpeg")
