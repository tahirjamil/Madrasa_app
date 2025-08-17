from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from utils.helpers.helpers import require_api_key
from config import config
from utils.helpers.improved_functions import send_json_response

api = APIRouter(prefix="/api/v1")

# Create a dependency for API key check
async def check_api_key(request: Request):
    """Check API key and maintenance mode"""
    # This will be replaced by the actual require_api_key logic
    # For now, we'll implement a basic version
    pass

@api.middleware("http")
async def check_middleware(request: Request, call_next):
    """Check API key and maintenance mode for all API routes"""
    # TODO: Implement API key check from require_api_key
    
    if config.is_maintenance():
        response, status = send_json_response("System is under maintenance. Please try again later.", 503)
        response.update({"action": "maintenance"})
        return JSONResponse(content=response, status_code=status)
    
    response = await call_next(request)
    return response



# Import routes from other modules to register them
from . import auth  # noqa: F401
from . import payments  # noqa: F401
from . import core  # noqa: F401