import asyncio
import os, time, logging
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
# TODO: BABEL NOT SETUP YET
import socket
from collections import deque

# ─── Logging Utilities ──────────────────────────────────────────────
from rich.traceback import install
from rich.logging import RichHandler
from logging.handlers import RotatingFileHandler

# ─── Import Configurations and Utilities ────────────────────────────
from config import config, MadrasaConfig
from utils import create_tables
from utils.helpers.improved_functions import send_json_response, get_project_root
from utils.keydb.keydb_utils import close_keydb
from utils.otel.otel_utils import init_otel, RequestTracingMiddleware

# ─── Import Routers ──────────────────────────────────────────
from utils.helpers.helpers import (get_system_health, initialize_application, security_manager, get_ip_address, redact_headers)
from utils.helpers.fastapi_helpers import (
    templates, setup_template_globals, 
    read_json_and_recreate)
from routes.api import api
from routes.web_routes import web_routes

# ─── Setup Logging ──────────────────────────────────────────

# Enable rich tracebacks for uncaught exceptions
install(show_locals=True)

fh = RotatingFileHandler("debug.log", maxBytes=10*1024*1024, backupCount=5)
level = logging.DEBUG if config.is_development() else logging.INFO
logging.basicConfig(
    level=level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        fh,                  # File logs
        RichHandler()        # Console logs with rich formatting
    ]
)
logger = logging.getLogger(__name__)

# ─── App Setup ──────────────────────────────────────────────
BASE_DIR = get_project_root()
load_dotenv(BASE_DIR / ".env", override=True)

async def create_tables_async():
    try:
        logger.debug("Started database table creation...")
        await create_tables()
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}", exc_info=True)

# ─── Helpers ──────────────────────────────────────────────
def content_type_starts_with(request: Request, prefix: str) -> bool:
    ct = request.headers.get("content-type", "")
    return ct.split(";",1)[0].strip().lower().startswith(prefix)

# ─── Lifespan Events ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for startup and shutdown"""
    # Startup
    app.state.start_time = time.time()
    
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
    
    await create_tables_async()
    # Initialize database connection pool
    try:
        logger.debug("Establishing database connection pool...")
        from utils.mysql.database_utils import get_db_pool
        from utils.keydb.keydb_utils import connect_to_keydb, set_global_keydb
        app.state.db_pool = await get_db_pool()
        app.state.keydb = await connect_to_keydb()
        set_global_keydb(app.state.keydb)
        yield
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

# Wrap ASGI app with tracing middleware only if OTEL is enabled
if config.OTEL_ENABLED:
    app.add_middleware(RequestTracingMiddleware)

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
            if (content_type_starts_with(request, "application/json") or 
                content_type_starts_with(request, "application/x-www-form-urlencoded") or 
                content_type_starts_with(request, "multipart/form-data")):
                # read + recreate inside helper (enforces max body)
                json_data, request = await read_json_and_recreate(request)  # uses MAX_JSON_BODY

                # if you need form data, only parse after recreation:
                # if ct.startswith("application/x-www-form-urlencoded") or ct.startswith("multipart/form-data"):
                #     form = await request.form()

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
        if request.url.path in ["/admin/info_data"]:
            return await call_next(request)

        req_json = None
        if content_type_starts_with(request, "application/json"):
            try:
                req_json, request = await read_json_and_recreate(request)
            except HTTPException as e:
                return JSONResponse({"error": e.detail}, status_code=e.status_code)
            except Exception:
                req_json = None

        entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ip": get_ip_address(request),
            "endpoint": request.url.path,
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
        
        # TODO: Capture response JSON if needed
        # This is complex in FastAPI middleware and may need a custom approach
        
        return response

app.add_middleware(RequestLoggingMiddleware)

# ─── Exception Handlers ────────────────────────────────────────────
@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    logger.warning(f"404 error: {request.method} {request.url} - Client: {request.client.host if request.client else 'unknown'}")
    logger.debug(f"404 details - Path: {request.url.path}, Query: {dict(request.query_params)}")

    context = {
        "request": request,
        "home_path": "/"
    }
    return templates.TemplateResponse("404.html", context, status_code=404)


@app.exception_handler(400)
async def bad_request_handler(request: Request, exc: HTTPException):
    logger.warning(f"400 error: {request.method} {request.url} - Detail: {exc.detail}")
    logger.debug(f"400 request headers: {redact_headers(dict(request.headers))}")
    
    # if exc.detail and "CSRF" in str(exc.detail):
    #     logger.warning(f"CSRF error detected: {request.url} - Detail: {exc.detail}")
    #     return templates.TemplateResponse('admin/csrf_error.html', 
    #                                     {'request': request, 'reason': str(exc.detail)}, 
    #                                     status_code=400)
    
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
    logger.debug(f"Request details - Headers: {redact_headers(dict(request.headers))}, Client: {request.client.host if request.client else 'unknown'}")
    
    # In development/test mode, include more details
    if config.is_development():
        response, status = send_json_response("Internal server error", 500, "An unexpected error occurred. Please try again later.") 
        response.update({
            "error": str(exc),
            "type": type(exc).__name__,
            "path": request.url.path
        })
    else:
        response, status = send_json_response("Internal server error", 500, "An unexpected error occurred. Please try again later.")
    
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
        health_status = await get_system_health(request)

        # Extra health check - use initialized start_time
        health_status.update({
            "uptime": time.time() - app.state.start_time if app.state.start_time else 0
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

# ─── Note ───────────────────────────────────────────────────
# This app should be run using: python run_server.py
# health checking, and production-ready server configuration.
