from fastapi import APIRouter
from utils.helpers.fastapi_helpers import require_api_key

api = APIRouter() # Can add prefix here if needed, e.g., prefix="/api/v1")

# Note: Middleware should be added to the main app, not to routers
# The maintenance mode check will be handled by dependencies in individual routes

# Import routes from other modules to register them
from .v1 import auth  # noqa: F401
from .v1 import payments  # noqa: F401
from .v1 import core  # noqa: F401

__all__ = ["api"]