import asyncio
import requests
from datetime import datetime
from quart import render_template, request, redirect, url_for, session, flash
from . import admin_routes
from config import config
from utils.helpers.helpers import rate_limit, require_csrf, get_client_info
from utils.helpers.logger import log

# Note: Login attempt tracking moved to session-based approach
# The global dictionary approach was removed as unused

@admin_routes.route('/login', methods=['GET', 'POST'])
@require_csrf
@rate_limit(max_requests=50, window=300)
async def login():

    # See for test mode
    test = True if config.is_testing() else False

    # Set session to expire after configured time
    session.permanent = True
    
    # Clear session on GET
    if request.method == 'GET':
        session.clear()

    # Initialize attempt counter
    if 'login_attempts' not in session:
        session['login_attempts'] = 0

    error = None
    show_captcha = False

    # Load keys safely
    RECAPTCHA_SITE_KEY = config.RECAPTCHA_SITE_KEY
    RECAPTCHA_SECRET_KEY = config.RECAPTCHA_SECRET_KEY

    if request.method == 'POST':
        form = await request.form
        username = form.get('username')
        password = form.get('password')
        
        # Get client info for logging
        client_info = await get_client_info() or {}
        ip_address = client_info.get("ip_address", "unknown")

        ADMIN_USER = config.ADMIN_USERNAME
        ADMIN_PASS = config.ADMIN_PASSWORD

        session['login_attempts'] += 1

        # Only require captcha if keys exist
        if RECAPTCHA_SITE_KEY and RECAPTCHA_SECRET_KEY:
            if session['login_attempts'] >= 4:
                show_captcha = True

                recaptcha_response = form.get('g-recaptcha-response')
                if not recaptcha_response:
                    error = "Please complete the reCAPTCHA."
                    return await render_template(
                        'admin/login.html',
                        error=error,
                        show_captcha=show_captcha,
                        site_key=RECAPTCHA_SITE_KEY
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
                    return await render_template(
                        'admin/login.html',
                        error=error,
                        show_captcha=show_captcha,
                        site_key=RECAPTCHA_SITE_KEY
                    )

        # SECURITY: In production, don't allow test bypass
        if test and config.is_development():
            # Only allow test bypass in development mode
            if username == ADMIN_USER and password == ADMIN_PASS:
                session['admin_logged_in'] = True
                session['admin_login_time'] = datetime.now().isoformat()
                session.pop('login_attempts', None)  # Reset
                log.info(action="admin_login_test", trace_info=ip_address, message="Admin logged in (test mode)", secure=False)
                return redirect(url_for('admin_routes.admin_dashboard'))
        else:
            # Production mode - strict authentication
            if username == ADMIN_USER and password == ADMIN_PASS:
                session['admin_logged_in'] = True
                session['admin_login_time'] = datetime.now().isoformat()
                session.pop('login_attempts', None)  # Reset
                log.info(action="admin_login_success", trace_info=ip_address, message=f"Admin {username} logged in", secure=False)
                return redirect(url_for('admin_routes.admin_dashboard'))
            
        error = "Invalid credentials"
        log.warning(action="admin_login_failed", trace_info=ip_address, message=f"Failed login attempt for: {username}", secure=False)

    return await render_template(
        'admin/login.html',
        error=error,
        show_captcha=(RECAPTCHA_SITE_KEY and RECAPTCHA_SECRET_KEY and session.get('login_attempts', 0) >= 4),
        site_key=RECAPTCHA_SITE_KEY
    )

@admin_routes.route('/logout')
async def admin_logout():
    # Get client info for logging
    client_info = await get_client_info() or {}
    ip_address = client_info.get("ip_address", "unknown")
    
    if session.get('admin_logged_in'):
        log.info(action="admin_logout", trace_info=ip_address, message="Admin logged out", secure=False)
    
    session.clear()
    return redirect(url_for('admin_routes.login'))
