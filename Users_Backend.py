from flask import Flask, request, jsonify 
from flask_cors import CORS
from pymysql.err import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
import phonenumbers
from phonenumbers.phonenumberutil import NumberParseException
import random
from mysql import connect_to_db, create_tables

app = Flask(__name__)
CORS(app)

# Code generator
def verification_code():
    return random.randint(1000, 9999)

# ====== MySQL Connection ======
conn = connect_to_db()
create_tables()

# ------------------ Validation ------------------

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

def format_phone_number(phone, region="BD"):
    try:
        number = phonenumbers.parse(phone, region)
        if not phonenumbers.is_valid_number(number):
            return None
        return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
    except NumberParseException:
        return None
    

# ------------------Send code-------------------
@app.route("/register_code", methods=["POST"])
def send_code():
    data = request.get_json()
    fullname = data.get("fullname")
    phone = data.get("phone")
    password = data.get("password")

    # Validate fields
    if not fullname or not phone or not password:
        return jsonify({"message": "All fields are required"}), 400

    fullname_validation = validate_fullname(fullname)
    if fullname_validation:
        return fullname_validation

    password_validation = validate_password(password)
    if password_validation:
        return password_validation

    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        return jsonify({"message": "Invalid phone number format"}), 400
    
    # Check if user already exists
    with conn.cursor() as cursor:
        cursor.execute("""SELECT * FROM users WHERE phone = %s and fullname = %s""", (formatted_phone, fullname))
        result = cursor.fetchone()
        if result:
            return jsonify({"message": "User already registered"})

    # Limit SMS to 3 per hour
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) AS recent_count 
            FROM verifications 
            WHERE phone = %s AND created_at > NOW() - INTERVAL 1 HOUR
        """, (formatted_phone,))
        count_result = cursor.fetchone()
        recent_count = count_result['recent_count'] if count_result and 'recent_count' in count_result else 0

        if recent_count >= 3:
            return jsonify({"message": "Limit reached. Try again later."}), 429

        # Generate and store code
        code = verification_code()
        cursor.execute(
            "INSERT INTO verifications (phone, code) VALUES (%s, %s)",
            (formatted_phone, code)
        )
        conn.commit()

    # Simulate sending SMS (you can replace this with your real function)
    print(f"Sending code {code} to {formatted_phone}")  # Optional debug

    return jsonify({"success": f"Verification code sent to {formatted_phone}"}), 200


# ------------------ Register ------------------

@app.route("/register", methods=["POST"])
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

    # --- Verify code ---
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

        import datetime
        now = datetime.datetime.now()
        created_at = result["created_at"]
        if (now - created_at).total_seconds() > 600:
            return jsonify({"message": "Verification code expired"}), 410

        if int(user_code) != result["code"]:
            return jsonify({"message": "Verification code mismatch"}), 400

    # --- Proceed to register ---
    hashed_password = generate_password_hash(password)

    try:
        with conn.cursor() as cursor:
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
            if not user_id:
                return jsonify({"message": "Failed to retrieve user ID"}), 500

            # Update 'people' table if the person exists
            cursor.execute(
                "SELECT * FROM people WHERE name_en = %s AND phone = %s",
                (fullname, formatted_phone)
            )
            existing = cursor.fetchone()
            if existing:
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

# ------------------ Login ------------------

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

# ------------------ Run App ------------------

if __name__ == "__main__":
    app.run(debug=True)
