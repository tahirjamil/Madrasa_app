"""
FastAPI helper functions and dependencies
Replaces Quart-specific helpers with FastAPI patterns
"""

from datetime import datetime
import json
from typing import Optional, Dict, Any, Callable, Tuple
from functools import wraps
import time
from collections import defaultdict

from fastapi import Request, HTTPException, Depends, Header
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, field_validator
from starlette.status import HTTP_403_FORBIDDEN, HTTP_429_TOO_MANY_REQUESTS
from starlette.requests import Request as StarletteRequest

from config import config
from .helpers import security_manager
from .improved_functions import get_env_var
from .logger import log


# ─── API Key Authentication ───────────────────────────────────────────
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def require_api_key(api_key: Optional[str] = Depends(api_key_header)) -> str:
    """FastAPI dependency for API key validation"""
    if not api_key:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="API key required"
        )
    
    if api_key not in config.API_KEYS:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Invalid API key"
        )
    
    return api_key


# ─── Client Info Dependency ───────────────────────────────────────────
class ClientInfo(BaseModel):
    """Client information model"""
    ip_address: str
    device_id: str
    device_model: Optional[str] = "unknown"
    device_os: Optional[str] = "unknown"
    device_brand: Optional[str] = "unknown"
    api_key: Optional[str] = None


async def get_client_info(
    request: Request,
    x_device_id: Optional[str] = Header(None),
    x_device_model: Optional[str] = Header(None),
    x_device_os: Optional[str] = Header(None),
    x_device_brand: Optional[str] = Header(None),
    api_key: Optional[str] = Depends(api_key_header)
) -> ClientInfo:
    """Extract client information from headers"""
    # Get IP address
    ip_address = request.headers.get("X-Forwarded-For", 
                                    request.client.host if request.client else "unknown")
    
    return ClientInfo(
        ip_address=ip_address,
        device_id=x_device_id or "unknown",
        device_model=x_device_model or "unknown",
        device_os=x_device_os or "unknown",
        device_brand=x_device_brand or "unknown",
        api_key=api_key
    )


# ─── Rate Limiting ───────────────────────────────────────────
# Simple in-memory rate limiter (consider using redis for production)
rate_limit_storage: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"count": 0, "reset_time": 0})

def rate_limit(max_requests: int = 10, window: int = 60):
    """Rate limiting decorator for FastAPI routes"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            # Get client identifier
            client_id = request.headers.get("X-Forwarded-For", 
                                          request.client.host if request.client else "unknown")
            
            current_time = time.time()
            client_data = rate_limit_storage[client_id]
            
            # Reset counter if window expired
            if current_time > client_data["reset_time"]:
                client_data["count"] = 0
                client_data["reset_time"] = current_time + window
            
            # Check rate limit
            if client_data["count"] >= max_requests:
                raise HTTPException(
                    status_code=HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again later."
                )
            
            # Increment counter
            client_data["count"] += 1
            
            # Call the original function
            return await func(request, *args, **kwargs)
        
        return wrapper
    return decorator


# ─── Error Handling ───────────────────────────────────────────
def handle_async_errors(func: Callable) -> Callable:
    """Error handling decorator for async routes"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            log.error(
                action=f"unhandled_error_{func.__name__}", 
                trace_info="system", 
                message=f"Unhandled error in {func.__name__}: {str(e)}",
                secure=False
            )
            raise HTTPException(
                status_code=500,
                detail="Internal server error"
            )
    return wrapper


# ─── Base Models for Common Request Patterns ───────────────────────────────────────────
class BaseAuthRequest(BaseModel):
    """Base model for authentication requests"""
    fullname: str
    phone: str
    ip_address: str = Field(default="unknown")
    device_id: str = Field(default="unknown")
    device_model: Optional[str] = Field(default="unknown")
    device_os: Optional[str] = Field(default="unknown")
    device_brand: Optional[str] = Field(default="unknown")
    madrasa_name: Optional[str] = Field(default=None)
    
    @field_validator('fullname', 'phone', 'device_id', 'device_model', 'device_os', 'device_brand')
    @classmethod
    def sanitize_input(cls, v):
        if isinstance(v, str):
            return security_manager.sanitize_inputs(v)
        return v
    
    @field_validator('*')
    @classmethod
    def check_sql_injection(cls, v, info):
        if isinstance(v, str) and security_manager.detect_sql_injection(v):
            raise ValueError(f"Invalid input detected in {info.field_name}")
        return v


