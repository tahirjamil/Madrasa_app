# from flask import request, jsonify
# from . import user_routes
# import pymysql
# import pymysql.cursors
# from datetime import datetime, timezone
# from database import connect_to_db
# from helpers import calculate_fees, format_phone_number
# from logger import log_event
# import os
# import time
# import requests
# from config import Config

# # ====== Payment Fee Info ======
# @user_routes.route('/due_payment', methods=['POST'])
# def payment():
#     conn = connect_to_db()

#     data = request.get_json()
#     phone = data.get('phone')
#     fullname = (data.get('fullname') or '').strip()

#     if not phone or not fullname:
#         log_event("payment_missing_fields", phone, "Phone or fullname missing")
#         return jsonify({"error": "Phone and fullname are required"}), 400

#     formatted_phone = format_phone_number(phone)

#     try:
#         with conn.cursor(pymysql.cursors.DictCursor) as cursor:
#             cursor.execute("""
#                 SELECT people.class, people.gender, payment.special_food, payment.reduce_fee,
#                     payment.food, payment.due_months AS month, users.phone, users.fullname
#                 FROM users
#                 JOIN people ON people.id = users.id
#                 JOIN payment ON payment.id = users.id
#                 WHERE users.phone = %s AND LOWER(users.fullname) = LOWER(%s)
#             """, (formatted_phone, fullname))
#             result = cursor.fetchone()

#         if not result:
#             log_event("payment_user_not_found", phone, f"User {fullname} not found")
#             return jsonify({"message": "User not found"}), 404
#     except Exception as e:
#         conn.rollback()
#         log_event("get_payment_failed", phone, f"DB Error: {str(e)}")
#         return jsonify({"error": "Transaction failed"}), 500
#     finally:
#         conn.close()


#     # Extract data
#     class_name = result['class']
#     gender = result['gender']
#     special_food = result['special_food']
#     reduce_fee = result['reduce_fee']
#     food = result['food']
#     due_months = result['month']

#     # Calculate fees
#     fees = calculate_fees(class_name, gender, special_food, reduce_fee, food)

#     return jsonify({"amount": fees, "month": due_months}), 200


# # ====== Save Transaction ======
# @user_routes.route('/add_transaction', methods=['POST'])
# def transaction():
#     conn = connect_to_db()

#     data = request.get_json()
#     phone = data.get('phone')
#     fullname = (data.get('fullname') or '').strip()
#     transaction_type = data.get('type')
#     amount = data.get('amount')
#     months = data.get('months')

#     if not phone or not fullname or amount is None or transaction_type is None:
#         log_event("payment_missing_fields", phone, "Missing fields")
#         return jsonify({"error": "Phone, fullname, type and amount are required"}), 400
    
#     formatted_phone = format_phone_number(phone)

#     if months:
#         if isinstance(months, list):
#             months = ', '.join(months)  # handle multiple months
#     else:
#         months = "Null"

#     try:
#         with conn.cursor(pymysql.cursors.DictCursor) as cursor:
#             cursor.execute("SELECT id FROM users WHERE phone = %s AND LOWER(fullname) = (%s)", (formatted_phone, fullname))
#             user = cursor.fetchone()
#     except Exception as e:
#         conn.rollback()
#         log_event("get_user_id_failed", phone, f"DB Error: {str(e)}")
#         return jsonify({"error": "Transaction failed"}), 500
#     finally:
#         conn.close()

#     if not user:
#         log_event("payment_user_not_found", phone, f"User {fullname} not found")
#         return jsonify({"message": "User not found"}), 404


#     user_id = user['id']
#     current_date = datetime.today().strftime('%Y-%m-%d')

#     try:
#         with conn.cursor(pymysql.cursors.DictCursor) as cursor:
#             cursor.execute("""
#                 INSERT INTO transactions (id, type, month, amount, date)
#                 VALUES (%s, %s, %s, %s, %s)
#             """, (user_id, transaction_type, months, amount, current_date))
#             conn.commit()
#         return jsonify({"message": "Transaction successful"}), 201
#     except Exception as e:
#         conn.rollback()
#         log_event("payment_insert_failed", phone, f"DB Error: {str(e)}")
#         return jsonify({"error": "Transaction failed"}), 500
#     finally:
#         conn.close()

# # ====== Get Transaction History ======
# @user_routes.route('/get_transactions', methods=['POST'])
# def get_transactions():
#     data = request.get_json() or {}
#     phone            = data.get('phone')
#     fullname         = (data.get('fullname') or '').strip()
#     transaction_type = data.get('type')
#     lastfetched      = data.get('updatedSince')

#     # Required fields
#     if not phone or not fullname or not transaction_type:
#         log_event("payment_missing_fields", phone,
#                   "Phone, fullname or transaction type missing")
#         return jsonify({"error": "Phone, fullname and type are required"}), 400

#     # Normalize phone
#     formatted_phone = format_phone_number(phone)
#     if not formatted_phone:
#         log_event("payment_invalid_phone", phone, "Invalid phone format")
#         return jsonify({"error": "Invalid phone number"}), 400

