import os
import json
from datetime import datetime
from flask import request, render_template, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from . import admin_routes
from logger import log_event

# ─── Compute project‐root‐relative upload folder ───────────
HERE         = os.path.dirname(__file__)                      # …/routes/admin_routes
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))# project root
EXAM_DIR     = os.path.join(PROJECT_ROOT, 'uploads', 'exam_results')
INDEX_FILE   = os.path.join(EXAM_DIR, 'index.json')

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

# Ensure folder and index.json exist
os.makedirs(EXAM_DIR, exist_ok=True)
if not os.path.exists(INDEX_FILE):
    with open(INDEX_FILE, 'w') as f:
        json.dump([], f)

def load_results():
    with open(INDEX_FILE, 'r') as f:
        return json.load(f)

def save_results(data):
    with open(INDEX_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@admin_routes.route('/exam_results', methods=['GET', 'POST'])
def exam_results():
    # auth
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    if request.method == 'POST':
        username    = request.form.get('username')
        password    = request.form.get('password')
        exam_date   = request.form.get('exam_date')
        exam_type   = request.form.get('exam_type')
        exam_class  = request.form.get('exam_class')
        file        = request.files.get('file')

        ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
        ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "admin123")

        if username != ADMIN_USER or password != ADMIN_PASS:
            flash("Unauthorized", "danger")
            return redirect(url_for('admin_routes.exam_results'))

        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(EXAM_DIR, filename)
            file.save(filepath)

            results = load_results()
            results.append({
                "filename":    filename,
                "exam_date":   exam_date,
                "exam_type":   exam_type,
                "exam_class":  exam_class,
                "uploaded_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            save_results(results)

            flash("Exam result uploaded.", "success")
            log_event("exam_uploaded", username, filename)
        else:
            flash("Invalid file format.", "warning")

        return redirect(url_for('admin_routes.exam_results'))

    # GET: show all together
    results = load_results()
    return render_template("admin/exam_results.html", results=results)


@admin_routes.route('/exam_results/delete/<filename>', methods=['POST'])
def delete_exam_result(filename):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    username = request.form.get('username')
    password = request.form.get('password')
    ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "admin123")
    if username != ADMIN_USER or password != ADMIN_PASS:
        flash("Unauthorized", "danger")
        return redirect(url_for('admin_routes.exam_results'))

    filepath = os.path.join(EXAM_DIR, filename)
    if os.path.exists(filepath):
        os.remove(filepath)

    results = load_results()
    results = [r for r in results if r['filename'] != filename]
    save_results(results)

    flash(f"Deleted {filename}.", "info")
    log_event("exam_deleted", username, filename)
    return redirect(url_for('admin_routes.exam_results'))
