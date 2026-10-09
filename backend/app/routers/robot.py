from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.security import require_invigilator
from backend.app.models.models import RobotDevice, User
from backend.app.schemas.schemas import RobotDispatchCommand, RobotStatusOut
from backend.app.routers.ws import manager

router = APIRouter(prefix="/api/robot", tags=["robot"])


@router.get("/status", response_model=Optional[RobotStatusOut])
async def get_robot_status(
    user: User = Depends(require_invigilator),
    db: AsyncSession = Depends(get_db),
):
    """The real robot record, or null.

    When no device has registered yet this returns None so the dashboard can say
    "no robot connected". Previously this endpoint invented a ROBOT-01 with a
    96.5% battery on first read.
    """
    device = (await db.execute(select(RobotDevice).order_by(RobotDevice.device_code))).scalars().first()
    if not device:
        return None
    return device


@router.post("/dispatch")
async def dispatch_robot(
    command: RobotDispatchCommand,
    user: User = Depends(require_invigilator),
    db: AsyncSession = Depends(get_db),
):
    """Send the robot to inspect a specific student track.

    Requires a monitoring role. Broadcasts only after the state change is
    committed.
    """
    device = (await db.execute(select(RobotDevice).order_by(RobotDevice.device_code))).scalars().first()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No robot device is connected",
        )

    device.status = f"inspecting_track_{command.target_track_id}"
    device.current_zone = f"Student {command.target_track_id}"
    device.last_ping = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()

    # Robot state is global rather than per-room, so this reaches every
    # authorised dashboard.
    await manager.broadcast({
        "type": "robot_dispatched",
        "data": {
            "device_code": device.device_code,
            "target_track_id": command.target_track_id,
            "reason": command.reason,
            "status": "en_route",
        },
    })
    return {"ok": True, "status": "dispatched", "target": command.target_track_id}
