from quart import jsonify, current_app, request
from password_validator import PasswordValidator
import phonenumbers
from phonenumbers.phonenumberutil import NumberParseException
import random
import requests
import os , datetime
from dotenv import load_dotenv
from database import connect_to_db
from logger import log_event
import aiomysql
from aiomysql import IntegrityError
import json
from functools import wraps
from config import Config
import smtplib
from email.mime.text import MIMEText
import re
from quart_babel import gettext as _
import asyncio

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

def is_valid_api_key(api_key):
    default_api = os.getenv("API_KEY") or os.getenv("MADRASA_API_KEY")

    if not default_api:
        return True
    
    if not api_key:
        return False
        
    if api_key != default_api:
        return False
    else:
        return True

def is_maintenance_mode():
    check = None
    verify = os.getenv("MAINTENANCE_MODE", "")
    if verify == True or (isinstance(verify, str) and verify.lower() in ("true", "yes", "on")):
        check = True
    return check

async def blocker(info):
    conn = await connect_to_db()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT COUNT(*) AS blocked FROM blocklist WHERE need_check = 1")
            result = await cursor.fetchone()
            need_check = result["blocked"] if result else 0

            if need_check > 3:
                return True
            else:
                return None
    except IntegrityError as e:
        log_event("check_blocklist_failed", info, f"IntegrityError: {e}")
        return None
    except Exception as e:
        log_event("check_blocklist_failed", info, f"Error: {e}")
        return None
    finally:
        if conn:
            await conn.close()

async def is_device_unsafe(ip_address, device_id, info=None):
    dev_email = os.getenv("DEV_EMAIL")
    madrasa_email = os.getenv("EMAIL_ADDRESS")
    dev_phone = os.getenv("DEV_PHONE")
    madrasa_phone = os.getenv("MADRASA_PHONE")

    # Fix: Check if device info is missing (not present), not if it exists
    if not ip_address or not device_id:
        log_event("security_breach", ip_address or device_id or info, "need to take action")

        for email in [dev_email, madrasa_email]:
            if email:
                send_email(subject="Security Breach", body=f"""An Unknown device tried to access the app
                         \nip_address: {ip_address}
                         device_id: {device_id}
                         info: {info}
                         \n@An-Nur.app""", to_email=email)
            
        for phone in [dev_phone, madrasa_phone]:
            if phone:
                send_sms(phone=phone, msg=f"""Security Breach
                         \nAn Unknown device tried to access the app
                         \nip_address: {ip_address}
                         device_id: {device_id}
                         info: {info}
                         \n@An-Nur.app""")
        conn = await connect_to_db()
        basic_info = ip_address or device_id or "Basic Info Breached"
        additional_info = info or "NULL"
        try:
            async with conn.cursor() as cursor:
                await cursor.execute("INSERT INTO blocklist (basic_info, additional_info) VALUES (%s, %s)", (basic_info, additional_info))
                await conn.commit()
                return True
        except Exception as e:
            log_event("update_blocklist_failed", info, f"failed to update blocklist : {e}")
            return True
        finally:
            if conn:
                await conn.close()
    else:
        return False

async def delete_code():
    conn = await connect_to_db()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                """
                DELETE FROM verifications
                WHERE created_at < NOW() - INTERVAL 1 DAY
            """
            )
        await conn.commit()
    except Exception as e:
        log_event("failed to delete verifications", "Null", f"Database Error {str(e)}")
    finally:
        if conn:
            await conn.close()

def send_sms(phone, signature=None, code=None, msg=None, lang="en"):
    import requests

    asyncio.create_task(delete_code())
    TEXTBELT_URL = "https://textbelt.com/text"

    # Use translation if no custom message is provided
    if not msg:
        msg = _("Verification code sent to %(target)s") % {"target": phone}
        if code:
            msg += f"\n{_('Your code is: %(code)s') % {'code': code}}"
        msg += "\n\n@An-Nur.app"

    response = requests.post(TEXTBELT_URL, {
                'phone': phone,
                'message': msg,
                'key': os.getenv("TEXTBELT_KEY")
            })

    try:
        result = response.json()
        return result.get("success", False)
    except Exception as e:
        print("SMS Error:", e)
        log_event("sms_error", phone, str(e))
        return False


# Email Sender
def send_email(to_email, code=None, subject=None, body=None, lang="en"):
    asyncio.create_task(delete_code())
    
    EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
    EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "fallback-email")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "fallback-pass")

    # Use translation if no custom subject/body is provided
    if not subject:
        subject = _("Verification Email")
    if not body:
        body = ""
        if code:
            body += f"\n{_('Your code is: %(code)s') % {'code': code}}"
        body += "\n\n@An-Nur.app"

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

