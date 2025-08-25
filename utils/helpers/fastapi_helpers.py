"""
FastAPI helper functions and dependencies
Replaces Quart-specific helpers with FastAPI patterns
"""

from datetime import datetime
import json
from typing import Optional, Dict, Any, Callable, Tuple
from functools import wraps
from collections import defaultdict

from fastapi import Request, HTTPException, Depends, Header, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, field_validator, model_validator
from starlette.status import HTTP_403_FORBIDDEN, HTTP_429_TOO_MANY_REQUESTS
from starlette.requests import Request as StarletteRequest

# Local Imports
from config.config import config
from .helpers import security_manager, validate_madrasa_name, format_phone_number
from .improved_functions import get_env_var
from .logger import log
from utils.keydb.keydb_utils import get_keydb_from_app


# ─── API Key Authentication ───────────────────────────────────────────
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

async def require_api_key(api_key: str = Security(api_key_header)) -> None:
    """FastAPI dependency for API key validation"""
    if api_key not in list(config.API_KEYS):
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Invalid API key"
        )
    
    return


# ─── Client Info Dependency ───────────────────────────────────────────
class ClientInfo(BaseModel):
    """Client information model"""
    ip_address: str
    device_id: str
    device_model: Optional[str] = None
    device_os: Optional[str] = None
    device_brand: Optional[str] = None
    api_key: Optional[str] = None


async def get_client_info(
    request: Request,
    x_device_id: str = Header("unknown"),
    x_device_model: Optional[str] = Header(None),
    x_device_brand: Optional[str] = Header(None),
    x_device_os: Optional[str] = Header(None),
    api_key: str = Security(api_key_header)
) -> ClientInfo:
    """Extract client information from headers"""
    from .helpers import get_ip_address, validate_request_headers, validate_device_fingerprint
    from utils.keydb.keydb_utils import get_keydb_from_app
    # Get IP address
    ip_address = get_ip_address(request)
    device_id = x_device_id or "unknown"
    cache_key = f"client:{ip_address}:{device_id}"

    # Check Redis cache
    pool = get_keydb_from_app(request)
    cached = await pool.get(cache_key) if pool else None
    if cached:
        info = json.loads(cached)
        request.state.client_info = ClientInfo(**info)
        return request.state.client_info
    
    # Validate headers & fingerprint
    if not await validate_request_headers(request):
        raise HTTPException(status_code=400, detail="Invalid headers")
    
    info = {
        "ip_address": ip_address,
        "device_id": x_device_id,
        "device_model": x_device_model or "",
        "device_brand": x_device_brand or "",
        "device_os": x_device_os or "",
        "api_key": api_key
    }

    if not await validate_device_fingerprint(device_data=info, request=request):
        raise HTTPException(status_code=403, detail="Invalid device fingerprint")
    
    # Store in Redis with TTL (10 minutes)
    if pool:
        await pool.set(cache_key, json.dumps(info), ex=600)

    # Cache for this request
    request.state.client_info = ClientInfo(**info)
    return request.state.client_info


# ─── Rate Limiting ───────────────────────────────────────────
def rate_limit(max_requests: int = 10, window: int = 60):
    """Redis-based rate limiting decorator for FastAPI routes"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            client_id = request.headers.get(
                "X-Forwarded-For",
                request.client.host if request.client else "unknown"
            )

            redis = get_keydb_from_app(request)  # your app-specific redis getter
            if not redis:
                # Fallback to no rate limiting if redis unavailable
                return await func(request, *args, **kwargs)

            key = f"rate_limit:{client_id}"
            current_count = await redis.get(key)

            if current_count is None:
                # First request in this window
                await redis.set(key, 1, ex=window)
            else:
                current_count = int(current_count)
                if current_count >= max_requests:
                    # Rate limit exceeded: abort request
                    raise HTTPException(
                        status_code=HTTP_429_TOO_MANY_REQUESTS,
                        detail="Rate limit exceeded. Please try again later."
                    )
                await redis.incr(key)

            return await func(request, *args, **kwargs)
        return wrapper
    return decorator


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

    # phone formatting
    @field_validator('phone')
    @classmethod
    def format_phone(cls, v):
        return format_phone_number(v)

    # madrasa name validation
    @model_validator(mode="after")
    def validate_madrasa_with_phone(self):
        if self.madrasa_name:
            validate_madrasa_name(self.madrasa_name, self.phone, secure=True)
        return self

# ─── Device Validation Dependency ─────────────────────────────────────────── # TODO: Unknown
async def validate_device_dependency(request: Request, client_info: ClientInfo = Depends(get_client_info)):
    from .helpers import validate_device_info
    from .logger import log
    redis = get_keydb_from_app(request)  # get your Redis/KeyDB instance
    
    # Handle both ClientInfo object and dict for backward compatibility
    if isinstance(client_info, dict):
        log.info(action="device_dependency_validation", trace_info=client_info.get('ip_address', ''), message=f"Validating device dependency in client_info dict", secure=False)
        device_id = client_info.get('device_id', '')
        ip_address = client_info.get('ip_address', '')
    else:
        log.info(action="device_dependency_validation", trace_info=client_info.ip_address, message=f"Validating device dependency in client_info object", secure=False)
        device_id = client_info.device_id
        ip_address = client_info.ip_address

    cache_key = f"device_valid:{device_id}:{ip_address}"
    
    cached = await redis.get(cache_key) if redis else None
    if cached is not None:
        if cached == b"1":
            return client_info
        log.warning(action="device_validation_cache_error", message="Cache is not valid in validate_device_dependency")

    # Validate device
    await validate_device_info(
        device_id=device_id,
        ip_address=ip_address
    )

    # Cache the result for 5 minutes
    if redis:
        await redis.set(cache_key, "1", ex=600)

    log.info(action="device_validation_success", trace_info=ip_address, message="Device validation successful", secure=False)
    return client_info


# ─── Centralized Templates Instance ──────────────────────────────────
# Create a single templates instance to be imported by all modules
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

# Add custom globals to templates
def setup_template_globals():
    """Setup custom globals for templates"""
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

    log.info(action="Recreate_request", trace_info="system", message=f"using max_bytes={max_bytes}, Content-Length={request.headers.get('content-length')}", secure=False)

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