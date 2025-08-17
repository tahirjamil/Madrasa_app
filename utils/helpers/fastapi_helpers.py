"""
FastAPI helper functions and dependencies
Replaces Quart-specific helpers with FastAPI patterns
"""

from typing import Optional, Dict, Any, Callable
from functools import wraps
import time
from collections import defaultdict

from fastapi import Request, HTTPException, Depends, Header
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, field_validator
from starlette.status import HTTP_403_FORBIDDEN, HTTP_429_TOO_MANY_REQUESTS

from config import config
from .helpers import security_manager
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
    @templates.env.global_function
    def url_for(name: str, **path_params) -> str:
        """Custom url_for that works with static files and routes"""
        # For static files, create the URL directly
        if name == "static":
            filename = path_params.get("filename", "")
            return f"/static/{filename}"
        elif name == "uploads":
            filename = path_params.get("filename", "")
            return f"/uploads/{filename}"
        # For other routes, you'd need the request context
        # This is a fallback - the request.url_for should be used when available
        return f"/{name}"
