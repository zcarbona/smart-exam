from datetime import datetime, timedelta, timezone
from typing import Any, Union, Optional
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import (
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_HOURS,
)
from backend.app.core.database import get_db
from backend.app.models.models import RobotDevice, User, UserRole

MAX_LOGIN_ATTEMPTS = 5
LOCK_MINUTES = 15

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Simple in-memory rate limiter: {key: list[datetime]}
_rate_limit_store: dict[str, list[datetime]] = {}

def _check_rate_limit(key: str, limit: int = 10, window_minutes: int = 1) -> bool:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=window_minutes)
    timestamps = _rate_limit_store.get(key, [])
    valid_timestamps = [t for t in timestamps if t > window_start]
    _rate_limit_store[key] = valid_timestamps
    if len(valid_timestamps) >= limit:
        return False
    _rate_limit_store[key].append(now)
    return True

def validate_password_strength(password: str) -> None:
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters")
    if not any(c.isupper() for c in password):
        raise ValueError("Password must be at least one uppercase letter")
    if not any(c.islower() for c in password):
        raise ValueError("Password must be at least one lowercase letter")
    if not any(c.isdigit() for c in password):
        raise ValueError("Password must be at least one number")
    if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?/~`" for c in password):
        raise ValueError("Password must be at least one special character")

def create_access_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"exp": expire, "sub": str(subject), "type": "access"}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(subject: Union[str, Any]) -> str:
    # Set to 2 hours per user requirement
    expire = datetime.now(timezone.utc) + timedelta(hours=REFRESH_TOKEN_EXPIRE_HOURS)
    to_encode = {"exp": expire, "sub": str(subject), "type": "refresh"}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def decode_token(token: str) -> dict:
    """Decode and validate a JWT, raising 401 on any failure.

    Used by both the HTTP bearer dependency and the WebSocket handshake so the
    two cannot drift apart.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload["sub"] = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


async def resolve_user(payload: dict, db: AsyncSession) -> User:
    """Load the user described by a decoded token and reject inactive accounts."""
    user = (await db.execute(select(User).where(User.id == payload["sub"]))).scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session user no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )
    return user


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> User:
    return await resolve_user(decode_token(token), db)


async def require_authenticated_user(
    user: User = Depends(get_current_user),
) -> User:
    """Any user holding a valid, active session."""
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Only the `admin` role. Invigilators receive 403, not 401."""
    if user.role is not UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator role required",
        )
    return user


async def require_invigilator(user: User = Depends(get_current_user)) -> User:
    """Admins and invigilators — i.e. every staff role that may monitor a room."""
    if user.role is UserRole.ADMIN or user.role is UserRole.INVIGILATOR:
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Monitoring role required",
    )


def user_can_access_session(user: User, session_room_id: Optional[int]) -> bool:
    """Room-level enforcement point for every exam/camera/event query.

    Admins see everything. An invigilator with no assignment also sees
    everything (the system supports both scoped and unscoped deployment), but
    once a room is assigned, access is restricted to that room only.
    """
    if is_admin_user(user):
        return True
    if user.assigned_room_id is None:
        return True
    return session_room_id == user.assigned_room_id


def is_admin_user(user: Optional[User]) -> bool:
    return user is not None and user.role is UserRole.ADMIN


def scoped_room_id(user: Optional[User]) -> Optional[int]:
    """The room `user` is restricted to, or None if they are unrestricted.

    Kept in sync with `user_can_access_session` so aggregate endpoints and
    per-row endpoints can never disagree about who sees what.
    """
    if user is None or is_admin_user(user) or user.assigned_room_id is None:
        return None
    return user.assigned_room_id


def _client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def access_denied() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have access to this exam room",
    )


async def get_current_robot(
    x_device_code: Optional[str] = Header(default=None),
    x_device_key: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> RobotDevice:
    """Authenticate a machine device (AI pipeline / robot).

    This is deliberately independent of invigilator login: the device presents a
    device code carried in `X-Device-Code` and a pre-shared key in
    `X-Device-Key`. The key is only ever stored hashed, and possession of it
    grants event-ingestion rights and nothing else — it can never read
    dashboards, users, or evidence listings.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid device credentials",
        headers={"WWW-Authenticate": "DeviceKey"},
    )

    if not x_device_code or not x_device_key:
        raise unauthorized

    device = (
        await db.execute(
            select(RobotDevice).where(RobotDevice.device_code == x_device_code)
        )
    ).scalars().first()

    # A device that exists but has no key configured cannot authenticate; that
    # row must be provisioned by an admin first.
    if not device or not device.api_key_hash or not verify_password(x_device_key, device.api_key_hash):
        raise unauthorized

    return device
