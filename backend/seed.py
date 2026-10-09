import asyncio
from sqlalchemy import select
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.security import get_password_hash
from backend.app.models.models import User, UserRole

async def seed_default_admin():
    async with AsyncSessionLocal() as session:
        query = select(User).where(User.username == "admin")
        existing = (await session.execute(query)).scalars().first()
        if not existing:
            admin_user = User(
                username="admin",
                email="admin@smartexam.edu",
                hashed_password=get_password_hash("Admin@12345678"),
                role=UserRole.ADMIN,
            )
            session.add(admin_user)
            await session.commit()
            print("[Seed] Created default admin proctor account: admin / Admin@12345678")
        else:
            print("[Seed] Admin user already exists.")

if __name__ == "__main__":
    asyncio.run(seed_default_admin())
