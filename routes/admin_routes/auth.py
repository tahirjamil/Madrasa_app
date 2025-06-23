from flask import session, redirect, url_for, request, render_template

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'

def login_required(view_func):
    def wrapped_view(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('admin.login', next=request.path))
        return view_func(*args, **kwargs)
    wrapped_view.__name__ = view_func.__name__
    return wrapped_view

def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            next_page = request.args.get('next') or url_for('admin.dashboard')
            return redirect(next_page)
        return render_template('admin/login.html', error='Invalid credentials')
    return render_template('admin/login.html')

def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin.login'))
