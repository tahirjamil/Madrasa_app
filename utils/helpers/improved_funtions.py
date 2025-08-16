import os
from pathlib import Path
from typing import Tuple, Any, Dict

def get_env_var(var_name: str, default: Any | None = None) -> Any:
    """Get an environment variable with a default value."""
    value = os.getenv(var_name)
    if not value:
        print(f"Critical: Environment variable {var_name} is not set")
        if not default:
            raise ValueError(f"Environment variable {var_name} is not set")
        return default
    return value

def get_project_root(marker_files= ("pyproject.toml", "app.py")) -> Path:
    """Return project root directory by searching upwards for a marker file."""
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if any((parent / marker).exists() for marker in marker_files):
            return parent
    raise FileNotFoundError("Project root not found")

def send_json_response(message: str, status_code: int, details: str | None = None) -> Tuple[Dict[str, Any], int]:
    """Send a JSON response with a status code."""
    success: bool = 200 <= status_code < 300
    error: bool = not success
    return {
        "success": success,
        "error": error,
        "message": message,
        "details": details
    }, status_code
