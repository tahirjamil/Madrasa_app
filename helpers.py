from flask import jsonify
from password_validator import PasswordValidator
import phonenumbers
from phonenumbers.phonenumberutil import NumberParseException
import random
import requests
import os , datetime
from dotenv import load_dotenv
from database import connect_to_db
from logger import log_event


load_dotenv()

# Check Code
def check_code(user_code, phone):
    CODE_EXPIRY_MINUTES = 10
    conn = connect_to_db()

    try:
        with conn.cursor() as cursor:
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
                return None
            else:
                log_event("verification_failed", phone, "Code mismatch")
                return jsonify({"message": "Verification code mismatch"}), 400


    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500


# Phone formatter
def format_phone_number(phone, region="BD"):
    try:
        number = phonenumbers.parse(phone, region)
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
    special_chars = "!@#$%^&*()_+=-"
    words = fullname.strip().split()

    if not all(any(c.isupper() for c in word) for word in words):
        return False, "Fullname should have Proper Uppercase letter"
    if any(c.isdigit() for c in fullname):
        return False, "Fullname shouldn’t contain digits"
    if any(c in special_chars for c in fullname):
        return False, "Fullname shouldn’t contain special characters"

    return True, ""

# Code Generator
def generate_code():
    return random.randint(1000, 9999)

# SMS Sender
def send_sms(phone, code):
    TEXTBELT_URL = "https://textbelt.com/text"

    try:
        response = requests.post(TEXTBELT_URL, {
            'phone': phone,
            'message': f"Your verification code is: {code}",
            'key': os.getenv("TEXTBELT_KEY")
        })
        result = response.json()
        return result.get("success", False)
    except Exception as e:
        print("SMS Error:", e)
        return False


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
        total - reduce_fee

    return total