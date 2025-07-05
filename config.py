import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Basic Info
    SECRET_KEY = os.getenv("SECRET_KEY", "fallback-key")
    WTF_CSRF_SECRET_KEY = os.getenv("CSRF_SECRET_KEY", "fallback-csrf-key")
    BASE_URL = os.getenv("BASE_URL")
    BASE_UPLOAD_FOLDER = os.path.join('uploads')
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

    # Advanced Info
    API_KEY = os.getenv("API_KEY")
    SESSION_COOKIE_DOMAIN = False  # Let Flask decide based on IP
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False  # Don't use HTTPS for dev testing
    RECAPTCHA_SITE_KEY = os.getenv("RECAPTCHA_SITE_KEY")
    RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY")

    # Upload Folders
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB max
    IMG_UPLOAD_FOLDER = os.path.join(BASE_UPLOAD_FOLDER, 'people_img')
    EXAM_DIR = os.path.join(BASE_UPLOAD_FOLDER, 'exam_results')
    NOTICES_DIR = os.path.join(BASE_UPLOAD_FOLDER, 'notices')
    MADRASA_IMG_DIR = os.path.join(BASE_UPLOAD_FOLDER, 'madrasa_img')

    # Extensions
    ALLOWED_NOTICE_EXTENSIONS = {'pdf', 'docx', 'png', 'jpg', 'jpeg'}
    ALLOWED_EXAM_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

    # MySQL Connection
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_USER = os.getenv("MYSQL_USER", "admin")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "admin")
    MYSQL_DB = os.getenv("MYSQL_DB", "default")