async def check_code(user_code, phone):
    CODE_EXPIRY_MINUTES = 10
    conn = await connect_to_db()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
                SELECT code, created_at FROM verifications
                WHERE phone = %s
                ORDER BY created_at DESC
                LIMIT 1
            """, (phone,))
            result = await cursor.fetchone()
            
            if not result:
                return jsonify({"message": "No verification code found"}), 404

            db_code = result["code"]
            created_at = result["created_at"]
            now = datetime.datetime.now()

            if (now - created_at).total_seconds() > CODE_EXPIRY_MINUTES * 60:
                return jsonify({"message": "Verification code expired"}), 410

            if int(user_code) == db_code:
                await delete_code()
                return None
            else:
                log_event("verification_failed", phone, "Code mismatch")
                return jsonify({"message": "Verification code mismatch"}), 400


    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500
    finally:
        if conn:
            await conn.close()

async def get_email(fullname, phone):
    conn = await connect_to_db()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""SELECT email FROM users 
                              WHERE fullname = %s AND phone = %s""", (fullname, phone))
            result = await cursor.fetchone()
            
            if result:
                return result['email']
            else:
                return None
    except Exception as e:
        log_event("db_error", phone, str(e))
        return None
    finally:
        if conn:
            await conn.close()

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

def validate_password(pwd):
    schema = PasswordValidator()
    schema.min(8).has().uppercase().has().lowercase().has().digits().has().no().spaces()
    if not schema.validate(pwd):
        return False, "Password must be at least 8 chars, with upper, lower, digit, no space"
    return True, ""

def validate_fullname(fullname):
    _FULLNAME_RE = re.compile(
    r'^(?!.*[\d])'                     # no digits
    r'(?!.*[!@#$%^&*()_+=-])'          # no forbidden special chars
    r'([A-Z][a-z]+)'                   # first word
    r'(?: [A-Z][a-z]+)*$'              # additional words
    )
    
    fullname = fullname.strip()

    
    if re.search(r'\d', fullname):
        return False, "Fullname shouldn’t contain digits"
    if re.search(r'[!@#$%^&*()_+=-]', fullname):
        return False, "Fullname shouldn’t contain special characters"

        
    if not _FULLNAME_RE.match(fullname):
        return False, "Fullname must be words starting with uppercase, followed by lowercase letters"

    return True, ""



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

async def get_id(phone, fullname):
    conn = await connect_to_db()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT id FROM users WHERE phone = %s AND fullname = %s", (phone, fullname))
            result = await cursor.fetchone()
            return result['id'] if result else None
    finally:
        if conn:
            await conn.close()

async def insert_person(fields: dict, acc_type, phone):
    conn = await connect_to_db()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
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
            await cursor.execute(sql, list(fields.values()))

            # Conditional insert for verify_people
            if acc_type in ['students', 'teachers', 'staffs', 'admins']:
                verify_sql = f"""
                    INSERT IGNORE INTO verify_people ({columns}) 
                    VALUES ({placeholders})
                """
                await cursor.execute(verify_sql, list(fields.values()))
                
        await conn.commit()
        log_event("insert_success", phone, "Upserted into people and conditionally inserted into verify_people")
    except Exception as e:
        await conn.rollback()
        log_event("db_insert_error", phone, str(e))
        raise
    finally:
        if conn:
            await conn.close()

async def delete_users(uid=None, acc_type=None):
    conn = await connect_to_db()
    try:
        if not uid and not acc_type:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute("""
                    SELECT u.id, p.acc_type 
                    FROM users u
                    JOIN people p ON u.id = p.id
                    WHERE u.scheduled_deletion_at IS NOT NULL
                    AND u.scheduled_deletion_at < NOW()
                """)
                users_to_delete = await cursor.fetchall()
        else:
            users_to_delete = [{'id': uid, 'acc_type': acc_type}]
            
            for user in users_to_delete:
                uid = user["id"]
                acc_type = user["acc_type"]

                if acc_type not in ['students', 'teachers', 'staffs', 'admins', 'badri_members']:
                    await cursor.execute("DELETE FROM people WHERE id = %s", (uid,))
                else:
                    await cursor.execute("""UPDATE people
                            SET 
                                date_of_birth = NULL,
                                birth_certificate = NULL,
                                national_id = NULL,
                                source = NULL,
                                present_address = NULL,
                                permanent_address = NULL,
                                father_or_spouse = NULL,
                                mother_en = NULL,
                                mother_bn = NULL,
                                mother_ar = NULL,
                                guardian_number = NULL,
                                available = NULL,
                                is_donor = NULL,
                                is_badri_member = NULL,
                                is_foundation_member = NULL
                            WHERE id = %s
                            """, (uid,))
                await cursor.execute("DELETE FROM transactions WHERE id = %s", (uid,))
                await cursor.execute("DELETE FROM verifications WHERE id = %s", (uid,))
                await cursor.execute("DELETE FROM users WHERE id = %s", (uid,))
        await conn.commit()
        
    except IntegrityError as e:
        log_event("auto_delete_error", "Null", f"IntegrityError: {e}")
        return True
    except Exception as e:
        log_event("auto_delete_error", "Null", str(e))
        return True
    finally:
        if conn:
            await conn.close()


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


