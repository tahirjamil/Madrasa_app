import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Base Info
    SECRET_KEY = os.getenv("SECRET_KEY")
    BASE_URL = 'http://localhost:5000/'
    BASE_UPLOAD_FOLDER = os.path.join('uploads')

    # Upload Folders
    IMG_UPLOAD_FOLDER = os.path.join(BASE_UPLOAD_FOLDER, 'people_img')
    EXAM_DIR     = os.path.join(BASE_UPLOAD_FOLDER, 'exam_results')
    NOTICES_DIR = os.path.join(BASE_UPLOAD_FOLDER, 'notices')
    MADRASA_IMG_DIR = os.path.join(BASE_UPLOAD_FOLDER, 'madrasa_img')

    # Extensions
    ALLOWED_NOTICE_EXTENSIONS = {'pdf', 'docx', 'png', 'jpg', 'jpeg'}
    ALLOWED_EXAM_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

    # MySQL Connection
    MYSQL_HOST = 'localhost'
    MYSQL_USER = 'tahir'
    MYSQL_PASSWORD = 'tahir'
    MYSQL_DB = 'madrasadb'
