---------------------------------------------- GLOBAL TABLES ----------------------------------------------

-- Create global database if it doesn't exist
CREATE DATABASE IF NOT EXISTS global;
USE global;

CREATE TABLE IF NOT EXISTS global_translations (
                translation_id      INT AUTO_INCREMENT PRIMARY KEY,
                translation_text    VARCHAR(255)   UNIQUE    NOT NULL,
                bn_text             VARCHAR(255)   NULL,
                ar_text             VARCHAR(255)   NULL,
                context             VARCHAR(50)    NOT NULL,
                table_name          VARCHAR(10)    NOT NULL,

                updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
                INDEX idx_global_translations_context (context)
                INDEX idx_global_translations_table_name (table_name)
                ) ENGINE = InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS users (
                user_id INT AUTO_INCREMENT PRIMARY KEY,
                fullname    VARCHAR(50)            NOT NULL,
                phone       VARCHAR(20)            NOT NULL,
                phone_hash    CHAR(64)           NOT NULL,
                phone_encrypted    VARCHAR(255)           NOT NULL,
                password_hash    CHAR(64)           NOT NULL,
                email       VARCHAR(50),
                email_hash    CHAR(64)           NOT NULL,
                email_encrypted    VARCHAR(255)           NOT NULL,
                ip_address  VARCHAR(45),
                deactivated_at  DATETIME            NULL,
                scheduled_deletion_at  DATETIME     NULL,

                created_at  TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP,

                UNIQUE KEY unique_user (fullname, phone),
                INDEX idx_users_phone_fullname (phone, fullname),
                INDEX idx_users_email (email)
                ) ENGINE = InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                user_id             INT     NOT NULL,
                type           VARCHAR(20)  NOT NULL CHECK (type IN ('fees','donations','others')),
                month          VARCHAR(50),
                amount         FLOAT    NOT NULL  CHECK (amount > 0.0),
                date           DATETIME NOT NULL,

                updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

                INDEX idx_transactions_user_id (user_id),
                INDEX idx_transactions_type (type),
                INDEX idx_transactions_month (month),
                INDEX idx_transactions_amount (amount),
                INDEX idx_transactions_updated_at (updated_at),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE ON UPDATE CASCADE
                ) ENGINE = InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS verifications (
                verification_id   INT   NOT NULL AUTO_INCREMENT PRIMARY KEY,
                created_at  TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP,

                phone       VARCHAR(20) NOT NULL,
                phone_hash  CHAR(64) NOT NULL,
                phone_encrypted VARCHAR(255) NOT NULL,
                code        VARCHAR(10) NOT NULL  CHECK (code >= 1000 AND code <= 999999),
                ip_address  VARCHAR(45),

                INDEX idx_verifications_phone (phone),
                INDEX idx_verifications_ip_address (ip_address)
                ) ENGINE = InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS books (
                book_id INT AUTO_INCREMENT PRIMARY KEY,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                name         VARCHAR(255)         NOT NULL,
                class   VARCHAR(50),

                INDEX idx_books_class (class),
                FOREIGN KEY (name) REFERENCES global_translations(translation_text) ON DELETE RESTRICT ON UPDATE CASCADE
                ) ENGINE = InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;                           


