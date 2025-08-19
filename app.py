import asyncio
from logging.handlers import RotatingFileHandler
import os, time, logging
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
# TODO: BABEL NOT SETUP YET
import socket
from collections import deque
import json

from config import config, MadrasaConfig
from utils import create_tables
from utils.helpers.improved_functions import send_json_response, get_project_root
from utils.keydb.keydb_utils import connect_to_keydb, close_keydb
from utils.otel.otel_utils import init_otel

# ─── Import Routers ──────────────────────────────────────────
from utils.helpers.helpers import (
    get_system_health, initialize_application, security_manager, get_ip_address
)
from utils.helpers.fastapi_helpers import (
    templates, setup_template_globals, 
    _content_length_ok, _stream_limited, read_and_recreate_request, 
    read_json_and_recreate, SessionSecurityMiddleware)
from routes.api import api
from routes.web_routes import web_routes

# ─── Setup Logging ──────────────────────────────────────────
fh = RotatingFileHandler("debug.log", maxBytes=10*1024*1024, backupCount=5)
level = logging.DEBUG if config.is_development() else logging.INFO
logging.basicConfig(
    level=level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        fh,
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ─── App Setup ──────────────────────────────────────────────
BASE_DIR = get_project_root()
load_dotenv(BASE_DIR / ".env", override=True)

# Initialize start time variable
app_start_time = None

async def create_tables_async():
    try:
        logger.debug("Starting database table creation...")
        await create_tables()
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}", exc_info=True)

# ─── Lifespan Events ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for startup and shutdown"""
    global app_start_time
    # Startup
    app_start_time = time.time()
    
    # Log configuration status
    logger.info(f"Configuration loaded - TEST_MODE: {config.is_testing()}, OTEL_ENABLED: {config.OTEL_ENABLED}")
    
    # Initialize observability (traces/metrics) only if enabled
    if config.OTEL_ENABLED:
        logger.info("Initializing OpenTelemetry...")
        init_otel(
            service_name="madrasa-app",
            environment="development" if config.is_development() else "production",
            service_version=getattr(config, 'SERVER_VERSION', '0.0.0')
        )
        logger.info("OpenTelemetry initialized successfully")
    else:
        logger.info("OpenTelemetry disabled")
    
    logger.debug("Initializing application...")
    initialize_application()
    logger.info("Application initialization completed")
    
    await create_tables_async()
    # Initialize database connection pool
    try:
        logger.debug("Establishing database connection pool...")
        from utils.mysql.database_utils import get_db_pool
        app.state.db_pool = await get_db_pool()
        app.state.keydb = await connect_to_keydb()
        logger.info("Database connection pool established successfully")
    except Exception as e:
        logger.error(f"Error establishing database connection pool: {e}")
        raise RuntimeError("Failed to initialize database connection pool") from e
    
    yield
    
    # Shutdown
    if getattr(app.state, "db_pool", None) is not None:
        try:
            from utils.mysql.database_utils import close_db_pool
            await close_db_pool()
            logger.info("Database connection pool closed")
        except Exception as e:
            logger.error(f"Error closing database connection pool: {e}")
    if getattr(app.state, "keydb", None) is not None:
        try:
            await close_keydb(app.state.keydb)
            logger.info("Keydb connection closed")
        except Exception as e:
            logger.error(f"Error closing keydb connection: {e}")

# Create FastAPI app
app = FastAPI(
    title=MadrasaConfig.APP_NAME,
    version=MadrasaConfig.SERVER_VERSION,
    lifespan=lifespan
)

# Setup template globals
setup_template_globals(app)

# ─── CORS Configuration ──────────────────────────────────────────────
if not config.is_development():
    # Allow only specific origins in production
    allowed_origins = config.ALLOWED_ORIGINS or []
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
# templates = Jinja2Templates(directory="templates")  # Remove this line - using centralized instance

# Wrap ASGI app with tracing middleware only if OTEL is enabled
if config.OTEL_ENABLED:
    from utils.otel.asgi_middleware import RequestTracingMiddleware
    app.add_middleware(RequestTracingMiddleware)

def content_type_starts_with(request: Request, prefix: str) -> bool:
    ct = request.headers.get("content-type", "")
    return ct.split(";", 1)[0].strip().lower().startswith(prefix)

# ─── Request/Response Logging ───────────────────────────────
# Thread-safe request log with max size of 100 entries
app.state.request_response_log = deque(maxlen=100)
app.state.request_log_lock = asyncio.Lock()

# Log important configuration
try:
    host_ip = socket.gethostbyname(socket.gethostname())
except Exception:
    host_ip = "unknown"
logger.info(f"BASE_URL: {config.BASE_URL}")
logger.info(f"Host IP: {host_ip}")
logger.info(f"CORS enabled: {not config.is_development() and 'Restricted' or 'All origins (dev)'}")

# ─── Middleware ───────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

# Add session middleware (needed for admin routes)
# Ensure SECRET_KEY is set, especially for test mode
secret_key = MadrasaConfig.SECRET_KEY
if config.is_testing():
    secret_key = "test-secret-key-for-development-only"

app.add_middleware(SessionMiddleware, secret_key=secret_key)

# Add session security middleware
app.add_middleware(SessionSecurityMiddleware)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        logger.debug(f"Processing request: {request.method} {request.url.path}")
        
        response = await call_next(request)
        
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Log request completion
        process_time = time.time() - start_time
        logger.debug(f"Request completed: {request.method} {request.url.path} - Status: {response.status_code} - Time: {process_time:.3f}s")
        
        return response

app.add_middleware(SecurityHeadersMiddleware)

class XSSProtectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            # only inspect typical bodies (json/form)
            ct = request.headers.get("content-type", "")
            if ct and (ct.startswith("application/json") or ct.startswith("application/x-www-form-urlencoded") or ct.startswith("multipart/form-data")):
                # read + recreate inside helper (enforces max body)
                json_data, request = await read_json_and_recreate(request)  # uses MAX_JSON_BODY
                # If you need form data, you can also:
                body_bytes, request = await read_and_recreate_request(request)
                # then parse form if required via starlette
                if json_data:
                    def _contains_xss(obj):
                        if isinstance(obj, str):
                            return security_manager.detect_xss(obj)
                        if isinstance(obj, dict):
                            return any(_contains_xss(v) for v in obj.values())
                        if isinstance(obj, (list, tuple, set)):
                            return any(_contains_xss(v) for v in obj)
                        return False
                    if _contains_xss(json_data):
                        response, status = send_json_response("Invalid input", 400, "XSS detected")
                        return JSONResponse(content=response, status_code=status)

            # continue to next middleware/handler (request is already recreated)
            return await call_next(request)
        except HTTPException as e:
            # bubble up payload-too-large
            return JSONResponse({"error": e.detail}, status_code=e.status_code)
        except Exception as e:
            logger.exception("XSS guard error")
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

        ip = get_ip_address(request)
        endpoint = request.url.path
        # SECURITY FIX: Add CSRF check for admin routes - safely check session
        # blocked = False
        # try:
        #     if endpoint.startswith("/admin/"):
        #         # Check if session is available and admin is logged in
        #         if hasattr(request, 'session') and request.session:
        #             blocked = not request.session.get("admin_logged_in", False)
        #         else:
        #             # Session not available, block admin routes
        #             blocked = True
        # except Exception:
        #     # Session access failed, block admin routes
        #     blocked = True

        # Get JSON payload if available
        req_json = None
        ct = request.headers.get("content-type", "")
        if ct and ct.startswith("application/json"):
            try:
                body = await request.body()
                req_json, request = await read_json_and_recreate(request)
                # Need to recreate request with body for downstream
                from starlette.datastructures import Headers
                async def receive():
                    return {"type": "http.request", "body": body, "more_body": False}
                request = Request(request.scope, receive=receive)
            except HTTPException as e:
                return JSONResponse({"error": e.detail}, status_code=e.status_code)
            except Exception:
                req_json = None

        entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ip": ip,
            "endpoint": endpoint,
            # "status": "Blocked" if blocked else "Allowed",
            "method": request.method,
            "path": request.url.path,
            "req_json": req_json,
            "res_json": None,
        }
        
        # Store entry in request state for response logging
        request.state.log_entry = entry
        
        # Thread-safe append to request log
        async with app.state.request_log_lock:
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
    logger.warning(f"404 error: {request.method} {request.url} - Client: {request.client.host if request.client else 'unknown'}")
    logger.debug(f"404 details - Path: {request.url.path}, Query: {dict(request.query_params)}")
    return templates.TemplateResponse('404.html', {'request': request}, status_code=404)

@app.exception_handler(400)
async def bad_request_handler(request: Request, exc: HTTPException):
    logger.warning(f"400 error: {request.method} {request.url} - Detail: {exc.detail}")
    logger.debug(f"400 request headers: {dict(request.headers)}")
    
    if exc.detail and "CSRF" in str(exc.detail):
        logger.warning(f"CSRF error detected: {request.url} - Detail: {exc.detail}")
        return templates.TemplateResponse('admin/csrf_error.html', 
                                        {'request': request, 'reason': str(exc.detail)}, 
                                        status_code=400)
    
    response, status = send_json_response("Bad request", 400, str(exc.detail) if exc.detail else None)
    return JSONResponse(content=response, status_code=status)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse({"error": "validation_error", "details": exc.errors()}, status_code=422)

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    import traceback
    
    logger.error(f"Unhandled exception on {request.method} {request.url}: {str(exc)}", exc_info=True)
    logger.error(f"Exception type: {type(exc).__name__}")
    logger.error(f"Full traceback:\n{traceback.format_exc()}")
    logger.debug(f"Request details - Headers: {dict(request.headers)}, Client: {request.client.host if request.client else 'unknown'}")
    
    # In development/test mode, include more details
    if config.is_development():
        response, status = send_json_response("Internal server error", 500) 
        response.update({
            "error": str(exc),
            "type": type(exc).__name__,
            "path": request.url.path
        })
    else:
        response, status = send_json_response("Internal server error", 500)
    
    return JSONResponse(content=response, status_code=status)

# ─── Routes ────────────────────────────────────────────
@app.get('/favicon.ico')
async def favicon():
    return FileResponse(
        path=os.path.join(BASE_DIR, 'static', 'favicon.ico'),
        media_type='image/vnd.microsoft.icon'
    )

@app.get('/health')
async def health_check(request: Request):
    """Health check endpoint for monitoring"""
    logger.debug(f"Health check requested from {request.client.host if request.client else 'unknown'}")
    
    try:
        # Advanced health check
        health_status = await get_system_health()

        # Extra health check - use initialized start_time
        health_status.update({
            "uptime": time.time() - app_start_time if app_start_time else 0
        })

        return JSONResponse(content=health_status, status_code=200)
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
# ─── Static Files ────────────────────────────────────────────
# Make sure static and uploads directories exist
if not os.path.exists("static"):
    os.makedirs("static")
if not os.path.exists("uploads"):
    os.makedirs("uploads")
# Mount static files BEFORE routers to ensure they're available for url_for
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Now include routers
app.include_router(web_routes)
app.include_router(api)
 
# ─── Template Context Processor ───────────────────────────────
# In FastAPI, we'll handle this differently when rendering templates
# by passing the csrf_token in the context for each template render

# ─── Note ───────────────────────────────────────────────────
# This app should be run using: python run_server.py
# health checking, and production-ready server configuration.
