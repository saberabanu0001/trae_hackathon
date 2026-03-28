import sys
from pathlib import Path

# Add backend directory to sys.path so we can import applysmart
backend_path = str(Path(__file__).resolve().parents[1] / "backend")
if backend_path not in sys.path:
    sys.path.append(backend_path)

# Import the FastAPI app
from applysmart.api.main import app
