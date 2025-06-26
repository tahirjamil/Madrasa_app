from flask import current_app
import pymysql
import pymysql.cursors

# Centralized DB Connection
def connect_to_db():
    return pymysql.connect(
        host=current_app.config['MYSQL_HOST'],
        user=current_app.config['MYSQL_USER'],
        password=current_app.config['MYSQL_PASSWORD'],
        db=current_app.config['MYSQL_DB'],
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False
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
                due_months INT NOT NULL,
                FOREIGN KEY (id) REFERENCES users(id)
            )
        """)

        # Transactions Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INT PRIMARY KEY AUTO_INCREMENT,
                id INT NOT NULL,
                type ENUM('fees', 'donation') NOT NULL,
                month VARCHAR(50),
                amount INT NOT NULL,
                date DATETIME NOT NULL,
                FOREIGN KEY (id) REFERENCES users(id),
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
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
        
        # People & Verify Table

        tables = ['people', 'verify']
        for table in tables:

            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    user_id INT PRIMARY KEY AUTO_INCREMENT,
                    member_id INT,
                    id INT UNIQUE,
                    student_id INT,
                    name_en VARCHAR(255) NOT NULL,
                    name_bn VARCHAR(255),
                    name_ar VARCHAR(255),
                    date_of_birth DATE,
                    birth_certificate VARCHAR(100),
                    national_id VARCHAR(100),
                    blood_group VARCHAR(20),
                    gender ENUM('Male', 'Female'),
                    title1 VARCHAR(255),
                    title2 VARCHAR(255),
                    source VARCHAR(255),
                    present_address TEXT,
                    address_bn TEXT,
                    address_ar TEXT,
                    permanent_address TEXT,
                    father_or_spouse VARCHAR(255),
                    father_en VARCHAR(255),
                    father_bn VARCHAR(255),
                    father_ar VARCHAR(255),
                    mother_en VARCHAR(255),
                    mother_bn VARCHAR(255),
                    mother_ar VARCHAR(255),
                    class VARCHAR(100),
                    phone VARCHAR(15) NOT NULL,
                    mail TEXT,
                    guardian_number TEXT,
                    available BOOLEAN DEFAULT 1,
                    degree VARCHAR(50),
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    image_path TEXT,
                    acc_type ENUM('admins', 'students', 'teachers', 'staffs', 'others', 'badri_members', 'donors'),
                    FOREIGN KEY (id) REFERENCES users(id)
                )
            """)

        # Routine table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS routine (
                routine_id INT AUTO_INCREMENT PRIMARY KEY,
                gender ENUM('male', 'female') NOT NULL,
                class_group VARCHAR(20) NOT NULL,
                class_level VARCHAR(30) NOT NULL,
                weekday ENUM('saturday', 'sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday') NOT NULL,
                subject_en VARCHAR(100),
                subject_bn VARCHAR(100),
                subject_ar VARCHAR(100),
                name_en VARCHAR(100),
                name_bn VARCHAR(100),
                name_ar VARCHAR(100),
                serial INT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)

        # Kitab table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS book (
                book_id INT PRIMARY KEY AUTO_INCREMENT,
                name_en VARCHAR(50),
                name_bn VARCHAR(50),
                name_ar VARCHAR(50),
                class VARCHAR(50)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                log_id INT AUTO_INCREMENT PRIMARY KEY,
                action VARCHAR(100),
                phone VARCHAR(20),
                message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
    conn.close()
