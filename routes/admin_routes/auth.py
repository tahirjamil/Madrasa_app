from flask import request, session, redirect, url_for, render_template
from . import admin_routes  # Use blueprint from __init__.py

@admin_routes.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == 'admin' and request.form['password'] == 'admin123':
            session['admin_logged_in'] = True
            return redirect(url_for('admin_routes.admin_dashboard'))
    return render_template("admin/login.html")

@admin_routes.route('/logout')
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_routes.login"))