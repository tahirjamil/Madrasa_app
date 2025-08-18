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
    # Parse form data manually - handle both multipart and urlencoded
    print("=== ADMIN LOGIN FUNCTION CALLED ===")  # Debug print
    content_type = request.headers.get('content-type', '')
    
    if 'application/x-www-form-urlencoded' in content_type:
        # Handle URL-encoded form data
        body = await request.body()
        form_data_str = body.decode('utf-8')
        form_data = {}
        for item in form_data_str.split('&'):
            if '=' in item:
                key, value = item.split('=', 1)
                # URL decode the values
                import urllib.parse
                form_data[urllib.parse.unquote(key)] = urllib.parse.unquote(value)
    else:
        # Handle multipart form data
        form_data = await request.form()
    
    username = form_data.get('username', '')
    password = form_data.get('password', '')
    recaptcha_response = form_data.get('g-recaptcha-response', '')
    
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
    
    # Debug: Log the raw form data
    log.info(action="admin_login_debug", trace_info=ip_address, message=f"Raw form data: {dict(form_data)}", secure=False)

    # Debug logging to see what credentials are being used
    log.info(action="admin_login_debug", trace_info=ip_address, message=f"Admin credentials - Username: '{ADMIN_USER}' (len: {len(str(ADMIN_USER)) if ADMIN_USER else 0}), Password: '{ADMIN_PASS}' (len: {len(str(ADMIN_PASS)) if ADMIN_PASS else 0})", secure=False)
    log.info(action="admin_login_debug", trace_info=ip_address, message=f"Login attempt - Username: '{username}' (len: {len(str(username)) if username else 0}), Password: '{password}' (len: {len(str(password)) if password else 0})", secure=False)
    log.info(action="admin_login_debug", trace_info=ip_address, message=f"Username match: {username == ADMIN_USER}, Password match: {password == ADMIN_PASS}", secure=False)

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

# ─── Logout ─────────────────────────────────────────────────────
@admin_routes.get('/logout', name="admin_logout")
async def admin_logout(request: Request, client_info: ClientInfo = Depends(get_client_info)):
    ip_address = client_info.ip_address
    
    if request.session.get('admin_logged_in'):
        log.info(action="admin_logout", trace_info=ip_address, message="Admin logged out", secure=False)
    
    # Use enhanced session clearing
    clear_user_session(request)
    return RedirectResponse(url='/admin/login', status_code=302)
