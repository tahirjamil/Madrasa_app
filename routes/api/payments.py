from flask import Blueprint, request, jsonify
from datetime import datetime
from database import connect_to_db
from helpers import calculate_fees, format_phone_number
from logger import log_event

# ====== Blueprint Setup ======
payment_routes = Blueprint('payment_routes', __name__)

# ====== Payment Fee Info ======
@payment_routes.route('/due_payment', methods=['POST'])
def payment():
    conn = connect_to_db()

    data = request.get_json()
    phone = data.get('phone')
    fullname = data.get('fullname').strip()

    if not phone or not fullname:
        log_event("payment_missing_fields", phone, "Phone or fullname missing")
        return jsonify({"error": "Phone and fullname are required"}), 400

    formatted_phone = format_phone_number(phone)

    with conn.cursor() as cursor:
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

# ====== Save Payment Transaction ======
@payment_routes.route('/add_transaction', methods=['POST'])
def transaction():
    conn = connect_to_db()

    data = request.get_json()
    phone = data.get('phone')
    fullname = data.get('fullname').strip()
    payed_fees = data.get('payed_fees')
    payed_months = data.get('payed_months')

    if not phone or not fullname or payed_fees is None:
        log_event("payment_missing_fields", phone, "Phone or fullname missing")
        return jsonify({"error": "Phone, fullname, and fees are required"}), 400
    
    formatted_phone = format_phone_number(phone)

    if isinstance(payed_months, list):
        payed_months = ', '.join(payed_months)  # handle multiple months

    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE phone = %s AND LOWER(fullname) = (%s)", (formatted_phone, fullname))
        user = cursor.fetchone()

    if not user:
        log_event("payment_user_not_found", formatted_phone, f"User {fullname} not found")
        return jsonify({"message": "User not found"}), 404


    user_id = user['id']
    current_date = datetime.today().strftime('%Y-%m-%d')

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO transactions (id, type, month, amount, date)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, 'payment', payed_months, payed_fees, current_date))
            conn.commit()
        return jsonify({"message": "Transaction successful"}), 201
    except Exception as e:
        log_event("payment_insert_failed", phone, f"DB Error: {str(e)}")
        return jsonify({"error": "Transaction failed"}), 500


# ====== Save Donation ======
@payment_routes.route('/add_donation', methods=['POST'])
def donation():
    conn = connect_to_db()

    data = request.get_json()
    phone = data.get('phone')
    fullname = data.get('fullname').strip()
    amount = data.get('amount')

    formatted_phone = format_phone_number(phone)

    if not phone or not fullname or amount is None:
        log_event("payment_missing_fields", phone, "Phone or fullname missing")
        return jsonify({"error": "Phone, fullname, and amount are required"}), 400

    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE phone = %s AND LOWER(fullname) = LOWER(%s)", (formatted_phone, fullname))
        user = cursor.fetchone()

    if not user:
        log_event("payment_user_not_found", formatted_phone, f"User {fullname} not found")
        return jsonify({"message": "User not found"}), 404

    user_id = user['id']
    current_date = datetime.today().strftime('%Y-%m-%d')

    with conn.cursor() as cursor:
        cursor.execute("""
            INSERT INTO transactions (id, type, month, amount, date)
            VALUES (%s, %s, NULL, %s, %s)
        """, (user_id, 'donation', amount, current_date))
        conn.commit()

    return jsonify({"message": "Donation successful"}), 201

# ====== Get Transaction History ======
@payment_routes.route('/get_transactions', methods=['POST'])
def get_transactions():
    conn = connect_to_db()
    
    data = request.get_json()
    phone = data.get('phone')
    fullname = data.get('fullname').strip()

    if not phone or not fullname:
        log_event("payment_missing_fields", phone, "Phone or fullname missing")
        return jsonify({"error": "Phone and fullname are required"}), 400
    
    formatted_phone = format_phone_number(phone)

    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT transactions.type, transactions.month, transactions.amount, transactions.date
            FROM transactions
            JOIN users ON transactions.id = users.id
            WHERE users.phone = %s AND LOWER(users.fullname) = LOWER(%s)
            ORDER BY transactions.date DESC
        """, (formatted_phone, fullname))
        transactions = cursor.fetchall()

    if not transactions:
        return jsonify({"message": "No transactions found"}), 404

    return jsonify(transactions), 200
