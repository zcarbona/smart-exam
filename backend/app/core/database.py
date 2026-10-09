from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.inspection import inspect

from backend.app.core.config import DATABASE_URL
from backend.app.models.models import Base

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# Columns introduced after the initial release. `create_all` only creates missing
# *tables*, so these are applied to existing databases here instead of by a
# destructive rebuild. Each entry is additive and nullable/defaulted, which is
# what makes the upgrade non-destructive for existing rows.
ADDED_COLUMNS = {
    "users": [
        ("is_active", "BOOLEAN NOT NULL DEFAULT 1"),
        ("full_name", "VARCHAR(100)"),
        ("assigned_room_id", "INTEGER"),
    ],
    "robot_devices": [
        ("api_key_hash", "VARCHAR(255)"),
        ("created_at", "DATETIME"),
        ("updated_at", "DATETIME"),
    ],
    "exam_sessions": [
        ("room_id", "INTEGER"),
    ],
    "exam_rooms": [
        ("is_active", "BOOLEAN NOT NULL DEFAULT 1"),
        ("created_at", "DATETIME"),
        ("updated_at", "DATETIME"),
    ],
    "camera_devices": [
        ("last_seen_at", "DATETIME"),
        ("last_error", "TEXT"),
        ("created_at", "DATETIME"),
        ("updated_at", "DATETIME"),
    ],
    "violation_events": [
        ("event_uid", "VARCHAR(64)"),
    ],
}

# Unique indexes introduced after the initial release. A unique index on
# `event_uid` is what makes device event ingestion idempotent: the AI pipeline
# can safely retry a POST after a timeout without creating a duplicate alert.
# Existing rows have a NULL uid, which SQLite and Postgres both allow in a
# unique index, so adding it is non-destructive.
UNIQUE_INDEXES = [
    (
        "violation_events",
        "event_uid",
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_violation_events_event_uid" '
        'ON "violation_events" ("event_uid")',
    ),
]

# Enum values are persisted by member *name*, so the legacy "PROCTOR" role has to
# be rewritten to the canonical "INVIGILATOR" name.
LEGACY_RENAME = {"proctor": "INVIGILATOR"}


async def _existing_columns(conn, table: str) -> set:
    def _cols(sync_conn):
        inspector = inspect(sync_conn)
        if table not in inspector.get_table_names():
            return set()
        return {c["name"] for c in inspector.get_columns(table)}

    return await conn.run_sync(_cols)


async def _apply_added_columns(conn) -> None:
    for table, columns in ADDED_COLUMNS.items():
        existing = await _existing_columns(conn, table)
        for name, ddl in columns:
            if name in existing:
                continue
            await conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {ddl}'))


async def _migrate_legacy_roles(conn) -> None:
    for legacy, canonical in LEGACY_RENAME.items():
        await conn.execute(
            text("UPDATE users SET role = :canonical WHERE role = :legacy"),
            {"canonical": canonical, "legacy": legacy},
        )


async def _apply_unique_indexes(conn) -> None:
    """Idempotent unique indexes. Existing rows keep NULL uids, which SQL and
    Postgres both permit in a unique index, so the backfill is safe."""
    for _table, _column, ddl in UNIQUE_INDEXES:
        await conn.execute(text(ddl))


async def init_db():
    async with engine.begin() as conn:
        # 1. Create any tables that do not exist yet (never drops existing ones).
        await conn.run_sync(Base.metadata.create_all)
        # 2. Bring pre-existing tables up to the current shape.
        await _apply_added_columns(conn)
        await _apply_unique_indexes(conn)
        await _migrate_legacy_roles(conn)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
