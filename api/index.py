"""Vercel entry point: exposes the FastAPI app in backend/app as a Python serverless function.

vercel.json rewrites /api/* here; FastAPI still sees the original path (e.g. /api/predict).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.main import app  # noqa: E402,F401
