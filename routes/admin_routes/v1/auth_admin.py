import asyncio
import requests
from datetime import datetime
from typing import Optional
from fastapi import Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel

from . import admin_routes, templates
from config import config
from utils.helpers.fastapi_helpers import rate_limit, ClientInfo, get_client_info
from pathlib import Path
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
    username: str = Form(default=""),
    password: str = Form(default=""),
    client_info: ClientInfo = Depends(get_client_info)
):
    """Handle admin login with proper FastAPI form handling"""
    
    # Log the login attempt
    log.info(action="admin_login_attempt", trace_info=client_info.ip_address,
             message=f"Login attempt - Username: '{username}', Has password: {bool(password)}", 
             secure=False)
    
    # Get reCAPTCHA from form if present
    try:
        form_data = await request.form()
        recaptcha_response = form_data.get('g-recaptcha-response', '')
    except:
        recaptcha_response = ''
    
    # See for test mode
    test = config.is_testing()
    
    # Initialize attempt counter
    if 'login_attempts' not in request.session:
        request.session['login_attempts'] = 0

    # Load admin credentials with robust fallback
    ADMIN_USER = config.ADMIN_USERNAME
    ADMIN_PASS = config.ADMIN_PASSWORD
    
    # Fallback: Read directly from .env if config failed
    if not ADMIN_USER or not ADMIN_PASS:
        try:
            env_path = Path(__file__).parent.parent.parent.parent / '.env'
            if env_path.exists():
                with open(env_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            value = value.strip().strip('"').strip("'")
                            if key == 'ADMIN_USERNAME' and not ADMIN_USER:
                                ADMIN_USER = value
                            elif key == 'ADMIN_PASSWORD' and not ADMIN_PASS:
                                ADMIN_PASS = value
        except Exception as e:
            log.error(action="admin_login_env_error", trace_info=client_info.ip_address,
                      message=f"Failed to read .env file: {e}", secure=False)
    
    # Final hardcoded fallback for development
    if not ADMIN_USER:
        ADMIN_USER = "admin"
    if not ADMIN_PASS:
        ADMIN_PASS = "admin123"
    
    # Debug logging
    log.info(action="admin_login_debug", trace_info=client_info.ip_address,
             message=f"Admin config - Username exists: {bool(ADMIN_USER)}, Password exists: {bool(ADMIN_PASS)}", 
             secure=False)
    
    # Validate credentials are configured
    if not ADMIN_USER or not ADMIN_PASS:
        log.error(action="admin_login_config_error", trace_info=client_info.ip_address,
                  message="Admin credentials not configured in environment!", secure=False)
        return templates.TemplateResponse('admin/login.html', {
            "request": request,
            "error": "System configuration error. Please contact administrator.",
            "show_captcha": False,
            "site_key": config.RECAPTCHA_SITE_KEY
        })

    # Increment login attempts
    request.session['login_attempts'] += 1
    
    # Check credentials
    credentials_valid = (username == ADMIN_USER and password == ADMIN_PASS)
    
    log.info(action="admin_login_validation", trace_info=client_info.ip_address,
             message=f"Credential validation - Username match: {username == ADMIN_USER}, "
                     f"Password match: {password == ADMIN_PASS}, Valid: {credentials_valid}", 
             secure=False)

    # Handle reCAPTCHA if needed
    show_captcha = False
    RECAPTCHA_SITE_KEY = config.RECAPTCHA_SITE_KEY
    RECAPTCHA_SECRET_KEY = config.RECAPTCHA_SECRET_KEY
    
    if RECAPTCHA_SITE_KEY and RECAPTCHA_SECRET_KEY and request.session['login_attempts'] >= 4:
        show_captcha = True
        if not recaptcha_response:
            return templates.TemplateResponse('admin/login.html', {
                "request": request,
                "error": "Please complete the reCAPTCHA.",
                "show_captcha": show_captcha,
                "site_key": RECAPTCHA_SITE_KEY
            })

        # Verify reCAPTCHA
        verify_url = "https://www.google.com/recaptcha/api/siteverify"
        payload = {'secret': RECAPTCHA_SECRET_KEY, 'response': recaptcha_response}
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: requests.post(verify_url, data=payload).json()
        )

        if not result.get('success'):
            log.warning(action="admin_recaptcha_failed", trace_info=client_info.ip_address, 
                       message="Failed reCAPTCHA verification", secure=False)
            return templates.TemplateResponse('admin/login.html', {
                "request": request,
                "error": "Invalid reCAPTCHA. Please try again.",
                "show_captcha": show_captcha,
                "site_key": RECAPTCHA_SITE_KEY
            })

    # Check credentials and handle login
    if credentials_valid:
        # Successful login
        create_user_session(
            request=request,
            user_id=1,  # Admin user ID
            device_id=client_info.device_id,
            ip_address=client_info.ip_address,
            admin_logged_in=True,
            admin_login_time=datetime.now().isoformat()
        )
        request.session.pop('login_attempts', None)  # Reset attempts
        
        log.info(action="admin_login_success", trace_info=client_info.ip_address, 
                 message=f"Admin '{username}' logged in successfully", secure=False)
        
        return RedirectResponse(url='/admin/', status_code=302)
    
    # Failed login
    log.warning(action="admin_login_failed", trace_info=client_info.ip_address, 
                message=f"Failed login attempt for username: '{username}'", secure=False)
    
    return templates.TemplateResponse('admin/login.html', {
        "request": request,
        "error": "Invalid credentials",
        "show_captcha": show_captcha,
        "site_key": RECAPTCHA_SITE_KEY,
        "test": test
    })

