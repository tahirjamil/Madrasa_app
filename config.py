import os, secrets
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Basic Info - Improved security
    SECRET_KEY = secrets.token_urlsafe(32)
    WTF_CSRF_SECRET_KEY = secrets.token_urlsafe(32)
    BASE_URL = os.getenv("BASE_URL")
    
    # Warn about default credentials
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
    
    # Private Keys
    MOBILE_CLIENT_KEY = os.getenv("MOBILE_CLIENT_KEY")
    WEB_CLIENT_KEY = os.getenv("WEB_CLIENT_KEY")
    ADMIN_KEY = os.getenv("ADMIN_KEY")

    API_KEYS = [MOBILE_CLIENT_KEY, WEB_CLIENT_KEY, ADMIN_KEY]
    
    # Session Security - Improved
    SESSION_COOKIE_DOMAIN = False  # Let Flask decide based on IP
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_SECURE", "False").lower() == "true"
    SESSION_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = 1 * 3600  # 1 hour session timeout
    
    # Security Headers
    WTF_CSRF_TIME_LIMIT = 1 * 3600  # CSRF token expires in 1 hour
    
    RECAPTCHA_SITE_KEY = os.getenv("RECAPTCHA_SITE_KEY")
    RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY")
    
    # Data Encryption Key
    # key = Fernet.generate_key() TODO: fix this
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

    # Upload Folders
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB max
    BASE_UPLOAD_FOLDER = os.path.join('uploads')
    BASE_TEMP_FOLDER = os.path.join('temp')
    STATIC_FOLDER = os.path.join('static')
    PROFILE_IMG_UPLOAD_FOLDER = os.path.join(STATIC_FOLDER, 'user_profile_img')
    EXAM_RESULTS_UPLOAD_FOLDER = os.path.join(BASE_UPLOAD_FOLDER, 'exam_results')
    NOTICES_UPLOAD_FOLDER = os.path.join(BASE_UPLOAD_FOLDER, 'notices')
    GALLERY_DIR = os.path.join(BASE_UPLOAD_FOLDER, 'gallery')

    # Extensions
    ALLOWED_NOTICE_EXTENSIONS = {'pdf', 'docx', 'png', 'jpg', 'jpeg'}
    ALLOWED_EXAM_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
    ALLOWED_PROFILE_IMG_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'HEIC'}

    # MySQL Connection - Improved warnings
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_USER = os.getenv("MYSQL_USER")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
    MYSQL_DB = os.getenv("MYSQL_DB")

    # Verification
    CODE_EXPIRY_MINUTES = 10
    CODE_LENGTH = 6

    # Dummy info
    DUMMY_FULLNAME = os.getenv("DUMMY_FULLNAME")
    DUMMY_PHONE = os.getenv("DUMMY_PHONE")
    DUMMY_EMAIL = os.getenv("DUMMY_EMAIL")
    DUMMY_PASSWORD = os.getenv("DUMMY_PASSWORD")

    # Rate Limiting
    DEFAULT_RATE_LIMIT = 10
    RATE_LIMIT_WINDOW = 60

    # Server Version
    SERVER_VERSION = "1.0.0"

    # Password Strength
    PASSWORD_MIN_LENGTH = 8
    
    # Warn about default database credentials
    if not MYSQL_USER or MYSQL_USER == "admin":
        print("WARNING: Using default MySQL username. Please set MYSQL_USER in .env")
        MYSQL_USER = "admin"
    
    if not MYSQL_PASSWORD or MYSQL_PASSWORD == "admin":
        print("WARNING: Using default MySQL password. Please set MYSQL_PASSWORD in .env")
        MYSQL_PASSWORD = "admin"
        
    if not MYSQL_DB or MYSQL_DB == "default":
        print("WARNING: Using default database name. Please set MYSQL_DB in .env")
        MYSQL_DB = "default"
    
    # Power Management
    POWER_KEY = os.getenv("POWER_KEY")
    if not POWER_KEY:
        print("WARNING: POWER_KEY not set. Power management will be disabled.")