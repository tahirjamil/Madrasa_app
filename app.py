import os, time, logging
from datetime import datetime
from pathlib import Path
from quart import (
    Quart, render_template, request, session, g,
    send_from_directory, jsonify
)
from quart_cors import cors
from dotenv import load_dotenv
import socket, platform
from quart_babel import Babel

from config import Config
from database import create_tables
from database.database_utils import connect_to_db

# API & Web Blueprints
from helpers import is_maintenance_mode
from routes.admin_routes import admin_routes
from routes.user_routes import user_routes
from routes.web_routes import web_routes

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

app = Quart(__name__)
app = cors(app, allow_origin="*")
app.config.from_object(Config)

# Quart-Babel setup
app.config['BABEL_DEFAULT_LOCALE'] = 'en'
app.config['BABEL_DEFAULT_TIMEZONE'] = 'Asia/Dhaka'
babel = Babel(app)

# Locale selector for Babel
def get_locale():
    # Try to get language from request args, headers, or session
    return request.args.get('lang') or request.accept_languages.best_match(['en', 'bn', 'ar'])

# Set the locale selector
babel.localeselector = get_locale

# Import CSRF protection from dedicated module
from csrf_protection import csrf

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
logger.info(f"BASE_URL: {Config.BASE_URL}")
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
async def before_serving():
    # Set app start time for health checks
    app.start_time = time.time()
    
    # Create database tables if they don't exist
    await create_tables_async()
    
    # Create single database connection for server lifetime
    app.db = await connect_to_db()
    if app.db is None:
        raise RuntimeError("Failed to establish database connection")
    print("Database connection established successfully")

@app.after_serving
async def after_serving():
    # Close database connection when server shuts down
    if hasattr(app, 'db') and app.db:
        try:
            app.db.close()
            print("Database connection closed successfully")
        except Exception as e:
            print(f"Error closing database connection: {e}")

# ─── Request/Response Logging ───────────────────────────────
request_response_log = []
setattr(app, 'request_response_log', request_response_log)

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
        # Basic health check
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0",
            "uptime": time.time() - app.start_time if hasattr(app, 'start_time') else 0
        }
        
        # Check database connection
        try:
            from database.database_utils import get_db_connection
            conn = await get_db_connection()
            if conn:
                health_status["database"] = "connected"
                conn.close()
            else:
                health_status["database"] = "disconnected"
        except Exception as e:
            health_status["database"] = f"error: {str(e)}"
        
        # Check maintenance mode
        health_status["maintenance_mode"] = is_maintenance_mode()
        
        return jsonify(health_status), 200
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500
        
# ─── Register Blueprints ────────────────────────────────────
app.register_blueprint(admin_routes, url_prefix='/admin')
app.register_blueprint(web_routes)
app.register_blueprint(user_routes)
 
# Inject CSRF token into templates (for forms)
@app.context_processor
def inject_csrf_token():
    from csrf_protection import generate_csrf_token
    return dict(csrf_token=generate_csrf_token)

# ─── Run ────────────────────────────────────────────────────
if __name__ == "__main__":
    host, port = "0.0.0.0", 8000
    
    # Log startup configuration
    logger.info(f"Maintenance Mode: {'Enabled' if is_maintenance_mode() else 'Disabled'}")
    current_os = platform.system()
    try:
        if current_os == "Windows":
            logger.info("Starting development server (Quart) on Windows...")
            app.run(debug=True, host=host, port=port)
        else:
            logger.info("""Detected non-Windows OS. Please use Hypercorn to run the server, e.g.: venv/bin/hypercorn -w 4 -b 0.0.0.0:80 app:app or use-- python run_server.py""")
    except Exception as e:
        logger.critical(f"Server failed to start: {str(e)}", exc_info=True)
        raise
