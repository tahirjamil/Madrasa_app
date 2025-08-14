import os, time, logging
from datetime import datetime, timezone
from pathlib import Path
from quart import (
    Response, render_template, request, session, g,
    send_from_directory, jsonify
)
from quart_cors import cors
from dotenv import load_dotenv
from quart_babel import Babel
import socket

from config import config, MadrasaConfig, MadrasaApp
from database import create_tables
from database.database_utils import connect_to_db
from keydb.keydb_utils import connect_to_keydb, close_keydb
from observability.otel_setup import init_otel
from observability.asgi_middleware import RequestTracingMiddleware

# API & Web Blueprints
from utils.helpers import get_system_health, initialize_application, metrics_collector, rate_limiter, security_manager
from routes.admin_routes import admin_routes
from routes.api import api
from routes.web_routes import web_routes

# ─── Validate Environment Variables ─────────────────────────
from utils.env_validator import validate_environment
if not validate_environment():
    import sys
    print("❌ Application startup aborted due to environment validation failures")
    sys.exit(1)

# ─── Setup Logging ──────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('debug.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ─── App Setup ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent

env = BASE_DIR / ".env"

# load development

load_dotenv(env)

app = MadrasaApp(__name__)
app = cors(app, allow_origin="*")
app.config.from_object(MadrasaConfig)

# Quart-Babel setup
app.config['BABEL_DEFAULT_LOCALE'] = 'en'
app.config['BABEL_DEFAULT_TIMEZONE'] = 'Asia/Dhaka'
babel = Babel(app)

# Locale selector for Babel
async def get_locale():
    json_data = await request.get_json(silent=True)
    return (
        request.args.get('lang')
        or request.accept_languages.best_match(['en', 'bn', 'ar'])
        or (json_data or {}).get('lang')
    )

babel.localeselector = get_locale

# Import CSRF protection from dedicated module
from utils.csrf_protection import csrf

# Wrap ASGI app with tracing middleware only if OTEL is enabled
if getattr(config, 'OTEL_ENABLED', True):
    app.asgi_app = RequestTracingMiddleware(app.asgi_app)

# Security headers
@app.after_request
async def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

# Log important configuration
logger.info(f"BASE_URL: {config.BASE_URL}")
logger.info(f"Host IP: {socket.gethostbyname(socket.gethostname())}")
logger.info(f"CORS enabled: True (quart_cors)")

# ensure upload folder exists
os.makedirs(app.config['PROFILE_IMG_UPLOAD_FOLDER'], exist_ok=True)

async def create_tables_async():
    try:
        await create_tables()
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}")

@app.before_serving
async def startup():
    # Set app start time for health checks
    app.start_time = time.time()

    # Initialize observability (traces/metrics) only if enabled
    if getattr(config, 'OTEL_ENABLED', True):
        init_otel(
            service_name="madrasa-app",
            environment="development",
            service_version=getattr(config, 'SERVER_VERSION', '0.0.0')
        )

    initialize_application()
    await create_tables_async()
    # Create single database connection for server lifetime
    app.db = await connect_to_db()
    app.keydb = await connect_to_keydb()
    if app.db is None:
        raise RuntimeError("Failed to establish database connection")
    print("Database connection established successfully")

@app.after_serving
async def shutdown():
    # Close database connection when server shuts down
    if hasattr(app, 'db') and app.db:
        try:
            app.db.close()
            print("Database connection closed successfully")
        except Exception as e:
            print(f"Error closing database connection: {e}")
    if hasattr(app, 'keydb') and app.keydb:
        try:
            await close_keydb(app.keydb)
            print("Keydb connection closed successfully")
        except Exception as e:
            print(f"Error closing keydb connection: {e}")

# ─── Request/Response Logging ───────────────────────────────
request_response_log = []
setattr(app, 'request_response_log', request_response_log)

