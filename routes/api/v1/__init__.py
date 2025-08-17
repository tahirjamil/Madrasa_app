from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from utils.helpers.fastapi_helpers import require_api_key
from config import config
from utils.helpers.improved_functions import send_json_response

api = APIRouter(prefix="/api/v1")

# Note: Middleware should be added to the main app, not to routers
# The maintenance mode check will be handled by dependencies in individual routes



# Import routes from other modules to register them
from . import auth  # noqa: F401
from . import payments  # noqa: F401
from . import core  # noqa: F401