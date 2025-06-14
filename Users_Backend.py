from flask import Flask, request, jsonify 
from flask_cors import CORS
import pymysql
import pymysql.cursors
from pymysql.err import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
import phonenumbers
from phonenumbers.phonenumberutil import NumberParseException

app = Flask(__name__)
CORS(app)

# Database setup
conn = pymysql.connect(
    host="localhost",
    user="tahir",
    password="tahir",
    database="madrashadb",
    cursorclass=pymysql.cursors.DictCursor  # Optional: easier fetch with dicts
)
cursor = conn.cursor()

# Create table if not exists
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    fullname VARCHAR(50),
    phone VARCHAR(20),
    password TEXT,
    UNIQUE KEY unique_user (fullname, phone)
)
""")
conn.commit()

def validate_fullname(fullname):
    special_characters = "!@#$%^&*()_+=-"
    words = fullname.strip().split()
    
    for word in words:
        if not any(char.isupper() for char in word):
            return jsonify({"message": "Fullname should have Proper Uppercase letter"}), 400
    if any(char.isdigit() for char in fullname):
        return jsonify({"message": "Fullname shouldn't contain digits"}), 400
    elif any(char in special_characters for char in fullname):
        return jsonify({"message": "Fullname shouldn't contain special characters"}), 400
    return None

def validate_password(password):
    if len(password) < 8 or len(password) > 20:
        return jsonify({"message": "Password should be between 8 and 20 characters"}), 400
    elif not any(char.isdigit() for char in password):
        return jsonify({"message": "Password should contain at least 1 digit"}), 400
    return None

# Phone validation and formatting
def format_phone_number(phone, region="BD"):
    try:
        number = phonenumbers.parse(phone, region)
        if not phonenumbers.is_valid_number(number):
            return None
        return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
    except NumberParseException:
        return None

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    fullname = data.get("fullname")
    phone = data.get("phone")
    password = data.get("password")

    if not fullname or not phone or not password:
        return jsonify({"message": "All fields are required"}), 400
    
    # Validate inputs
    for validator in (validate_fullname(fullname), validate_password(password)):
        if validator:
            return validator

    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        return jsonify({"message": "Invalid phone number format"}), 400

    hashed_password = generate_password_hash(password)

    try:
        cursor.execute(
            "INSERT INTO users (fullname, phone, password) VALUES (%s, %s, %s)",
            (fullname, formatted_phone, hashed_password)
        )
        conn.commit()
        return jsonify({"success": "Registration successful"}), 201
    except IntegrityError:
        return jsonify({"message": "User with this fullname and phone already registered"}), 400

@app.route("/login", methods=["POST"])
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

if __name__ == "__main__":
    app.run(debug=True)
