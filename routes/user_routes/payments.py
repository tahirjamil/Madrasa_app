from quart import request, jsonify
from . import user_routes
import aiomysql, os, time, requests
from datetime import datetime, timezone
from database.database_utils import get_db_connection
from helpers import calculate_fees, format_phone_number, log_event, is_test_mode, hash_sensitive_data
from config import Config
from quart_babel import gettext as _

# ====== Payment Fee Info ======
@user_routes.route('/due_payments', methods=['POST'])
async def payments():
    conn = await get_db_connection()

    data = await request.get_json()
    phone = data.get('phone') or ""
    fullname = (data.get('fullname') or 'guest').strip()

    if is_test_mode():
        fullname = Config.DUMMY_FULLNAME
        phone = Config.DUMMY_PHONE

    formatted_phone, msg = format_phone_number(phone)
    if not formatted_phone:
        return await jsonify({"error": msg}), 400

    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
                SELECT peoples.class, peoples.gender, payments.special_food, payments.reduced_fee,
                    payments.food, payments.due_months AS month, users.phone, users.fullname
                FROM users
                JOIN peoples ON peoples.user_id = users.user_id
                JOIN payments ON payments.user_id = users.user_id
                WHERE users.phone = %s AND LOWER(users.fullname) = LOWER(%s)
            """, (formatted_phone, fullname))
            result = await cursor.fetchone()

        if not result:
            log_event("payments_user_not_found", hash_sensitive_data(formatted_phone), f"User {hash_sensitive_data(fullname)} not found")
            return await jsonify({"message": _("User not found for payments")}), 404
    except Exception as e:
        await conn.rollback()
        log_event("get_payments_failed", hash_sensitive_data(formatted_phone), f"DB Error: {str(e)}")
        return await jsonify({"error": _("Transaction failed")}), 500


    # Extract data
    class_name = result['class']
    gender = result['gender']
    special_food = result['special_food']
    reduced_fee = result['reduced_fee']
    food = result['food']
    due_months = result['month']

    # Calculate fees
    fees = await calculate_fees(class_name, gender, special_food, reduced_fee, food)

    return await jsonify({"amount": fees, "month": due_months}), 200


# ====== Get Transaction History ======
@user_routes.route('/get_transactions', methods=['POST'])
async def get_transactions():
    data = await request.get_json() or {}
    phone            = data.get('phone')
    fullname         = data.get('fullname')
    transaction_type = data.get('type')
    lastfetched      = data.get('updatedSince')
    
    if is_test_mode():
        fullname = Config.DUMMY_FULLNAME
        phone = Config.DUMMY_PHONE

    if not phone or not fullname or not transaction_type:
        log_event("payment_missing_fields", hash_sensitive_data(phone or "unknown"),
                  "Phone, fullname or transaction type missing")
        return await jsonify({"error": _("Phone, fullname and payment type required")}), 400

    fullname = fullname.strip().lower()
    formatted_phone, msg = format_phone_number(phone)
    if not formatted_phone:
        log_event("payment_invalid_phone", hash_sensitive_data(phone or "unknown"), "Invalid phone format")
        return await jsonify({"error": _("Invalid phone number")}), 400

    # Build base query and params
    sql = """
      SELECT
        t.type,
        t.month     AS details,
        t.amount,
        t.date
      FROM transactions t
      JOIN users        u ON t.user_id = u.user_id
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
            log_event("payment_invalid_timestamp", hash_sensitive_data(formatted_phone), lastfetched)
            return await jsonify({"error": _("Invalid updatedSince format")}), 400

    # Final ordering
    sql += " ORDER BY t.date DESC"

    # Execute
    conn = await get_db_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(sql, params)
            transactions = await cursor.fetchall()
    except Exception as e:
        await conn.rollback()
        log_event("payment_transaction_error", hash_sensitive_data(formatted_phone), str(e))
        return await jsonify({"error": _("Internal server error during payments processing")}), 500

    # Handle no‐results
    if not transactions:
        return await jsonify({"message": _("No transactions found")}), 404

    # Normalize dates to ISO-8601 Z format
    for tx in transactions:
        d = tx.get("date")
        if isinstance(d, datetime):
            tx["date"] = d.astimezone(timezone.utc) \
                         .isoformat().replace("+00:00","Z")
                         
    # Return payload
    return await jsonify({
        "transactions": transactions,
        "lastSyncedAt": datetime.now(timezone.utc)
                              .isoformat().replace("+00:00","Z")
    }), 200

