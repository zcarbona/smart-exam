"""Dashboard statistics computed from persisted records.

Everything returned here is derived from database rows. There are no constants,
no baseline totals, and no fallback figures: if the tables are empty the counts
simply come back as zero and the UI shows an empty state.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import DEVICE_HEARTBEAT_TIMEOUT_SECONDS
from backend.app.core.security import scoped_room_id
from backend.app.models.models import (
    CameraDevice,
    ExamSession,
    ExamStatus,
    RobotDevice,
    StudentTrack,
    ViolationEvent,
)


# The canonical single-scope helper: one definition of "what room is this user
# locked to", shared by aggregate endpoints and per-row checks.
_scoped_room_id = scoped_room_id


async def build_dashboard_stats(db: AsyncSession, user: Optional[object] = None) -> dict:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    hour_ago = now - timedelta(hours=1)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    device_cutoff = now - timedelta(seconds=DEVICE_HEARTBEAT_TIMEOUT_SECONDS)

    room_scope = _scoped_room_id(user)

    # Session ids a scoped invigilator may aggregate over. `None` means
    # unrestricted; an empty set mean "nothing visible".
    allowed_session_ids: Optional[set] = None
    if room_scope is not None:
        allowed_session_ids = set(
            (
                await db.execute(
                    select(ExamSession.id).where(ExamSession.room_id == room_scope)
                )
            ).scalars().all()
        )

    def _in_scope(column):
        """Restrict a session-keyed column to the visible session set."""
        if allowed_session_ids is None:
            return None
        if not allowed_session_ids:
            # No visible sessions: match nothing rather than everything.
            return column.in_([-1])
        return column.in_(allowed_session_ids)

    # --- exam sessions -------------------------------------------------------
    status_rows = (
        await db.execute(
            select(ExamSession.status, func.count(ExamSession.id))
            .where(ExamSession.status != ExamStatus.COMPLETED)
            .group_by(ExamSession.status)
        )
    ).all()
    status_counts = {row[0]: int(row[1]) for row in status_rows}
    active_exams = status_counts.get(ExamStatus.RUNNING, 0)
    paused_exams = status_counts.get(ExamStatus.PAUSED, 0)

    # --- students ------------------------------------------------------------
    student_scope = _in_scope(StudentTrack.exam_session_id)
    student_query = select(func.count(StudentTrack.id))
    suspicious_query = select(func.count(StudentTrack.id)).where(StudentTrack.is_suspicious.is_(True))
    if student_scope is not None:
        student_query = student_query.where(student_scope)
        suspicious_query = suspicious_query.where(student_scope)

    tracked_students = (await db.execute(student_query)).scalar() or 0
    suspicious_students = (await db.execute(suspicious_query)).scalar() or 0

    # --- events --------------------------------------------------------------
    event_scope = _in_scope(ViolationEvent.exam_session_id)

    def _count_events(extra=None):
        query = select(func.count(ViolationEvent.id))
        if event_scope is not None:
            query = query.where(event_scope)
        if extra is not None:
            query = query.where(extra)
        return query

    total_events = (await db.execute(_count_events())).scalar() or 0
    events_last_hour = (
        await db.execute(_count_events(ViolationEvent.timestamp >= hour_ago))
    ).scalar() or 0
    events_today = (
        await db.execute(_count_events(ViolationEvent.timestamp >= day_start))
    ).scalar() or 0

    breakdown_query = (
        select(ViolationEvent.event_type, func.count(ViolationEvent.id))
        .group_by(ViolationEvent.event_type)
        .order_by(func.count(ViolationEvent.id).desc())
        .limit(10)
    )
    if event_scope is not None:
        breakdown_query = breakdown_query.where(event_scope)
    breakdown_rows = (await db.execute(breakdown_query)).all()
    event_type_breakdown = [{"event_type": r[0], "count": int(r[1])} for r in breakdown_rows]

    # --- cameras -------------------------------------------------------------
    camera_query = select(CameraDevice)
    if room_scope is not None:
        camera_query = camera_query.where(CameraDevice.room_id == room_scope)

    camera_rows = (
        await db.execute(
            camera_query.with_only_columns(CameraDevice.status, func.count(CameraDevice.id))
            .group_by(CameraDevice.status)
        )
    ).all()
    camera_counts = {row[0]: int(row[1]) for row in camera_rows}
    cameras_total = sum(camera_counts.values())
    cameras_online = camera_counts.get("online", 0)
    cameras_offline = camera_counts.get("offline", 0)
    cameras_unknown = camera_counts.get("unknown", 0)

    # A camera that reported online but has since gone quiet is offline; a
    # configuration row that never reported in stays `unknown`, never `online`.
    stale_online = (
        (
            await db.execute(
                camera_query.with_only_columns(func.count(CameraDevice.id)).where(
                    CameraDevice.status == "online",
                    or_(
                        CameraDevice.last_seen_at.is_(None),
                        CameraDevice.last_seen_at < device_cutoff,
                    ),
                )
            )
        ).scalar()
        or 0
    )
    if stale_online:
        cameras_online = max(cameras_online - int(stale_online), 0)
        cameras_offline = cameras_offline + int(stale_online)

    # --- robots --------------------------------------------------------------
    robot_rows = (
        await db.execute(select(RobotDevice.status, func.count(RobotDevice.id)).group_by(RobotDevice.status))
    ).all()
    robots_total = sum(int(c) for _, c in robot_rows)
    robots_online = sum(
        int(c) for status_value, c in robot_rows
        if status_value and status_value.lower() not in ("offline", "idle")
    )

    return {
        "active_exams": int(active_exams),
        "paused_exams": int(paused_exams),
        "tracked_students": int(tracked_students),
        "suspicious_students": int(suspicious_students),
        "total_events": int(total_events),
        "events_last_hour": int(events_last_hour),
        "events_today": int(events_today),
        "cameras_total": int(cameras_total),
        "cameras_online": int(cameras_online),
        "cameras_offline": int(cameras_offline),
        "cameras_unknown": int(cameras_unknown),
        "robots_total": int(robots_total),
        "robots_online": int(robots_online),
        "event_type_breakdown": event_type_breakdown,
    }
