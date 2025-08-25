from fastapi import APIRouter, Security
from utils.helpers.fastapi_helpers import require_api_key

api = APIRouter(dependencies=[Security(require_api_key)]) # Can add prefix here if needed, e.g., prefix="/api/v1")

# Import routes from other modules to register them
from .v1 import auth  # noqa: F401
from .v1 import payments  # noqa: F401
from .v1 import core  # noqa: F401
from .v1 import files  # noqa: F401

__all__ = ["api"]