CREATE TABLE IF NOT EXISTS interactions (
                interaction_id INT AUTO_INCREMENT PRIMARY KEY,
                user_id             INT NULL,
                device_id      VARCHAR(255) NOT NULL,
                device_brand   VARCHAR(255),
                ip_address     VARCHAR(45)  NOT NULL,
                open_times     INT  NOT NULL DEFAULT 1,
                os_version     VARCHAR(50),
                app_version    VARCHAR(50),

                created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

                UNIQUE KEY uniq_user_device (user_id, device_id(191)),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE ON UPDATE CASCADE,
                INDEX idx_interactions_device_id (device_id),
                INDEX idx_interactions_ip_address (ip_address),
                INDEX idx_interactions_user_id (user_id)
                ) ENGINE = InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS blocklist (
                block_id            INT             AUTO_INCREMENT PRIMARY KEY,
                basic_info          VARCHAR(50)     NOT NULL,
                additional_info     TEXT,
                threat          BOOLEAN         NOT NULL   DEFAULT 1,
                threat_level     VARCHAR(10)  NOT NULL CHECK (threat_level IN ('low','medium','high')) DEFAULT 'high',

                INDEX idx_blocklist_basic_info (basic_info),
                INDEX idx_blocklist_additional_info (additional_info(191)),
                INDEX idx_blocklist_threat (threat),
                INDEX idx_blocklist_threat_level (threat_level),

                created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE = InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS acc_types (
                user_id INT UNIQUE NOT NULL,
                main_type VARCHAR(20) NOT NULL CHECK (main_type IN ('admins','students','teachers','staffs','others','badri_members','donors')),
                teacher BOOLEAN NOT NULL DEFAULT 0,
                student BOOLEAN NOT NULL DEFAULT 0,
                staff BOOLEAN NOT NULL DEFAULT 0,
                donor BOOLEAN NOT NULL DEFAULT 0,
                badri_member BOOLEAN NOT NULL DEFAULT 0,
                special_member BOOLEAN NOT NULL DEFAULT 0,

                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

                INDEX idx_acc_types_main_type (main_type),
                INDEX idx_acc_types_teacher (teacher),
                INDEX idx_acc_types_student (student),
                INDEX idx_acc_types_staff (staff),
                INDEX idx_acc_types_donor (donor),
                INDEX idx_acc_types_badri_member (badri_member),

                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE ON UPDATE CASCADE
                ) ENGINE = InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

---------------------------------------------- MADRASAH SPECIFIC TABLES ----------------------------------------------

-- Create madrasa database if it doesn't exist  
CREATE DATABASE IF NOT EXISTS annur;
USE annur;

CREATE TABLE IF NOT EXISTS translations (
                translation_id      INT AUTO_INCREMENT PRIMARY KEY,
                translation_text    VARCHAR(255)   UNIQUE    NOT NULL,
                bn_text             VARCHAR(255)   NULL,
                ar_text             VARCHAR(255)   NULL,
                context             VARCHAR(100)   NOT NULL,
                table_name          VARCHAR(10)    NOT NULL,

                updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
                INDEX idx_global_translations_context (context)
                INDEX idx_global_translations_table_name (table_name)
                ) ENGINE = InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS peoples (
                    person_id            INT            NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    user_id              INT            NULL,
                    serial          INT              CHECK (serial >= 0),
                    student_id         INT              CHECK (student_id >= 0),
                    name               VARCHAR(255)     NOT NULL,
                    date_of_birth      DATE,
                    birth_certificate  VARCHAR(100),
                    birth_certificate_encrypted VARCHAR(255) NOT NULL,
                    national_id        VARCHAR(100),
                    national_id_encrypted VARCHAR(255) NOT NULL,
                    blood_group        VARCHAR(20),
                    gender             ENUM('male','female', 'others')  NOT NULL,
                    title1             VARCHAR(255),
                    title2             VARCHAR(255),
                    source             VARCHAR(255),
                    present_address    VARCHAR(255),
                    present_address_hash  CHAR(64) NOT NULL,
                    address            VARCHAR(255)    NULL,
                    address_hash  CHAR(64) NOT NULL,
                    permanent_address  VARCHAR(255),
                    permanent_address_hash  CHAR(64) NOT NULL,
                    father_or_spouse   VARCHAR(255),
                    father_name        VARCHAR(255)    NULL,
                    mother_name        VARCHAR(255)    NULL,
                    class              VARCHAR(100),
                    phone              VARCHAR(20)     NOT NULL,
                    guardian_number    VARCHAR(20),
                    available          BOOLEAN         DEFAULT 1,
                    degree             VARCHAR(50),
                    image_path         VARCHAR(255),
                    status             VARCHAR(50)  NOT NULL CHECK (status IN ('verified', 'pending', 'rejected')) DEFAULT 'pending',

                    INDEX idx_peoples_name_phone (name, phone),
                    INDEX idx_peoples_user_id (user_id),
                    INDEX idx_peoples_status (status),
                    INDEX idx_peoples_gender (gender),
                    INDEX idx_peoples_class (class),

                    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

                    UNIQUE KEY unique_person (name, phone),
                    FOREIGN KEY (user_id) REFERENCES global.users(user_id) ON DELETE SET NULL ON UPDATE CASCADE,
                    FOREIGN KEY (name) REFERENCES translations(translation_text) ON DELETE RESTRICT ON UPDATE CASCADE,
                    FOREIGN KEY (address) REFERENCES translations(translation_text) ON DELETE SET NULL ON UPDATE CASCADE,
                    FOREIGN KEY (father_name) REFERENCES translations(translation_text) ON DELETE SET NULL ON UPDATE CASCADE,
                    FOREIGN KEY (mother_name) REFERENCES translations(translation_text) ON DELETE SET NULL ON UPDATE CASCADE
                    ) ENGINE = InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS payments (
                payment_id     INT           NOT NULL AUTO_INCREMENT PRIMARY KEY,
                user_id        INT           NULL,
                food         BOOLEAN       NOT NULL,
                special_food BOOLEAN       NOT NULL,
                reduced_fee   FLOAT       DEFAULT 0.0    CHECK (reduced_fee >= 0.0),
                due_months   INT           NOT NULL     CHECK (due_months >= 0),
                tax           FLOAT           NOT NULL     CHECK (tax >= 0.0),

                updated_at   TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                created_at   TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

                INDEX idx_payments_user_id (user_id),
                INDEX idx_payments_special_food (special_food),
                INDEX idx_payments_reduced_fee (reduced_fee),
                INDEX idx_payments_due_months (due_months),
                INDEX idx_payments_updated_at (updated_at),
                FOREIGN KEY (user_id) REFERENCES global.users(user_id) ON DELETE SET NULL ON UPDATE CASCADE
                ) ENGINE = InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS routines (
                routine_id   INT    NOT NULL AUTO_INCREMENT PRIMARY KEY,
                created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

                gender       ENUM('male','female', 'others')  NOT NULL,
                class_group  VARCHAR(20)            NOT NULL,
                class_level  VARCHAR(30)            NOT NULL,
                weekday      ENUM('saturday','sunday','monday','tuesday','wednesday','thursday','friday') NOT NULL,
                subject      VARCHAR(255)           NOT NULL,
                name         VARCHAR(255)           NOT NULL,
                serial       INT                    NOT NULL CHECK (serial > 0),

                UNIQUE KEY unique_routine (class_group, class_level, weekday, serial),
                INDEX idx_routines_class_group (class_group),
                INDEX idx_routines_class_level (class_level),
                INDEX idx_routines_weekday (weekday),
                FOREIGN KEY (subject) REFERENCES translations(translation_text) ON DELETE RESTRICT ON UPDATE CASCADE,
                FOREIGN KEY (name) REFERENCES translations(translation_text) ON DELETE RESTRICT ON UPDATE CASCADE
                ) ENGINE = InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS exams (
                exam_id         INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
                created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

                book            VARCHAR(255)  NULL,
                class           VARCHAR(50)  NOT NULL,
                gender          ENUM('male','female', 'others')  NOT NULL,
                start_time      TIMESTAMP    NOT NULL,
                end_time        TIMESTAMP    NOT NULL,
                sec_start_time  TIMESTAMP,
                sec_end_time    TIMESTAMP,
                date            DATE         NOT NULL,
                weekday         ENUM('saturday','sunday','monday','tuesday','wednesday','thursday','friday') NOT NULL,
                                
                INDEX idx_exams_class (class),
                INDEX idx_exams_gender (gender),
                INDEX idx_exams_weekday (weekday),
                FOREIGN KEY (book) REFERENCES translations(translation_text) ON DELETE SET NULL ON UPDATE CASCADE
                ) ENGINE = InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS events (
                event_id     INT       AUTO_INCREMENT PRIMARY KEY,
                created_at   TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at   TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

                type         VARCHAR(20)  NOT NULL CHECK (type IN ('event', 'function')),
                title        VARCHAR(255)  NOT NULL,
                time         TIMESTAMP    NOT NULL,
                date         DATE         NOT NULL,
                function_url VARCHAR(255),

                INDEX idx_events_type (type),
                INDEX idx_events_title (title),
                FOREIGN KEY (title) REFERENCES translations(translation_text) ON DELETE RESTRICT ON UPDATE CASCADE
                ) ENGINE = InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

---------------------------------------------- LOG TABLES ----------------------------------------------

-- Create logs database if it doesn't exist  
CREATE DATABASE IF NOT EXISTS logs;
USE logs;

CREATE TABLE IF NOT EXISTS logs (
                log_id     INT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

                action     VARCHAR(100) NOT NULL,
                trace_info      VARCHAR(255),
                trace_info_hash  CHAR(64) NULL,
                trace_info_encrypted VARCHAR(255) NULL,
                level      VARCHAR(10)  NOT NULL CHECK (level IN ('info','warning','error','critical')) DEFAULT 'info',
                message    TEXT NOT NULL,
                metadata   JSON,

                INDEX idx_logs_trace_info (trace_info),
                INDEX idx_logs_action (action),
                INDEX idx_logs_created_at (created_at)
                ) ENGINE = InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;            

CREATE TABLE IF NOT EXISTS password_reset_logs (
                password_reset_log_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

                user_id INT NOT NULL,
                ip_address VARCHAR(255) NOT NULL,
                reset_method VARCHAR(255) NOT NULL,

                INDEX idx_password_reset_logs_user_id (user_id),
                INDEX idx_password_reset_logs_reset_method (reset_method)
                ) ENGINE = InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;