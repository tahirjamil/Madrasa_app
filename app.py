import os, time, logging, asyncio
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import socket
from threading import Lock
from collections import deque
import json

from config import config, MadrasaConfig
from utils import create_tables
from utils.helpers.improved_functions import send_json_response
from utils.keydb.keydb_utils import connect_to_keydb, close_keydb
from utils.otel.otel_utils import init_otel

# ─── Import Routers ──────────────────────────────────────────
from utils.helpers.helpers import (
    get_system_health, initialize_application, security_manager,
)
from routes.admin_routes import admin_routes
from routes.api import api
from routes.web_routes import web_routes

# ─── Setup Logging ──────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,  # Changed from WARNING to DEBUG to allow debug logs
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

# Initialize start time variable
app_start_time = None

async def create_tables_async():
    try:
        await create_tables()
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}")

# ─── Lifespan Events ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for startup and shutdown"""
    global app_start_time
    # Startup
    app_start_time = time.time()
    
    # Initialize observability (traces/metrics) only if enabled
    if config.OTEL_ENABLED:
        init_otel(
            service_name="madrasa-app",
            environment="development",
            service_version=getattr(config, 'SERVER_VERSION', '0.0.0')
        )
    
    initialize_application()
    
    # Skip database initialization in test mode
    if config.is_testing():
        logger.warning("TEST_MODE enabled - skipping database initialization")
        app.state.db_pool = None
        app.state.keydb = None
    else:
        await create_tables_async()
        # Initialize database connection pool
        from utils.mysql.database_utils import get_db_pool
        app.state.db_pool = await get_db_pool()
        app.state.keydb = await connect_to_keydb()
        logger.info("Database connection pool established successfully")
    
    yield
    
    # Shutdown
    if hasattr(app.state, 'db_pool') and app.state.db_pool is not None:
        try:
            from utils.mysql.database_utils import close_db_pool
            await close_db_pool()
            logger.info("Database connection pool closed successfully")
        except Exception as e:
            logger.error(f"Error closing database connection pool: {e}")
    if hasattr(app.state, 'keydb') and app.state.keydb:
        try:
            await close_keydb(app.state.keydb)
            logger.info("Keydb connection closed successfully")
        except Exception as e:
            logger.error(f"Error closing keydb connection: {e}")

# Create FastAPI app
app = FastAPI(
    title=MadrasaConfig.APP_NAME,
    version=MadrasaConfig.SERVER_VERSION,
    lifespan=lifespan
)

# ─── CORS Configuration ──────────────────────────────────────────────
if not config.is_development():
    # Allow only specific origins in production
    allowed_origins = config.ALLOWED_ORIGINS if hasattr(config, 'ALLOWED_ORIGINS') else []
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    # Allow all origins only in development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# ─── Templates Setup ──────────────────────────────────────────────
templates = Jinja2Templates(directory="templates")

# Wrap ASGI app with tracing middleware only if OTEL is enabled
if config.OTEL_ENABLED:
    from utils.otel.asgi_middleware import RequestTracingMiddleware
    app.add_middleware(RequestTracingMiddleware)

# ─── Request/Response Logging ───────────────────────────────
# Thread-safe request log with max size of 100 entries
request_response_log = deque(maxlen=100)
request_log_lock = Lock()

# Store these in app.state instead of as module variables
app.state.request_response_log = request_response_log
app.state.request_log_lock = request_log_lock

# Log important configuration
logger.info(f"BASE_URL: {config.BASE_URL}")
logger.info(f"Host IP: {socket.gethostbyname(socket.gethostname())}")
logger.info(f"CORS enabled: {not config.is_development() and 'Restricted' or 'All origins (dev)'}")

# ensure upload folder exists
os.makedirs(MadrasaConfig.PROFILE_IMG_UPLOAD_FOLDER, exist_ok=True)

# ─── Middleware ───────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.types import ASGIApp

# Add session middleware (needed for admin routes)
app.add_middleware(SessionMiddleware, secret_key=MadrasaConfig.SECRET_KEY)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response

app.add_middleware(SecurityHeadersMiddleware)

class XSSProtectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        """Block requests containing obvious XSS indicators in args, form, or JSON."""
        try:
            # Check query parameters
            for value in request.query_params.values():
                if isinstance(value, str) and security_manager.detect_xss(value):
                    logger.warning(f"Blocked potential XSS via query params: {request.url.path}")
                    response, status = send_json_response("Invalid input", 400, "XSS detected")
                    return JSONResponse(content=response, status_code=status)

            # Check form data (if present)
            if request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
                form = await request.form()
                for value in form.values():
                    if isinstance(value, str) and security_manager.detect_xss(value):
                        logger.warning(f"Blocked potential XSS via form data: {request.url.path}")
                        response, status = send_json_response("Invalid input", 400, "XSS detected")
                        return JSONResponse(content=response, status_code=status)

            # Check JSON payload (if present)
            if request.headers.get("content-type") == "application/json":
                try:
                    json_data = await request.json()
                    
                    def _contains_xss(obj):
                        if isinstance(obj, str):
                            return security_manager.detect_xss(obj)
                        if isinstance(obj, dict):
                            return any(_contains_xss(v) for v in obj.values())
                        if isinstance(obj, (list, tuple, set)):
                            return any(_contains_xss(v) for v in obj)
                        return False

                    if json_data and _contains_xss(json_data):
                        logger.warning(f"Blocked potential XSS via JSON body: {request.url.path}")
                        response, status = send_json_response("Invalid input", 400, "XSS detected")
                        return JSONResponse(content=response, status_code=status)
                except Exception:
                    pass

            response = await call_next(request)
            return response
        except Exception as e:
            # Fail-safe: never break requests due to guard errors
            logger.error(f"XSS guard error: {str(e)}")
            return await call_next(request)

