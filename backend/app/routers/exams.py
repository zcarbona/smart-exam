from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.database import get_db
from backend.app.core.security import (
    require_admin,
    require_invigilator,
    scoped_room_id,
    user_can_access_session,
)
from backend.app.models.models import ExamRoom, ExamSession, ExamStatus, StudentTrack, User, ViolationEvent
from backend.app.schemas.schemas import (
    ExamStartRequest,
    ExamStatusOut,
    StudentAssignRequest,
    StudentTrackOut,
    ViolationEventOut,
)
from backend.app.routers.ws import manager

router = APIRouter(prefix="/api/exams", tags=["exams"])


def _visible_session(user: User, session: Optional[ExamSession]) -> Optional[ExamSession]:
    """Per-row authorization. A scoped invigilator gets None instead of a
    404-vs-403 distinction so the existence of another room's session is not
    leaked."""
    if session is None:
        return None
    if not user_can_access_session(user, session.room_id):
        return None
    return session


async def get_active_session(db: AsyncSession, user: Optional[User] = None) -> Optional[ExamSession]:
    query = (
        select(ExamSession)
        .where(ExamSession.status != ExamStatus.COMPLETED)
        .order_by(ExamSession.created_at.desc())
    )
    if user is not None:
        room_scope = scoped_room_id(user)
        if room_scope is not None:
            query = query.where(ExamSession.room_id == room_scope)
    return (await db.execute(query)).scalars().first()


@router.get("/status", response_model=Optional[ExamStatusOut])
async def get_current_exam_status(
    user: User = Depends(require_invigilator),
    db: AsyncSession = Depends(get_db),
):
    """The caller's active exam, or null.

    A GET never creates a session: if no exam is running the answer is honestly
    "there is none" rather than a fabricated default exam in "Hall 101".
    """
    session = _visible_session(user, await get_active_session(db, user))
    return session


@router.post("/start", response_model=ExamStatusOut)
async def start_exam(
    payload: Optional[ExamStartRequest] = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Begin a new exam session. Admin-only, and always tied to a real room."""
    payload = payload or ExamStartRequest()

    room: Optional[ExamRoom] = None
    if payload.room_id is not None:
        room = await db.get(ExamRoom, payload.room_id)
        if not room:
            raise HTTPException(status_code=400, detail="Exam room does not exist")
    elif payload.room_name:
        room = (
            await db.execute(select(ExamRoom).where(ExamRoom.name == payload.room_name))
        ).scalars().first()
        if not room:
            raise HTTPException(
                status_code=400,
                detail="Exam room does not exist. Create it first, then start the exam.",
            )
    else:
        raise HTTPException(status_code=400, detail="An exam must be assigned to a room")

    existing = (
        await db.execute(
            select(ExamSession)
            .where(ExamSession.status != ExamStatus.COMPLETED, ExamSession.room_id == room.id)
            .order_by(ExamSession.created_at.desc())
        )
    ).scalars().first()
    if existing:
        return existing

    session = ExamSession(
        title=payload.title,
        room_id=room.id,
        room_name=room.name,
        status=ExamStatus.RUNNING,
        student_count=0,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    await manager.broadcast(
        {"type": "exam_state", "data": {"status": "running", "session_id": session.id, "room": room.name}},
        room_id=session.room_id,
    )
    return session


@router.post("/pause", response_model=ExamStatusOut)
async def pause_exam(
    reason: str = "Manual proctor pause",
    user: User = Depends(require_invigilator),
    db: AsyncSession = Depends(get_db),
):
    session = await get_active_session(db, user)
    if not session or not user_can_access_session(user, session.room_id):
        raise HTTPException(status_code=404, detail="No accessible active exam session")
    session.status = ExamStatus.PAUSED
    session.pause_reason = reason
    await db.commit()
    await db.refresh(session)

    await manager.broadcast(
        {"type": "exam_state", "data": {"status": "paused", "reason": reason}},
        room_id=session.room_id,
    )
    return session


@router.post("/resume", response_model=ExamStatusOut)
async def resume_exam(
    user: User = Depends(require_invigilator),
    db: AsyncSession = Depends(get_db),
):
    session = await get_active_session(db, user)
    if not session or not user_can_access_session(user, session.room_id):
        raise HTTPException(status_code=404, detail="No accessible active exam session")
    session.status = ExamStatus.RUNNING
    session.pause_reason = None
    await db.commit()
    await db.refresh(session)

    await manager.broadcast(
        {"type": "exam_state", "data": {"status": "running"}},
        room_id=session.room_id,
    )
    return session


@router.get("/students", response_model=List[StudentTrackOut])
async def list_students(
    user: User = Depends(require_invigilator),
    db: AsyncSession = Depends(get_db),
):
    session = _visible_session(user, await get_active_session(db, user))
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
                    student_name=s.student_name,
                    student_college_id=s.student_college_id,
                    event_type=ev.event_type,
                    points=ev.points,
                    total_score=s.score,
                    is_suspicious=s.is_suspicious,
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
    user: User = Depends(require_invigilator),
    db: AsyncSession = Depends(get_db),
):
    session = await get_active_session(db, user)
    if not session or not user_can_access_session(user, session.room_id):
        raise HTTPException(status_code=404, detail="No accessible active exam session")

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

    await manager.broadcast(
        {
            "type": "student_assigned",
            "data": {
                "track_id": student.track_id,
                "student_college_id": student.student_college_id,
                "student_name": student.student_name,
            },
        },
        room_id=session.room_id,
    )
    return {"ok": True, "track_id": student.track_id, "student_name": student.student_name}
