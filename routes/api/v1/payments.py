from fastapi import Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import aiomysql
from datetime import datetime, timezone

# Local imports
from utils.helpers.improved_functions import get_env_var, send_json_response
from utils.helpers.fastapi_helpers import BaseAuthRequest, ClientInfo, validate_device_dependency, handle_async_errors
from routes.api import api
from utils.mysql.database_utils import get_db_connection
from utils.helpers.helpers import calculate_fees, format_phone_number, cache_with_invalidation, validate_madrasa_name
from config import config
from utils.helpers.logger import log

# ─── Pydantic Models ───────────────────────────────────────────
class PaymentRequest(BaseAuthRequest):
    """Payment request model"""
    pass

class PaymentData(BaseModel):
    """Payment data model for payment processing"""
    full_name: str
    phone: str
    total_amount: float
    bank_ac: str
    bank_name: str
    description: str
    transaction_id: str

# ====== Payment Fee Info ======
@api.post('/due_payments')
@cache_with_invalidation
@handle_async_errors
async def payments(
    request: Request,
    data: PaymentRequest,
    client_info: ClientInfo = Depends(validate_device_dependency)
) -> JSONResponse:

    phone = data.phone
    fullname = data.fullname.strip()
    madrasa_name = get_env_var("MADRASA_NAME", "annur")  # Default to annur if not set
    
    # SECURITY: Validate madrasa_name is in allowed list
    if not validate_madrasa_name(madrasa_name, phone):
        response, status = send_json_response("Invalid configuration", 500)
        return JSONResponse(content=response, status_code=status)

    formatted_phone, msg = format_phone_number(phone)
    if not formatted_phone:
        response, status = send_json_response(msg, 400)
        return JSONResponse(content=response, status_code=status)


    async with get_db_connection() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(f"""
            SELECT p.class, p.gender, pay.special_food, pay.reduced_fee,
                pay.food, pay.due_months AS month, pay.tax, u.phone, u.fullname
                FROM global.users u
                JOIN {madrasa_name}.peoples p ON p.user_id = u.user_id
                JOIN {madrasa_name}.payments pay ON pay.user_id = u.user_id
                WHERE u.phone = %s AND LOWER(u.fullname) = LOWER(%s)
            """, (formatted_phone, fullname))
            result = await cursor.fetchone()

            if not result:
                log.error(action="payments_user_not_found", trace_info=formatted_phone, message=f"User {fullname} not found", secure=True)
                response, status = send_json_response("User not found for payments", 404)
                return JSONResponse(content=response, status_code=status)


    # Extract data
    class_name: str = result['class']
    gender: str = result['gender']
    special_food: bool = result['special_food'] == 1
    reduced_fee: float = float(result['reduced_fee'] or 0.0)
    food: bool = result['food'] == 1
    due_months: int = int(result['month'])
    tax: float = float(result['tax'] or 0.0)

    # Calculate fees
    fees: float = calculate_fees(class_name, gender, special_food, reduced_fee, food, tax)

    return JSONResponse(content={"amount": fees, "month": due_months}, status_code=200)


# ====== Get Transaction History ======
@api.post('/transaction_history')
@cache_with_invalidation
@handle_async_errors
async def transaction_history(
    request: Request,
    data: PaymentRequest,
    client_info: ClientInfo = Depends(validate_device_dependency)
) -> JSONResponse:

    phone = data.phone
    fullname = data.fullname
    madrasa_name = get_env_var("MADRASA_NAME", "annur")
    
    # SECURITY: Validate madrasa_name is in allowed list
    if not validate_madrasa_name(madrasa_name, phone):
        response, status = send_json_response("Invalid configuration", 500)
        return JSONResponse(content=response, status_code=status)

    formatted_phone, msg = format_phone_number(phone)
    if not formatted_phone:
        response, status = send_json_response(msg, 400)
        return JSONResponse(content=response, status_code=status)

    async with get_db_connection() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            
            # Get user_id first
            await cursor.execute(
                "SELECT user_id FROM global.users WHERE phone = %s AND LOWER(fullname) = LOWER(%s)",
                (formatted_phone, fullname)
            )
            user_result = await cursor.fetchone()
            
            if not user_result:
                response, status = send_json_response("User not found", 404)
                return JSONResponse(content=response, status_code=status)
            
            # Get transaction history
            await cursor.execute(f"""
                SELECT 
                    pt.transaction_id,
                    pt.amount,
                    pt.bank_ac,
                    pt.bank_name,
                    pt.payment_date,
                    pt.description,
                    pt.created_at,
                    p.class,
                    p.gender,
                    u.fullname,
                    u.phone
                FROM {madrasa_name}.payments_transaction pt
                JOIN global.users u ON pt.user_id = u.user_id
                JOIN {madrasa_name}.peoples p ON p.user_id = u.user_id
                WHERE pt.user_id = %s
                ORDER BY pt.created_at DESC
                LIMIT 50
            """, (user_result['user_id'],))
            
            transactions = await cursor.fetchall()
            
            # Format dates in transactions
            for trans in transactions:
                if trans.get('payment_date'):
                    trans['payment_date'] = trans['payment_date'].isoformat() if hasattr(trans['payment_date'], 'isoformat') else str(trans['payment_date'])
                if trans.get('created_at'):
                    trans['created_at'] = trans['created_at'].isoformat() if hasattr(trans['created_at'], 'isoformat') else str(trans['created_at'])
    
    return JSONResponse(content={
        "transactions": transactions,
        "count": len(transactions)
    }, status_code=200)


