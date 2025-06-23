from flask import jsonify
from password_validator import PasswordValidator
import phonenumbers
from phonenumbers.phonenumberutil import NumberParseException
import random
import requests


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
    schema \
        .min(8) \
        .has().uppercase() \
        .has().lowercase() \
        .has().digits() \
        .has().no().spaces()

# Code Generator
def generate_code():
    return random.randint(1000, 9999)
    
# Fullname Validator
def validate_fullname(fullname):
    special_chars = "!@#$%^&*()_+=-"
    words = fullname.strip().split()
    if not all(any(c.isupper() for c in word) for word in words):
        return jsonify({"message": "Fullname should have Proper Uppercase letter"}), 400
    if any(c.isdigit() for c in fullname):
        return jsonify({"message": "Fullname shouldn't contain digits"}), 400
    if any(c in special_chars for c in fullname):
        return jsonify({"message": "Fullname shouldn't contain special characters"}), 400
    return None

# SMS Sender
def send_sms(phone, code):
    TEXTBELT_URL = "https://textbelt.com/text"

    try:
        response = requests.post(TEXTBELT_URL, {
            'phone': phone,
            'message': f"Your verification code is: {code}",
            'key': 'textbelt'
        })
        result = response.json()
        return result.get("success", False)
    except Exception as e:
        print("SMS Error:", e)
        return False
