import os
from datetime import datetime
from flask import Flask, render_template, request, session, g, redirect, url_for
from flask_cors import CORS
from dotenv import load_dotenv
from waitress import serve
from config import Config
from database import create_tables
# API & Web Blueprints
from routes.api.auth import api_auth_routes
from routes.api.payments import payment_routes
from routes.api.additionals import other_routes
from routes.admin_routes import admin_routes

# ─── App Setup ──────────────────────────────────────────────
load_dotenv()
app = Flask(__name__)
CORS(app)
app.config.from_object(Config)
app.secret_key = os.getenv("SECRET_KEY", "fallback-key")

# ensure upload folder exists
os.makedirs(app.config['IMG_UPLOAD_FOLDER'], exist_ok=True)

with app.app_context():
    create_tables()

# ─── Request/Response Logging ───────────────────────────────
request_response_log = []
@app.before_request
def log_every_request():
    ip       = request.headers.get("X-Forwarded-For", request.remote_addr)
    endpoint = request.endpoint or "unknown"
    blocked  = endpoint.startswith("admin_routes.") and not session.get("admin_logged_in")

    entry = {
        "time":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ip":       ip,
        "endpoint": endpoint,
        "status":   "Blocked" if blocked else "Allowed",
        "method":   request.method,
        "path":     request.path,
        "req_json": request.get_json(silent=True),  # always present
        "res_json": None,                            # always present
    }
    g.log_entry = entry
    request_response_log.append(entry)
    if len(request_response_log) > 100:
        request_response_log.pop(0)

@app.after_request
def attach_response_data(response):
    entry = getattr(g, "log_entry", None)
    if entry:
        if response.content_type.startswith("application/json"):
            try:
                entry["res_json"] = response.get_json(silent=True)
            except Exception:
                entry["res_json"] = None
        else:
            entry["res_json"] = None
    return response

# ─── Status & Info Routes ───────────────────────────────────
@app.route("/status")
def status():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))
    return render_template("status.html", requests=request_response_log)

@app.route("/info")
def info():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))
    logs = request_response_log[-100:]
    return render_template("info.html", logs=logs)

# ─── Error & Favicon ────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.route('/favicon.ico')
def favicon():
    return '', 204

# ─── Register Blueprints ────────────────────────────────────
app.register_blueprint(api_auth_routes)
app.register_blueprint(payment_routes)
app.register_blueprint(other_routes)
app.register_blueprint(admin_routes, url_prefix='/admin')

@app.route("/")
def home():
    return render_template("home.html", current_year=datetime.now().year)

# ─── Run ────────────────────────────────────────────────────
if __name__ == "__main__":
    URL = "http://localhost:8000/"

    if os.environ.get("FLASK_ENV") == "development":
        print("Starting Flask dev server at http://0.0.0.0 with port:8000")
        print(f"You can check server status at {URL}status or logs at {URL}info")
        app.run(debug=True, host="0.0.0.0", port=8000)
    else:
        print("Starting production server with Waitress at http://0.0.0.0 with port:8000")
        print(f"You can check server status at {URL}status or logs at {URL}info")
        serve(app, host="0.0.0.0", port=8000)
