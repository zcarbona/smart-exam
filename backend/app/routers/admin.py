from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.database import get_db
from backend.app.core.security import (
    get_password_hash,
    require_admin,
    validate_password_strength,
)
from backend.app.models.models import CameraDevice, ExamRoom, RobotDevice, User, UserRole
from backend.app.routers.ws import manager
from backend.app.schemas.schemas import (
    DashboardStatsOut,
    CameraCreate,
    CameraOut,
    InvigilatorCreate,
    InvigilatorUpdate,
    RobotDeviceCreate,
    RoomCreate,
    RoomDetailOut,
    RoomOut,
    RoomUpdate,
    UserOut,
)

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _client_error(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


# ---------------------------------------------------------------- invigilators

@router.post("/invigilators", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_invigilator(
    payload: InvigilatorCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create an invigilator account.

    The role is hard-coded server-side: this endpoint can only ever mint
    `invigilator` accounts. There is no registration route, and no way to ask
    this endpoint for anything else.
    """
    username = payload.username.strip()
    if not username:
        raise _client_error("Username must not be empty")

    existing = (
        await db.execute(select(User).where((User.username == username) | (User.email == payload.email)))
    ).scalars().first()
    if existing:
        raise _client_error("An account with that username or email already exists")

    if payload.assigned_room_id is not None:
        room = (
            await db.execute(select(ExamRoom).where(ExamRoom.id == payload.assigned_room_id))
        ).scalars().first()
        if not room:
            raise _client_error("Assigned exam room does not exist")

    try:
        validate_password_strength(payload.password)
    except ValueError as exc:
        raise _client_error(str(exc))

    user = User(
        username=username,
        email=payload.email or None,
        full_name=payload.full_name,
        hashed_password=get_password_hash(payload.password),
        role=UserRole.INVIGILATOR,
        is_active=True,
        assigned_room_id=payload.assigned_room_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/invigilators", response_model=List[UserOut])
async def list_invigilators(
    include_inactive: bool = True,
    db: AsyncSession = Depends(get_db),
):
    query = select(User).where(User.role != UserRole.ADMIN).order_by(User.created_at.desc())
    if not include_inactive:
        query = query.where(User.is_active.is_(True))
    return list((await db.execute(query)).scalars().all())


@router.get("/invigilators/{invigilator_id}", response_model=UserOut)
async def get_invigilator(
    invigilator_id: int,
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, invigilator_id)
    if not user or user.role is UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invigilator not found")
    return user


@router.patch("/invigilators/{invigilator_id}", response_model=UserOut)
async def update_invigilator(
    invigilator_id: int,
    payload: InvigilatorUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Activate, deactivate, reassign, rename, or reset an invigilator."""
    user = await db.get(User, invigilator_id)
    if not user or user.role is UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invigilator not found")

    if payload.email is not None:
        clash = (
            await db.execute(
                select(User).where(User.email == payload.email, User.id != user.id)
            )
        ).scalars().first()
        if clash:
            raise _client_error("That email is already in use")

    if payload.assigned_room_id is not None:
        room = (
            await db.execute(select(ExamRoom).where(ExamRoom.id == payload.assigned_room_id))
        ).scalars().first()
        if not room:
            raise _client_error("Assigned exam room does not exist")

    was_active = bool(user.is_active)
    becoming_inactive = payload.is_active is False and was_active

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.email is not None:
        user.email = payload.email or None
    if payload.assigned_room_id is not None:
        user.assigned_room_id = payload.assigned_room_id
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password is not None or becoming_inactive:
        # Both a password reset and a deactivation must invalidate any session
        # opened under the old credentials.
        user.refresh_token = None
        user.refresh_token_expires = None
    if payload.password is not None:
        try:
            validate_password_strength(payload.password)
        except ValueError as exc:
            raise _client_error(str(exc))
        user.hashed_password = get_password_hash(payload.password)
        user.failed_login_attempts = 0
        user.locked_until = None

    user.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    if becoming_inactive:
        # Force-close live sockets so deactivation takes effect immediately.
        await manager.drop_deactivated(user.id)

    return user


# ---------------------------------------------------------------------- rooms

@router.post("/rooms", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
async def create_room(
    payload: RoomCreate,
    db: AsyncSession = Depends(get_db),
):
    room_code = payload.room_code.strip()
    if not room_code:
        raise _client_error("Room code must not be empty")

    clash = (
        await db.execute(select(ExamRoom).where(ExamRoom.room_code == room_code))
    ).scalars().first()
    if clash:
        raise _client_error("A room with that code already exists")

    room = ExamRoom(
        room_code=room_code,
        name=payload.name.strip(),
        building=payload.building,
        is_active=payload.is_active if payload.is_active is not None else True,
    )
    db.add(room)
    await db.commit()
    await db.refresh(room)
    return room


@router.get("/rooms", response_model=List[RoomOut])
async def list_rooms(
    db: AsyncSession = Depends(get_db),
):
    return list((await db.execute(select(ExamRoom).order_by(ExamRoom.room_code))).scalars().all())


@router.get("/rooms/{room_id}", response_model=RoomDetailOut)
async def get_room(
    room_id: int,
    db: AsyncSession = Depends(get_db),
):
    # Eager-load cameras: touching a lazy relationship outside a sync session
    # would raise instead of returning data.
    room = (
        await db.execute(
            select(ExamRoom)
            .where(ExamRoom.id == room_id)
            .options(selectinload(ExamRoom.cameras))
        )
    ).scalars().first()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam room not found")
    return room


@router.patch("/rooms/{room_id}", response_model=RoomOut)
async def update_room(
    room_id: int,
    payload: RoomUpdate,
    db: AsyncSession = Depends(get_db),
):
    room = await db.get(ExamRoom, room_id)
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam room not found")

    if payload.name is not None:
        room.name = payload.name.strip()
    if payload.building is not None:
        room.building = payload.building
    if payload.is_active is not None:
        room.is_active = payload.is_active
    room.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    db.add(room)
    await db.commit()
    await db.refresh(room)
    return room


@router.post("/rooms/{room_id}/cameras", response_model=CameraOut, status_code=status.HTTP_201_CREATED)
async def register_camera(
    room_id: int,
    payload: CameraCreate,
    db: AsyncSession = Depends(get_db),
):
    """Register a camera under a room.

    Registering a camera never marks it online — its state stays `unknown` until
    the device pipeline actually reports in.
    """
    room = await db.get(ExamRoom, room_id)
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam room not found")

    device_code = payload.device_code.strip()
    clash = (
        await db.execute(select(CameraDevice).where(CameraDevice.device_code == device_code))
    ).scalars().first()
    if clash:
        raise _client_error("A camera with that device code already exists")

    camera = CameraDevice(room_id=room.id, name=payload.name.strip(), device_code=device_code, status="unknown")
    db.add(camera)
    await db.commit()
    await db.refresh(camera)
    return camera


# --------------------------------------------------------------------- robots

@router.post("/robot-devices", status_code=status.HTTP_201_CREATED)
async def register_robot_device(
    payload: RobotDeviceCreate,
    db: AsyncSession = Depends(get_db),
):
    """Provision a device credential for the AI pipeline / robot.

    The plaintext key is returned exactly once and only ever stored hashed.
    """
    device_code = payload.device_code.strip()
    if not device_code:
        raise _client_error("Device code must not be empty")

    clash = (
        await db.execute(select(RobotDevice).where(RobotDevice.device_code == device_code))
    ).scalars().first()
    if clash:
        raise _client_error("A device with that code already exists")

    try:
        validate_password_strength(payload.device_key)
    except ValueError as exc:
        raise _client_error(str(exc))

    device = RobotDevice(
        device_code=device_code,
        api_key_hash=get_password_hash(payload.device_key),
        status="offline",
        battery_level=0.0,
    )
    db.add(device)
    await db.commit()

    return {
        "ok": True,
        "device_code": device.device_code,
        "device_key": payload.device_key,
        "warning": "Store this key now; it is not retrievable afterwards.",
    }


@router.get("/robot-devices")
async def list_robot_devices(
    db: AsyncSession = Depends(get_db),
):
    devices = list(
        (await db.execute(select(RobotDevice).order_by(RobotDevice.device_code))).scalars().all()
    )
    return [
        {
            "device_code": d.device_code,
            "status": d.status,
            "battery_level": d.battery_level,
            "current_zone": d.current_zone,
            "last_ping": d.last_ping,
            "has_credentials": bool(d.api_key_hash),
        }
        for d in devices
    ]


@router.get("/cameras", response_model=List[CameraOut])
async def list_all_cameras(
    db: AsyncSession = Depends(get_db),
):
    return list((await db.execute(select(CameraDevice))).scalars().all())


@router.get("/stats", response_model=DashboardStatsOut)
async def admin_stats(
    db: AsyncSession = Depends(get_db),
):
    """Admin-wide figures, computed entirely from persisted rows."""
    from backend.app.services.stats import build_dashboard_stats

    return DashboardStatsOut(**await build_dashboard_stats(db))
