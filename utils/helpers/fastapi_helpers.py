"""
FastAPI helper functions and dependencies
Replaces Quart-specific helpers with FastAPI patterns
"""

from typing import Optional, Dict, Any, Callable, Tuple
from functools import wraps
import time
from collections import defaultdict
from datetime import datetime

from fastapi import Request, HTTPException, Depends, Header
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, field_validator
from starlette.status import HTTP_403_FORBIDDEN, HTTP_429_TOO_MANY_REQUESTS
from starlette.middleware.base import BaseHTTPMiddleware

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
    def url_for(name: str, **path_params) -> str:
        """Custom url_for that works with static files and routes"""
        # For static files, create the URL directly
        if name == "static":
            filename = path_params.get("filename", "")
            return f"/static/{filename}"
        elif name == "uploads":
            filename = path_params.get("filename", "")
            return f"/uploads/{filename}"
        
        # Handle admin routes with prefix
        if name.startswith("admin_routes."):
            route_name = name.replace("admin_routes.", "")
            # Map route names to paths
            admin_route_map = {
                "admin_dashboard": "/admin/",
                "login": "/admin/login",
                "admin_logout": "/admin/logout",
                "view_logs": "/admin/logs",
                "logs_data": "/admin/logs/data",
                "info_page": "/admin/info",
                "info_data_admin": "/admin/info/data",
                "exam_results": "/admin/exam_results",
                "delete_exam_result": "/admin/exam_results/delete",
                "members": "/admin/members",
                "manage_member": "/admin/members/manage",
                "delete_pending_member": "/admin/members/delete",
                "notice_page": "/admin/notice",
                "delete_notice": "/admin/notice/delete",
                "routines": "/admin/routines",
                "add_routine": "/admin/routines/add",
                "events": "/admin/events",
                "add_exam": "/admin/events/exams/add",
                "madrasa_pictures": "/admin/madrasa_pictures",
                "delete_picture": "/admin/pictures/delete",
                "exams": "/admin/admin/events/exams",
                "interactions": "/admin/interactions",
                "power_management": "/admin/power",
                "modify_payment": "/admin/payment/modify",
            }
            
            base_path = admin_route_map.get(route_name, f"/admin/{route_name}")
            
            # Handle path parameters
            if path_params:
                # For query parameters
                query_params = []
                for key, value in path_params.items():
                    if key not in ["filename", "verify_people_id", "user_id", "modify"]:
                        query_params.append(f"{key}={value}")
                
                # Special handling for specific routes
                if route_name == "delete_exam_result" and "filename" in path_params:
                    return f"{base_path}/{path_params['filename']}"
                elif route_name == "delete_notice" and "filename" in path_params:
                    return f"{base_path}/{path_params['filename']}"
                elif route_name == "delete_picture" and "filename" in path_params:
                    return f"{base_path}/{path_params['filename']}"
                elif route_name == "delete_pending_member" and "verify_people_id" in path_params:
                    return f"{base_path}/{path_params['verify_people_id']}"
                elif route_name == "manage_member" and "modify" in path_params:
                    base_path = f"/admin/members/{path_params['modify']}"
                    if "user_id" in path_params:
                        query_params.append(f"user_id={path_params['user_id']}")
                elif route_name == "modify_payment" and "modify" in path_params:
                    base_path = f"/admin/payment/{path_params['modify']}"
                    if "user_id" in path_params:
                        query_params.append(f"user_id={path_params['user_id']}")
                
                if query_params:
                    return f"{base_path}?{'&'.join(query_params)}"
            
            return base_path
        
        # Handle API routes
        elif name.startswith("api."):
            route_name = name.replace("api.", "")
            api_route_map = {
                "manage_account": "/api/v1/account/manage",
                "process_payment": "/api/v1/process_payment",
                "due_payments": "/api/v1/due_payments",
            }
            base_path = api_route_map.get(route_name, f"/api/v1/{route_name}")
            
            # Handle query parameters
            if path_params:
                query_params = []
                for key, value in path_params.items():
                    if key == "page_type":
                        # For manage_account, page_type is in the path
                        base_path = base_path.replace("/manage", f"/{value}")
                    else:
                        query_params.append(f"{key}={value}")
                
                if query_params:
                    return f"{base_path}?{'&'.join(query_params)}"
            
            return base_path
        
        # For other routes (web routes)
        else:
            # Direct mapping for known routes
            route_map = {
                "home": "/",
                "donate": "/donate",
                "contact": "/contact",
                "privacy": "/privacy",
                "terms": "/terms",
            }
            return route_map.get(name, f"/{name}")
    
    def get_flashed_messages(with_categories=False):
        """FastAPI compatible flash messages - returns empty list for now"""
        # In FastAPI, flash messages are typically passed as template context
        # This is a placeholder that returns empty to prevent template errors
        return []
    
    def csrf_token():
        """FastAPI compatible CSRF token - returns empty string for now"""
        # In FastAPI, CSRF protection is typically handled by middleware
        # This is a placeholder that returns empty to prevent template errors
        return ""
    
    # Add the functions as globals to the template environment
    templates.env.globals["url_for"] = url_for
    templates.env.globals["get_flashed_messages"] = get_flashed_messages
    templates.env.globals["csrf_token"] = csrf_token


