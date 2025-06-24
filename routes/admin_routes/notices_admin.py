import os, json
from flask import request, render_template, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from datetime import datetime, date
from . import admin_routes
from config import Config
from logger import log_event

NOTICES_DIR = os.path.join('uploads', 'notices')
INDEX_FILE = os.path.join(NOTICES_DIR, 'index.json')
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'png', 'jpg', 'jpeg'}

os.makedirs(NOTICES_DIR, exist_ok=True)
if not os.path.exists(INDEX_FILE):
    with open(INDEX_FILE, 'w') as f:
        json.dump([], f)


def load_notices():
    try:
        with open(INDEX_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        # auto-fix broken JSON
        with open(INDEX_FILE, 'w') as f:
            json.dump([], f)
        return []


def save_notices(data):
    with open(INDEX_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@admin_routes.route('/notice', methods=['GET', 'POST'])
def notice_page():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        target_date = request.form.get('target_date')
        file = request.files.get('file')

        ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
        ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "admin123")

        if username != ADMIN_USER or password != ADMIN_PASS:
            flash("Unauthorized", "danger")
            return redirect(url_for('admin_routes.notice_page'))

        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(NOTICES_DIR, filename)
            file.save(filepath)

            notices = load_notices()
            notices.append({
                "filename": filename,
                "target_date": target_date,
                "uploaded_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            save_notices(notices)

            flash("Notice uploaded.", "success")
            log_event("notice_uploaded", username, filename)
        else:
            flash("Invalid file format.", "warning")

        return redirect(url_for('admin_routes.notice_page'))

    notices = load_notices()
    today = date.today()
    upcoming, ongoing, past = [], [], []

    for n in notices:
        try:
            n_date = datetime.strptime(n['target_date'], '%Y-%m-%d').date()
            if n_date > today:
                upcoming.append(n)
            elif n_date == today:
                ongoing.append(n)
            else:
                past.append(n)
        except Exception:
            past.append(n)

    return render_template("admin/notice.html",
                           upcoming=upcoming,
                           ongoing=ongoing,
                           past=past)


@admin_routes.route('/notice/delete/<filename>', methods=['POST'])
def delete_notice(filename):
    username = request.form.get('username')
    password = request.form.get('password')

    ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "admin123")

    if username != ADMIN_USER or password != ADMIN_PASS:
        flash("Unauthorized", "danger")
        return redirect(url_for('admin_routes.notice_page'))

    filepath = os.path.join(NOTICES_DIR, filename)
    if os.path.exists(filepath):
        os.remove(filepath)

    notices = load_notices()
    notices = [n for n in notices if n['filename'] != filename]
    save_notices(notices)

    flash(f"Notice '{filename}' deleted.", "info")
    log_event("notice_deleted", username, filename)
    return redirect(url_for('admin_routes.notice_page'))
