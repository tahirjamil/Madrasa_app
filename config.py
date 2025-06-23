import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    BASE_URL = 'http://localhost:5000/'
    BASE_UPLOAD_FOLDER = os.path.join('uploads')

    # MySQL Connection
    MYSQL_HOST = 'localhost'
    MYSQL_USER = 'tahir'
    MYSQL_PASSWORD = 'tahir'
    MYSQL_DB = 'madrasadb'
