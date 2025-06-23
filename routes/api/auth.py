from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from pymysql.err import IntegrityError
import datetime
from database import connect_to_db
from helpers import validate_fullname, validate_password, send_sms, format_phone_number, generate_code

# Blueprint
api_auth_routes = Blueprint("api_auth_routes", __name__)

# Connect DB
conn = connect_to_db()

# Check Code
def check_code(code, phone):
    CODE_EXPIRY_MINUTES = 10

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

            if int(code) == db_code:
                return None
            else:
                return jsonify({"message": "Verification code mismatch"}), 400

    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500


# ========== Routes ==========
@api_auth_routes.route("/register", methods=["POST"])
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
            conn.commit()

            cursor.execute(
                "SELECT * FROM people WHERE LOWER(name_en) = LOWER(%s) AND phone = %s",
                (fullname, formatted_phone)
            )
            people_result = cursor.fetchone()

            if people_result:
                cursor.execute(
                    "UPDATE people SET id = %s WHERE LOWER(name_en) = LOWER(%s) AND phone = %s",
                    (user_id, fullname, formatted_phone)
                )
                conn.commit()

            return jsonify({"success": "Registration successful"}), 201

        except IntegrityError:
            return jsonify({"message": "User with this fullname and phone already registered"}), 400
        except Exception as e:
            return jsonify({"message": "Internal server error", "error": str(e)}), 500


@api_auth_routes.route("/login", methods=["POST"])
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
        

@api_auth_routes.route("/send_code", methods=["POST"])
def send_verification_code():
    SEND_LIMIT_PER_HOUR = 3
    data = request.get_json()
    phone = data.get("phone")
    fullname = data.get("fullname")
    password = data.get("password")

    if not phone:
        return jsonify({"message": "Phone number required"}), 400

    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        return jsonify({"message": "Invalid phone number format"}), 400

    try:
        with conn.cursor() as cursor:
            if fullname and password:
                if (v := validate_fullname(fullname)): return v
                if (v := validate_password(password)): return v

                cursor.execute("SELECT * FROM users WHERE phone = %s AND fullname = %s", (formatted_phone, fullname))
                if cursor.fetchone():
                    return jsonify({"message": "User already registered"}), 409

            # Rate limit check
            cursor.execute("""
                SELECT COUNT(*) AS recent_count 
                FROM verifications 
                WHERE phone = %s AND created_at > NOW() - INTERVAL 1 HOUR
            """, (formatted_phone,))
            result = cursor.fetchone()
            count = result["recent_count"] if result else 0

            if count >= SEND_LIMIT_PER_HOUR:
                return jsonify({"message": "Limit reached. Try again later."}), 429

            # Send verification code
            code = generate_code()
            cursor.execute("INSERT INTO verifications (phone, code) VALUES (%s, %s)", (formatted_phone, code))
            conn.commit()

        if send_sms(formatted_phone, code):
            return jsonify({"success": f"Verification code sent to {formatted_phone}"}), 200
        else:
            return jsonify({"message": "Failed to send SMS"}), 500

    except Exception as e:
        return jsonify({"message": f"Internal error: {str(e)}"}), 500




@api_auth_routes.route("/reset_password", methods=["POST"])
def reset_password():
    data = request.get_json()
    phone = data.get("phone")
    fullname = data.get("fullname")
    user_code = data.get("code")
    old_password = data.get("old_password")
    new_password = data.get("new_password")
    hashed_password = generate_password_hash(new_password)

    if not all([phone, fullname, new_password]):
        return jsonify({"message": "All fields required"}), 400
    
    if not old_password:
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
                    return jsonify({"message": "No code found"}), 404

                db_code = result["code"]
                created_at = result["created_at"]
                now = datetime.datetime.now()

                if (now - created_at).total_seconds() > 600:
                    return jsonify({"message": "Code expired"}), 410

                if int(user_code) != db_code:
                    return jsonify({"message": "Code mismatched"}), 400

                cursor.execute("UPDATE users SET password = %s WHERE fullname = %s AND phone = %s",
                            (hashed_password, fullname, phone))
                conn.commit()
                return jsonify({"message": "Password reset successful"}), 200

        except Exception as e:
            return jsonify({"message": f"Error: {str(e)}"}), 500
    
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT password FROM users WHERE phone = %s AND fullname = %s",
            (phone, fullname)
        )
        result = cursor.fetchone()
        if not result:
            return jsonify({"message": "User not found"}), 404

        if check_password_hash(result['password'], old_password):
            cursor.execute("UPDATE users SET password = %s WHERE fullname = %s AND phone = %s",
                            (hashed_password, fullname, phone))
            
            conn.commit()
            return jsonify({"message": "Password reset successful"}), 200
        else:
            return jsonify({"message": "Incorrect password"}), 401