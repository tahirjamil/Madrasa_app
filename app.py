import os
from datetime import datetime
from pathlib import Path
from functools import wraps
from flask import (
    Flask, render_template, request, session, g,
    send_from_directory, jsonify
)
from flask_cors import CORS
from flask_wtf import CSRFProtect
from dotenv import load_dotenv
from waitress import serve

from config import Config
from database import create_tables

# API & Web Blueprints
from routes.user_routes import user_routes
from routes.admin_routes import admin_routes

# ─── App Setup ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent

dev_env = BASE_DIR / "dev.env"
env = BASE_DIR / ".env"

# load the correct .env
if dev_env.is_file():
    load_dotenv(dev_env, override=True)
else:
    load_dotenv(env)

app = Flask(__name__)
CORS(app)
app.config.from_object(Config)

RESTART_KEY = os.getenv("RESTART_KEY", "fallback-key")

csrf = CSRFProtect()
csrf.init_app(app)

def require_secret(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.headers.get("RESTART-KEY") != RESTART_KEY:
            return jsonify({"message": "Unauthorized"}), 403
        return f(*args, **kwargs)
    return wrapper

# ensure upload folder exists
os.makedirs(app.config['IMG_UPLOAD_FOLDER'], exist_ok=True)

with app.app_context():
    create_tables()

# ─── Request/Response Logging ───────────────────────────────
request_response_log = []

# expose it so blueprints can read it via current_app.request_response_log
setattr(app, 'request_response_log', request_response_log)

@app.before_request
def log_every_request():
    # don’t log the client‐side poll
    if request.endpoint == "admin_routes.info_data_admin":
        return

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
        "req_json": request.get_json(silent=True),
        "res_json": None,
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

# ─── Public Routes ──────────────────────────────────────────
@app.route("/donate")
def donate():
    return render_template("donate.html", current_year=datetime.now().year)

@app.route("/")
def home():
    return render_template("home.html", current_year=datetime.now().year)

@csrf.exempt
@app.route("/restart", methods=["POST"])
@require_secret
def restart_service():
    try:
        print("Restart endpoint hit, trying to restart...")
        result = os.system("sudo systemctl restart madrasa-app.service")
        print(f"System call result: {result}")
        return jsonify({"message": "Service restarted"}), 200
    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500

# ─── Error & Favicon ────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )

# ─── Register Blueprints ────────────────────────────────────
app.register_blueprint(user_routes)
app.register_blueprint(admin_routes, url_prefix='/admin')

csrf.exempt(user_routes)
csrf.exempt(admin_routes)

# ─── Run ────────────────────────────────────────────────────
if __name__ == "__main__":
    env_flag = os.environ.get("FLASK_ENV")
    host, port = "0.0.0.0", 8000

    if env_flag == "development":
        app.run(debug=True, host=host, port=port)
    else:
        restart_cmd = 'curl -X POST http://(your-domain)/restart -H "RESTART-KEY: (your-restart-key)"'
        # production
        port = 80
        URL = Config.BASE_URL
        print(f"Quick logs available at {URL}/admin/info")
        print(f"restart though: {restart_cmd}")
        serve(app, host=host, port=port)
