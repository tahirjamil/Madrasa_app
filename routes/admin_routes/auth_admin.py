import requests
from datetime import datetime
from quart import render_template, request, redirect, url_for, session, flash
from . import admin_routes
from config import Config
from functools import wraps
from helpers import is_test_mode, rate_limit

login_attempts = {}

# CSRF validation
async def validate_csrf_token():
    """Validate CSRF token from form data"""
    from csrf_protection import validate_csrf_token
    form = await request.form
    token = form.get('csrf_token')
    if not validate_csrf_token(token):
        await flash("CSRF token validation failed. Please try again.", "danger")
        return False
    return True

def require_csrf(f):
    """Decorator to require CSRF validation for POST requests"""
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if request.method == 'POST':
            if not await validate_csrf_token():
                return redirect(request.url)
        return await f(*args, **kwargs)
    return decorated_function

@admin_routes.route('/login', methods=['GET', 'POST'])
@require_csrf
@rate_limit(max_requests=5, window=300)  # 5 attempts per 5 minutes for admin security
async def login():

    # See for test mode
    test = True if is_test_mode() else False

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
    RECAPTCHA_SITE_KEY = Config.RECAPTCHA_SITE_KEY
    RECAPTCHA_SECRET_KEY = Config.RECAPTCHA_SECRET_KEY

    if request.method == 'POST':
        form = await request.form
        username = form.get('username')
        password = form.get('password')

        ADMIN_USER = Config.ADMIN_USERNAME
        ADMIN_PASS = Config.ADMIN_PASSWORD

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
                r = requests.post(verify_url, data=payload)
                result = r.json()

                if not result.get('success'):
                    error = "Invalid reCAPTCHA. Please try again."
                    return await render_template(
                        'admin/login.html',
                        error=error,
                        show_captcha=show_captcha,
                        site_key=RECAPTCHA_SITE_KEY
                    )

        if (username == ADMIN_USER and password == ADMIN_PASS) or test:
            session['admin_logged_in'] = True
            session['admin_login_time'] = datetime.now().isoformat()
            session.pop('login_attempts', None)  # Reset
            return redirect(url_for('admin_routes.admin_dashboard'))
        else:
            error = "Invalid credentials"

    return await render_template(
        'admin/login.html',
        error=error,
        show_captcha=(RECAPTCHA_SITE_KEY and RECAPTCHA_SECRET_KEY and session.get('login_attempts', 0) >= 4),
        site_key=RECAPTCHA_SITE_KEY
    )

@admin_routes.route('/logout')
async def admin_logout():
    session.clear()
    return redirect(url_for('admin_routes.login'))
