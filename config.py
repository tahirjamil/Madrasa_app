"""
Madrasha Application Configuration Module

This module provides a comprehensive configuration system for the Madrasha application,
consolidating authentication, core functionality, security, and application settings
into a single, well-documented configuration structure.

Author: Madrasha Development Team
Version: 1.0.0
"""

import os
from dotenv import load_dotenv
from functools import lru_cache

# Load environment variables
load_dotenv()


class MadrasaConfig:
    """ Configuration class for the Madrasha application. """
    
    # ============================================================================
    # APPLICATION CORE SETTINGS
    # ============================================================================
    
    # Application Identity
    APP_NAME = "Madrasha Management System"
    SERVER_VERSION = "1.0.0"
    BASE_URL = "http://www.annurcomplex.com/"
    
    # ============================================================================
    # SECURITY CONFIGURATION
    # ============================================================================
    
    # Secret Keys and Encryption
    SECRET_KEY = os.getenv("SECRET_KEY") # secrets.token_urlsafe(32)
    WTF_CSRF_SECRET_KEY = os.getenv("WTF_CSRF_SECRET_KEY")
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
    
    # API Keys for Different Client Types
    MOBILE_CLIENT_KEY = os.getenv("MOBILE_CLIENT_KEY")
    WEB_CLIENT_KEY = os.getenv("WEB_CLIENT_KEY")
    ADMIN_KEY = os.getenv("ADMIN_KEY")
    API_KEYS = [MOBILE_CLIENT_KEY, WEB_CLIENT_KEY, ADMIN_KEY]
    
    # Power Management
    POWER_KEY = os.getenv("POWER_KEY")
    
    # Admin Credentials (with warnings)
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
    
    # ============================================================================
    # SESSION AND COOKIE SECURITY
    # ============================================================================
    
    # Session Configuration
    SESSION_COOKIE_DOMAIN = False  # Let Flask decide based on IP
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = 1 * 3600  # 1 hour session timeout
    
    # CSRF Protection
    WTF_CSRF_TIME_LIMIT = 1 * 3600  # CSRF token expires in 1 hour
    
    # reCAPTCHA Configuration
    RECAPTCHA_SITE_KEY = os.getenv("RECAPTCHA_SITE_KEY")
    RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY")
    
    # ============================================================================
    # AUTHENTICATION AND USER MANAGEMENT
    # ============================================================================

    # Email and SMS Verification
    SERVICE_PHONE_URL = "https://textbelt.com/text"
    SERVICE_PHONE_API_KEY = os.getenv("SMS_API_KEY")
    SERVICE_EMAIL_PORT = 587
    SERVICE_EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
    SERVICE_EMAIL_API_KEY = os.getenv("EMAIL_API_KEY")
    
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
    BUSINESS_EMAIL = os.getenv("BUSINESS_EMAIL")
    BUSINESS_PHONE = os.getenv("BUSINESS_PHONE")

    DEV_EMAIL = os.getenv("DEV_EMAIL")
    DEV_PHONE = os.getenv("DEV_PHONE")

    MADRASA_NAMES_LIST = ['annur']
    
    
    # ============================================================================
    # DATABASE CONFIGURATION
    # ============================================================================
    
    # MySQL Connection Settings
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_USER = os.getenv("MYSQL_USER", "admin")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "admin")
    MYSQL_DB = os.getenv("MYSQL_DB", "default")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
    MYSQL_UNIX_SOCKET = os.getenv("MYSQL_UNIX_SOCKET", None)

    # Database Connection Pooling
    DB_POOL_SIZE = 10
    DB_MAX_OVERFLOW = 5
    DB_TIMEOUT = 60
    
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
    GALLERY_DIR = os.path.join(BASE_UPLOAD_FOLDER, 'gallery')\
    
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
    
    # Redis/KeyDB cache settings
    USE_REDIS_CACHE = os.getenv("USE_REDIS_CACHE", "false").lower() in ("1", "true", "yes", "on")
    REDIS_URL = os.getenv("REDIS_URL") or os.getenv("KEYDB_URL")
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB = int(os.getenv("REDIS_DB", 0))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
    REDIS_PREFIX = os.getenv("REDIS_PREFIX", "madrasa")
    
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
            print(f"WARNING: Missing or default values for critical settings: {missing_settings}")
    
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
        
        # Print warnings
        for warning in warnings:
            print(f"WARNING: {warning}")
    
    @lru_cache(maxsize=1)
    def get_database_url(self) -> str:
        """Generate database connection URL."""
        return f"mysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}/{self.MYSQL_DB}"
    
    @lru_cache(maxsize=1)
    def is_maintenance(self) -> bool:
        """Check if running in production environment."""
        verify = os.getenv("MAINTENANCE_MODE", "")
        return verify is True or (isinstance(verify, str) and verify.lower() in ("true", "yes", "on"))
    
    @lru_cache(maxsize=1)
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return os.getenv("FLASK_ENV", "development") == "development"
    
    @lru_cache(maxsize=1)
    def is_testing(self) -> bool:
        """Check if running in testing environment."""
        verify = os.getenv("TEST_MODE", "")
        return verify is True or (isinstance(verify, str) and verify.lower() in ("true", "yes", "on"))

# Create global configuration instance
config = MadrasaConfig()