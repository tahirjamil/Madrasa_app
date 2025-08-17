from typing import Tuple
from quart import Response, request, jsonify

from utils.helpers.improved_functions import get_env_var, send_json_response
from . import api
import aiomysql, os, time, requests
from datetime import datetime, timezone
from utils.mysql.database_utils import get_db_connection
from utils.helpers.helpers import calculate_fees, format_phone_number, handle_async_errors, cache_with_invalidation
from config import config
from utils.helpers.logger import log
from quart_babel import gettext as _

# ====== Payment Fee Info ======
@api.route('/due_payments', methods=['POST']) # type: ignore
@cache_with_invalidation
@handle_async_errors
async def payments() -> Tuple[Response, int]:
    conn = await get_db_connection()

    data = await request.get_json()
    phone = data.get('phone') or ""
    fullname = (data.get('fullname') or 'guest').strip()
    madrasa_name = get_env_var("MADRASA_NAME", "annur")  # Default to annur if not set

    if config.is_testing():
        fullname = config.DUMMY_FULLNAME
        phone = config.DUMMY_PHONE

    formatted_phone, msg = format_phone_number(phone)
    if not formatted_phone:
        response, status = send_json_response(msg, 400)
        return jsonify(response), status


    async with conn.cursor(aiomysql.DictCursor) as _cursor:
        from utils.otel.db_tracing import TracedCursorWrapper
        cursor = TracedCursorWrapper(_cursor)
        await cursor.execute(f"""
        SELECT p.class, p.gender, pay.special_food, pay.reduced_fee,
            pay.food, pay.due_months AS month, u.phone, u.fullname
            FROM global.users u
            JOIN {madrasa_name}.peoples p ON p.user_id = u.user_id
            JOIN {madrasa_name}.payments pay ON pay.user_id = u.user_id
            WHERE u.phone = %s AND LOWER(u.fullname) = LOWER(%s)
        """, (formatted_phone, fullname))
        result = await cursor.fetchone()

        if not result:
            log.error(action="payments_user_not_found", trace_info=formatted_phone, message=f"User {fullname} not found", secure=True)
            response, status = send_json_response(_("User not found for payments"), 404)
            return jsonify(response), status


    # Extract data
    class_name = result['class']
    gender = result['gender']
    special_food = result['special_food']
    reduced_fee = result['reduced_fee']
    food = result['food']
    due_months = result['month']

    # Calculate fees
    fees = calculate_fees(class_name, gender, special_food, reduced_fee, food)

    return jsonify({"amount": fees, "month": due_months}), 200


