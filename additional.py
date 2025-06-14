from flask import Flask, request, jsonify
from flask_cors import CORS
import pymysql
from pymysql.cursors import DictCursor
from datetime import datetime

# ====== MySQL Connection ======
conn = pymysql.connect(
    host='localhost',
    user='tahir',
    password='tahir',
    database='madrashadb',
    cursorclass=DictCursor
)

# ====== Create Tables (Run Once on Start) ======
with conn.cursor() as cursor:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payment (
            id INT PRIMARY KEY,
            food BOOLEAN NOT NULL,
            special_food BOOLEAN NOT NULL,
            reduce_fee INT DEFAULT 0,
            due_months INT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id INT PRIMARY KEY AUTO_INCREMENT,
            id INT NOT NULL,
            type ENUM('payment', 'donation') NOT NULL,
            month VARCHAR(50),
            amount INT NOT NULL,
            date DATE NOT NULL DEFAULT CURRENT_DATE,
            FOREIGN KEY (id) REFERENCES users(id)
        )
    """)
    conn.commit()

# ====== Fee Calculation Function ======
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

    return total - reduce_fee

# ====== Flask App Setup ======
app = Flask(__name__)
CORS(app)

# ====== Payment Fee Info ======
@app.route('/payment', methods=['POST'])
def payment():
    data = request.get_json()
    phone = data.get('phone')
    fullname = data.get('fullname')

    if not phone or not fullname:
        return jsonify({"error": "Phone and fullname are required"}), 400

    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT people.class, people.gender, payment.special_food, payment.reduce_fee,
                   payment.food, payment.due_months, users.phone, users.fullname
            FROM users
            JOIN people ON people.id = users.id
            JOIN payment ON payment.id = users.id
            WHERE users.phone = %s AND users.fullname = %s
        """, (phone, fullname))
        result = cursor.fetchone()

    if not result:
        return jsonify({"message": "User not found"}), 404

    # Extract data
    class_name = result['class']
    gender = result['gender']
    special_food = result['special_food']
    reduce_fee = result['reduce_fee']
    food = result['food']
    due_months = result['due_months']

    # Calculate fees
    fees = calculate_fees(class_name, gender, special_food, reduce_fee, food)

    return jsonify({"fees": fees, "due_months": due_months}), 200

# ====== Save Payment Transaction ======
@app.route('/transaction', methods=['POST'])
def transaction():
    data = request.get_json()
    phone = data.get('phone')
    fullname = data.get('fullname')
    payed_fees = data.get('payed_fees')
    payed_months = data.get('payed_months')

    if not phone or not fullname or payed_fees is None:
        return jsonify({"error": "Phone, fullname, and fees are required"}), 400

    if isinstance(payed_months, list):
        payed_months = ', '.join(payed_months)  # handle multiple months

    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE phone = %s AND fullname = %s", (phone, fullname))
        user = cursor.fetchone()

    if not user:
        return jsonify({"message": "User not found"}), 404

    user_id = user['id']
    current_date = datetime.today().strftime('%Y-%m-%d')

    with conn.cursor() as cursor:
        cursor.execute("""
            INSERT INTO transactions (id, type, month, amount, date)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, 'payment', payed_months, payed_fees, current_date))
        conn.commit()

    return jsonify({"message": "Transaction successful"}), 201

# ====== Save Donation ======
@app.route('/donation', methods=['POST'])
def donation():
    data = request.get_json()
    phone = data.get('phone')
    fullname = data.get('fullname')
    amount = data.get('amount')

    if not phone or not fullname or amount is None:
        return jsonify({"error": "Phone, fullname, and amount are required"}), 400

    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE phone = %s AND fullname = %s", (phone, fullname))
        user = cursor.fetchone()

    if not user:
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
@app.route('/get_transactions', methods=['GET'])
def get_transactions():
    phone = request.args.get('phone')
    fullname = request.args.get('fullname')

    if not phone or not fullname:
        return jsonify({"error": "Phone and fullname are required"}), 400

    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT transactions.type, transactions.month, transactions.amount, transactions.date
            FROM transactions
            JOIN users ON transactions.id = users.id
            WHERE users.phone = %s AND users.fullname = %s
            ORDER BY transactions.date DESC
        """, (phone, fullname))
        transactions = cursor.fetchall()

    if not transactions:
        return jsonify({"message": "No transactions found"}), 404

    return jsonify(transactions), 200

# ====== Run App ======
if __name__ == "__main__":
    app.run(debug=True)
