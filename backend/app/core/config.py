import os
from pathlib import Path

# Load a local .env when running outside Docker (docker compose already
# injects these variables itself). The import is guarded so a missing
# python-dotenv never prevents startup.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ROOT_DIR = BASE_DIR.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "smart-exam-super-secret-key-graduation-project-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_HOURS = int(os.environ.get("REFRESH_TOKEN_EXPIRE_HOURS", "2"))  # 2 hours per requirement

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite+aiosqlite:///{ROOT_DIR / 'smart_exam.db'}")

EVIDENCE_DIR = os.environ.get("EVIDENCE_DIR", str(ROOT_DIR / "evidence"))
os.makedirs(EVIDENCE_DIR, exist_ok=True)

# --- Bootstrap admin (the single permitted mock-login exception) ---------------
# This is the transition-only mock admin. It is intentionally the *only* place
# credentials are hardcoded, and only on the server where they are hashed before
# they ever reach the database. Override both via the environment for any
# deployment; the defaults exist purely so the existing admin login keeps
# working through the migration. Never expose these values to the browser.
BOOTSTRAP_ADMIN_USERNAME = os.environ.get("BOOTSTRAP_ADMIN_USERNAME", "admin")
BOOTSTRAP_ADMIN_PASSWORD = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "Admin@12345678")
BOOTSTRAP_ADMIN_EMAIL = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "admin@smartexam.edu")

# --- Machine-to-machine credentials for the AI pipeline / robot ---------------
# Separate from invigilator accounts: a device identifies itself with
# X-Device-Code + X-Device-Key. The key is stored hashed, and the defaults are
# development-only — set these in the AI service environment in production.
# NOTE: the default must satisfy validate_password_strength(), otherwise
# seed_robot_device() skips provisioning and the pipeline is locked out.
ROBOT_DEVICE_CODE = os.environ.get("ROBOT_DEVICE_CODE", "ROBOT-01")
ROBOT_DEVICE_KEY = os.environ.get("ROBOT_DEVICE_KEY", "Robot-Dev-Key-2026!")

# How stale a device heartbeat may be before the device is considered offline.
DEVICE_HEARTBEAT_TIMEOUT_SECONDS = int(os.environ.get("DEVICE_HEARTBEAT_TIMEOUT_SECONDS", "30"))
