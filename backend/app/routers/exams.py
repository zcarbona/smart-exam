from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user
from backend.app.models.models import ExamSession, ExamStatus, StudentTrack, User, ViolationEvent
from backend.app.schemas.schemas import ExamStatusOut, StudentAssignRequest, StudentTrackOut, ViolationEventOut
from backend.app.routers.ws import manager

router = APIRouter(prefix="/api/exams", tags=["exams"])

async def get_active_session(db: AsyncSession) -> Optional[ExamSession]:
    query = (
        select(ExamSession)
        .where(ExamSession.status != ExamStatus.COMPLETED)
        .order_by(ExamSession.created_at.desc())
    )
    return (await db.execute(query)).scalars().first()

@router.get("/status", response_model=ExamStatusOut)
async def get_current_exam_status(db: AsyncSession = Depends(get_db)):
    session = await get_active_session(db)
    if not session:
        session = ExamSession(title="Proctored Exam", room_name="Hall 101", status=ExamStatus.RUNNING)
        db.add(session)
        await db.commit()
        await db.refresh(session)
    return session

@router.post("/pause", response_model=ExamStatusOut)
async def pause_exam(
    reason: str = "Manual proctor pause",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await get_active_session(db)
    if not session:
        raise HTTPException(status_code=404, detail="No active exam session")
    session.status = ExamStatus.PAUSED
    session.pause_reason = reason
    await db.commit()
    await db.refresh(session)

    await manager.broadcast({
        "type": "exam_state",
        "data": {"status": "paused", "reason": reason}
    })
    return session

@router.post("/resume", response_model=ExamStatusOut)
async def resume_exam(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await get_active_session(db)
    if not session:
        raise HTTPException(status_code=404, detail="No active exam session")
    session.status = ExamStatus.RUNNING
    session.pause_reason = None
    await db.commit()
    await db.refresh(session)

    await manager.broadcast({
        "type": "exam_state",
        "data": {"status": "running"}
    })
    return session

@router.get("/students", response_model=List[StudentTrackOut])
async def list_students(db: AsyncSession = Depends(get_db)):
    session = await get_active_session(db)
    if not session:
        return []

    query = (
        select(StudentTrack)
        .where(StudentTrack.exam_session_id == session.id)
        .options(selectinload(StudentTrack.events))
    )
    students = (await db.execute(query)).scalars().all()
    results = []
    for s in students:
        ev_out = []
        for ev in s.events[-20:]:
            ev_url = f"/api/events/evidence/{ev.evidence_path}" if ev.evidence_path else None
            ev_out.append(
                ViolationEventOut(
                    id=ev.id,
                    track_id=ev.track_id,
                    event_type=ev.event_type,
                    points=ev.points,
                    evidence_url=ev_url,
                    timestamp=ev.timestamp,
                )
            )
        results.append(
            StudentTrackOut(
                track_id=s.track_id,
                student_college_id=s.student_college_id,
                student_name=s.student_name,
                score=s.score,
                is_suspicious=s.is_suspicious,
                presence_state=s.presence_state,
                head_yaw=s.head_yaw,
                head_pitch=s.head_pitch,
                gaze_direction=s.gaze_direction,
                zone_status=s.zone_status,
                events=ev_out,
            )
        )
    return results

@router.post("/assign-student")
async def assign_student(
    payload: StudentAssignRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await get_active_session(db)
    if not session:
        raise HTTPException(status_code=404, detail="No active exam session")

    query = select(StudentTrack).where(
        StudentTrack.exam_session_id == session.id,
        StudentTrack.track_id == payload.track_id,
    )
    student = (await db.execute(query)).scalars().first()
    if not student:
        student = StudentTrack(
            exam_session_id=session.id,
            track_id=payload.track_id,
            student_college_id=payload.student_college_id,
            student_name=payload.student_name,
        )
        db.add(student)
    else:
        student.student_college_id = payload.student_college_id
        student.student_name = payload.student_name

    await db.commit()
    await db.refresh(student)

    await manager.broadcast({
        "type": "student_assigned",
        "data": {
            "track_id": student.track_id,
            "student_college_id": student.student_college_id,
            "student_name": student.student_name,
        }
    })
    return {"ok": True, "track_id": student.track_id, "student_name": student.student_name}
