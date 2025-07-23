import os
import logging
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
import socket
import platform
from flask_wtf.csrf import CSRFError

from config import Config
from database import create_tables

# API & Web Blueprints
from helpers import is_maintenance_mode
from routes.admin_routes import admin_routes
from routes.user_routes import user_routes
from routes.web_routes import web_routes

# ─── Setup Logging ──────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('debug.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ─── App Setup ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent

dev_env = BASE_DIR / "dev.env"
env = BASE_DIR / ".env"

# load development
dev_mode = False
if dev_env.is_file():
    dev_mode = True
    logger.info("Running in development mode")
else:
    logger.info("Running in production mode")

load_dotenv(env)

app = Flask(__name__)
CORS(app)
app.config.from_object(Config)

# Log important configuration
logger.info(f"BASE_URL: {Config.BASE_URL}")
logger.info(f"Host IP: {socket.gethostbyname(socket.gethostname())}")
logger.info(f"CORS enabled: {bool(CORS)}")

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
    try:
        create_tables()
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}")

# ─── Request/Response Logging ───────────────────────────────
request_response_log = []

# expose it so blueprints can read it via current_app.request_response_log
setattr(app, 'request_response_log', request_response_log)

@app.before_request
def log_every_request():
    # Log request details
    logger.debug(f"Incoming request: {request.method} {request.path}")
    logger.debug(f"Headers: {dict(request.headers)}")
    logger.debug(f"Remote addr: {request.remote_addr}")
    logger.debug(f"X-Forwarded-For: {request.headers.get('X-Forwarded-For')}")

    # don't log the client‐side poll
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
    # Log response details
    logger.debug(f"Response status: {response.status}")
    logger.debug(f"Response headers: {dict(response.headers)}")
    
    entry = getattr(g, "log_entry", None)
    if entry:
        if response.content_type and response.content_type.startswith("application/json"):
            try:
                entry["res_json"] = response.get_json(silent=True)
            except Exception as e:
                logger.error(f"Error parsing JSON response: {str(e)}")
                entry["res_json"] = None
        else:
            entry["res_json"] = None
    return response

@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"Unhandled exception: {str(e)}", exc_info=True)
    return jsonify({
        "error": "Internal server error",
        "message": str(e)
    }), 500

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    logger.warning(f"CSRF error: {e.description}")
    return render_template('admin/csrf_error.html', reason=e.description), 400

# ─── Public Routes ──────────────────────────────────────────
@app.route("/donate")
def donate():
    return render_template("donate.html", current_year=datetime.now().year)

@app.route("/")
def home():
    return render_template("home.html", current_year=datetime.now().year)

@csrf.exempt
# ─── Error & Favicon ────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    logger.warning(f"404 error: {request.path}")
    return render_template('404.html'), 404

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )

# ─── Health Check ───────────────────────────────────────────
@app.route('/health')
def health_check():
    try:
        # Check database connection
        with app.app_context():
            create_tables()  # This will try to connect to the database
        
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "environment": "development" if dev_mode else "production",
            "host_ip": socket.gethostbyname(socket.gethostname()),
            "base_url": Config.BASE_URL
        })
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

# ─── Remote Restart Endpoint ───────────────────────────────
@app.route('/restart', methods=['POST'])
@require_secret
def restart_server():
    logger.warning("Remote restart triggered via /restart endpoint!")
    # Optionally, add more logging or notification here
    os._exit(0)  # Process manager (systemd, supervisor, Docker) should restart the app

# ─── Register Blueprints ────────────────────────────────────
app.register_blueprint(admin_routes, url_prefix='/admin')
app.register_blueprint(web_routes)
app.register_blueprint(user_routes)

csrf.exempt(user_routes)

# ─── Run ────────────────────────────────────────────────────
if __name__ == "__main__":
    host, port = "0.0.0.0", 8000
    
    # Log startup configuration
    logger.info(f"Maintenance Mode: {'Enabled' if is_maintenance_mode() else 'Disabled'}")

    current_os = platform.system()
    try:
        if current_os == "Windows":
            if dev_mode:
                logger.info("Starting development server (Flask) on Windows...")
                app.run(debug=True, host=host, port=port)
            else:
                logger.info(f"Starting production server (Waitress) on Windows on port {port}")
                logger.info(f"Quick logs available at {Config.BASE_URL}/admin/info")
                serve(app, host=host, port=port)
        else:
            # On Linux or other OS, do not start a server here. Expect Gunicorn to be used.
            logger.info("Detected non-Windows OS. Please use Gunicorn to run the server, e.g.: gunicorn -w 4 -b 0.0.0.0:8000 app:app")
    except Exception as e:
        logger.critical(f"Server failed to start: {str(e)}", exc_info=True)
        raise