#     # Build base query and params
#     sql = """
#       SELECT
#         t.type,
#         t.month     AS details,
#         t.amount,
#         t.date
#       FROM transactions t
#       JOIN users        u ON t.id = u.id
#       WHERE u.phone = %s
#         AND LOWER(u.fullname) = LOWER(%s)
#         AND t.type = %s
#     """
#     params = [formatted_phone, fullname, transaction_type]

#     # If updatedSince provided, parse & add to WHERE
#     if lastfetched:
#         try:
#             cutoff = datetime.fromisoformat(
#                 lastfetched.replace("Z", "+00:00")
#             )
#             sql += " AND t.updated_at > %s"
#             params.append(cutoff)
#         except ValueError:
#             log_event("payment_invalid_timestamp", phone, lastfetched)
#             return jsonify({"error": "Invalid updatedSince format"}), 400

#     # Final ordering
#     sql += " ORDER BY t.date DESC"

#     # Execute
#     conn = connect_to_db()
#     try:
#         with conn.cursor(cursor=pymysql.cursors.DictCursor) as cursor:
#             cursor.execute(sql, params)
#             transactions = cursor.fetchall()
#     except Exception as e:
#         conn.rollback()
#         log_event("payment_transaction_error", phone, str(e))
#         return jsonify({"error": "Internal server error"}), 500
#     finally:
#         conn.close()

#     # Handle no‐results
#     if not transactions:
#         return jsonify({"message": "No transactions found"}), 404

#     # Normalize dates to ISO-8601 Z format
#     for tx in transactions:
#         d = tx.get("date")
#         if isinstance(d, datetime):
#             tx["date"] = d.astimezone(timezone.utc) \
#                          .isoformat().replace("+00:00", "Z")

#     # Return payload
#     return jsonify({
#         "transactions": transactions,
#         "lastSyncedAt": datetime.now(timezone.utc)
#                               .isoformat().replace("+00:00","Z")
#     }), 200

# # ====== ShurjoPay Payment Initiation ======
# @user_routes.route('/pay_shurjopay', methods=['POST'])
# def pay_shurjopay():
#     data = request.get_json() or {}
#     phone = data.get('phone')
#     fullname = (data.get('fullname') or '').strip()
#     amount = data.get('amount')
#     months = data.get('months')

#     if not phone or not fullname or amount is None:
#         log_event("payment_missing_fields", phone, "Missing payment info")
#         return jsonify({"error": "Phone, fullname and amount required"}), 400

#     tran_id = f"shurjo_{int(time.time())}"
#     username = os.getenv("SHURJOPAY_USERNAME", "your-username-here")
#     password = os.getenv("SHURJOPAY_PASSWORD", "your-password-here")

#     auth_payload = {
#         "username": username,
#         "password": password,
#     }

#     try:
#         token_res = requests.post(
#             'https://sandbox.shurjopayment.com/api/get_token',
#             data=auth_payload,
#             timeout=10,
#         )
#         token = token_res.json().get('token')
#     except Exception as e:
#         log_event("shurjopay_auth_error", phone, str(e))
#         return jsonify({"error": "Gateway unreachable"}), 502

#     payment_payload = {
#         "token": token,
#         "order_id": tran_id,
#         "currency": "BDT",
#         "amount": amount,
#         "customer_name": fullname,
#         "customer_phone": phone,
#         "return_url": Config.BASE_URL + 'payment_success_shurjo',
#         "cancel_url": Config.BASE_URL + 'payment_fail_shurjo',
#         "value1": phone,
#         "value2": fullname,
#         "value3": months or '',
#     }

#     try:
#         r = requests.post(
#             'https://sandbox.shurjopayment.com/api/secret-pay',
#             data=payment_payload,
#             timeout=10,
#         )
#         res = r.json()
#     except Exception as e:
#         log_event("shurjopay_error", phone, str(e))
#         return jsonify({"error": "Gateway unreachable"}), 502

#     if res.get('checkout_url'):
#         return jsonify({"checkout_url": res.get('checkout_url')}), 200

#     return jsonify({"error": "Payment initiation failed"}), 500


# @user_routes.route('/payment_success_shurjo', methods=['POST'])
# def payment_success_shurjo():
#     data = request.form.to_dict() or {}
#     phone = data.get('value1') or data.get('customer_phone')
#     fullname = data.get('value2') or data.get('customer_name')
#     amount = data.get('amount')
#     months = data.get('value3')

#     try:
#         requests.post(
#             Config.BASE_URL + 'add_transaction',
#             json={
#                 'phone': phone,
#                 'fullname': fullname,
#                 'type': 'shurjopay',
#                 'amount': amount,
#                 'months': months,
#             },
#             timeout=5,
#         )
#     except Exception as e:
#         log_event("transaction_callback_fail", phone, str(e))

#     return jsonify({"message": "Payment recorded"}), 200