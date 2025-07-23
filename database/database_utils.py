import pymysql
import pymysql.cursors
from config import Config

# Centralized DB Connection
def connect_to_db():
    return pymysql.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        db=Config.MYSQL_DB,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,  # Changed: Disable autocommit for better transaction control
        charset='utf8mb4',
        connect_timeout=60,
        read_timeout=30,
        write_timeout=30
    )

# Table Creation
def create_tables():
    conn = None
    try:
        conn = connect_to_db()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # ─── users ──────────────────────────────────────────────────────────────
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                fullname    VARCHAR(50)            NOT NULL,
                phone       VARCHAR(20)            NOT NULL,
                password    TEXT                   NOT NULL,
                email       TEXT,
                ip_address  VARCHAR(20),
                deactivated_at  DATETIME            NULL,
                scheduled_deletion_at  DATETIME     NULL,
                UNIQUE KEY unique_user (fullname, phone)
            )
            """)

            # ─── payment ────────────────────────────────────────────────────────────
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS payment (
                id           INT           PRIMARY KEY,
                food         BOOLEAN       NOT NULL,
                special_food BOOLEAN       NOT NULL,
                reduce_fee   INT           DEFAULT 0,
                due_months   INT           NOT NULL,
                FOREIGN KEY (id) REFERENCES users(id)
            )
            """)

            # ─── transactions ───────────────────────────────────────────────────────
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                id             INT NOT NULL,
                type           ENUM('fees','donations') NOT NULL,
                month          VARCHAR(50),
                amount         INT    NOT NULL,
                date           DATETIME NOT NULL,
                updated_at     TIMESTAMP 
                                 NOT NULL 
                                 DEFAULT CURRENT_TIMESTAMP 
                                 ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (id) REFERENCES users(id)
            )
            """)

            # ─── verifications ─────────────────────────────────────────────────────
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS verifications (
                verification_id   INT   NOT NULL AUTO_INCREMENT PRIMARY KEY,
                created_at  TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP,
                phone       VARCHAR(20) NOT NULL,
                code        INT,
                ip_address  VARCHAR(20),
            )
            """)

            # ─── people & verify_people ────────────────────────────────────────────
            for table in ('people','verify_people'):
                cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS `{table}` (
                    user_id            INT             NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    member_id          INT,
                    id                 INT             UNIQUE,
                    student_id         INT,
                    name_en            VARCHAR(255)    NOT NULL,
                    name_bn            VARCHAR(255),
                    name_ar            VARCHAR(255),
                    date_of_birth      DATE,
                    birth_certificate  VARCHAR(100),
                    national_id        VARCHAR(100),
                    blood_group        VARCHAR(20),
                    gender             ENUM('Male','Female'),
                    title1             VARCHAR(255),
                    title2             VARCHAR(255),
                    source             VARCHAR(255),
                    present_address    TEXT,
                    address_en         TEXT,
                    address_bn         TEXT,
                    address_ar         TEXT,
                    permanent_address  TEXT,
                    father_or_spouse   VARCHAR(255),
                    father_en          VARCHAR(255),
                    father_bn          VARCHAR(255),
                    father_ar          VARCHAR(255),
                    mother_en          VARCHAR(255),
                    mother_bn          VARCHAR(255),
                    mother_ar          VARCHAR(255),
                    class              VARCHAR(100),
                    phone              VARCHAR(20)     NOT NULL,
                    guardian_number    TEXT,
                    available          BOOLEAN         DEFAULT 1,
                    degree             VARCHAR(50),
                    updated_at         DATETIME        NOT NULL
                                      DEFAULT CURRENT_TIMESTAMP
                                      ON UPDATE CURRENT_TIMESTAMP,
                    image_path         TEXT,
                    acc_type           ENUM(
                                          'admins','students','teachers',
                                          'staffs','others','badri_members',
                                          'donors'
                                        ),
                    is_donor            BOOLEAN         DEFAULT 0,
                    is_badri_member     BOOLEAN         DEFAULT 0,
                    is_foundation_member BOOLEAN        DEFAULT 0,
                    UNIQUE KEY unique_person (name_en, phone),
                    FOREIGN KEY (id) REFERENCES users(id)
                )
                """)

            # ─── routine ────────────────────────────────────────────────────────────
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS routine (
                routine_id   INT    NOT NULL AUTO_INCREMENT PRIMARY KEY,
                updated_at   TIMESTAMP 
                              NOT NULL 
                              DEFAULT CURRENT_TIMESTAMP 
                              ON UPDATE CURRENT_TIMESTAMP,
                gender       ENUM('male','female') NOT NULL,
                class_group  VARCHAR(20)            NOT NULL,
                class_level  VARCHAR(30)            NOT NULL,
                weekday      ENUM(
                                'saturday','sunday','monday','tuesday',
                                'wednesday','thursday','friday'
                             ) NOT NULL,
                subject_en   VARCHAR(100),
                subject_bn   VARCHAR(100),
                subject_ar   VARCHAR(100),
                name_en      VARCHAR(100),
                name_bn      VARCHAR(100),
                name_ar      VARCHAR(100),
                serial       INT                   NOT NULL
            )
            """)

            # ─── book ───────────────────────────────────────────────────────────────
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS book (
                book_id INT AUTO_INCREMENT PRIMARY KEY,
                name_en VARCHAR(50),
                name_bn VARCHAR(50),
                name_ar VARCHAR(50),
                class   VARCHAR(50)
            )
            """)

            # ─── logs ───────────────────────────────────────────────────────────────
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                log_id     INT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                action     VARCHAR(100),
                phone      VARCHAR(20),
                message    TEXT
            )
            """)

            # ─── exam ───────────────────────────────────────────────────────────────
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS exam (
                exam_id         INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
                created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,
                book_en         VARCHAR(50)  NOT NULL,
                book_bn         VARCHAR(50)  NOT NULL,
                book_ar         VARCHAR(50)  NOT NULL,
                class           VARCHAR(50)  NOT NULL,
                gender          ENUM('male','female') NOT NULL,
                start_time      TIMESTAMP    NOT NULL,
                end_time        TIMESTAMP    NOT NULL,
                sec_start_time  TIMESTAMP,
                sec_end_time    TIMESTAMP,
                date            DATE         NOT NULL,
                weekday         ENUM(
                                  'saturday','sunday','monday','tuesday',
                                  'wednesday','thursday','friday'
                                ) NOT NULL
            )
            """)

            # ─── event(s) ──────────────────────────────────────────────────────────
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id     INT       AUTO_INCREMENT PRIMARY KEY,
                created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                                ON UPDATE CURRENT_TIMESTAMP,
                type         ENUM('event', 'function') NOT NULL,
                title        VARCHAR(50),
                time         TIMESTAMP NOT NULL,
                date         DATE      NOT NULL,
                function_url TEXT
            )
            """)
            # ─── interaction(s) ──────────────────────────────────────────────────────────
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS interactions (
                device_id      TEXT NOT NULL,
                device_brand   TEXT,
                ip_address     TEXT NOT NULL,
                id             INT  NOT NULL,
                open_times     INT  NOT NULL DEFAULT 1
            )
            """)
            # ─── Block(s) ──────────────────────────────────────────────────────────
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS Blocker (
                block_id            INT             AUTO_INCREMENT PRIMARY KEY,
                basic_info          VARCHAR(50)     NOT NULL,
                additional_info    TEXT,
                need_check          BOOLEAN         NOT NULL   DEFAULT 1
            )
            """)

            conn.commit()
            print("All database tables created successfully")
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Database table creation failed: {e}")
        raise
    finally:
        if conn:
            conn.close()
