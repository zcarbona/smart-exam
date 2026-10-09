from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt

from backend.app.core.config import SECRET_KEY, ALGORITHM, REFRESH_TOKEN_EXPIRE_HOURS
from backend.app.core.database import get_db
from backend.app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    _check_rate_limit,
    _client_ip,
    MAX_LOGIN_ATTEMPTS,
    LOCK_MINUTES,
    require_authenticated_user,
)
from backend.app.models.models import User
from backend.app.routers.ws import manager
from backend.app.schemas.schemas import (
    LogoutResponse,
    Token,
    LoginRequest,
    RefreshRequest,
    UserOut,
)

router = APIRouter(prefix="/api/auth", tags=["authentication"])

@router.post("/login", response_model=Token)
async def login(
    request: Request,
    form_data: Optional[OAuth2PasswordRequestForm] = Depends(lambda: None),
    json_data: Optional[LoginRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Login endpoint adhering to ProjectAlpha authentication specs:
    Supports both OAuth2PasswordRequestForm (form-encoded) and JSON body.
    """
    client_ip = _client_ip(request)
    if not _check_rate_limit(f"login:{client_ip}", limit=10, window_minutes=1):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )

    username = None
    password = None

    if form_data and form_data.username:
        username = form_data.username
        password = form_data.password
    elif json_data:
        username = json_data.username
        password = json_data.password
    else:
        # Fallback to reading JSON from request body if passed as raw json
        try:
            body = await request.json()
            username = body.get("username")
            password = body.get("password")
        except Exception:
            pass

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password are required",
        )

    query = select(User).where((User.username == username) | (User.email == username))
    result = await db.execute(query)
    user = result.scalars().first()

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if user and user.locked_until and user.locked_until > now:
        remaining_minutes = int((user.locked_until - now).total_seconds() / 60) + 1
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account locked due to too many failed attempts. Try again in {remaining_minutes} minutes.",
        )

    if not user or not verify_password(password, user.hashed_password):
        if user:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
                user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
            db.add(user)
            await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact an administrator.",
        )

    # Reset failed attempts upon successful login
    if user.failed_login_attempts or user.locked_until:
        user.failed_login_attempts = 0
        user.locked_until = None

    access_token = create_access_token(subject=user.id)
    refresh_token = create_refresh_token(subject=user.id)

    # Store hashed refresh token in DB with 2-hour expiry
    user.refresh_token = get_password_hash(refresh_token)
    user.refresh_token_expires = now + timedelta(hours=REFRESH_TOKEN_EXPIRE_HOURS)
    db.add(user)
    await db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }

@router.post("/refresh", response_model=Token)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """
    Refresh session token endpoint:
    Rotates access token and refresh token, extending the 2-hour window.
    """
    try:
        payload_data = jwt.decode(payload.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload_data.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = int(payload_data.get("sub"))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    if not user.is_active:
        # Revoke the session immediately so a deactivated account cannot rotate
        # its way back into a live access token.
        user.refresh_token = None
        user.refresh_token_expires = None
        db.add(user)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    if (
        not user.refresh_token
        or not verify_password(payload.refresh_token, user.refresh_token)
        or (user.refresh_token_expires and user.refresh_token_expires < now)
    ):
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    access_token = create_access_token(subject=user.id)
    new_refresh_token = create_refresh_token(subject=user.id)

    user.refresh_token = get_password_hash(new_refresh_token)
    user.refresh_token_expires = now + timedelta(hours=REFRESH_TOKEN_EXPIRE_HOURS)
    db.add(user)
    await db.commit()

    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }

@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(require_authenticated_user)):
    return user

@router.post("/logout", response_model=LogoutResponse)
async def logout(
    user: User = Depends(require_authenticated_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke the server-side refresh token and close any open dashboards.

    The short-lived access token stays valid until it expires on its own; the
    important half is that no *new* access token can be minted afterwards.
    """
    user.refresh_token = None
    user.refresh_token_expires = None
    db.add(user)
    await db.commit()

    await manager.drop_deactivated(user.id)
    return LogoutResponse(ok=True)
