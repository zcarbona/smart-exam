import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.core.config import EVIDENCE_DIR
from backend.app.core.database import init_db
from backend.app.routers import auth, events, exams, robot, ws

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables
    await init_db()
    # Run seed to ensure default admin exists
    from backend.seed import seed_default_admin
    await seed_default_admin()
    yield

app = FastAPI(
    title="Smart Exam Proctoring API",
    description="Backend Server for AI-assisted Exam Proctoring with ProjectAlpha JWT and Real-time WebSockets",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(events.router)
app.include_router(exams.router)
app.include_router(robot.router)
app.include_router(ws.router)

# Mount evidence static directory
if os.path.exists(EVIDENCE_DIR):
    app.mount("/evidence", StaticFiles(directory=EVIDENCE_DIR), name="evidence")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "smart-exam-backend", "version": "2.0.0"}
