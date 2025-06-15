# db_utils.py

import pymysql
from pymysql.cursors import DictCursor

# Centralized DB Connection
def connect_to_db():
    return pymysql.connect(
        host='localhost',
        user='tahir',
        password='tahir',
        database='madrasadb',
        cursorclass=DictCursor
    )

# Table Creation
def create_tables():
    conn = connect_to_db()
    with conn.cursor() as cursor:
        # Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                fullname VARCHAR(50) NOT NULL,
                phone VARCHAR(20) NOT NULL,
                password TEXT NOT NULL,
                UNIQUE KEY unique_user (fullname, phone)
            )
        """)

        # Payment Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payment (
                id INT PRIMARY KEY,
                food BOOLEAN NOT NULL,
                special_food BOOLEAN NOT NULL,
                reduce_fee INT DEFAULT 0,
                due_months INT NOT NULL
            )
        """)

        # Transactions Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INT PRIMARY KEY AUTO_INCREMENT,
                id INT NOT NULL,
                type ENUM('payment', 'donation') NOT NULL,
                month VARCHAR(50),
                amount INT NOT NULL,
                date DATE NOT NULL,
                FOREIGN KEY (id) REFERENCES users(id)
            )
        """)

        # Verifications Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS verifications (
                phone VARCHAR(20) NOT NULL,
                code INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # People Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS people (
                user_id INT PRIMARY KEY AUTO_INCREMENT,
                id INT UNIQUE,
                name_en VARCHAR(255) NOT NULL,
                name_bn VARCHAR(255),
                name_ar VARCHAR(255),
                date_of_birth DATE,
                birth_certificate_number VARCHAR(100),
                national_id_number VARCHAR(100),
                blood_group VARCHAR(20),
                gender ENUM('Male', 'Female'),
                title_primary VARCHAR(255),
                source_of_information VARCHAR(255),
                present_address TEXT,
                permanent_address TEXT,
                father_or_spouse VARCHAR(255),
                father_name_en VARCHAR(255),
                father_name_bn VARCHAR(255),
                father_name_ar VARCHAR(255),
                mother_name_en VARCHAR(255),
                mother_name_bn VARCHAR(255),
                mother_name_ar VARCHAR(255),
                class VARCHAR(100),
                phone VARCHAR(15) NOT NULL,
                image_path TEXT,
                acc_type ENUM('Admin', 'Student', 'Teacher', 'Staff', 'Guest')
            )
        """)

        conn.commit()
    conn.close()