@user_routes.route('/pay_sslcommerz', methods=['POST'])
async def pay_sslcommerz():
    data = await request.get_json() or {}
    phone            = data.get('phone') or "01XXXXXXXXX"
    fullname         = (data.get('fullname') or 'guest').strip()
    amount           = data.get('amount')
    months           = data.get('months')
    transaction_type = data.get('type')
    email            = (data.get('email') or '').strip()

    # fallback dummy email .
    if not email:
       email = Config.DUMMY_EMAIL

    if not transaction_type or amount is None:
        log_event("payment_missing_fields", hash_sensitive_data(phone), "Missing payment info")
        return await jsonify({"error": _("Amount and payment type are required")}), 400

    tran_id    = f"ssl_{int(time.time())}"
    store_id   = os.getenv("SSLCOMMERZ_STORE_ID")
    store_pass = os.getenv("SSLCOMMERZ_STORE_PASS")
    if not store_id or not store_pass:
        log_event("sslcommerz_config_missing", hash_sensitive_data(phone), "SSLCommerz credentials not set")
        return await jsonify({"error": _("Payment gateway is not properly configured")}), 500

    payload = {
        # merchant + txn
        "store_id":      store_id,
        "store_passwd":  store_pass,
        "total_amount":  amount,
        "currency":      "BDT",
        "tran_id":       tran_id,
        "success_url":   f"{Config.BASE_URL}payments/payment_success_ssl",
        "fail_url":      f"{Config.BASE_URL}payments/payment_fail_ssl",
        "cancel_url":    f"{Config.BASE_URL}payments/payment_cancel_ssl",   # new
        "ipn_url":       f"{Config.BASE_URL}payments/payment_ipn",          # optional

        # product
        "product_name":      transaction_type.capitalize(),
        "product_category":  transaction_type.capitalize(),
        "product_profile":   "non-physical-goods",

        # customer (Mirpur defaults)
        "cus_name":    fullname,
        "cus_email":   email,
        "cus_add1":    "Mirpur 10",
        "cus_add2":    "", 
        "cus_city":    "Dhaka",
        "cus_postcode":"1216",
        "cus_country": "Bangladesh",
        "cus_phone":   phone,

        # passthrough fields
        "value_a": phone,
        "value_b": fullname,
        "value_c": months or '',
        "value_d": transaction_type,
        "value_e": tran_id,

        # others
        "emi_option": 0,
        "shipping_method": "NO",
        "num_of_item": 1,
        "weight_of_items": 0.5,
        "logistic_pickup_id": "madrasaid123",
        "logistic_delivery_type": "madrasadilevery_by_air"
    }

    try:
        log_event("sslcommerz_request", hash_sensitive_data(phone), f"Initiating {tran_id} for {amount}")
        r   = requests.post(
            'https://sandbox.sslcommerz.com/gwprocess/v4/api.php',
            data=payload,
            timeout=10
        )
        res = r.json()
    except Exception as e:
        log_event("sslcommerz_request_error", hash_sensitive_data(phone), str(e))
        return await jsonify({"error": _("Payment gateway is currently unreachable")}), 502

    if res.get('status') == 'SUCCESS':
        return await jsonify({"GatewayPageURL": res.get('GatewayPageURL')}), 200
    else:
        log_event(
            "sslcommerz_initiation_failed",
            hash_sensitive_data(phone),
            f"{res.get('status')} – {res.get('failedreason')}"
        )
        return await jsonify({
            "error":  _("Payment initiation failed"),
            "reason": res.get('failedreason')
        }), 400


@user_routes.route('/payments/<return_type>', methods=['POST'])
async def payments_success_ssl(return_type):
    valid_types = ['payment_success_ssl', 'payment_fail_ssl', 'payment_cancel_ssl', 'payment_ipn_ssl']
    if return_type not in valid_types:
        return await jsonify({"error": _("Invalid return type")}), 400
    if return_type == 'payment_fail_ssl':
        return await jsonify({"error": _("Payment failed")}), 400
    elif return_type == 'payment_cancel_ssl':
        return await jsonify({"error": _("Payment cancelled")}), 400
    
    data            = (await request.form).to_dict() or {}
    phone           = data.get('value_a')
    fullname        = data.get('value_b')
    amount          = data.get('amount')
    months          = data.get('value_c')
    transaction_type= data.get('value_d')
    tran_id         = data.get('value_e')

    # Ensure we received our transaction identifier back
    if not tran_id:
        log_event("sslcommerz_callback_no_tranid", hash_sensitive_data(phone or "unknown"), "Missing value_e")
        return await jsonify({"error": _("Missing transaction identifier")}), 400
        
    formatted_phone, msg = format_phone_number(phone)
    if not formatted_phone:
        return await jsonify({"error": msg}), 400

    # 1️⃣ Validate callback with SSLCommerz
    store_id   = os.getenv("SSLCOMMERZ_STORE_ID")
    store_pass = os.getenv("SSLCOMMERZ_STORE_PASS")
    try:
        validation = requests.get(
            'https://sandbox.sslcommerz.com/validator/api/validationserverAPI',
            params={
                'tran_id':      tran_id,
                'store_id':     store_id,
                'store_passwd': store_pass
            },
            timeout=10
        ).json()
        if validation.get('status') != 'VALID':
            log_event("sslcommerz_validation_failed", hash_sensitive_data(formatted_phone), validation.get('status'))
            return await jsonify({"error": _("Payment validation failed")}), 400
    except Exception as e:
        log_event("sslcommerz_validation_error", hash_sensitive_data(formatted_phone), str(e))
        return await jsonify({"error": _("Error during payments validation")}), 502

        
    # 2️⃣ Record transaction directly in the database
    db = None
    try:
        db = await get_db_connection()
        async with db.cursor(aiomysql.DictCursor) as cursor:
            # Start transaction
            await db.begin()
            
            # Fetch the user's internal ID
            await cursor.execute(
                "SELECT user_id FROM users WHERE phone=%s AND LOWER(fullname)=LOWER(%s)",
                (formatted_phone, fullname)
            )
            user = await cursor.fetchone()
            if not user:
                log_event("transaction_user_not_found", hash_sensitive_data(formatted_phone), hash_sensitive_data(fullname))
                return await jsonify({"error": _("User not found for payments")}), 404
                
            # Insert the new transaction
            await cursor.execute(
                "INSERT INTO transactions (user_id, type, month, amount, date) "
                "VALUES (%s, %s, %s, %s, CURDATE())",
                (user['user_id'], transaction_type, months or '', amount)
            )
            # Commit transaction
            await db.commit()
    except Exception as e:
        if db:
            await db.rollback()
        log_event("payment_insert_fail", hash_sensitive_data(formatted_phone), str(e))
        return await jsonify({"error": _("Transaction failed")}), 500
            
    return await jsonify({"message": _("Payment recorded successfully")}), 200
