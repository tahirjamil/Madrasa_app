import os
from pathlib import Path
from typing import Tuple, Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)

def get_env_var(var_name: str, default: Optional[Any] = None, required: bool = True) -> Any:
    """Get an environment variable with a default value."""
    value = os.getenv(var_name)
    if value and value.lower() in ("none", "null", ""):
        value = None
    if not value:
        logger.debug(f"Environment variable {var_name} not set, using default: {default}")
        if required and not default:
            raise ValueError(f"Environment variable {var_name} is not set, and no default provided.")
        return default
    return value

def get_project_root(marker_files: Tuple[str, ...] = ("pyproject.toml", "app.py")) -> Path:
    """Return project root directory by searching upwards for a marker file."""
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if any((parent / marker).exists() for marker in marker_files):
            return parent
    raise FileNotFoundError("Project root not found")

def send_json_response(
    message: str,
    status_code: int,
    details: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None
) -> Tuple[Dict[str, Any], int]:
    """Send a JSON response with a status code."""
    success: bool = 200 <= status_code < 300
    response: Dict[str, Any] = {
        "success": success,
        "error": not success,
        "message": message,
    }
    if details is not None:
        response["details"] = details
    if data is not None:
        response["data"] = data
    return response, status_code
