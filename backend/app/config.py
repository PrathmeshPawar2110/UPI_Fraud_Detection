"""Settings from environment variables (all optional for local development).

Locally, values can also come from backend/.env (see backend/.env.example). Real environment
variables always win over the file, and on Vercel the file doesn't exist, so nothing changes there.
"""

import os
import secrets
import warnings
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
if ENV_FILE.is_file() and not os.environ.get("UPIG_NO_DOTENV"):  # tests set UPIG_NO_DOTENV
    try:
        from dotenv import load_dotenv
    except ImportError:  # python-dotenv comes with uvicorn[standard]; skip quietly if absent
        pass
    else:
        load_dotenv(ENV_FILE, override=False)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


IS_PRODUCTION = _env("VERCEL_ENV") == "production" or _env("APP_ENV") == "production"
ON_VERCEL = bool(_env("VERCEL"))

# Postgres in production (e.g. Neon / Vercel Postgres); a local SQLite file otherwise.
DATABASE_URL = _env("DATABASE_URL")
if not DATABASE_URL:
    if IS_PRODUCTION:
        raise RuntimeError("DATABASE_URL must be set in production (Vercel's filesystem is read-only)")
    if ON_VERCEL:  # preview deployments: throwaway database in /tmp, wiped on cold start
        DATABASE_URL = "sqlite:////tmp/upi_guard.db"
        warnings.warn("DATABASE_URL not set: using a temporary SQLite database in /tmp (data will be lost)")
    else:
        DATABASE_URL = f"sqlite:///{Path(__file__).resolve().parents[1] / 'upi_guard.db'}"
if DATABASE_URL.startswith("postgres://"):  # Heroku/Neon style -> SQLAlchemy dialect name
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]

# Signs session cookies. Must be set (and kept secret) wherever data persists across restarts.
SECRET_KEY = _env("SECRET_KEY")
if not SECRET_KEY:
    if IS_PRODUCTION:
        raise RuntimeError("SECRET_KEY must be set in production")
    SECRET_KEY = secrets.token_urlsafe(32)
    warnings.warn("SECRET_KEY not set: using a random key, sessions end when the server restarts")

SESSION_DAYS = int(_env("SESSION_DAYS", "7"))

# Claude API for the AI investigator (feature is disabled when the key is missing).
ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
AI_MODEL = _env("AI_MODEL", "claude-opus-5-5")
AI_DAILY_LIMIT = int(_env("AI_DAILY_LIMIT", "20"))  # questions per user per day (cost control)

# Request limits
MAX_BODY_BYTES = int(_env("MAX_BODY_BYTES", str(1_000_000)))
MAX_IMPORT_ROWS = int(_env("MAX_IMPORT_ROWS", "2000"))
