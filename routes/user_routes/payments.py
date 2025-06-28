from flask import request, jsonify
from . import user_routes
import pymysql
import pymysql.cursors
from datetime import datetime, timezone
from database import connect_to_db
from helpers import calculate_fees, format_phone_number
from logger import log_event

# ====== Payment Fee Info ======
@user_routes.route('/due_payment', methods=['POST'])
def payment():
    conn = connect_to_db()

    data = request.get_json()
    phone = data.get('phone')
    fullname = (data.get('fullname') or '').strip()

    if not phone or not fullname:
        log_event("payment_missing_fields", phone, "Phone or fullname missing")
        return jsonify({"error": "Phone and fullname are required"}), 400

    formatted_phone = format_phone_number(phone)

    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("""
            SELECT people.class, people.gender, payment.special_food, payment.reduce_fee,
                   payment.food, payment.due_months AS month, users.phone, users.fullname
            FROM users
            JOIN people ON people.id = users.id
            JOIN payment ON payment.id = users.id
            WHERE users.phone = %s AND LOWER(users.fullname) = LOWER(%s)
        """, (formatted_phone, fullname))
        result = cursor.fetchone()

    if not result:
        log_event("payment_user_not_found", formatted_phone, f"User {fullname} not found")
        return jsonify({"message": "User not found"}), 404


    # Extract data
    class_name = result['class']
    gender = result['gender']
    special_food = result['special_food']
    reduce_fee = result['reduce_fee']
    food = result['food']
    due_months = result['month']

    # Calculate fees
    fees = calculate_fees(class_name, gender, special_food, reduce_fee, food)

    return jsonify({"amount": fees, "month": due_months}), 200

# ====== Get Transaction History ======
@user_routes.route('/get_transactions', methods=['POST'])
def get_transactions():
    data = request.get_json() or {}
    phone            = data.get('phone')
    fullname         = (data.get('fullname') or '').strip()
    transaction_type = data.get('type')
    lastfetched      = data.get('updatedSince')

    # Required fields
    if not phone or not fullname or not transaction_type:
        log_event("payment_missing_fields", phone,
                  "Phone, fullname or transaction type missing")
        return jsonify({"error": "Phone, fullname and type are required"}), 400

    # Normalize phone
    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        log_event("payment_invalid_phone", phone, "Invalid phone format")
        return jsonify({"error": "Invalid phone number"}), 400

    # Build base query and params
    sql = """
      SELECT
        t.type,
        t.month     AS details,
        t.amount,
        t.date
      FROM transactions t
      JOIN users        u ON t.id = u.id
      WHERE u.phone = %s
        AND LOWER(u.fullname) = LOWER(%s)
        AND t.type = %s
    """
    params = [formatted_phone, fullname, transaction_type]

    # If updatedSince provided, parse & add to WHERE
    if lastfetched:
        try:
            cutoff = datetime.fromisoformat(
                lastfetched.replace("Z", "+00:00")
            )
            sql += " AND t.updated_at > %s"
            params.append(cutoff)
        except ValueError:
            log_event("payment_invalid_timestamp", formatted_phone, lastfetched)
            return jsonify({"error": "Invalid updatedSince format"}), 400

    # Final ordering
    sql += " ORDER BY t.date DESC"

    # Execute
    conn = connect_to_db()
    try:
        with conn.cursor(cursor=pymysql.cursors.DictCursor) as cursor:
            cursor.execute(sql, params)
            transactions = cursor.fetchall()
    except Exception as e:
        conn.rollback()
        log_event("payment_transaction_error", formatted_phone, str(e))
        return jsonify({"error": "Internal server error"}), 500
    finally:
        conn.close()

    # Handle no‐results
    if not transactions:
        return jsonify({"message": "No transactions found"}), 404

    # Normalize dates to ISO-8601 Z format
    for tx in transactions:
        d = tx.get("date")
        if isinstance(d, datetime):
            tx["date"] = d.astimezone(timezone.utc) \
                         .isoformat().replace("+00:00", "Z")

    # Return payload
    return jsonify({
        "transactions": transactions,
        "lastSyncedAt": datetime.now(timezone.utc)
                              .isoformat().replace("+00:00","Z")
    }), 200