# ====== Get Transaction History ======
@api.route('/get_transactions', methods=['POST']) # type: ignore
@cache_with_invalidation
@handle_async_errors
async def get_transactions():
    data = await request.get_json() or {}
    phone            = data.get('phone')
    fullname         = data.get('fullname')
    transaction_type = data.get('type')
    lastfetched      = data.get('updatedSince')
    
    if config.is_testing():
        fullname = config.DUMMY_FULLNAME
        phone = config.DUMMY_PHONE

    if not phone or not fullname or not transaction_type:
        log.error(action="payment_missing_fields", trace_info=phone or "", message="Phone, fullname or transaction type missing", secure=True)
        response, status = send_json_response(_("Phone, fullname and payment type required"), 400)
        return jsonify(response), status

    fullname = fullname.strip().lower()
    formatted_phone, msg = format_phone_number(phone)
    if not formatted_phone:
        log.error(action="payment_invalid_phone", trace_info=phone, message="Invalid phone format", secure=True)
        response, status = send_json_response(_("Invalid phone number"), 400)
        return jsonify(response), status

    # Build base query and params
    sql = """
      SELECT
        t.type,
        t.month     AS details,
        t.amount,
        t.date
      FROM global.transactions t
      JOIN global.users        u ON t.user_id = u.user_id
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
            log.error(action="payment_invalid_timestamp", trace_info=formatted_phone, message=lastfetched, secure=True)
            response, status = send_json_response(_("Invalid updatedSince format"), 400)
            return jsonify(response), status

    # Final ordering
    sql += " ORDER BY t.date DESC"

    # Execute
    conn = await get_db_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as _cursor:
            from utils.otel.db_tracing import TracedCursorWrapper
            cursor = TracedCursorWrapper(_cursor)
            await cursor.execute(sql, params)
            transactions = await cursor.fetchall()
    except Exception as e:
        await conn.rollback()
        log.critical(action="payment_transaction_error", trace_info=formatted_phone, message=str(e), secure=True)
        response, status = send_json_response(_("Internal server error during payments processing"), 500)
        return jsonify(response), status

    # Handle no‐results
    if not transactions:
        response, status = send_json_response(_("No transactions found"), 404)
        return jsonify(response), status

    # Normalize dates to ISO-8601 Z format
    for tx in transactions:
        d = tx.get("date")
        if isinstance(d, datetime):
            tx["date"] = d.astimezone(timezone.utc) \
                         .isoformat().replace("+00:00","Z")
                         
    # Return payload
    return jsonify({
        "transactions": transactions,
        "lastSyncedAt": datetime.now(timezone.utc)
                              .isoformat().replace("+00:00","Z")
    }), 200

@api.route('/pay_sslcommerz', methods=['POST'])
@handle_async_errors
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
       email = config.DUMMY_EMAIL

    if not transaction_type or amount is None:
        log.error(action="payment_missing_fields", trace_info=phone, message="Missing payment info", secure=True)
        response, status = send_json_response(_("Amount and payment type are required"), 400)
        return jsonify(response), status

    tran_id    = f"ssl_{int(time.time())}"
    store_id   = get_env_var("SSLCOMMERZ_STORE_ID")
    store_pass = get_env_var("SSLCOMMERZ_STORE_PASS")
    if not store_id or not store_pass:
        log.warning(action="sslcommerz_config_missing", trace_info=phone, message="SSLCommerz credentials not set", secure=True)
        response, status = send_json_response(_("Payment gateway is not properly configured"), 500)
        return jsonify(response), status

    payload = {
        # merchant + txn
        "store_id":      store_id,
        "store_passwd":  store_pass,
        "total_amount":  amount,
        "currency":      "BDT",
        "tran_id":       tran_id,
        "success_url":   f"{config.BASE_URL}payments/payment_success_ssl",
        "fail_url":      f"{config.BASE_URL}payments/payment_fail_ssl",
        "cancel_url":    f"{config.BASE_URL}payments/payment_cancel_ssl",   # new
        "ipn_url":       f"{config.BASE_URL}payments/payment_ipn",          # optional

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
        log.info(action="sslcommerz_request", trace_info=phone, message=f"Initiating {tran_id} for {amount}", secure=True)
        r   = requests.post(
            'https://sandbox.sslcommerz.com/gwprocess/v4/api.php',
            data=payload,
            timeout=10
        )
        res = r.json()
    except Exception as e:
        log.critical(action="sslcommerz_request_error", trace_info=phone, message=str(e), secure=True)
        response, status = send_json_response(_("Payment gateway is currently unreachable"), 502)
        return jsonify(response), status

    if res.get('status') == 'SUCCESS':
        response, status = send_json_response(res.get('GatewayPageURL'), 200)
        return jsonify(response), status
    else:
        log.critical(action="sslcommerz_initiation_failed", trace_info=phone, message=f"{res.get('status')} – {res.get('failedreason')}", secure=True)
        response, status = send_json_response(_("Payment initiation failed"), 400)
        response.update({"reason": res.get('failedreason')})
        return jsonify(response), status


@api.route('/payments/<return_type>', methods=['POST'])
@handle_async_errors
async def payments_success_ssl(return_type):
    valid_types = ['payment_success_ssl', 'payment_fail_ssl', 'payment_cancel_ssl', 'payment_ipn_ssl']
    if return_type not in valid_types:
        response, status = send_json_response(_("Invalid return type"), 400)
        return jsonify(response), status
    if return_type == 'payment_fail_ssl':
        response, status = send_json_response(_("Payment failed"), 400)
        return jsonify(response), status
    elif return_type == 'payment_cancel_ssl':
        response, status = send_json_response(_("Payment cancelled"), 400)
        return jsonify(response), status
    
    data            = (await request.form).to_dict() or {}
    phone           = str(data.get('value_a'))
    fullname        = str(data.get('value_b'))
    amount          = data.get('amount')
    months          = data.get('value_c')
    transaction_type= data.get('value_d')
    tran_id         = data.get('value_e')

    # Ensure we received our transaction identifier back
    if not tran_id:
        log.error(action="sslcommerz_callback_no_tranid", trace_info=phone, message="Missing value_e", secure=True)
        response, status = send_json_response(_("Missing transaction identifier"), 400)
        return jsonify(response), status
        
    formatted_phone, msg = format_phone_number(phone)
    if not formatted_phone:
        response, status = send_json_response(msg, 400)
        return jsonify(response), status

    # 1️⃣ Validate callback with SSLCommerz
    store_id   = get_env_var("SSLCOMMERZ_STORE_ID")
    store_pass = get_env_var("SSLCOMMERZ_STORE_PASS")
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
            log.warning(action="sslcommerz_validation_failed", trace_info=formatted_phone, message=validation.get('status'), secure=True)
            response, status = send_json_response(_("Payment validation failed"), 400)
            return jsonify(response), status
    except Exception as e:
        log.critical(action="sslcommerz_validation_error", trace_info=formatted_phone, message=str(e), secure=True)
        response, status = send_json_response(_("Error during payments validation"), 502)
        return jsonify(response), status

        
    # 2️⃣ Record transaction directly in the database
    db = None
    try:
        db = await get_db_connection()
        async with db.cursor(aiomysql.DictCursor) as cursor:
            # Start transaction
            await db.begin()
            
            # Fetch the user's internal ID
            await cursor.execute(
                "SELECT user_id FROM global.users WHERE phone=%s AND LOWER(fullname)=LOWER(%s)",
                (formatted_phone, fullname)
            )
            user = await cursor.fetchone()
            if not user:
                log.error(action="transaction_user_not_found", trace_info=formatted_phone, message=fullname, secure=True)
                response, status = send_json_response(_("User not found for payments"), 404)
                return jsonify(response), status
                
            # Insert the new transaction
            await cursor.execute(
                "INSERT INTO global.transactions (user_id, type, month, amount, date) "
                "VALUES (%s, %s, %s, %s, CURDATE())",
                (user['user_id'], transaction_type, months or '', amount)
            )
            # Commit transaction
            await db.commit()
    except Exception as e:
        if db:
            await db.rollback()
        log.critical(action="payment_insert_fail", trace_info=formatted_phone, message=str(e), secure=True)
        response, status = send_json_response(_("Transaction failed"), 500)
        return jsonify(response), status
            
    response, status = send_json_response(_("Payment recorded successfully"), 200)
    return jsonify(response), status
