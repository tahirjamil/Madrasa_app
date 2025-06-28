import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Basic Info
    SECRET_KEY = os.getenv("SECRET_KEY", "fallback-key")
    WTF_CSRF_SECRET_KEY = os.getenv("CSRF_SECRET_KEY", "fallback-csrf-key")
    BASE_URL = 'http://localhost:5000/'
    BASE_UPLOAD_FOLDER = os.path.join('uploads')

    # Advanced
    API_KEY = os.getenv("API_KEY")
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True 
    SESSION_COOKIE_SAMESITE = "Lax"
    RECAPTCHA_SITE_KEY = os.getenv("RECAPTCHA_SITE_KEY")
    RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY")

    # Upload Folders
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB max
    IMG_UPLOAD_FOLDER = os.path.join(BASE_UPLOAD_FOLDER, 'people_img')
    EXAM_DIR     = os.path.join(BASE_UPLOAD_FOLDER, 'exam_results')
    NOTICES_DIR = os.path.join(BASE_UPLOAD_FOLDER, 'notices')

    # Extensions
    ALLOWED_NOTICE_EXTENSIONS = {'pdf', 'docx', 'png', 'jpg', 'jpeg'}
    ALLOWED_EXAM_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

    # MySQL Connection
    MYSQL_HOST = 'localhost'
    MYSQL_USER = os.getenv("MYSQL_USER")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
    MYSQL_DB = 'madrasadb'
