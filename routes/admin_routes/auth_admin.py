import os
from flask import render_template, request, redirect, url_for, session
from . import admin_routes

@admin_routes.route('/login', methods=['GET', 'POST'])
def login():
    # Force a clean slate any time someone lands on /admin/login
    session.clear()

    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
        ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "admin123")

        if username == ADMIN_USER and password == ADMIN_PASS:
            session['admin_logged_in'] = True
            session.permanent = False  # cookie dies on browser close
            return redirect(url_for('admin_routes.admin_dashboard'))
        else:
            error = "Invalid credentials"

    return render_template('admin/login.html', error=error)


@admin_routes.route('/logout')
def admin_logout():
    session.clear()  # actually clear the session
    return redirect(url_for('admin_routes.login'))
