from flask import request, jsonify
from . import user_routes
import pymysql
import pymysql.cursors
from datetime import datetime, timezone
from database import connect_to_db
from helpers import format_phone_number
from logger import log_event


# ====== Save Payment Transaction ======
@user_routes.route('/add_transaction', methods=['POST'])
def transaction():
    conn = connect_to_db()

    data = request.get_json()
    phone = data.get('phone')
    fullname = (data.get('fullname') or '').strip()
    transaction_type = data.get('type')
    amount = data.get('amount')
    months = data.get('months')

    if not phone or not fullname or amount is None or transaction_type is None:
        log_event("payment_missing_fields", phone, "Missing fields")
        return jsonify({"error": "Phone, fullname, type and amount are required"}), 400
    
    formatted_phone = format_phone_number(phone)

    if isinstance(months, list):
        months = ', '.join(months)  # handle multiple months

    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("SELECT id FROM users WHERE phone = %s AND LOWER(fullname) = (%s)", (formatted_phone, fullname))
        user = cursor.fetchone()

    if not user:
        log_event("payment_user_not_found", formatted_phone, f"User {fullname} not found")
        return jsonify({"message": "User not found"}), 404


    user_id = user['id']
    current_date = datetime.today().strftime('%Y-%m-%d')

    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                INSERT INTO transactions (id, type, month, amount, date)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, transaction_type, months, amount, current_date))
            conn.commit()
        return jsonify({"message": "Transaction successful"}), 201
    except Exception as e:
        conn.rollback()
        log_event("payment_insert_failed", phone, f"DB Error: {str(e)}")
        return jsonify({"error": "Transaction failed"}), 500
    finally:
        conn.close()