from flask import jsonify, current_app, request
from password_validator import PasswordValidator
import phonenumbers
from phonenumbers.phonenumberutil import NumberParseException
import random
import requests
import os , datetime
from dotenv import load_dotenv
from database import connect_to_db
from logger import log_event
import pymysql
import pymysql.cursors
import json
from functools import wraps
from config import Config
import smtplib
from email.mime.text import MIMEText
import re


# ─── Compute Upload Folder ───────────
load_dotenv()

EXAM_DIR     = Config.EXAM_DIR
EXAM_RESULT_INDEX_FILE   = os.path.join(EXAM_DIR, 'index.json')
ALLOWED_EXAM_EXTENSIONS = Config.ALLOWED_EXAM_EXTENSIONS

NOTICES_DIR = Config.NOTICES_DIR
NOTICES_INDEX_FILE = os.path.join(NOTICES_DIR, 'index.json')
ALLOWED_NOTICE_EXTENSIONS = Config.ALLOWED_NOTICE_EXTENSIONS

os.makedirs(EXAM_DIR, exist_ok=True)
if not os.path.exists(EXAM_RESULT_INDEX_FILE):
    with open(EXAM_RESULT_INDEX_FILE, 'w') as f:
        json.dump([], f)

os.makedirs(NOTICES_DIR, exist_ok=True)
if not os.path.exists(NOTICES_INDEX_FILE):
    with open(NOTICES_INDEX_FILE, 'w') as f:
        json.dump([], f)




# ------------------------------- User ----------------------------------------

# Api_token_Protection
# TODO
# add @require_api_key after every user_routes
def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get('X-API-KEY')
        if not key or key != current_app.config.get('API_KEY'):
            return jsonify({"message": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

# Delete Code
def delete_code():
    conn = connect_to_db()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                """
                DELETE FROM verifications
                WHERE created_at < NOW() - INTERVAL 1 DAY
            """
            )
        conn.commit()
    except Exception as e:
        log_event("failed to delete verifications", "Null", f"Database Error {str(e)}")
    finally:
        conn.close()

# SMS Sender
def send_sms(phone, code, signature):
    delete_code()
    TEXTBELT_URL = "https://textbelt.com/text"

    try:
        response = requests.post(TEXTBELT_URL, {
            'phone': phone,
            'message': f"Your verification code is: {code}\n@annur.app #{signature}",
            'key': os.getenv("TEXTBELT_KEY")
        })
        result = response.json()
        return result.get("success", False)
    except Exception as e:
        print("SMS Error:", e)
        log_event("sms_error", phone, str(e))
        return False


# Email Sender
def send_email(to_email, code=None, subject=None, body=None):
    delete_code()
    
    EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
    EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "fallback-email")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "fallback-pass")

    if not subject or not body:
        subject = "Your Verification Code"
        body = f"Your verification code is: {code}\n@annur.app"

    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = to_email

        server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print("Email Error:", e)
        log_event("email_error", to_email, str(e))
        return False
    

# Code Generator
def generate_code():
    return random.randint(100000, 999999)

