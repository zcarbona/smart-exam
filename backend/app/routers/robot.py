from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user
from backend.app.models.models import RobotDevice, User
from backend.app.schemas.schemas import RobotStatusOut, RobotDispatchCommand
from backend.app.routers.ws import manager

router = APIRouter(prefix="/api/robot", tags=["robot"])

@router.get("/status", response_model=RobotStatusOut)
async def get_robot_status(db: AsyncSession = Depends(get_db)):
    """
    Prepared Robot Manager status endpoint:
    Returns status of the proctor assistance robot (stubbed / standby for MQTT).
    """
    query = select(RobotDevice)
    robot = (await db.execute(query)).scalars().first()
    if not robot:
        robot = RobotDevice(device_code="ROBOT-01", status="idle", battery_level=96.5, current_zone="Aisle 1")
        db.add(robot)
        await db.commit()
        await db.refresh(robot)
    return robot

@router.post("/dispatch")
async def dispatch_robot(
    command: RobotDispatchCommand,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Prepared dispatch command to send the robot to inspect a specific student track.
    Ready for future MQTT publish.
    """
    query = select(RobotDevice)
    robot = (await db.execute(query)).scalars().first()
    if robot:
        robot.status = f"inspecting_track_{command.target_track_id}"
        robot.current_zone = f"Student {command.target_track_id}"
        await db.commit()

    await manager.broadcast({
        "type": "robot_dispatched",
        "data": {
            "device_code": "ROBOT-01",
            "target_track_id": command.target_track_id,
            "reason": command.reason,
            "status": "en_route",
        }
    })
    return {"ok": True, "status": "dispatched", "target": command.target_track_id}
