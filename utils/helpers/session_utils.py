# """
# Session Management Utilities for FastAPI
# Provides enhanced session management, security, and tracking capabilities
# """

# import time
# import secrets
# from datetime import datetime, timezone, timedelta
# from typing import Dict, Any, Optional, Tuple, List
# from fastapi import Request, HTTPException, Depends
# from starlette.status import HTTP_403_FORBIDDEN, HTTP_401_UNAUTHORIZED
# from starlette.middleware.base import BaseHTTPMiddleware

# from config.config import config
# from .logger import log


# class SessionManager:
#     """Enhanced session management with security features"""
    
#     def __init__(self):
#         self.session_timeout = config.PERMANENT_SESSION_LIFETIME
#         self.max_sessions_per_user = 5  # Maximum concurrent sessions per user
    
#     def create_session_token(self, user_id: int, device_id: str) -> str:
#         """Create a secure session token"""
#         timestamp = str(int(time.time()))
#         random_part = secrets.token_urlsafe(16)
#         return f"{user_id}:{device_id}:{timestamp}:{random_part}"
    
#     def validate_session_token(self, token: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
#         """Validate a session token and return session data"""
#         try:
#             parts = token.split(':')
#             if len(parts) != 4:
#                 return False, None
            
#             user_id, device_id, timestamp, _ = parts
#             session_time = int(timestamp)
#             current_time = int(time.time())
            
#             # Check if session is expired
#             if current_time - session_time > self.session_timeout:
#                 return False, None
            
#             return True, {
#                 'user_id': int(user_id),
#                 'device_id': device_id,
#                 'created_at': session_time
#             }
#         except (ValueError, IndexError):
#             return False, None
    
#     def is_session_expired(self, session_data: Dict[str, Any]) -> bool:
#         """Check if session has expired"""
#         if 'timestamp' not in session_data:
#             return True
        
#         try:
#             session_time = datetime.fromisoformat(session_data['timestamp'].replace('Z', '+00:00'))
#             current_time = datetime.now(timezone.utc)
#             return (current_time - session_time).total_seconds() > self.session_timeout
#         except (ValueError, KeyError):
#             return True


# # Global session manager instance
# session_manager = SessionManager()


# class SessionActivityTracker:
#     """Track session activity for security monitoring"""
    
#     def __init__(self):
#         self.activity_log: List[Dict[str, Any]] = []
#         self.max_log_size = 1000
    
#     def log_activity(self, user_id: int, activity_type: str, ip_address: str, details: Dict[str, Any] = None):
#         """Log session activity"""
#         activity = {
#             'timestamp': datetime.now().isoformat(),
#             'user_id': user_id,
#             'activity_type': activity_type,
#             'ip_address': ip_address,
#             'details': details or {}
#         }
        
#         self.activity_log.append(activity)
        
#         # Keep log size manageable
#         if len(self.activity_log) > self.max_log_size:
#             self.activity_log = self.activity_log[-self.max_log_size:]
        
#         # Log to application logger
#         log.info(
#             action=f"session_activity_{activity_type}",
#             trace_info=ip_address,
#             message=f"Session activity: {activity_type} for user {user_id}",
#             secure=True
#         )
    
#     def get_user_activity(self, user_id: int, hours: int = 24) -> List[Dict[str, Any]]:
#         """Get user activity for the last N hours"""
#         cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        
#         return [
#             activity for activity in self.activity_log
#             if activity['user_id'] == user_id and 
#             datetime.fromisoformat(activity['timestamp'].replace('Z', '+00:00')) > cutoff_time
#         ]


# # Global activity tracker instance
# activity_tracker = SessionActivityTracker()


# # ─── FastAPI Dependencies ───────────────────────────────────────────

# async def require_valid_session(request: Request) -> Dict[str, Any]:
#     """Dependency to require a valid session"""
#     session_data = request.session.get('user_data')
    
#     if not session_data:
#         raise HTTPException(
#             status_code=HTTP_401_UNAUTHORIZED,
#             detail="Valid session required"
#         )
    
#     # Check if session is expired
#     if session_manager.is_session_expired(session_data):
#         request.session.clear()
#         raise HTTPException(
#             status_code=HTTP_401_UNAUTHORIZED,
#             detail="Session has expired"
#         )
    
#     return session_data


# async def require_admin_session(request: Request) -> bool:
#     """Dependency to require admin session"""
#     if not request.session.get('admin_logged_in'):
#         raise HTTPException(
#             status_code=HTTP_403_FORBIDDEN,
#             detail="Admin access required"
#         )
#     return True