# ─── Device Validation Dependency ───────────────────────────────────────────
async def validate_device_dependency(client_info: ClientInfo = Depends(get_client_info)):
    """Validate device information"""
    # Import here to avoid circular imports
    from .helpers import validate_device_info
    
    is_valid, error = await validate_device_info(
        device_id=client_info.device_id,
        ip_address=client_info.ip_address,
        device_model=client_info.device_model or "unknown",
        device_os=client_info.device_os or "unknown",
        device_brand=client_info.device_brand or "unknown"
    )
    
    if not is_valid:
        log.warning(
            action="invalid_device",
            trace_info=client_info.ip_address,
            message=f"Invalid device: {error}",
            secure=False
        )
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=error
        )
    
    return client_info


# ─── Centralized Templates Instance ──────────────────────────────────
# Create a single templates instance to be imported by all modules
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

# Add custom globals to templates
def setup_template_globals(app):
    """Setup custom globals for templates"""
    def url_for(name: str, **path_params) -> str:
        """Custom url_for that works with static files and routes"""
        # For static files, create the URL directly
        if name == "static":
            filename = path_params.get("filename", "")
            return f"/static/{filename}"
        elif name == "uploads":
            filename = path_params.get("filename", "")
            return f"/uploads/{filename}"
        
        # For other routes (web routes)
        else:
            # Direct mapping for known routes
            route_map = {
                "home": "/",
                "donate": "/donate",
                "privacy": "/privacy",
                "terms": "/terms",
            }
            return route_map.get(name, f"/{name}")
    
    def get_flashed_messages(with_categories=False):
        """FastAPI compatible flash messages - returns empty list for now"""
        # In FastAPI, flash messages are typically passed as template context
        # This is a placeholder that returns empty to prevent template errors
        # TODO: Implement actual flash message handling if needed with keydb
        return []
    
    # Add the functions as globals to the template environment
    templates.env.globals["url_for"] = url_for
    templates.env.globals["get_flashed_messages"] = get_flashed_messages
    templates.env.globals.update({
    "home_path": "/",
    "donate_path": "/donate",
    "privacy_path": "/privacy",
    "terms_path": "/terms",
    "current_year": datetime.now(),
    })


# default (module-level) - still useful if env not set
MAX_JSON_BODY = int(get_env_var("MAX_JSON_BODY", 1_000_000))  # default 1MB

def _content_length_ok(request: Request, max_bytes: int) -> bool:
    cl = request.headers.get("content-length")
    if not cl:
        return True
    try:
        return int(cl) <= max_bytes
    except ValueError:
        return True

async def _stream_limited(request: Request, max_bytes: int) -> bytes:
    size = 0
    parts = []
    async for chunk in request.stream():
        size += len(chunk)
        if size > max_bytes:
            log.info(action="Streaming limit exceeded", trace_info="system", message=f"size: {size} max_bytes: {max_bytes}", secure=False)
            raise HTTPException(status_code=413, detail="Payload too large")
        parts.append(chunk)
    return b"".join(parts)

async def read_and_recreate_request(request: Request, max_bytes: Optional[int] = None) -> Tuple[bytes, StarletteRequest]:
    # Resolve effective max_bytes at call time:
    if max_bytes is None:
        max_bytes = MAX_JSON_BODY

    # sanity check
    if max_bytes <= 0:
        max_bytes = MAX_JSON_BODY

    log.info(action="Recreate_request", trace_info="system", message=f"using max_bytes={max_bytes}, Content-Length={request.headers.get("content-length")}", secure=False)

    # cheap Content-Length check
    if not _content_length_ok(request, max_bytes):
        log.warning(action="Large Content", trace_info="system", message="Content-Length too large, rejecting early", secure=False)
        raise HTTPException(status_code=413, detail="Payload too large")

    # fast path if content-length present
    if request.headers.get("content-length"):
        body = await request.body()
        if len(body) > max_bytes:
            log.warning(action="Body size exceeds max_bytes", trace_info="system", message=f"P{len(body)} > {max_bytes}", secure=False)
            raise HTTPException(status_code=413, detail="Payload too large")
    else:
        # stream and enforce limit
        body = await _stream_limited(request, max_bytes)

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    new_request = Request(request.scope, receive=receive)
    return body, new_request


async def read_json_and_recreate(request: Request, max_bytes: Optional[int] = None):
    # Read and recreate the request
    body, new_req = await read_and_recreate_request(request, max_bytes=max_bytes)
    if not body:
        return None, new_req
    try:
        return json.loads(body), new_req
    except Exception:
        return None, new_req