# Check Code
def check_code(user_code, phone):
    CODE_EXPIRY_MINUTES = 10
    conn = connect_to_db()

    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                SELECT code, created_at FROM verifications
                WHERE phone = %s
                ORDER BY created_at DESC
                LIMIT 1
            """, (phone,))
            result = cursor.fetchone()

            if not result:
                return jsonify({"message": "No verification code found"}), 404

            db_code = result["code"]
            created_at = result["created_at"]
            now = datetime.datetime.now()

            if (now - created_at).total_seconds() > CODE_EXPIRY_MINUTES * 60:
                return jsonify({"message": "Verification code expired"}), 410

            if int(user_code) == db_code:
                delete_code()
                return None
            else:
                log_event("verification_failed", phone, "Code mismatch")
                return jsonify({"message": "Verification code mismatch"}), 400


    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500
    finally:
        conn.close()


# Phone formatter
import phonenumbers
from phonenumbers import NumberParseException

def format_phone_number(phone):
    if not phone:
        return None

    phone = phone.strip().replace(" ", "").replace("-", "")

    if phone.startswith("8801") and len(phone) == 13:
        # User entered "8801..." without plus ➜ add "+"
        phone = "+" + phone
    elif phone.startswith("01") and len(phone) == 11:
        # User entered local BD number ➜ add "+880"
        phone = "+88" + phone
    elif not phone.startswith("+"):
        # Foreign number but no + ➜ invalid (force +<countrycode> for non-BD)
        return None

    try:
        number = phonenumbers.parse(phone, None)
        if not phonenumbers.is_valid_number(number):
            return None
        return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
    except NumberParseException:
        return None


# Password Validator
def validate_password(pwd):
    schema = PasswordValidator()
    schema.min(8).has().uppercase().has().lowercase().has().digits().has().no().spaces()
    if not schema.validate(pwd):
        return False, "Password must be at least 8 chars, with upper, lower, digit, no space"
    return True, ""

# Fullname Validator
def validate_fullname(fullname):
    _FULLNAME_RE = re.compile(
    r'^(?!.*[\d])'                     # no digits
    r'(?!.*[!@#$%^&*()_+=-])'          # no forbidden special chars
    r'([A-Z][a-z]+)'                   # first word
    r'(?: [A-Z][a-z]+)*$'              # additional words
    )
    
    fullname = fullname.strip()

    # 1) Quick checks for specific errors
    if re.search(r'\d', fullname):
        return False, "Fullname shouldn’t contain digits"
    if re.search(r'[!@#$%^&*()_+=-]', fullname):
        return False, "Fullname shouldn’t contain special characters"

    # 2) Full regex for proper casing & spacing
    if not _FULLNAME_RE.match(fullname):
        return False, "Fullname must be words starting with uppercase, followed by lowercase letters"

    return True, ""


# Fee Calculation
def calculate_fees(class_name, gender, special_food, reduce_fee, food):
    total = 0
    class_lower = class_name.lower()

    if food == 1:
        total += 2400
    if special_food == 1:
        total += 3000

    if gender.lower() == 'male':
        if class_lower in ['class 3', 'class 2']:
            total += 1600
        elif class_lower in ['hifz', 'nazara']:
            total += 1800
        else:
            total += 1300
    elif gender.lower() == 'female':
        if class_lower == 'nursery':
            total += 800
        elif class_lower == 'class 1':
            total += 1000
        elif class_lower == 'hifz':
            total += 2000
        elif class_lower in ['class 2', 'class 3', 'nazara']:
            total += 1200
        else:
            total += 1500

    if reduce_fee:
        total -= reduce_fee

    return total

# Fetch ID
def get_id(phone, fullname):
    conn = connect_to_db()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT id FROM users WHERE phone = %s AND fullname = %s", (phone, fullname))
            result = cursor.fetchone()
            return result['id'] if result else None
    finally:
        conn.close()

# Insert People
def insert_person(fields: dict, acc_type, phone):
    conn = connect_to_db()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Prepare fields
            columns = ', '.join(fields.keys())
            placeholders = ', '.join(['%s'] * len(fields))

            # Only update non-identity or safe fields (exclude 'id', 'created_at', etc.)
            updatable_fields = [col for col in fields.keys() if col not in ('id', 'created_at')]
            updates = ', '.join([f"{col} = VALUES({col})" for col in updatable_fields])

            # UPSERT for people
            sql = f"""
                INSERT INTO people ({columns}) 
                VALUES ({placeholders}) 
                ON DUPLICATE KEY UPDATE {updates}
            """
            cursor.execute(sql, list(fields.values()))

            # Conditional insert for verify_people
            if acc_type in ['students', 'teachers', 'staffs', 'admins']:
                # Safe: insert only if not exists
                verify_sql = f"""
                    INSERT IGNORE INTO verify_people ({columns}) 
                    VALUES ({placeholders})
                """
                cursor.execute(verify_sql, list(fields.values()))

        conn.commit()
        log_event("insert_success", phone, "Upserted into people and conditionally inserted into verify_people")
    except pymysql.MySQLError as e:
        conn.rollback()
        log_event("db_insert_error", phone, str(e))
        raise
    finally:
        conn.close()


# ------------------------------------ Admin -------------------------------------------


def load_results():
    with open(EXAM_RESULT_INDEX_FILE, 'r') as f:
        return json.load(f)

def save_results(data):
    with open(EXAM_RESULT_INDEX_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def allowed_exam_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXAM_EXTENSIONS


def load_notices():
    try:
        with open(NOTICES_INDEX_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        # auto-fix broken JSON
        with open(NOTICES_INDEX_FILE, 'w') as f:
            json.dump([], f)
        return []


def save_notices(data):
    with open(NOTICES_INDEX_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def allowed_notice_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_NOTICE_EXTENSIONS


