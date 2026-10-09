import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ROOT_DIR = BASE_DIR.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "smart-exam-super-secret-key-graduation-project-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_HOURS = int(os.environ.get("REFRESH_TOKEN_EXPIRE_HOURS", "2"))  # 2 hours per requirement

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite+aiosqlite:///{ROOT_DIR / 'smart_exam.db'}")

EVIDENCE_DIR = os.environ.get("EVIDENCE_DIR", str(ROOT_DIR / "evidence"))
os.makedirs(EVIDENCE_DIR, exist_ok=True)