# # ====== Process Payment ======
# @api.post('/process_payment')
# @handle_async_errors
# async def process_payment(
#     request: Request,
#     payment_data: PaymentData,
#     client_info: ClientInfo = Depends(validate_device_dependency)
# ) -> JSONResponse:
#     """Process a payment transaction"""
    
#     try:
#         madrasa_name = get_env_var("MADRASA_NAME", "annur")
        

#         # SECURITY: Validate madrasa_name is in allowed list
#         if not validate_madrasa_name(madrasa_name, payment_data.phone):
#             response, status = send_json_response("Invalid configuration", 500)
#             return JSONResponse(content=response, status_code=status)
        
#         # Validate phone
#         formatted_phone, msg = format_phone_number(payment_data.phone)
#         if not formatted_phone:
#             response, status = send_json_response(msg, 400)
#             return JSONResponse(content=response, status_code=status)
        
#         # Start database transaction
#         async with get_db_connection() as conn:
#             async with conn.cursor(aiomysql.DictCursor) as cursor:
#                 try:
#                     # Begin transaction
#                     await conn.begin()
                    
#                     # Get user_id
#                     await cursor.execute(
#                         "SELECT user_id FROM global.users WHERE phone = %s AND LOWER(fullname) = LOWER(%s)",
#                         (formatted_phone, payment_data.full_name)
#                     )
#                     user_result = await cursor.fetchone()
                    
#                     if not user_result:
#                         response, status = send_json_response("User not found", 404)
#                         return JSONResponse(content=response, status_code=status)
                    
#                     user_id = user_result['user_id']
                    
#                     # Check if transaction_id already exists
#                     await cursor.execute(f"""
#                         SELECT transaction_id FROM {madrasa_name}.payments_transaction 
#                         WHERE transaction_id = %s
#                     """, (payment_data.transaction_id,))
                    
#                     if await cursor.fetchone():
#                         response, status = send_json_response("Transaction ID already exists", 409)
#                         return JSONResponse(content=response, status_code=status)
                    
#                     # Insert payment transaction
#                     await cursor.execute(f"""
#                         INSERT INTO {madrasa_name}.payments_transaction 
#                         (user_id, transaction_id, amount, bank_ac, bank_name, description, payment_date, created_at)
#                         VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
#                     """, (
#                         user_id,
#                         payment_data.transaction_id,
#                         payment_data.total_amount,
#                         payment_data.bank_ac,
#                         payment_data.bank_name,
#                         payment_data.description,
#                         datetime.now(timezone.utc),
#                         datetime.now(timezone.utc)
#                     ))
                    
#                     # Update payment status if needed
#                     await cursor.execute(f"""
#                         UPDATE {madrasa_name}.payments 
#                         SET last_payment_date = %s, 
#                             total_paid = total_paid + %s
#                         WHERE user_id = %s
#                     """, (datetime.now(timezone.utc), payment_data.total_amount, user_id))
                    
#                     # Commit transaction
#                     
                    
#                     log.info(
#                         action="payment_processed_successfully",
#                         trace_info=client_info.ip_address,
#                         message=f"Payment processed for user {payment_data.full_name}, amount: {payment_data.total_amount}",
#                         secure=False
#                     )
                    
#                     response, status = send_json_response("Payment processed successfully", 200)
#                     response.update({
#                         "transaction_id": payment_data.transaction_id,
#                         "amount": payment_data.total_amount
#                     })
#                     return JSONResponse(content=response, status_code=status)
                    
#                 except Exception as e:
#                     log.error(
#                         action="payment_processing_failed",
#                         trace_info=client_info.ip_address,
#                         message=f"Payment processing failed: {str(e)}",
#                         secure=False
#                     )
#                     raise
                    
#     except Exception as e:
#         log.critical(
#             action="process_payment_error",
#             trace_info="system",
#             message=f"Payment processing error: {str(e)}",
#             secure=False
#         )
#         response, status = send_json_response("Payment processing failed", 500, str(e))
#         return JSONResponse(content=response, status_code=status)
