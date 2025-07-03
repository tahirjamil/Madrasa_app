import os
import requests
from flask import render_template, request, redirect, url_for, session
from . import admin_routes
from config import Config

login_attempts = {}

@admin_routes.route('/login', methods=['GET', 'POST'])
def login():
    session.permanent = False
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
        username = request.form.get('username')
        password = request.form.get('password')

        ADMIN_USER = os.getenv("ADMIN_USERNAME")
        ADMIN_PASS = os.getenv("ADMIN_PASSWORD")

        session['login_attempts'] += 1

        # Only require captcha if keys exist
        if RECAPTCHA_SITE_KEY and RECAPTCHA_SECRET_KEY:
            if session['login_attempts'] >= 4:
                show_captcha = True

                recaptcha_response = request.form.get('g-recaptcha-response')
                if not recaptcha_response:
                    error = "Please complete the reCAPTCHA."
                    return render_template(
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
                    return render_template(
                        'admin/login.html',
                        error=error,
                        show_captcha=show_captcha,
                        site_key=RECAPTCHA_SITE_KEY
                    )

        if username == ADMIN_USER and password == ADMIN_PASS:
            session['admin_logged_in'] = True
            session.pop('login_attempts', None)  # Reset
            return redirect(url_for('admin_routes.admin_dashboard'))
        else:
            error = "Invalid credentials"

    return render_template(
        'admin/login.html',
        error=error,
        show_captcha=(RECAPTCHA_SITE_KEY and RECAPTCHA_SECRET_KEY and session.get('login_attempts', 0) >= 4),
        site_key=RECAPTCHA_SITE_KEY
    )

@admin_routes.route('/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_routes.login'))
