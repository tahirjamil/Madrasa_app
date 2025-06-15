from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from pymysql.err import IntegrityError
import phonenumbers
from phonenumbers.phonenumberutil import NumberParseException
import random
import datetime
from mysql import connect_to_db

# Blueprint
user_routes = Blueprint("user_routes", __name__)

# Connect DB
conn = connect_to_db()

# Helper: Phone formatter
def format_phone_number(phone, region="BD"):
    try:
        number = phonenumbers.parse(phone, region)
        if not phonenumbers.is_valid_number(number):
            return None
        return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
    except NumberParseException:
        return None

# Validation helpers
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

def validate_password(password):
    if len(password) < 8 or len(password) > 20:
        return jsonify({"message": "Password should be between 8 and 20 characters"}), 400
    if not any(c.isdigit() for c in password):
        return jsonify({"message": "Password should contain at least 1 digit"}), 400
    return None

def verification_code():
    return random.randint(1000, 9999)

# ========== Routes ==========

@user_routes.route("/register_code", methods=["POST"])
def send_code():
    data = request.get_json()
    fullname = data.get("fullname")
    phone = data.get("phone")
    password = data.get("password")

    if not fullname or not phone or not password:
        return jsonify({"message": "All fields are required"}), 400

    if (v := validate_fullname(fullname)): return v
    if (v := validate_password(password)): return v

    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        return jsonify({"message": "Invalid phone number format"}), 400

    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM users WHERE phone = %s AND fullname = %s", (formatted_phone, fullname))
        if cursor.fetchone():
            return jsonify({"message": "User already registered"})

        cursor.execute("""
            SELECT COUNT(*) AS recent_count 
            FROM verifications 
            WHERE phone = %s AND created_at > NOW() - INTERVAL 1 HOUR
        """, (formatted_phone,))
        result = cursor.fetchone()
        count = result['recent_count'] if result else 0

        if count >= 3:
            return jsonify({"message": "Limit reached. Try again later."}), 429

        code = verification_code()
        cursor.execute("INSERT INTO verifications (phone, code) VALUES (%s, %s)", (formatted_phone, code))
        conn.commit()

    print(f"Sending code {code} to {formatted_phone}")
    return jsonify({"success": f"Verification code sent to {formatted_phone}"}), 200


@user_routes.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    fullname = data.get("fullname")
    phone = data.get("phone")
    password = data.get("password")
    user_code = data.get("code")

    if not fullname or not phone or not password or not user_code:
        return jsonify({"message": "All fields including code are required"}), 400

    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        return jsonify({"message": "Invalid phone number format"}), 400

    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT code, created_at FROM verifications 
            WHERE phone = %s 
            ORDER BY created_at DESC 
            LIMIT 1
        """, (formatted_phone,))
        result = cursor.fetchone()

        if not result:
            return jsonify({"message": "No verification code found"}), 404

        if (datetime.datetime.now() - result["created_at"]).total_seconds() > 600:
            return jsonify({"message": "Verification code expired"}), 410
        if int(user_code) != result["code"]:
            return jsonify({"message": "Verification code mismatch"}), 400

        hashed_password = generate_password_hash(password)

        try:
            cursor.execute(
                "INSERT INTO users (fullname, phone, password) VALUES (%s, %s, %s)",
                (fullname, formatted_phone, hashed_password)
            )
            conn.commit()

            cursor.execute(
                "SELECT id FROM users WHERE fullname = %s AND phone = %s",
                (fullname, formatted_phone)
            )
            result = cursor.fetchone()
            user_id = result['id'] if result else None

            cursor.execute(
                "SELECT * FROM people WHERE name_en = %s AND phone = %s",
                (fullname, formatted_phone)
            )
            if cursor.fetchone():
                cursor.execute(
                    "UPDATE people SET id = %s WHERE name_en = %s AND phone = %s",
                    (user_id, fullname, formatted_phone)
                )
                conn.commit()

            return jsonify({"success": "Registration successful"}), 201

        except IntegrityError:
            return jsonify({"message": "User with this fullname and phone already registered"}), 400
        except Exception as e:
            return jsonify({"message": "Internal server error", "error": str(e)}), 500


@user_routes.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    fullname = data.get("fullname")
    phone = data.get("phone")
    password = data.get("password")

    if not fullname or not phone or not password:
        return jsonify({"message": "All fields are required"}), 400

    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        return jsonify({"message": "Invalid phone number format"}), 400

    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT password FROM users WHERE phone = %s AND fullname = %s",
            (formatted_phone, fullname)
        )
        result = cursor.fetchone()

        if not result:
            return jsonify({"message": "User not found"}), 404
        if check_password_hash(result['password'], password):
            return jsonify({"success": "Login successful"}), 200
        else:
            return jsonify({"message": "Incorrect password"}), 401
