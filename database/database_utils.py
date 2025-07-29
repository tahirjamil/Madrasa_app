import aiomysql
from config import Config

# Centralized Async DB Connection
def get_db_config():
    # Ensure all required config values are present and not None
    if not all([
        Config.MYSQL_HOST,
        Config.MYSQL_USER,
        Config.MYSQL_PASSWORD is not None,  # Password can be empty string but not None
        Config.MYSQL_DB
    ]):
        raise ValueError("Database configuration is incomplete. Please check your config settings.")
    return dict(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD or "",
        db=Config.MYSQL_DB,
        autocommit=False,
        charset='utf8mb4',
        connect_timeout=60
    )

async def connect_to_db():
    try:
        config = get_db_config()
        return await aiomysql.connect(**config)
    except Exception as e:
        print(f"Database connection failed: {e}")
        return None

# Table Creation
async def create_tables():
    conn = None
    try:
        conn = await connect_to_db()
        if conn is None:
            print("Database connection failed during table creation")
            return

        # Suppress MySQL warnings
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SET sql_notes = 0")
            await conn.commit()

            # ─── users ──────────────────────────────────────────────────────────────
            await cursor.execute("""
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
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
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
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
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
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS verifications (
                verification_id   INT   NOT NULL AUTO_INCREMENT PRIMARY KEY,
                created_at  TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP,
                phone       VARCHAR(20) NOT NULL,
                code        INT,
                ip_address  VARCHAR(20)
            )
            """)

        # ─── people & verify_people ────────────────────────────────────────────
        for table in ('people','verify_people'):
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(f"""
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
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
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
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS book (
                book_id INT AUTO_INCREMENT PRIMARY KEY,
                name_en VARCHAR(50),
                name_bn VARCHAR(50),
                name_ar VARCHAR(50),
                class   VARCHAR(50)
            )
            """)

        # ─── logs ───────────────────────────────────────────────────────────────
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                log_id     INT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                action     VARCHAR(100),
                phone      VARCHAR(20),
                message    TEXT
            )
            """)

        # ─── exam ───────────────────────────────────────────────────────────────
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
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
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
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
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS interactions (
                device_id      TEXT NOT NULL,
                device_brand   TEXT,
                ip_address     TEXT NOT NULL,
                id             INT  NOT NULL,
                open_times     INT  NOT NULL DEFAULT 1
            )
            """)
        # ─── Block(s) ──────────────────────────────────────────────────────────
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS blocklist (
                block_id            INT             AUTO_INCREMENT PRIMARY KEY,
                basic_info          VARCHAR(50)     NOT NULL,
                additional_info    TEXT,
                need_check          BOOLEAN         NOT NULL   DEFAULT 1,
                created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP
                                            ON UPDATE CURRENT_TIMESTAMP
            )
            """)

        # Re-enable MySQL warnings
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SET sql_notes = 1")
            await conn.commit()

        print("All database tables created successfully")

    except Exception as e:
        if conn:
            await conn.rollback()
        print(f"Database table creation failed: {e}")
        raise
    finally:
        if conn:
            await conn.close()
