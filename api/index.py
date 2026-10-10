"""Vercel entry point: exposes the FastAPI app (API + the web app at /app)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from greenghar.api.main import app  # noqa: E402,F401