# ─── Debug Endpoints ─────────────────────────────────────────────────────
@admin_routes.get('/debug-config')
async def debug_config(request: Request):
    """Debug endpoint to check configuration"""
    import os
    
    # Get environment variables
    env_vars = {
        "ADMIN_USERNAME_ENV": os.environ.get('ADMIN_USERNAME', 'NOT_SET'),
        "ADMIN_PASSWORD_ENV": os.environ.get('ADMIN_PASSWORD', 'NOT_SET'),
        "ADMIN_USERNAME_ENV_EXISTS": 'ADMIN_USERNAME' in os.environ,
        "ADMIN_PASSWORD_ENV_EXISTS": 'ADMIN_PASSWORD' in os.environ,
    }
    
    # Get config values
    config_values = {
        "config.ADMIN_USERNAME": config.ADMIN_USERNAME,
        "config.ADMIN_PASSWORD": '*' * len(config.ADMIN_PASSWORD) if config.ADMIN_PASSWORD else None,
        "config.ADMIN_USERNAME_type": type(config.ADMIN_USERNAME).__name__,
        "config.ADMIN_PASSWORD_type": type(config.ADMIN_PASSWORD).__name__,
        "config.ADMIN_USERNAME_len": len(str(config.ADMIN_USERNAME)) if config.ADMIN_USERNAME else 0,
        "config.ADMIN_PASSWORD_len": len(str(config.ADMIN_PASSWORD)) if config.ADMIN_PASSWORD else 0,
    }
    
    # Test comparison
    test_username = "admin"
    test_password = "admin123"
    comparisons = {
        "test_username": test_username,
        "test_password_len": len(test_password),
        "username_matches_test": config.ADMIN_USERNAME == test_username,
        "password_matches_test": config.ADMIN_PASSWORD == test_password,
    }
    
    return JSONResponse({
        "environment": env_vars,
        "config": config_values,
        "test_comparisons": comparisons,
        "note": "Check if environment variables are properly loaded"
    })

@admin_routes.post('/debug-form')
async def debug_form(
    request: Request,
    username: str = Form(default=""),
    password: str = Form(default="")
):
    """Debug endpoint to test form parsing with FastAPI Form"""
    content_type = request.headers.get('content-type', '')
    
    # Also try raw form parsing
    try:
        form_data = await request.form()
        raw_form = dict(form_data)
    except:
        raw_form = None
    
    result = {
        "content_type": content_type,
        "fastapi_form_params": {
            "username": username,
            "password_len": len(password),
            "username_type": type(username).__name__,
            "password_type": type(password).__name__,
        },
        "raw_form_data": raw_form,
        "credentials_check": {
            "username_matches_admin": username == config.ADMIN_USERNAME,
            "password_matches_admin": password == config.ADMIN_PASSWORD,
            "config_username": config.ADMIN_USERNAME,
            "config_password_len": len(config.ADMIN_PASSWORD) if config.ADMIN_PASSWORD else 0,
        }
    }
    
    log.info(action="debug_form", trace_info="debug", message=f"Debug form data: {result}", secure=False)
    
    return JSONResponse(result)

@admin_routes.post('/test-login')
async def test_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    """Simple test login endpoint"""
    # Direct comparison
    expected_user = "admin"
    expected_pass = "admin123"
    
    result = {
        "received": {
            "username": username,
            "password_len": len(password)
        },
        "expected": {
            "username": expected_user,
            "password_len": len(expected_pass)
        },
        "matches": {
            "username": username == expected_user,
            "password": password == expected_pass
        },
        "config_values": {
            "config_username": config.ADMIN_USERNAME,
            "config_password_exists": bool(config.ADMIN_PASSWORD),
            "config_matches_expected": {
                "username": config.ADMIN_USERNAME == expected_user,
                "password": config.ADMIN_PASSWORD == expected_pass
            }
        }
    }
    
    if username == expected_user and password == expected_pass:
        result["status"] = "SUCCESS - Credentials match!"
    else:
        result["status"] = "FAILED - Credentials don't match"
    
    return JSONResponse(result)

# ─── Logout ─────────────────────────────────────────────────────
@admin_routes.get('/logout', name="admin_logout")
async def admin_logout(request: Request, client_info: ClientInfo = Depends(get_client_info)):
    ip_address = client_info.ip_address
    
    if request.session.get('admin_logged_in'):
        log.info(action="admin_logout", trace_info=ip_address, message="Admin logged out", secure=False)
    
    # Use enhanced session clearing
    clear_user_session(request)
    return RedirectResponse(url='/admin/login', status_code=302)
