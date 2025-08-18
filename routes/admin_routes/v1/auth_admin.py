import asyncio
import requests
from datetime import datetime
from typing import Optional
from fastapi import Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from . import admin_routes, templates
from config import config
from utils.helpers.fastapi_helpers import rate_limit, ClientInfo, get_client_info
from utils.helpers.logger import log
from utils.helpers.session_utils import create_user_session, update_session_activity, clear_user_session

# Note: Login attempt tracking moved to session-based approach
# The global dictionary approach was removed as unused

class LoginForm(BaseModel):
    username: str
    password: str
    recaptcha_response: Optional[str] = None

# ─── Login Page ─────────────────────────────────────────────────
@admin_routes.get('/login', response_class=HTMLResponse, name="login")
@rate_limit(max_requests=50, window=300)
async def login_page(request: Request):
    # See for test mode
    test = True if config.is_testing() else False
    
    # Clear session on GET
    request.session.clear()
    
    # Load keys safely
    RECAPTCHA_SITE_KEY = config.RECAPTCHA_SITE_KEY
    
    return templates.TemplateResponse('admin/login.html', {
        "request": request,
        "error": None,
        "show_captcha": False,
        "site_key": RECAPTCHA_SITE_KEY,
        "test": test
    })

# ─── Login Handler ──────────────────────────────────────────────
@admin_routes.post('/login')
@rate_limit(max_requests=50, window=300)
async def login(
    request: Request,
    client_info: ClientInfo = Depends(get_client_info)
):
    # Enhanced debugging for form data parsing
    print("=== ADMIN LOGIN FUNCTION CALLED ===")  # Debug print
    content_type = request.headers.get('content-type', '')
    
    # Log request details for debugging
    log.info(action="admin_login_request", trace_info=client_info.ip_address, 
             message=f"Login request received - Content-Type: {content_type}, Method: {request.method}", 
             secure=False)
    
    # Parse form data with better error handling
    form_data = None
    username = ''
    password = ''
    recaptcha_response = ''
    
    try:
        # Always use FastAPI's form parser first - it handles both urlencoded and multipart
        form = await request.form()
        
        # Convert FormData to dict for consistent handling
        form_data = {}
        for key in form:
            form_data[key] = form[key]
        
        log.info(action="admin_login_debug", trace_info=client_info.ip_address,
                 message=f"Form parsed successfully - Fields: {list(form_data.keys())}, Content-Type: {content_type}", 
                 secure=False)
        
        # Log each field (masking password)
        for key, value in form_data.items():
            masked_value = '*' * len(str(value)) if key == 'password' else str(value)
            log.info(action="admin_login_debug", trace_info=client_info.ip_address,
                     message=f"Form field: {key}={masked_value} (len: {len(str(value))})", 
                     secure=False)
        
        # Extract values with debugging
        username = str(form_data.get('username', '')).strip()
        password = str(form_data.get('password', '')).strip()
        recaptcha_response = str(form_data.get('g-recaptcha-response', '')).strip()
        
        log.info(action="admin_login_debug", trace_info=client_info.ip_address,
                 message=f"Extracted values - Username present: {bool(username)}, Password present: {bool(password)}, Captcha present: {bool(recaptcha_response)}",
                 secure=False)
                 
    except Exception as e:
        log.error(action="admin_login_parse_error", trace_info=client_info.ip_address,
                  message=f"Error parsing form data: {str(e)}", secure=False)
        # Try to fall back to direct form parsing
        try:
            form_data = await request.form()
            username = str(form_data.get('username', '')).strip()
            password = str(form_data.get('password', '')).strip()
            recaptcha_response = str(form_data.get('g-recaptcha-response', '')).strip()
        except Exception as e2:
            log.error(action="admin_login_parse_error_fallback", trace_info=client_info.ip_address,
                      message=f"Fallback form parsing also failed: {str(e2)}", secure=False)
    
    # See for test mode
    test = True if config.is_testing() else False
    
    # Initialize attempt counter
    if 'login_attempts' not in request.session:
        request.session['login_attempts'] = 0

    error = None
    show_captcha = False

    # Load keys safely
    RECAPTCHA_SITE_KEY = config.RECAPTCHA_SITE_KEY
    RECAPTCHA_SECRET_KEY = config.RECAPTCHA_SECRET_KEY
    
    # Get client info for logging
    ip_address = client_info.ip_address

    ADMIN_USER = config.ADMIN_USERNAME
    ADMIN_PASS = config.ADMIN_PASSWORD
    
    # Enhanced debug logging for form data and credentials
    if form_data:
        safe_form_data = {k: ('*' * len(v) if k == 'password' else v) for k, v in form_data.items()}
        log.info(action="admin_login_debug", trace_info=ip_address, message=f"Parsed form data: {safe_form_data}", secure=False)
    else:
        log.warning(action="admin_login_debug", trace_info=ip_address, message="Form data is None or empty", secure=False)

    # Enhanced debug logging for credentials comparison
    log.info(action="admin_login_debug", trace_info=ip_address, 
             message=f"Config Admin Username: '{ADMIN_USER}' (len: {len(str(ADMIN_USER)) if ADMIN_USER else 0}, type: {type(ADMIN_USER).__name__})", 
             secure=False)
    log.info(action="admin_login_debug", trace_info=ip_address, 
             message=f"Config Admin Password: {'*' * len(str(ADMIN_PASS)) if ADMIN_PASS else 'None'} (len: {len(str(ADMIN_PASS)) if ADMIN_PASS else 0}, type: {type(ADMIN_PASS).__name__})", 
             secure=False)
    log.info(action="admin_login_debug", trace_info=ip_address, 
             message=f"Submitted Username: '{username}' (len: {len(username)}, type: {type(username).__name__})", 
             secure=False)
    log.info(action="admin_login_debug", trace_info=ip_address, 
             message=f"Submitted Password: {'*' * len(password) if password else 'None'} (len: {len(password)}, type: {type(password).__name__})", 
             secure=False)
    
    # Detailed comparison
    username_match = username == ADMIN_USER
    password_match = password == ADMIN_PASS
    log.info(action="admin_login_debug", trace_info=ip_address, 
             message=f"Comparison results - Username match: {username_match}, Password match: {password_match}", 
             secure=False)
    
    # Check for common issues
    if not username:
        log.warning(action="admin_login_debug", trace_info=ip_address, message="Username is empty!", secure=False)
    if not password:
        log.warning(action="admin_login_debug", trace_info=ip_address, message="Password is empty!", secure=False)
    if not ADMIN_USER or not ADMIN_PASS:
        log.error(action="admin_login_debug", trace_info=ip_address, 
                  message=f"Admin credentials not properly configured! User configured: {bool(ADMIN_USER)}, Pass configured: {bool(ADMIN_PASS)}", 
                  secure=False)

    request.session['login_attempts'] += 1

    # Only require captcha if keys exist
    if RECAPTCHA_SITE_KEY and RECAPTCHA_SECRET_KEY:
        if request.session['login_attempts'] >= 4:
            show_captcha = True

            if not recaptcha_response:
                error = "Please complete the reCAPTCHA."
                return templates.TemplateResponse(
                    'admin/login.html',
                    {
                        "request": request,
                        "error": error,
                        "show_captcha": show_captcha,
                        "site_key": RECAPTCHA_SITE_KEY
                    }
                )

            verify_url = "https://www.google.com/recaptcha/api/siteverify"
            payload = {
                'secret': RECAPTCHA_SECRET_KEY,
                'response': recaptcha_response
            }
            
            # FIX: Run blocking request in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: requests.post(verify_url, data=payload).json()
            )

            if not result.get('success'):
                error = "Invalid reCAPTCHA. Please try again."
                log.warning(action="admin_recaptcha_failed", trace_info=ip_address, message="Failed reCAPTCHA verification", secure=False)
                return templates.TemplateResponse(
                    'admin/login.html',
                    {
                        "request": request,
                        "error": error,
                        "show_captcha": show_captcha,
                        "site_key": RECAPTCHA_SITE_KEY
                    }
                )

    # SECURITY: In production, don't allow test bypass
    if test and config.is_development():
        # Only allow test bypass in development mode
        if username == ADMIN_USER and password == ADMIN_PASS:
            # Create enhanced admin session
            create_user_session(
                request=request,
                user_id=1,  # Admin user ID
                device_id=client_info.device_id,
                ip_address=ip_address,
                admin_logged_in=True,
                admin_login_time=datetime.now().isoformat()
            )
            request.session.pop('login_attempts', None)  # Reset
            log.info(action="admin_login_test", trace_info=ip_address, message="Admin logged in (test mode)", secure=False)
            return RedirectResponse(url='/admin/', status_code=302)
    else:
        # Production mode - strict authentication
        if username == ADMIN_USER and password == ADMIN_PASS:
            # Create enhanced admin session
            create_user_session(
                request=request,
                user_id=1,  # Admin user ID
                device_id=client_info.device_id,
                ip_address=ip_address,
                admin_logged_in=True,
                admin_login_time=datetime.now().isoformat()
            )
            request.session.pop('login_attempts', None)  # Reset
            log.info(action="admin_login_success", trace_info=ip_address, message=f"Admin {username} logged in", secure=False)
            return RedirectResponse(url='/admin/', status_code=302)
        
    error = "Invalid credentials"
    log.warning(action="admin_login_failed", trace_info=ip_address, message=f"Failed login attempt for: {username}", secure=False)

    return templates.TemplateResponse(
        'admin/login.html',
        {
            "request": request,
            "error": error,
            "show_captcha": (RECAPTCHA_SITE_KEY and RECAPTCHA_SECRET_KEY and request.session.get('login_attempts', 0) >= 4),
            "site_key": RECAPTCHA_SITE_KEY
        }
    )

# ─── Debug Endpoint ─────────────────────────────────────────────────────
@admin_routes.post('/debug-form')
async def debug_form(request: Request):
    """Debug endpoint to check form parsing"""
    content_type = request.headers.get('content-type', '')
    body = await request.body()
    
    result = {
        "content_type": content_type,
        "body_raw": body.decode('utf-8', errors='ignore')[:500],  # First 500 chars
        "body_len": len(body),
    }
    
    try:
        # Try to parse as form
        form_data = await request.form()
        result["form_data"] = dict(form_data)
    except Exception as e:
        result["form_error"] = str(e)
    
    log.info(action="debug_form", trace_info="debug", message=f"Debug form data: {result}", secure=False)
    
    return result

# ─── Logout ─────────────────────────────────────────────────────
@admin_routes.get('/logout', name="admin_logout")
async def admin_logout(request: Request, client_info: ClientInfo = Depends(get_client_info)):
    ip_address = client_info.ip_address
    
    if request.session.get('admin_logged_in'):
        log.info(action="admin_logout", trace_info=ip_address, message="Admin logged out", secure=False)
    
    # Use enhanced session clearing
    clear_user_session(request)
    return RedirectResponse(url='/admin/login', status_code=302)