# async def get_optional_session(request: Request) -> Optional[Dict[str, Any]]:
#     """Dependency to get session if it exists and is valid"""
#     session_data = request.session.get('user_data')
    
#     if session_data and not session_manager.is_session_expired(session_data):
#         return session_data
    
#     return None


# # ─── Session Management Functions ───────────────────────────────────────────

# def create_user_session(request: Request, user_id: int, device_id: str, ip_address: str, **kwargs) -> Dict[str, Any]:
#     """Create a new user session"""
#     session_data = {
#         'user_id': user_id,
#         'device_id': device_id,
#         'ip_address': ip_address,
#         'timestamp': datetime.now(timezone.utc).isoformat(),
#         'created_at': datetime.now(timezone.utc).isoformat(),
#         'session_token': session_manager.create_session_token(user_id, device_id),
#         **kwargs
#     }
    
#     request.session['user_data'] = session_data
    
#     # Log session creation
#     activity_tracker.log_activity(
#         user_id=user_id,
#         activity_type='session_created',
#         ip_address=ip_address,
#         details={'device_id': device_id}
#     )
    
#     return session_data


# def update_session_activity(request: Request, activity_type: str, details: Dict[str, Any] = None):
#     """Update session activity"""
#     session_data = request.session.get('user_data')
#     if session_data:
#         # Update last activity timestamp
#         session_data['last_activity'] = datetime.now(timezone.utc).isoformat()
#         request.session['user_data'] = session_data
        
#         # Log activity
#         activity_tracker.log_activity(
#             user_id=session_data['user_id'],
#             activity_type=activity_type,
#             ip_address=session_data.get('ip_address', 'unknown'),
#             details=details
#         )


# def clear_user_session(request: Request):
#     """Clear user session"""
#     session_data = request.session.get('user_data')
#     if session_data:
#         # Log session termination
#         activity_tracker.log_activity(
#             user_id=session_data['user_id'],
#             activity_type='session_terminated',
#             ip_address=session_data.get('ip_address', 'unknown')
#         )
    
#     request.session.clear()


# def get_session_info(request: Request) -> Optional[Dict[str, Any]]:
#     """Get current session information"""
#     session_data = request.session.get('user_data')
#     if session_data and not session_manager.is_session_expired(session_data):
#         return {
#             'user_id': session_data.get('user_id'),
#             'device_id': session_data.get('device_id'),
#             'ip_address': session_data.get('ip_address'),
#             'created_at': session_data.get('created_at'),
#             'last_activity': session_data.get('last_activity'),
#             'is_admin': request.session.get('admin_logged_in', False)
#         }
#     return None


# # ─── Session Security Middleware ───────────────────────────────────────────

# class SessionSecurityMiddleware(BaseHTTPMiddleware):
#     """Enhanced session security middleware"""
    
#     async def dispatch(self, request: Request, call_next):
#         # Add session security headers
#         response = await call_next(request)
        
#         # Set secure session cookies
#         if hasattr(response, 'set_cookie'):
#             response.set_cookie(
#                 'session',
#                 secure=config.SESSION_COOKIE_SECURE,
#                 httponly=config.SESSION_COOKIE_HTTPONLY,
#                 samesite='lax',
#                 max_age=config.PERMANENT_SESSION_LIFETIME
#             )
        
#         return response


# class SessionActivityMiddleware(BaseHTTPMiddleware):
#     """Middleware to track session activity"""
    
#     async def dispatch(self, request: Request, call_next):
#         # Track session activity before processing
#         session_data = request.session.get('user_data')
#         if session_data:
#             update_session_activity(
#                 request, 
#                 'request_processed', 
#                 {'path': request.url.path, 'method': request.method}
#             )
        
#         response = await call_next(request)
#         return response


# # ─── Session Cleanup Utilities ───────────────────────────────────────────

# async def cleanup_expired_sessions():
#     """Clean up expired sessions (can be called periodically)"""
#     # This would typically be called by a background task
#     # For now, we'll just log that cleanup is needed
#     log.info(
#         action="session_cleanup",
#         trace_info="system",
#         message="Session cleanup check completed",
#         secure=False
#     )


# def get_session_statistics() -> Dict[str, Any]:
#     """Get session statistics"""
#     return {
#         'total_activities': len(activity_tracker.activity_log),
#         'max_log_size': activity_tracker.max_log_size,
#         'session_timeout': session_manager.session_timeout,
#         'max_sessions_per_user': session_manager.max_sessions_per_user
#     }
