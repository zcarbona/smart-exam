import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt
from sqlalchemy import select

from backend.app.core.config import SECRET_KEY, ALGORITHM
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.models import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websockets"])

# Application-specific close codes so the client can distinguish "you are not
# authenticated" from a network drop and avoid hammering reconnect.
WS_UNAUTHORIZED = 4401
WS_FORBIDDEN = 4403


@dataclass
class Connection:
    """A single authenticated dashboard subscription."""

    websocket: WebSocket
    user: Optional[User] = None
    subscribed_room_id: Optional[int] = None
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_admin(self) -> bool:
        return self.user is not None and self.user.role is UserRole.ADMIN

    def may_receive_room(self, room_id: Optional[int]) -> bool:
        """Scoped invigilators only ever see their assigned room."""
        if self.user is None:
            return False
        if self.user.role is UserRole.ADMIN:
            return True
        if self.user.assigned_room_id is None:
            return True
        return room_id == self.user.assigned_room_id


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[Connection] = []

    async def connect(self, connection: Connection):
        await connection.websocket.accept()
        self.active_connections.append(connection)
        logger.info(
            "WebSocket client authenticated (user=%s role=%s room=%s). Active: %d",
            connection.user.username if connection.user else "?",
            connection.user.role.name if connection.user else "?",
            connection.subscribed_room_id,
            len(self.active_connections),
        )

    def disconnect(self, connection: Connection):
        if connection in self.active_connections:
            self.active_connections.remove(connection)
            logger.info("WebSocket client disconnected. Active: %d", len(self.active_connections))

    async def send_personal(self, connection: Connection, message: dict):
        try:
            await connection.websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.warning("Error sending to WebSocket client: %s", e)
            self.disconnect(connection)

    async def broadcast(self, message: dict, room_id: Optional[int] = None):
        """Fan out an already-validated, already-persisted backend event.

        Callers pass the room the event belongs to (they already know it from the
        exam session) rather than an id to be re-resolved here. That keeps the
        hot path free of an extra query per event and avoids opening a second
        connection while a request transaction is live.

        `room_id=None` means "not room scoped": unscoped invigilators and admins
        receive it, scoped invigilators do not.
        """
        payload = json.dumps(message)
        for connection in list(self.active_connections):
            if not connection.may_receive_room(room_id):
                continue
            try:
                await connection.websocket.send_text(payload)
            except Exception as e:
                logger.warning("Error broadcasting to WebSocket client: %s", e)
                self.disconnect(connection)

    async def drop_deactivated(self, user_id: int):
        """Force-close sockets belonging to a deactivated or logged-out account."""
        for connection in list(self.active_connections):
            if connection.user and connection.user.id == user_id:
                try:
                    await connection.websocket.close(code=WS_FORBIDDEN, reason="Session revoked")
                except Exception:
                    pass
                self.disconnect(connection)


manager = ConnectionManager()


async def authenticate_websocket(websocket: WebSocket) -> Connection:
    """Validate the handshake before the socket is ever accepted.

    Returns a Connection; raises WebSocketDisconnect with an application close
    code when the peer is not allowed in. Starlette performs the actual close
    when it sees WebSocketDisconnect, so there is no pre-close here.
    """
    token = websocket.query_params.get("token") or websocket.query_params.get("access_token")
    if not token:
        raise WebSocketDisconnect(code=WS_UNAUTHORIZED)

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise ValueError("wrong token type")
        user_id = int(payload.get("sub"))
    except Exception:
        raise WebSocketDisconnect(code=WS_UNAUTHORIZED)

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.id == user_id))).scalars().first()

    if not user:
        raise WebSocketDisconnect(code=WS_UNAUTHORIZED)
    if not user.is_active:
        raise WebSocketDisconnect(code=WS_FORBIDDEN)

    # Explicit room subscription is optional; without it the user's own assigned
    # room governs what they can see.
    raw_room = websocket.query_params.get("room_id")
    subscribed_room_id: Optional[int] = None
    if raw_room is not None:
        try:
            subscribed_room_id = int(raw_room)
        except (TypeError, ValueError):
            raise WebSocketDisconnect(code=WS_FORBIDDEN)

        if user.assigned_room_id is not None and subscribed_room_id != user.assigned_room_id:
            # A scoped invigilator may only subscribe to the room they own.
            raise WebSocketDisconnect(code=WS_FORBIDDEN)

    return Connection(
        websocket=websocket,
        user=user,
        subscribed_room_id=subscribed_room_id if subscribed_room_id is not None else user.assigned_room_id,
    )


@router.websocket("/ws/dashboard")
async def websocket_endpoint(websocket: WebSocket):
    connection = await authenticate_websocket(websocket)
    await manager.connect(connection)
    try:
        await manager.send_personal(connection, {
            "type": "connected",
            "data": {
                "user": connection.user.username,
                "role": connection.user.role.value,
                "room_id": connection.subscribed_room_id,
            },
        })

        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except Exception:
                continue

            msg_type = msg.get("type")
            # Client-originated messages are never treated as domain events. A
            # "ping" is answered locally and nothing else is trusted.
            if msg_type == "ping":
                connection.last_seen_at = datetime.now(timezone.utc)
                await manager.send_personal(connection, {"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(connection)
    except Exception as e:
        logger.warning("WebSocket connection error: %s", e)
        manager.disconnect(connection)
