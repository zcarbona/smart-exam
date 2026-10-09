"""One-time provisioning.

Two things are seeded here, and only these two:

1. The bootstrap admin account. This is the single permitted mock-login
   exception during the migration — it lives here, isolated in one function, so
   it can be deleted wholesale once real administrative provisioning exists.
2. A robot/edge device credential, so the AI pipeline can authenticate its
   event ingestion instead of posting anonymously.

Passwords are read from the environment and only ever stored hashed.
"""

import asyncio

from sqlalchemy import select

from backend.app.core.config import (
    BOOTSTRAP_ADMIN_EMAIL,
    BOOTSTRAP_ADMIN_PASSWORD,
    BOOTSTRAP_ADMIN_USERNAME,
    ROBOT_DEVICE_CODE,
    ROBOT_DEVICE_KEY,
)
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.security import get_password_hash, validate_password_strength
from backend.app.models.models import RobotDevice, User, UserRole


async def seed_default_admin() -> None:
    """Ensure the bootstrap admin exists.

    Only creates the account when absent, so an admin whose password has been
    rotated is never silently reset back to the development default.
    """
    async with AsyncSessionLocal() as session:
        query = select(User).where(User.username == BOOTSTRAP_ADMIN_USERNAME)
        existing = (await session.execute(query)).scalars().first()
        if not existing:
            admin_user = User(
                username=BOOTSTRAP_ADMIN_USERNAME,
                email=BOOTSTRAP_ADMIN_EMAIL,
                hashed_password=get_password_hash(BOOTSTRAP_ADMIN_PASSWORD),
                role=UserRole.ADMIN,
                is_active=True,
                full_name="System Administrator",
            )
            session.add(admin_user)
            await session.commit()
            print("[Seed] Created bootstrap admin account.")
        else:
            if existing.role is not UserRole.ADMIN:
                existing.role = UserRole.ADMIN
                session.add(existing)
                await session.commit()
                print("[Seed] Elevated existing bootstrap account to admin.")
            else:
                print("[Seed] Admin user already exists.")


async def seed_robot_device() -> None:
    """Provision the device credential for AI event ingestion.

    The plaintext key is only shown in logs at creation time; afterwards only
    the hash is retained.
    """
    async with AsyncSessionLocal() as session:
        existing = (
            await session.execute(select(RobotDevice).where(RobotDevice.device_code == ROBOT_DEVICE_CODE))
        ).scalars().first()
        if existing:
            print(f"[Seed] Robot device '{ROBOT_DEVICE_CODE}' already provisioned.")
            return

        try:
            validate_password_strength(ROBOT_DEVICE_KEY)
        except ValueError as exc:
            print(f"[Seed] Skipping robot device provisioning — {exc}")
            return

        device = RobotDevice(
            device_code=ROBOT_DEVICE_CODE,
            api_key_hash=get_password_hash(ROBOT_DEVICE_KEY),
            status="offline",
            battery_level=0.0,
        )
        session.add(device)
        await session.commit()
        print(f"[Seed] Provisioned robot device '{ROBOT_DEVICE_CODE}'.")


async def seed_all() -> None:
    await seed_default_admin()
    await seed_robot_device()


if __name__ == "__main__":
    asyncio.run(seed_all())
