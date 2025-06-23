from flask import request, session, redirect, url_for, render_template
from . import admin_routes  # Use blueprint from __init__.py

@admin_routes.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == 'admin' and request.form['password'] == 'admin123':
            session.clear()
            session['admin_logged_in'] = True
            session.permanent = False
            return redirect(url_for('admin_routes.admin_dashboard'))
    return render_template('admin/login.html')

@admin_routes.route('/logout')
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_routes.login"))

def members():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))
    return render_template("admin/members.html")

def routine():

    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))
    return render_template("admin/members.html")