@app.before_request
async def block_xss_inputs():
    """Block requests containing obvious XSS indicators in args, form, or JSON."""
    try:
        # Check query parameters
        for value in request.args.values():
            if isinstance(value, str) and security_manager.detect_xss(value):
                logger.warning(f"Blocked potential XSS via query params: {request.path}")
                return jsonify({"error": "Invalid input"}), 400

        # Check form data (if present)
        try:
            form = await request.form
        except Exception:
            form = None
        if form:
            for value in form.values():
                if isinstance(value, str) and security_manager.detect_xss(value):
                    logger.warning(f"Blocked potential XSS via form data: {request.path}")
                    return jsonify({"error": "Invalid input"}), 400

        # Check JSON payload (if present)
        json_data = await request.get_json(silent=True)

        def _contains_xss(obj):
            if isinstance(obj, str):
                return security_manager.detect_xss(obj)
            if isinstance(obj, dict):
                return any(_contains_xss(v) for v in obj.values())
            if isinstance(obj, (list, tuple, set)):
                return any(_contains_xss(v) for v in obj)
            return False

        if json_data and _contains_xss(json_data):
            logger.warning(f"Blocked potential XSS via JSON body: {request.path}")
            return jsonify({"error": "Invalid input"}), 400
    except Exception as e:
        # Fail-safe: never break requests due to guard errors
        logger.error(f"XSS guard error: {str(e)}")
        return None

@app.before_request
async def log_every_request():
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
        "req_json": await request.get_json(silent=True),
        "res_json": None,
    }
    g.log_entry = entry
    request_response_log.append(entry)
    if len(request_response_log) > 100:
        request_response_log.pop(0)

@app.after_request
async def attach_response_data(response):
    logger.debug(f"Response status: {response.status}")
    logger.debug(f"Response headers: {dict(response.headers)}")
    entry = getattr(g, "log_entry", None)
    if entry:
        if response.content_type and response.content_type.startswith("application/json"):
            try:
                entry["res_json"] = await response.get_json(silent=True)
            except Exception as e:
                logger.error(f"Error parsing JSON response: {str(e)}")
                entry["res_json"] = None
        else:
            entry["res_json"] = None
    return response

@app.errorhandler(Exception)
async def handle_exception(e):
    logger.error(f"Unhandled exception: {str(e)}", exc_info=True)
    return jsonify({
        "error": "Internal server error",
        "message": str(e)
    }), 500

# ─── Error & Favicon ────────────────────────────────────────
# CSRF error handler
@app.errorhandler(404)
async def not_found(e):
    logger.warning(f"404 error: {request.path}")
    return await render_template('404.html'), 404

@app.errorhandler(400)
async def csrf_error(e):
    if "CSRF" in str(e):
        logger.warning(f"CSRF error: {request.path}")
        return await render_template('admin/csrf_error.html', reason=str(e)), 400
    return jsonify({"error": "Bad request"}), 400

@app.route('/favicon.ico')
async def favicon():
    return await send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )

@app.route('/health')
async def health_check():
    """Health check endpoint for monitoring"""
    try:
        # Advanced health check
        health_status = await get_system_health()

        # Extra health check
        health_status.update({
            "uptime": time.time() - app.start_time if hasattr(app, 'start_time') else 0
        })

        return jsonify(health_status), 200
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "unknown",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/metrics')
async def get_metrics() -> Response:
    """Metrics endpoint placeholder (metrics moved to OpenTelemetry)."""
    return jsonify({
        "message": "Metrics are exported via OpenTelemetry (OTLP).",
        "rate_limiter_size": len(rate_limiter._requests),
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
        
# ─── Register Blueprints ────────────────────────────────────
app.register_blueprint(admin_routes, url_prefix='/admin')
app.register_blueprint(web_routes)
app.register_blueprint(api)
 
# Inject CSRF token into templates (for forms)
@app.context_processor
def inject_csrf_token():
    from utils.csrf_protection import generate_csrf_token
    return dict(csrf_token=generate_csrf_token)

# ─── Note ───────────────────────────────────────────────────
# This app should be run using: python run_server.py
# The run_server.py script provides proper process management,
# health checking, and production-ready server configuration.
