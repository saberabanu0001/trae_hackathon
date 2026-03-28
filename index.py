"""
Vercel serverless entry — must live at repo root for stable routing.
"""
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent / "backend"
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from applysmart.api.main import app  # noqa: E402
