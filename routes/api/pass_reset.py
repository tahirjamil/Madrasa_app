from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import random
import requests
import datetime
from pymysql.cursors import DictCursor
from database import connect_to_db

# Blueprint
reset_routes = Blueprint("reset_routes", __name__)

# ====== MySQL Connection ======
conn = connect_to_db()
cursor = conn.cursor(DictCursor)

TEXTBELT_URL = "https://textbelt.com/text"
CODE_EXPIRY_MINUTES = 10
SEND_LIMIT_PER_HOUR = 3


def generate_code():
    return random.randint(1000, 9999)


def send_sms(phone, code):
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


@reset_routes.route("/send_code", methods=["POST"])
def send_code():
    data = request.get_json()
    phone = data.get("phone")

    if not phone:
        return jsonify({"message": "Phone number required"}), 400

    try:
        # Limit check: only 3 codes allowed per hour
        cursor.execute("""
            SELECT COUNT(*) AS recent_count 
            FROM verifications 
            WHERE phone = %s AND created_at > NOW() - INTERVAL 1 HOUR
        """, (phone,))
        count_result = cursor.fetchone()

        if not count_result or count_result.get("recent_count", 0) >= SEND_LIMIT_PER_HOUR:
            return jsonify({"message": "Limit reached. Try again later."}), 429

        code = generate_code()
        cursor.execute("INSERT INTO verifications (phone, code) VALUES (%s, %s)", (phone, code))
        conn.commit()

        if send_sms(phone, code):
            return jsonify({"message": f"Verification code sent to {phone}"}), 200
        else:
            return jsonify({"message": "Failed to send SMS"}), 500

    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500


@reset_routes.route("/check_code", methods=["POST"])
def check_code():
    data = request.get_json()
    phone = data.get("phone")
    user_code = data.get("code")

    if not phone or not user_code:
        return jsonify({"message": "Phone and code required"}), 400

    try:
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

        if (now - created_at).total_seconds() > CODE_EXPIRY_MINUTES * 60:
            return jsonify({"message": "Code expired"}), 410

        if int(user_code) == db_code:
            return jsonify({"status": "success"}), 200
        else:
            return jsonify({"message": "Code mismatched"}), 400

    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500


@reset_routes.route("/reset_password", methods=["POST"])
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

            if (now - created_at).total_seconds() > CODE_EXPIRY_MINUTES * 60:
                return jsonify({"message": "Code expired"}), 410

            if int(user_code) != db_code:
                return jsonify({"message": "Code mismatched"}), 400

            cursor.execute("UPDATE users SET password = %s WHERE fullname = %s AND phone = %s",
                        (hashed_password, fullname, phone))
            conn.commit()
            return jsonify({"message": "Password reset successful"}), 200

        except Exception as e:
            return jsonify({"message": f"Error: {str(e)}"}), 500
        
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