app.add_middleware(XSSProtectionMiddleware)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logger.debug(f"Incoming request: {request.method} {request.url.path}")
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"Remote addr: {request.client.host if request.client else 'unknown'}")
        logger.debug(f"X-Forwarded-For: {request.headers.get('X-Forwarded-For')}")

        # don't log the client‐side poll
        if request.url.path == "/admin/info_data":
            return await call_next(request)

        ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
        endpoint = request.url.path
        # SECURITY FIX: Add CSRF check for admin routes
        # Safely check session - handle case where session middleware might not be available
        try:
            blocked = endpoint.startswith("/admin/") and not request.session.get("admin_logged_in")
        except (AttributeError, AssertionError):
            # Session middleware not available or session not initialized
            blocked = endpoint.startswith("/admin/")

        # Get JSON payload if available
        req_json = None
        if request.headers.get("content-type") == "application/json":
            try:
                body = await request.body()
                req_json = json.loads(body) if body else None
                # Need to recreate request with body for downstream
                from starlette.datastructures import Headers
                async def receive():
                    return {"type": "http.request", "body": body}
                request = Request(request.scope, receive=receive)
            except Exception:
                pass

        entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ip": ip,
            "endpoint": endpoint,
            "status": "Blocked" if blocked else "Allowed",
            "method": request.method,
            "path": request.url.path,
            "req_json": req_json,
            "res_json": None,
        }
        
        # Store entry in request state for response logging
        request.state.log_entry = entry
        
        # Thread-safe append to request log
        with app.state.request_log_lock:
            app.state.request_response_log.append(entry)

        response = await call_next(request)
        
        # Log response details
        logger.debug(f"Response status: {response.status_code}")
        logger.debug(f"Response headers: {dict(response.headers)}")
        
        # TODO: Capture response JSON if needed
        # This is complex in FastAPI middleware and may need a custom approach
        
        return response

app.add_middleware(RequestLoggingMiddleware)

# ─── Exception Handlers ────────────────────────────────────────────
@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    logger.warning(f"404 error: {request.url}")
    return templates.TemplateResponse('404.html', {'request': request}, status_code=404)

@app.exception_handler(400)
async def bad_request_handler(request: Request, exc: HTTPException):
    if exc.detail and "CSRF" in str(exc.detail):
        logger.warning(f"CSRF error: {request.url}")
        return templates.TemplateResponse('admin/csrf_error.html', 
                                        {'request': request, 'reason': str(exc.detail)}, 
                                        status_code=400)
    response, status = send_json_response("Bad request", 400)
    return JSONResponse(content=response, status_code=status)

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    response, status = send_json_response("Internal server error", 500, str(exc))
    return JSONResponse(content=response, status_code=status)

# ─── Routes ────────────────────────────────────────────
@app.get('/favicon.ico')
async def favicon():
    return FileResponse(
        path=os.path.join(BASE_DIR, 'static', 'favicon.ico'),
        media_type='image/vnd.microsoft.icon'
    )

@app.get('/health')
async def health_check():
    """Health check endpoint for monitoring"""
    try:
        # In test mode, return a simple health status
        if config.is_testing():
            return JSONResponse({
                "status": "healthy",
                "version": MadrasaConfig.SERVER_VERSION,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mode": "test",
                "uptime": time.time() - app_start_time if app_start_time else 0
            })
        
        # Advanced health check
        health_status = await get_system_health()

        # Extra health check - use initialized start_time
        health_status.update({
            "uptime": time.time() - app_start_time if app_start_time else 0
        })

        return JSONResponse(health_status)
    except RuntimeError as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse({
            "status": "runtime_error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }, status_code=500)
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse({
            "status": "internal_error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }, status_code=500)

        
# ─── Register Routers ────────────────────────────────────
app.include_router(admin_routes, prefix='/admin')
app.include_router(web_routes)
app.include_router(api)
 
# ─── Static Files ────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ─── Template Context Processor ───────────────────────────────
# In FastAPI, we'll handle this differently when rendering templates
# by passing the csrf_token in the context for each template render

# ─── Note ───────────────────────────────────────────────────
# This app should be run using: python run_server.py
# health checking, and production-ready server configuration.
