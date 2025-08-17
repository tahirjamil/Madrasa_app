"""
Madrasha Application Configuration Module

This module provides a comprehensive configuration system for the Madrasha application,
consolidating authentication, core functionality, security, and application settings
into a single, well-documented configuration structure.

Author: Madrasha Development Team
Version: 1.0.0
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from functools import lru_cache
from quart import Quart
from typing import Optional, Union
from aiomysql import Connection
from redis.asyncio import Redis

from utils.helpers.improved_functions import get_env_var

# Load environment variables
load_dotenv()

# Setup logger for configuration module
logger = logging.getLogger(__name__)


class MadrasaApp(Quart):
    start_time: float | None
    db: Optional[Connection]
    keydb: Optional[Union[Redis, 'TracedRedisPool']]  # type: ignore [Use string annotation to avoid import]

class MadrasaConfig:
    """ Configuration class for the Madrasha application. """
    
    # ============================================================================
    # APPLICATION CORE SETTINGS
    # ============================================================================
    
    # Application Identity
    APP_NAME = "Madrasha Management System"
    SERVER_VERSION = "1.0.0"
    BASE_URL = "http://www.annurcomplex.com/"
    
    # CORS Configuration
    ALLOWED_ORIGINS = get_env_var("ALLOWED_ORIGINS").split(",").strip()
    
    # ============================================================================
    # OBSERVABILITY / OPENTELEMETRY CONFIGURATION
    # ============================================================================
    # Enable/disable OpenTelemetry completely. If disabled, no tracing/metrics are initialized.
    OTEL_ENABLED = get_env_var("OTEL_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    # Strict mode: if enabled and exporter is unreachable, the app raises (fails fast) instead of logging warnings.
    OTEL_STRICT = get_env_var("OTEL_STRICT", "false").lower() in ("1", "true", "yes", "on")
    OTEL_EXPORTER_OTLP_ENDPOINT = get_env_var("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    
    # ============================================================================
    # SECURITY CONFIGURATION
    # ============================================================================
    
    # Secret Keys and Encryption
    SECRET_KEY = get_env_var("SECRET_KEY") # secrets.token_urlsafe(32)
    WTF_CSRF_SECRET_KEY = get_env_var("WTF_CSRF_SECRET_KEY")
    ENCRYPTION_KEY = get_env_var("ENCRYPTION_KEY")
    
    # API Keys for Different Client Types
    MOBILE_CLIENT_KEY = get_env_var("MOBILE_CLIENT_KEY")
    WEB_CLIENT_KEY = get_env_var("WEB_CLIENT_KEY")
    ADMIN_KEY = get_env_var("ADMIN_KEY")
    API_KEYS = [MOBILE_CLIENT_KEY, WEB_CLIENT_KEY, ADMIN_KEY]
    
    # Power Management
    POWER_KEY = get_env_var("POWER_KEY")
    
    # Admin Credentials (with warnings)
    ADMIN_USERNAME = get_env_var("ADMIN_USERNAME")
    ADMIN_PASSWORD = get_env_var("ADMIN_PASSWORD")
    
    # ============================================================================
    # SESSION AND COOKIE SECURITY
    # ============================================================================
    
    # Session Configuration
    SESSION_COOKIE_DOMAIN = False  # Let Flask decide based on IP
    SESSION_COOKIE_SAMESITE = "Lax"
    # SECURITY: Check if in production mode and set secure cookies
    SESSION_COOKIE_SECURE = not get_env_var("FLASK_ENV") == "development"
    SESSION_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = 1 * 3600  # 1 hour session timeout
    
    # CSRF Protection
    WTF_CSRF_TIME_LIMIT = 1 * 3600  # CSRF token expires in 1 hour
    
    # reCAPTCHA Configuration
    RECAPTCHA_SITE_KEY = get_env_var("RECAPTCHA_SITE_KEY")
    RECAPTCHA_SECRET_KEY = get_env_var("RECAPTCHA_SECRET_KEY")
    
    # ============================================================================
    # AUTHENTICATION AND USER MANAGEMENT
    # ============================================================================

    # Email and SMS Verification
    SERVICE_PHONE_URL = "https://textbelt.com/text"
    SERVICE_PHONE_API_KEY = get_env_var("SMS_API_KEY")
    SERVICE_EMAIL_PORT = 587
    SERVICE_EMAIL_PASSWORD = get_env_var("EMAIL_PASSWORD")
    
    # Password Security
    PASSWORD_MIN_LENGTH = 8
    SESSION_TIMEOUT_HOURS = 24
    MAX_DEVICES_PER_USER = 3
    
    # Account Management
    ACCOUNT_DELETION_DAYS = 30
    ACCOUNT_REACTIVATION_DAYS = 14
    GLOBAL_REQUIRED_FIELDS = ["madrasa_name"]
    
    # Verification Settings
    CODE_EXPIRY_MINUTES = 10
    CODE_LENGTH = 6
    
    # Rate Limiting for Authentication
    SMS_LIMIT_PER_HOUR = 5
    EMAIL_LIMIT_PER_HOUR = 15
    LOGIN_ATTEMPTS_LIMIT = 5
    LOGIN_LOCKOUT_MINUTES = 15
    
    # ============================================================================
    # BUSINESS CONFIGURATION
    # ============================================================================

    # Business Information
    BUSINESS_EMAIL = get_env_var("BUSINESS_EMAIL")
    BUSINESS_PHONE = get_env_var("BUSINESS_PHONE")

    DEV_EMAIL = get_env_var("DEV_EMAIL")
    DEV_PHONE = get_env_var("DEV_PHONE")

    MADRASA_NAMES_LIST = ['annur']
    

    # ============================================================================
    # MYSQL CONFIGURATION
    # ============================================================================

    # MySQL Connection Settings
    MYSQL_HOST = get_env_var("MYSQL_HOST")
    MYSQL_USER = get_env_var("MYSQL_USER")
    MYSQL_PASSWORD = get_env_var("MYSQL_PASSWORD")
    MYSQL_DB = get_env_var("MYSQL_DB")
    MYSQL_PORT = int(get_env_var("MYSQL_PORT", 3306))
    MYSQL_UNIX_SOCKET = get_env_var("MYSQL_UNIX_SOCKET", None, required=False)
    MYSQL_MIN_CONNECTIONS = 2
    MYSQL_MAX_CONNECTIONS = 10
    MYSQL_MAX_OVERFLOW = 5
    MYSQL_TIMEOUT = 60.0

    # ============================================================================
    # REDIS CONFIGURATION
    # ============================================================================

    # Redis Connection Settings
    REDIS_HOST = get_env_var("REDIS_HOST", "localhost")
    REDIS_PORT = int(get_env_var("REDIS_PORT", 6379))
    REDIS_PASSWORD = get_env_var("REDIS_PASSWORD", None, required=False) # REMINDER: ADD THIS IN PRODUCTION
    REDIS_DB = int(get_env_var("REDIS_DB", 0))
    REDIS_SSL = get_env_var("REDIS_SSL", "false")
    REDIS_MINSIZE = 1
    REDIS_MAXSIZE = 10
    REDIS_TIMEOUT = 10.0
    REDIS_ENCODING = "utf-8"
    REDIS_PREFIX = "madrasa"
    USE_REDIS_CACHE = get_env_var("USE_REDIS_CACHE", "false").lower() in ("1", "true", "yes", "on")

    # ============================================================================
    # FILE UPLOAD AND STORAGE
    # ============================================================================

    # Upload Limits
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB max
    
    # Base Directories
    BASE_UPLOAD_FOLDER = os.path.join('uploads')
    BASE_TEMP_FOLDER = os.path.join('temp')
    STATIC_FOLDER = os.path.join('static')
    
    # Specific Upload Directories
    PROFILE_IMG_UPLOAD_FOLDER = os.path.join(BASE_UPLOAD_FOLDER, 'profile_pics')
    EXAM_RESULTS_UPLOAD_FOLDER = os.path.join(BASE_UPLOAD_FOLDER, 'exam_results')
    NOTICES_UPLOAD_FOLDER = os.path.join(BASE_UPLOAD_FOLDER, 'notices')
    GALLERY_DIR = os.path.join(BASE_UPLOAD_FOLDER, 'gallery')
    
    # Index Files
    EXAM_RESULTS_INDEX_FILE = os.path.join(EXAM_RESULTS_UPLOAD_FOLDER, 'index.json')
    GALLERY_INDEX_FILE = os.path.join(GALLERY_DIR, 'index.json')
    NOTICES_INDEX_FILE = os.path.join(NOTICES_UPLOAD_FOLDER, 'index.json')
    
    # Allowed File Extensions
    ALLOWED_NOTICE_EXTENSIONS = {'pdf', 'docx', 'png', 'jpg', 'jpeg'}
    ALLOWED_EXAM_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
    ALLOWED_PROFILE_IMG_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'HEIC'}
    ALLOWED_IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp', 'gif']
    ALLOWED_DOCUMENT_EXTENSIONS = ['pdf', 'doc', 'docx', 'txt']
    
    # ============================================================================
    # GALLERY AND CONTENT MANAGEMENT
    # ============================================================================
    
    # Gallery Configuration
    ALLOWED_GALLERY_FOLDERS = [
        'garden', 'library', 'office', 'roof_and_kitchen', 
        'mosque', 'studio', 'other'
    ]
    ALLOWED_GALLERY_GENDERS = ['male', 'female', 'both']
    ALLOWED_CLASS_FOLDERS = [
        'hifz', 'moktob', 'meshkat', 'daora', 'ulumul_hadith', 
        'ifta', 'madani_nesab', 'other'
    ]
    
    # ============================================================================
    # RATE LIMITING AND CACHING
    # ============================================================================
    
    # General Rate Limiting
    DEFAULT_RATE_LIMIT = 10
    HIGH_RATE_LIMIT = 100  # requests per hour
    STRICT_RATE_LIMIT = 20    # requests per hour for sensitive operations
    RATE_LIMIT_WINDOW = 60

    MAX_REQUESTS_PER_HOUR = 1000
    LOCKOUT_DURATION_MINUTES = 5
    MAX_LOGIN_ATTEMPTS = 5
    
    # Cache Configuration
    CACHE_TTL = 3600  # 1 hour
    SHORT_CACHE_TTL = 300  # 5 minutes
    
    # ============================================================================
    # TESTING AND DEVELOPMENT
    # ============================================================================
    
    # Dummy Data for Testing
    DUMMY_FULLNAME = "Dummy User"
    DUMMY_PHONE = "+8801712345678"
    DUMMY_EMAIL = "dummy@example.com"
    DUMMY_PASSWORD = "dummy123"

    # ============================================================================
    # CONFIGURATION VALIDATION AND WARNINGS
    # ============================================================================
    
    def __init__(self):
        """Initialize configuration and validate critical settings."""
        self._validate_critical_settings()
        self._print_security_warnings()
    
    def _validate_critical_settings(self) -> None:
        """Validate critical configuration settings."""
        critical_settings = {
            'SECRET_KEY': self.SECRET_KEY,
            'ENCRYPTION_KEY': self.ENCRYPTION_KEY,
            'MYSQL_USER': self.MYSQL_USER,
            'MYSQL_PASSWORD': self.MYSQL_PASSWORD,
            'MYSQL_DB': self.MYSQL_DB
        }
        
        missing_settings = [key for key, value in critical_settings.items() 
                          if not value or value in ['admin', 'default']]
        
        if missing_settings:
            logger.warning(f"Missing or default values for critical settings: {missing_settings}")
    
    def _print_security_warnings(self) -> None:
        """Print security warnings for default or missing values."""
        warnings = []
        
        # Database credentials warnings
        if not self.MYSQL_USER or self.MYSQL_USER == "admin":
            warnings.append("Using default MySQL username. Please set MYSQL_USER in .env")
        
        if not self.MYSQL_PASSWORD or self.MYSQL_PASSWORD == "admin":
            warnings.append("Using default MySQL password. Please set MYSQL_PASSWORD in .env")
        
        if not self.MYSQL_DB or self.MYSQL_DB == "default":
            warnings.append("Using default database name. Please set MYSQL_DB in .env")
        
        # Power management warning
        if not self.POWER_KEY:
            warnings.append("POWER_KEY not set. Power management will be disabled.")
        
        # Encryption key warning
        if not self.ENCRYPTION_KEY:
            warnings.append("ENCRYPTION_KEY not set. Data encryption may be compromised.")
        
        # Session security warning
        if not self.SESSION_COOKIE_SECURE and not self.is_development():
            warnings.append("SESSION_COOKIE_SECURE is False in non-development mode. This is a security risk!")
            
        # Redis password warning
        if not self.REDIS_PASSWORD and not self.is_development():
            warnings.append("REDIS_PASSWORD not set in non-development mode. Redis may be unsecured!")
        
        # Log warnings using logger instead of print
        for warning in warnings:
            logger.warning(warning)

    @lru_cache(maxsize=1)
    def get_project_root(self, marker_files: tuple[str, ...] = ("pyproject.toml", "app.py")) -> Path:
        """Return project root directory by searching upwards for a marker file."""
        current = Path(__file__).resolve()
        for parent in [current] + list(current.parents):
            if any((parent / marker).exists() for marker in marker_files):
                return parent
        raise FileNotFoundError("Project root not found")
    
    @lru_cache(maxsize=1)
    def get_database_url(self, include_password: bool = False) -> Optional[str]:
        """Generate database connection URL."""
        try:
            if include_password:
                return f"mysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}/{self.MYSQL_DB}"
            else:
                return f"mysql://{self.MYSQL_USER}:***@{self.MYSQL_HOST}/{self.MYSQL_DB}"
        except Exception as e:
            logger.error(f"Error generating database connection URL: {e}")
            return None

    @lru_cache(maxsize=1)
    def get_keydb_url(self, include_password: bool = False) -> Optional[str]:
        """Generate keydb connection URL."""
        try:
            url = "redis://"
            if self.REDIS_PASSWORD:
                if include_password:
                    url += f":{self.REDIS_PASSWORD}@"
                else:
                    url += f":***@"
            url += f"{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
            return url
        except Exception as e:
            logger.error(f"Error generating keydb connection URL: {e}")
            return None
    
    @lru_cache(maxsize=1)
    def is_maintenance(self) -> bool:
        """Check if running in production environment."""
        verify = get_env_var("MAINTENANCE_MODE", "")
        return verify is True or (isinstance(verify, str) and verify.lower() in ("true", "yes", "on"))
    
    @lru_cache(maxsize=1)
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return get_env_var("FLASK_ENV", "development") == "development"
    
    @lru_cache(maxsize=1)
    def is_testing(self) -> bool:
        """Check if running in testing environment."""
        verify = get_env_var("TEST_MODE", "")
        return verify is True or (isinstance(verify, str) and verify.lower() in ("true", "yes", "on"))

# Create global configuration instance
config = MadrasaConfig()

class ServerConfig:
    """Configuration for the server."""

    # Server Configuration
    SERVER_HOST = get_env_var("SERVER_HOST", "0.0.0.0")
    SERVER_PORT = int(get_env_var("SERVER_PORT", 8000))
    SERVER_WORKERS = 1
    SERVER_TIMEOUT = 15
    SERVER_MAX_REQUESTS = 1000
    SERVER_MAX_REQUESTS_JITTER = 50
    
    # Logging Configuration
    LOGGING_LEVEL = "INFO"
    LOGGING_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOGGING_ROTATION = "1 day"
    LOGGING_RETENTION = "30 days"
    LOGGING_MAX_SIZE = "10MB"
    
    # Monitoring Configuration 
    HEALTH_CHECK_INTERVAL = 30
    MAX_MEMORY_USAGE = "512MB"
    MAX_CPU_USAGE = 80
    AUTO_RESTART = True
    RESTART_THRESHOLD = 3

    # Security Configuration
    BIND_HOST = get_env_var("BIND_HOST", "127.0.0.1")  # Add default
    ALLOWED_HOSTS = list(get_env_var("ALLOWED_HOSTS", "*").split(","))
    RATE_LIMIT = 100
    TIMEOUT = 30

server_config = ServerConfig()