# ─── Session Management Helpers ───────────────────────────────────────────
def create_session_data(user_id: int, device_id: str, ip_address: str, **kwargs) -> Dict[str, Any]:
    """Create session data with standard fields"""
    from datetime import datetime, timezone
    
    session_data = {
        'user_id': user_id,
        'device_id': device_id,
        'ip_address': ip_address,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'created_at': datetime.now(timezone.utc).isoformat(),
        **kwargs
    }
    return session_data


def validate_session_data(session_data: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate session data for required fields and security"""
    required_fields = ['user_id', 'device_id', 'ip_address', 'timestamp']
    
    for field in required_fields:
        if not session_data.get(field):
            return False, f"Missing required session field: {field}"
    
    # Validate session age
    try:
        from datetime import datetime, timezone
        session_time = datetime.fromisoformat(session_data['timestamp'].replace('Z', '+00:00'))
        current_time = datetime.now(timezone.utc)
        
        # Check if session is older than 24 hours
        if (current_time - session_time).total_seconds() > 24 * 3600:
            return False, "Session has expired"
    except (ValueError, KeyError):
        return False, "Invalid session timestamp"
    
    return True, ""


async def require_authenticated_session(request: Request) -> Dict[str, Any]:
    """Dependency to require an authenticated session"""
    session_data = request.session.get('user_data')
    
    if not session_data:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Authentication required"
        )
    
    is_valid, error = validate_session_data(session_data)
    if not is_valid:
        # Clear invalid session
        request.session.clear()
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=error
        )
    
    return session_data


async def require_admin_session(request: Request) -> bool:
    """Dependency to require admin session"""
    if not request.session.get('admin_logged_in'):
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return True


def clear_user_session(request: Request) -> None:
    """Clear user session data"""
    request.session.clear()


def set_user_session(request: Request, user_data: Dict[str, Any]) -> None:
    """Set user session data"""
    request.session['user_data'] = user_data


def get_user_session(request: Request) -> Optional[Dict[str, Any]]:
    """Get user session data if it exists and is valid"""
    session_data = request.session.get('user_data')
    if session_data:
        is_valid, _ = validate_session_data(session_data)
        if is_valid:
            return session_data
    return None


# ─── Session Security Middleware ───────────────────────────────────────────
class SessionSecurityMiddleware(BaseHTTPMiddleware):
    """Middleware to enhance session security"""
    
    async def dispatch(self, request: Request, call_next):
        # Add session security headers
        response = await call_next(request)
        
        # Set secure session cookies
        if hasattr(response, 'set_cookie'):
            response.set_cookie(
                'session',
                secure=config.SESSION_COOKIE_SECURE,
                httponly=config.SESSION_COOKIE_HTTPONLY,
                samesite='lax',  # Default to lax for compatibility
                max_age=config.PERMANENT_SESSION_LIFETIME
            )
        
        return response


# ─── Session Activity Tracking ───────────────────────────────────────────
async def track_session_activity(request: Request, activity_type: str, details: Optional[Dict[str, Any]] = None) -> None:
    """Track session activity for security monitoring"""
    session_data = get_user_session(request)
    if session_data:
        activity = {
            'timestamp': datetime.now().isoformat(),
            'activity_type': activity_type,
            'user_id': session_data.get('user_id'),
            'ip_address': session_data.get('ip_address'),
            'device_id': session_data.get('device_id'),
            'details': details or {}
        }
        
        log.info(
            action=f"session_activity_{activity_type}",
            trace_info=session_data.get('ip_address', 'unknown'),
            message=f"Session activity: {activity_type}",
            secure=True
        )
