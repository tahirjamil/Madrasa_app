import asyncio
import os
from datetime import datetime, timedelta, timezone
import datetime as dt
from typing import Any, Dict, Tuple, Optional

import aiomysql
from fastapi import HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from werkzeug.security import generate_password_hash, check_password_hash

from utils.helpers.improved_functions import get_env_var, send_json_response

# Local imports
from . import api
from utils.mysql.database_utils import get_db_connection
from config import config
from utils.helpers.helpers import (
    check_code, check_device_limit, check_login_attempts, format_phone_number, generate_code, 
    get_client_info as get_client_info_from_helpers, record_login_attempt, secure_data, send_sms, send_email, 
    get_email, rate_limit, encrypt_sensitive_data, hash_sensitive_data,
    handle_async_errors, validate_email, validate_fullname, validate_password_strength, validate_madrasa_name
)
from utils.helpers.logger import log
from utils.helpers.fastapi_helpers import (
    BaseAuthRequest, ClientInfo, get_client_info, validate_device_dependency,
    rate_limit, handle_async_errors
)

# ─── Pydantic Models ───────────────────────────────────────────
class RegisterRequest(BaseAuthRequest):
    """Registration request model extending base auth request"""
    password: str
    code: str
    email: Optional[str] = None
    
    @validator('password')
    def validate_password_field(cls, v):
        is_valid, error = validate_password_strength(v)
        if not is_valid:
            raise ValueError(error)
        return v
    
    @validator('email')
    def validate_email_field(cls, v):
        if v:
            is_valid, error = validate_email(v)
            if not is_valid:
                raise ValueError(error)
        return v

# Add more Pydantic models for the remaining endpoints
class LoginRequest(BaseAuthRequest):
    """Login request model"""
    password: str
    
class SendCodeRequest(BaseAuthRequest):
    """Send verification code request"""
    email: Optional[str] = None
    password: Optional[str] = None

class ResetPasswordRequest(BaseAuthRequest):
    """Reset password request"""
    old_password: Optional[str] = None
    new_password: Optional[str] = None
    code: Optional[str] = None

class AccountCheckRequest(BaseAuthRequest):
    """Account check request"""
    student_id: Optional[str] = None
    birth_date: Optional[str] = None
    join_date: Optional[str] = None
    madrasa_name: Optional[str] = None

# ─── Errors ───────────────────────────────────────────────
ERROR_MESSAGES = {
        'missing_fields': "All required fields are missing",
        'invalid_credentials': "Invalid login credentials",
        'account_deactivated': "Account is deactivated",
        'account_not_found': "Account not found",
        'device_unsafe': "Unknown device detected",
        'device_limit_exceeded': "Maximum devices reached. Please remove an existing device to add this one.",
        'rate_limit_exceeded': "Too many attempts. Please try again later.",
        'verification_failed': "Verification code is invalid or expired",
        'password_mismatch': "Passwords do not match",
        'weak_password': "Password is too weak",
        'invalid_email': "Invalid email format",
        'invalid_phone': "Invalid phone number format",
        'user_already_exists': "User already exists",
        'session_expired': "Session has expired",
        'maintenance_mode': "Application is currently in maintenance mode",
        'unauthorized': "Unauthorized access",
        'internal_error': "An internal error occurred",
        'validation_error': "Validation error",
        'database_error': "Database operation failed"
    }


# ─── Enhanced Authentication Routes ───────────────────────────────────────────

@api.post("/register", 
         response_model=None,
         responses={
             201: {"description": "Registration successful"},
             400: {"description": "Bad request"},
             409: {"description": "User already exists"},
             500: {"description": "Internal server error"}
         })
@rate_limit(max_requests=10, window=60)
@handle_async_errors
async def register(
    request: Request,
    data: RegisterRequest,
    client_info: ClientInfo = Depends(validate_device_dependency)
) -> JSONResponse:
    """Register a new user with comprehensive validation and security"""
    
    # Test mode handling
    if config.is_testing():
        response, status = send_json_response("Ignored because in test mode", 201)
        response.update({"info": None})
        return JSONResponse(content=response, status_code=status)
    
    try:
        # Data is already validated by Pydantic, client info by dependency
        fullname = data.fullname
        email = data.email
        phone = data.phone
        password = data.password
        user_code = data.code
        device_id = client_info.device_id
        ip_address = client_info.ip_address
        
        # Validate and format phone number
        formatted_phone, phone_error = format_phone_number(phone)
        if not formatted_phone:
            response, status = send_json_response(phone_error, 400)
            return JSONResponse(content=response, status_code=status)
        
        # Validate fullname
        is_valid_name, name_error = validate_fullname(fullname or "")
        if not is_valid_name:
            response, status = send_json_response(name_error, 400)
            return JSONResponse(content=response, status_code=status)
        
        # Validate password strength
        is_valid_password, password_error = validate_password_strength(password or "")
        if not is_valid_password:
            response, status = send_json_response(password_error, 400)
            return JSONResponse(content=response, status_code=status)
        
        # Validate email if provided
        if email:
            is_valid_email, email_error = validate_email(email)
            if not is_valid_email:
                response, status = send_json_response(email_error, 400)
                return JSONResponse(content=response, status_code=status)
        
        # Verify code
        verification_result = await check_code(user_code or "", formatted_phone)
        if verification_result:
            return verification_result
        
        # Hash password with salt
        hashed_password = generate_password_hash(password or "")
        hashed_phone = hash_sensitive_data(formatted_phone)
        encrypted_phone = encrypt_sensitive_data(formatted_phone)
        encrypted_email = encrypt_sensitive_data(email) if email else None
        hashed_email = hash_sensitive_data(email) if email else None
        
        # Insert user into database
        madrasa_name = get_env_var("MADRASA_NAME")
        # SECURITY: Validate madrasa_name is in allowed list
        if not validate_madrasa_name(madrasa_name, ip_address):
            response, status = send_json_response(ERROR_MESSAGES['unauthorized'], 401)
            return JSONResponse(content=response, status_code=status)
        
        
        try:
            async with get_db_connection() as conn:
                async with conn.cursor(aiomysql.DictCursor) as _cursor:
                    from utils.otel.db_tracing import TracedCursorWrapper
                    cursor = TracedCursorWrapper(_cursor)
                # Check if user already exists
                await cursor.execute(
                    "SELECT user_id FROM global.users WHERE phone = %s OR LOWER(fullname) = LOWER(%s)",
                    (formatted_phone, fullname)
                )
                existing_user = await cursor.fetchone()
                
                if existing_user:
                    log.warning(action="register_user_exists", trace_info=ip_address, message=f"User already exists: {fullname}", secure=False)
                    response, status = send_json_response(ERROR_MESSAGES['user_already_exists'], 409)
                    return JSONResponse(content=response, status_code=status)
                
                # Insert new user
                await cursor.execute(
                    """INSERT INTO global.users 
                    (fullname, phone, phone_hash, phone_encrypted, password_hash, 
                    email, email_hash, email_encrypted, ip_address) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (fullname, formatted_phone, hashed_phone, encrypted_phone, 
                    hashed_password, email, hashed_email, encrypted_email, ip_address)
                )
                await conn.commit()
                
                # Get user ID
                await cursor.execute(
                    "SELECT user_id FROM global.users WHERE LOWER(fullname) = LOWER(%s) AND phone = %s",
                    (fullname, formatted_phone)
                )
                result = await cursor.fetchone()
                user_id = result['user_id'] if result else None
                
                # Check device limit for new user
                if user_id:
                    is_device_allowed, device_limit_error = await check_device_limit(user_id, device_id)
                    if not is_device_allowed:
                        log.warning(action="register_device_limit_exceeded", trace_info=ip_address, message=f"Device limit exceeded during registration for: {fullname}", secure=False)
                        response, status = send_json_response(device_limit_error, 403)
                        return JSONResponse(content=response, status_code=status)
                
                # Get user profile information
                await cursor.execute(
                    f"""SELECT 
                        p.*,
                        a.main_type AS acc_type, a.teacher, a.student, a.staff, 
                        a.donor, a.badri_member, a.special_member,
                        tname.translation_text AS name_en, tname.bn_text AS name_bn, tname.ar_text AS name_ar,
                        taddress.translation_text AS address_en, taddress.bn_text AS address_bn, taddress.ar_text AS address_ar,
                        tfather.translation_text AS father_en, tfather.bn_text AS father_bn, tfather.ar_text AS father_ar,
                        tmother.translation_text AS mother_en, tmother.bn_text AS mother_bn, tmother.ar_text AS mother_ar
                        FROM {madrasa_name}.peoples p
                        JOIN global.acc_types a ON a.user_id = p.user_id
                        JOIN global.translations tname ON tname.translation_text = p.name
                        LEFT JOIN global.translations taddress ON taddress.translation_text = p.address
                        JOIN global.translations tfather ON tfather.translation_text = p.father_name
                        LEFT JOIN global.translations tmother ON tmother.translation_text = p.mother_name
                        WHERE LOWER(p.name) = LOWER(%s) AND p.phone = %s""",
                    (fullname, formatted_phone)
                )
                people_result = await cursor.fetchone()
                
                # Update people record with user_id if found
                if people_result:
                    await cursor.execute(
                        "UPDATE peoples SET user_id = %s WHERE LOWER(name) = LOWER(%s) AND phone = %s",
                        (user_id, fullname, formatted_phone)
                    )
                    await conn.commit()
                
                # Log successful registration
                log.info(action="user_registered_successfully", trace_info=ip_address, message=f"User registered successfully: {fullname}", secure=False)
                
                response, status = send_json_response("Registration successful", 201)
                response.update({"info": people_result})
                return JSONResponse(content=response, status_code=status)
                
        except aiomysql.IntegrityError as e:
            log.critical(action="register_integrity_error", trace_info=ip_address, message=f"Database integrity error: {str(e)}", secure=False)
            response, status = send_json_response(ERROR_MESSAGES['user_already_exists'], 409)
            return JSONResponse(content=response, status_code=status)
            
        except Exception as e:
            log.critical(action="register_database_error", trace_info=ip_address, message=f"Database error during registration: {str(e)}", secure=False)
            response, status = send_json_response(ERROR_MESSAGES['database_error'], 500)
            return JSONResponse(content=response, status_code=status)
            
    except Exception as e:
        log.critical(action="register_error", trace_info="system", message=f"Registration error: {str(e)}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['internal_error'], 500)
        return JSONResponse(content=response, status_code=status)

@api.post("/login",
         response_model=None,
         responses={
             200: {"description": "Login successful"},
             400: {"description": "Bad request"},
             401: {"description": "Invalid credentials"},
             403: {"description": "Account deactivated or device limit exceeded"},
             404: {"description": "Account not found"}
         })
@rate_limit(max_requests=10, window=60)
@handle_async_errors
async def login(
    request: Request,
    data: LoginRequest,
    client_info: ClientInfo = Depends(validate_device_dependency)
) -> JSONResponse:
    """Authenticate user login with enhanced security and validation"""
    
    if config.is_testing():
        response, status = send_json_response("Ignored because in test mode", 201)
        response.update({"info": None})
        return JSONResponse(content=response, status_code=status)
        
    # Extract and sanitize data
    fullname = data.fullname
    phone = data.phone
    password = data.password
    device_id = client_info.device_id
    ip_address = client_info.ip_address
    
    # Validate and format phone number
    formatted_phone, phone_error = format_phone_number(phone)
    if not formatted_phone:
        response, status = send_json_response(phone_error, 400)
        return JSONResponse(content=response, status_code=status)
        
    # Check login attempts
    identifier = f"{formatted_phone}:{fullname}"
    is_allowed, remaining_attempts = await check_login_attempts(identifier)
    
    if not is_allowed:
        log.warning(action="login_rate_limited", trace_info=ip_address, message=f"Login rate limited for: {fullname} remaining attempts: {remaining_attempts}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['rate_limit_exceeded'], 429)
        return JSONResponse(content=response, status_code=status)
    
    # Authenticate user
    madrasa_name = data.madrasa_name or get_env_var("MADRASA_NAME")
    # SECURITY: Validate madrasa_name is in allowed list  
    if not validate_madrasa_name(madrasa_name, ip_address):
        response, status = send_json_response(ERROR_MESSAGES['unauthorized'], 401)
        return JSONResponse(content=response, status_code=status)
    
    
    try: 
        async with get_db_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                # Get user by phone and fullname
                await cursor.execute(
                    "SELECT * FROM people WHERE phone = %s AND fullname = %s",
                    (formatted_phone, fullname)
                )
                user = await cursor.fetchone()
                
                if not user:
                    await record_login_attempt(identifier, False)
                    log.error(action="login_user_not_found", trace_info=formatted_phone, message=f"User not found: {fullname}", secure=True)
                    response, status = send_json_response(ERROR_MESSAGES['account_not_found'], 404)
                    return JSONResponse(content=response, status_code=status)
                
                # Check password
                if not check_password_hash(user["password_hash"], password or ""):
                    await record_login_attempt(identifier, False)
                    log.warning(action="login_incorrect_password", trace_info=formatted_phone, message="Incorrect password", secure=True)
                    response, status = send_json_response(ERROR_MESSAGES['invalid_credentials'], 401)
                    return JSONResponse(content=response, status_code=status)
                
                # Check if account is deactivated
                if user["deactivated_at"] is not None:
                    log.warning(action="login_account_deactivated", trace_info=formatted_phone, message="Account is deactivated", secure=True)
                    response, status = send_json_response(ERROR_MESSAGES['account_deactivated'], 403)
                    response.update({"action": "deactivate"})
                    return JSONResponse(content=response, status_code=status)
                
                # Check device limit
                is_device_allowed, device_limit_error = await check_device_limit(user["user_id"], device_id)
                if not is_device_allowed:
                    log.warning(action="login_device_limit_exceeded", trace_info=formatted_phone, message=f"Device limit exceeded for user: {fullname}", secure=True)
                    response, status = send_json_response(device_limit_error, 403)
                    return JSONResponse(content=response, status_code=status)
                
                # Record successful login
                await record_login_attempt(identifier, True)
                
                # Get user's profile information
                await cursor.execute(
                    "SELECT * FROM people WHERE user_id = %s",
                    (user["user_id"],)
                )
                profile = await cursor.fetchone()
                
                if not profile:
                    log.critical(action="login_profile_not_found", trace_info=formatted_phone, message="User profile not found", secure=True)
                    response, status = send_json_response(ERROR_MESSAGES['internal_error'], 500)
                    return JSONResponse(content=response, status_code=status)
                
                # Process profile data
                info = await get_client_info_from_helpers(request=None, full_record=profile)
                
                # Check if profile is incomplete
                incomplete_fields = []
                if info.get('student_id') == None:
                    incomplete_fields.append('student_id')
                if info.get('birth_date') == None:
                    incomplete_fields.append('birth_date')
                if info.get('join_date') == None:
                    incomplete_fields.append('join_date')
                
                if incomplete_fields:
                    log.warning(action="login_incomplete_profile", trace_info=formatted_phone, message="Missing profile info", secure=True)
                    response, status = send_json_response("Additional info required", 422)
                    response.update({"error": "incomplete_profile", "info" : info})
                    return JSONResponse(content=response, status_code=status)
                
                # Remove sensitive information
                info.pop("password", None)
                info.pop("password_hash", None)
                
                # Update last login
                await cursor.execute(
                    "UPDATE people SET last_login = %s WHERE user_id = %s",
                    (datetime.now(timezone.utc), user["user_id"])
                )
                await conn.commit()
                
                # Track device
                await cursor.execute("""
                    INSERT INTO device_interactions (user_id, device_id, interaction_type, ip_address)
                    VALUES (%s, %s, 'login', %s)
                """, (user["user_id"], device_id, ip_address))
                await conn.commit()
                
                log.info(action="login_successful", trace_info=ip_address, message=f"User logged in successfully: {fullname}", secure=False)
                
                response, status = send_json_response("Login successful", 200)
                response.update({"info": info})
                return JSONResponse(content=response, status_code=status)
                
    except Exception as e:
        log.critical(action="login_error", trace_info=ip_address, message=f"Login error: {str(e)}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['internal_error'], 500)
        return JSONResponse(content=response, status_code=status)

@api.post("/send_code",
         response_model=None,
         responses={
             200: {"description": "Code sent successfully"},
             400: {"description": "Bad request"},
             409: {"description": "User already exists"},
             429: {"description": "Rate limit exceeded"}
         })
@rate_limit(max_requests=10, window=60)
@handle_async_errors
async def send_verification_code(
    request: Request,
    data: SendCodeRequest,
    client_info: ClientInfo = Depends(validate_device_dependency)
) -> JSONResponse:
    """Send verification code via SMS or email with enhanced security"""
    # Test mode handling
    if config.is_testing():
        response, status = send_json_response(f"Verification code sent to {config.DUMMY_EMAIL}", 200)
        return JSONResponse(content=response, status_code=status)
    
    try:
        # Extract and sanitize data
        phone = data.phone
        fullname = data.fullname
        password = data.password
        email = data.email
        ip_address = client_info.ip_address
        
        # Validate and format phone number
        formatted_phone, phone_error = format_phone_number(phone)
        if not formatted_phone:
            response, status = send_json_response(phone_error, 400)
            return JSONResponse(content=response, status_code=status)
        
        # Validate fullname if provided
        is_valid_name, name_error = validate_fullname(fullname)
        if not is_valid_name:
            response, status = send_json_response(name_error, 400)
            return JSONResponse(content=response, status_code=status)
        
        # Validate password if provided
        if password:
            is_valid_password, password_error = validate_password_strength(password)
            if not is_valid_password:
                response, status = send_json_response(password_error, 400)
                return JSONResponse(content=response, status_code=status)
        
        # Validate email if provided
        if email:
            is_valid_email, email_error = validate_email(email)
            if not is_valid_email:
                response, status = send_json_response(email_error, 400)
                return JSONResponse(content=response, status_code=status)
        else:
            email = await get_email(phone=formatted_phone, fullname=fullname)
        
        # Check if user already exists
        async with get_db_connection() as conn:
            async with conn.cursor() as cursor:
                if fullname and password:
                    # Check if user exists (for registration)
                    await cursor.execute(
                        "SELECT user_id FROM people WHERE phone = %s AND fullname = %s",
                        (formatted_phone, fullname)
                    )
                    existing_user = await cursor.fetchone()
                    
                    if existing_user:
                        log.warning(action="send_code_user_exists", trace_info=ip_address, message=f"User already exists: {fullname}", secure=False)
                        response, status = send_json_response(ERROR_MESSAGES['user_already_exists'], 409)
                        return JSONResponse(content=response, status_code=status)
                
                # Check rate limit for verification codes
                await cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM sms_logs
                    WHERE phone = %s
                    AND created_at > DATE_SUB(NOW(), INTERVAL 1 HOUR)
                """, (formatted_phone,))
                
                result = await cursor.fetchone()
                count = result[0] if result else 0
                
                # Check rate limits
                max_limit = max(config.SMS_LIMIT_PER_HOUR, config.EMAIL_LIMIT_PER_HOUR)
                if count >= max_limit:
                    log.warning(action="send_code_rate_limited", trace_info=ip_address, message=f"Rate limit exceeded for phone: {formatted_phone}", secure=False)
                    response, status = send_json_response(ERROR_MESSAGES['rate_limit_exceeded'], 429)
                    return JSONResponse(content=response, status_code=status)
                
                # Generate and send verification code
                code = generate_code()
                
                # Try SMS first
                if count < config.SMS_LIMIT_PER_HOUR:
                    sms_sent = await send_sms(
                        phone=formatted_phone,
                        msg=f"Your verification code is: {code}"
                    )
                    
                    if sms_sent:
                        # Store in database
                        await cursor.execute("""
                            INSERT INTO sms_logs (phone, code, ip_address, expires_at)
                            VALUES (%s, %s, %s, DATE_ADD(NOW(), INTERVAL 10 MINUTE))
                        """, (formatted_phone, code, ip_address))
                        await conn.commit()
                        
                        log.info(action="verification_code_sent_sms", trace_info=ip_address, message=f"Verification code sent via SMS to: {formatted_phone}", secure=False)
                        
                        response, status = send_json_response(f"Verification code sent to {formatted_phone}", 200)
                        return JSONResponse(content=response, status_code=status)
                
                # Try email if SMS failed or limit reached
                if email and count < config.EMAIL_LIMIT_PER_HOUR:
                    email_sent = await send_email(
                        to_email=email,
                        subject="Verification Code",
                        body=f"Your verification code is: {code}"
                    )
                    
                    if email_sent:
                        # Store in database
                        await cursor.execute("""
                            INSERT INTO sms_logs (phone, code, ip_address, expires_at)
                            VALUES (%s, %s, %s, DATE_ADD(NOW(), INTERVAL 10 MINUTE))
                        """, (formatted_phone, code, ip_address))
                        await conn.commit()
                        
                        log.info(action="verification_code_sent_email", trace_info=ip_address, message=f"Verification code sent via email to: {email}", secure=False)
                        
                        response, status = send_json_response(f"Verification code sent to {email}", 200)
                        return JSONResponse(content=response, status_code=status)
                
                # If both methods failed
                log.critical(action="verification_code_failed", trace_info=ip_address, message="Failed to send verification code via any method", secure=False)
                response, status = send_json_response("Failed to send verification code", 500)
                return JSONResponse(content=response, status_code=status)
                
    except Exception as e:
        log.critical(action="send_code_error", trace_info="system", message=f"Error sending verification code: {str(e)}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['internal_error'], 500)
        return JSONResponse(content=response, status_code=status)

@api.post("/reset_password")
@handle_async_errors
async def reset_password(
    request: Request,
    data: ResetPasswordRequest,
    client_info: ClientInfo = Depends(validate_device_dependency)
) -> JSONResponse:
    """Reset user password with enhanced security validation"""
    
    try:
        # Extract and sanitize data
        phone = data.phone
        fullname = data.fullname
        old_password = data.old_password
        new_password = data.new_password
        code = data.code
        device_id = client_info.device_id
        ip_address = client_info.ip_address
        
        # Test mode handling
        if config.is_testing():
            if not new_password:
                response, status = send_json_response("App in test mode", 200)
                return JSONResponse(content=response, status_code=status)
            else:
                response, status = send_json_response("App in test mode", 201)
                return JSONResponse(content=response, status_code=status)
        
        # Validate and format phone number
        formatted_phone, phone_error = format_phone_number(phone)
        if not formatted_phone:
            response, status = send_json_response(phone_error, 400)
            return JSONResponse(content=response, status_code=status)
        
        # If old password is not provided, use code verification
        if not old_password:
            if code:
                # Verify code
                validate_code_result = await check_code(code, formatted_phone)
                if validate_code_result is not None:
                    return validate_code_result
                elif not new_password:
                    response, status = send_json_response("Code successfully matched", 200)
                    return JSONResponse(content=response, status_code=status)
        
        # Validate new password if provided
        if new_password:
            is_valid_password, password_error = validate_password_strength(new_password)
            if not is_valid_password:
                response, status = send_json_response(password_error, 400)
                return JSONResponse(content=response, status_code=status)
        
        # Authenticate user and update password
        
        # Validate madrasa name
        madrasa_name = data.madrasa_name or get_env_var("MADRASA_NAME")
        # SECURITY: Validate madrasa_name is in allowed list
        if not validate_madrasa_name(madrasa_name, ip_address):
            response, status = send_json_response(ERROR_MESSAGES['unauthorized'], 401)
            return JSONResponse(content=response, status_code=status)
        
        
        async with get_db_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                # Get user
                await cursor.execute(
                    "SELECT * FROM people WHERE phone = %s AND fullname = %s",
                    (formatted_phone, fullname)
                )
                user = await cursor.fetchone()
                
                if not user:
                    log.error(action="reset_password_user_not_found", trace_info=formatted_phone, message=f"User not found: {fullname}", secure=True)
                    response, status = send_json_response(ERROR_MESSAGES['account_not_found'], 404)
                    return JSONResponse(content=response, status_code=status)
                
                # Check device limit
                is_device_allowed, device_limit_error = await check_device_limit(user["user_id"], device_id)
                if not is_device_allowed:
                    log.warning(action="reset_password_device_limit_exceeded", trace_info=formatted_phone, message=f"Device limit exceeded during password reset for user: {fullname}", secure=True)
                    response, status = send_json_response(device_limit_error, 403)
                    return JSONResponse(content=response, status_code=status)
                
                # If old password is provided, verify it
                if old_password:
                    if not check_password_hash(user['password_hash'], old_password):
                        log.warning(action="reset_password_incorrect_old_password", trace_info=formatted_phone, message="Incorrect old password", secure=True)
                        response, status = send_json_response("Incorrect old password", 401)
                        return JSONResponse(content=response, status_code=status)
                
                # Hash new password
                if not new_password:
                    response, status = send_json_response("New password is required", 400)
                    return JSONResponse(content=response, status_code=status)
                hashed_password = generate_password_hash(new_password)
                
                # Check if new password is same as current
                if check_password_hash(user['password_hash'], new_password):
                    response, status = send_json_response("New password cannot be the same as the current password.", 400)
                    return JSONResponse(content=response, status_code=status)
                
                # Update password
                await cursor.execute(
                    "UPDATE people SET password_hash = %s, updated_at = %s WHERE user_id = %s",
                    (hashed_password, datetime.now(timezone.utc), user['user_id'])
                )
                await conn.commit()
                
                # Track password reset event
                await cursor.execute("""
                    INSERT INTO password_reset_logs (user_id, ip_address, reset_method)
                    VALUES (%s, %s, %s)
                """, (user['user_id'], ip_address, 'code' if code else 'old_password'))
                await conn.commit()
                
                log.info(action="password_reset_successful", trace_info=ip_address, message=f"Password reset successful for: {fullname}", secure=False)
                
                response, status = send_json_response("Password Reset Successful", 201)
                return JSONResponse(content=response, status_code=status)
                
    except Exception as e:
        log.critical(action="reset_password_error", trace_info="system", message=f"Password reset error: {str(e)}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['internal_error'], 500)
        return JSONResponse(content=response, status_code=status)

@api.post("/account/{page_type}")
@rate_limit(max_requests=10, window=60)
@handle_async_errors
async def manage_account(
    page_type: str,
    request: Request,
    data: BaseAuthRequest,
    client_info: ClientInfo = Depends(validate_device_dependency)
) -> JSONResponse:
    """Manage account (deactivate/delete) with enhanced security"""
    # Validate page type
    if page_type not in ("remove", "deactivate", "delete"):
        response, status = send_json_response("Invalid page type", 400)
        return JSONResponse(content=response, status_code=status)
    
    # Handle POST request
    try:
        # Extract and sanitize data
        phone = data.phone
        fullname = data.fullname
        password = data.password if hasattr(data, 'password') else None
        
        # Validate and format phone number
        formatted_phone, phone_error = format_phone_number(phone)
        if not formatted_phone:
            response, status = send_json_response(phone_error, 400)
            return JSONResponse(content=response, status_code=status)
        
        # Authenticate user
        async with get_db_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                # Get user
                await cursor.execute(
                    "SELECT * FROM people WHERE phone = %s AND fullname = %s",
                    (formatted_phone, fullname)
                )
                user = await cursor.fetchone()
                
                if not user or not check_password_hash(user["password_hash"], password or ""):
                    log.error(action="manage_account_invalid_credentials", trace_info=formatted_phone, message="Invalid credentials for account management", secure=True)
                    response, status = send_json_response("Invalid login details", 401)
                    return JSONResponse(content=response, status_code=status)
                
                # Prepare confirmation message
                deletion_days = config.ACCOUNT_DELETION_DAYS
                if page_type in ["remove", "delete"]:
                    subject = "Account Deletion Confirmation"
                    msg = f"Your account will be permanently deleted in {deletion_days} days. To cancel, log in and reactivate."
                else:
                    subject = "Account Deactivation Confirmation"
                    msg = "Your account has been deactivated. You can reactivate it anytime by logging in."
                
                # Send confirmation via SMS
                errors = 0
                if not await send_sms(phone=formatted_phone, msg=msg):
                    errors += 1
                
                # Send confirmation via email if available
                email = await get_email(fullname=fullname, phone=formatted_phone)
                if email:
                    is_valid_email, email_error = validate_email(email)
                    if not is_valid_email:
                        response, status = send_json_response(email_error, 400)
                        return JSONResponse(content=response, status_code=status)
                    if not await send_email(to_email=email, subject=subject, body=msg):
                        errors += 1
                else:
                    errors += 1
                
                if errors > 1:
                    log.critical(action="manage_account_notification_failed", trace_info=formatted_phone, message="Could not send confirmation notifications", secure=True)
                    response, status = send_json_response("Could not send confirmation. Try again later.", 500)
                    return JSONResponse(content=response, status_code=status)
                
                # Schedule deactivation/deletion
                now = datetime.now(timezone.utc)
                scheduled_deletion = now + timedelta(days=deletion_days) if page_type in ["remove", "delete"] else None
                
                await cursor.execute(
                    """UPDATE people SET 
                    deactivated_at = %s, 
                    scheduled_deletion_at = %s,
                    updated_at = %s
                    WHERE user_id = %s""",
                    (now, scheduled_deletion, now, user["user_id"])
                )
                await conn.commit()
                
                # Log the action
                action = "delete" if page_type in ["remove", "delete"] else "deactivate"
                await cursor.execute(
                    """INSERT INTO account_actions (user_id, action_type, ip_address)
                    VALUES (%s, %s, %s)""",
                    (user["user_id"], action, client_info.ip_address)
                )
                await conn.commit()
                
                if page_type in ["remove", "delete"]:
                    log.warning(action="account_deletion_scheduled", trace_info=formatted_phone, message=f"User {hash_sensitive_data(fullname)} scheduled for deletion", secure=True)
                    response, status = send_json_response("Account deletion initiated. Check your messages.", 200)
                    return JSONResponse(content=response, status_code=status)
                else:
                    log.warning(action="account_deactivated", trace_info=formatted_phone, message=f"User {hash_sensitive_data(fullname)} deactivated", secure=True)
                    response, status = send_json_response("Account deactivated successfully.", 200)
                    return JSONResponse(content=response, status_code=status)
                    
    except Exception as e:
        log.critical(action="manage_account_error", trace_info="system", message=f"Account management error: {str(e)}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['internal_error'], 500)
        return JSONResponse(content=response, status_code=status)

@api.post("/account/reactivate")
@rate_limit(max_requests=10, window=60)
@handle_async_errors
async def undo_remove(
    request: Request,
    data: BaseAuthRequest,
    client_info: ClientInfo = Depends(validate_device_dependency)
) -> JSONResponse:
    """Reactivate a deactivated account with enhanced validation"""
    
    # Test mode handling
    if config.is_testing():
        response, status = send_json_response("App in test mode", 200)
        return JSONResponse(content=response, status_code=status)
    
    try:
        # Extract and sanitize data
        phone = data.phone
        fullname = data.fullname
        ip_address = client_info.ip_address
        
        # Validate and format phone number
        formatted_phone, phone_error = format_phone_number(phone)
        if not formatted_phone:
            response, status = send_json_response(phone_error, 400)
            return JSONResponse(content=response, status_code=status)
        
        # Reactivate account
        
        # Validate madrasa name
        madrasa_name = data.madrasa_name or get_env_var("MADRASA_NAME")
        # SECURITY: Validate madrasa_name is in allowed list
        if not validate_madrasa_name(madrasa_name, ip_address):
            response, status = send_json_response(ERROR_MESSAGES['unauthorized'], 401)
            return JSONResponse(content=response, status_code=status)
        
        
        async with get_db_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                # Get deactivated user
                await cursor.execute(
                    """SELECT * FROM people 
                    WHERE phone = %s AND fullname = %s AND deactivated_at IS NOT NULL""",
                    (formatted_phone, fullname)
                )
                user = await cursor.fetchone()
                
                if not user or not user["deactivated_at"]:
                    log.warning(action="reactivate_no_deactivated_account", trace_info=ip_address, message=f"No deactivated account found for: {fullname}", secure=False)
                    response, status = send_json_response("No deactivated account found", 404)
                    return JSONResponse(content=response, status_code=status)
                
                # Check if reactivation period has expired
                deactivated_at = user["deactivated_at"]
                if (datetime.now(timezone.utc) - deactivated_at).days > config.ACCOUNT_REACTIVATION_DAYS and user["scheduled_deletion_at"]:
                    log.warning(action="reactivate_period_expired", trace_info=ip_address, message=f"Reactivation period expired for: {fullname}", secure=False)
                    response, status = send_json_response("Undo period expired", 403)
                    return JSONResponse(content=response, status_code=status)
                
                # Reactivate account
                await cursor.execute(
                    """UPDATE people SET 
                    deactivated_at = NULL, 
                    scheduled_deletion_at = NULL,
                    updated_at = %s
                    WHERE user_id = %s""",
                    (datetime.now(timezone.utc), user["user_id"])
                )
                await conn.commit()
                
                # Log the reactivation
                await cursor.execute(
                    """INSERT INTO account_actions (user_id, action_type, ip_address)
                    VALUES (%s, 'reactivate', %s)""",
                    (user["user_id"], ip_address)
                )
                await conn.commit()
                
                log.info(action="account_reactivated_successfully", trace_info=ip_address, message=f"Account reactivated successfully for: {fullname}", secure=False)
                
                response, status = send_json_response("Account reactivated.", 200)
                return JSONResponse(content=response, status_code=status)
                
    except Exception as e:
        log.critical(action="reactivate_error", trace_info="system", message=f"Account reactivation error: {str(e)}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['internal_error'], 500)
        return JSONResponse(content=response, status_code=status)

@api.post("/account/check")
@handle_async_errors
async def get_account_status(
    request: Request,
    data: AccountCheckRequest,
    client_info: ClientInfo = Depends(validate_device_dependency)
) -> JSONResponse:
    """Check account status and validate session with enhanced security"""
    # Test mode handling
    if config.is_testing():
        response, status = send_json_response("App in test mode", 200)
        return JSONResponse(content=response, status_code=status)
    
    try:
        # Extract and validate device information
        device_id = client_info.device_id
        device_brand = client_info.device_brand
        ip_address = client_info.ip_address
        
        # Get other fields
        phone = data.phone
        fullname = data.fullname
        student_id = data.student_id
        birth_date = data.birth_date
        join_date = data.join_date
        
        # Validate madrasa name
        madrasa_name = data.madrasa_name or get_env_var("MADRASA_NAME")
        # SECURITY: Validate madrasa_name is in allowed list
        if not validate_madrasa_name(madrasa_name, ip_address):
            response, status = send_json_response(ERROR_MESSAGES['unauthorized'], 401)
            return JSONResponse(content=response, status_code=status)
        
        # Validate and format phone number
        formatted_phone, phone_error = format_phone_number(phone)
        if not formatted_phone:
            response, status = send_json_response(phone_error, 400)
            response.update({"action": "logout"})
            return JSONResponse(content=response, status_code=status)
        
        # Define fields to check
        checks = {
            "student_id": student_id,
            "birth_date": birth_date,
            "join_date": join_date
        }
        
        # Validate all required fields are present
        for field_name, field_value in checks.items():
            if not field_value:
                log.info(action="account_check_missing_field", trace_info=ip_address, message=f"Field {field_name} is missing", secure=False)
                response, status = send_json_response("Session invalidated. Please log in again.", 400)
                response.update({"action": "logout"})
                return JSONResponse(content=response, status_code=status)
        
        # Validate account in database
        
        async with get_db_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                # Get user record
                await cursor.execute(
                    "SELECT * FROM people WHERE phone = %s AND fullname = %s",
                    (formatted_phone, fullname)
                )
                record = await cursor.fetchone()
                
                if not record:
                    log.error(action="account_check_not_found", trace_info=ip_address, message="No matching user found", secure=False)
                    response, status = send_json_response("Session invalidated. Please log in again.", 401)
                    response.update({"action": "logout"})
                    return JSONResponse(content=response, status_code=status)
                
                # Check if account is deactivated
                if record.get("deactivated_at"):
                    log.warning(action="account_check_deactivated", trace_info=record["user_id"], message="Account is deactivated", secure=False)
                    response, status = send_json_response("Account is deactivated", 401)
                    response.update({"action": "deactivate"})
                    return JSONResponse(content=response, status_code=status)
                
                # Compare provided fields with database values
                for col, provided in checks.items():
                    db_val = record.get(col)
                    
                    # Handle date comparisons
                    if "_date" in col and provided:
                        try:
                            provided_date = datetime.strptime(provided, "%Y-%m-%d").date()
                        except ValueError:
                            log.error(action="account_check_bad_date", trace_info=record["user_id"], message=f"Bad date format: {provided}", secure=False)
                            response, status = send_json_response("Session invalidated. Please log in again.", 401)
                            response.update({"action": "logout"})
                            return JSONResponse(content=response, status_code=status)
                        
                        if db_val:
                            db_date = db_val.date() if isinstance(db_val, dt.datetime) else db_val
                            if db_date != provided_date:
                                log.warning(action="account_check_date_mismatch", trace_info=record["user_id"], message=f"Date mismatch: {col}: {provided_date} != {db_date}", secure=False)
                                response, status = send_json_response("Session invalidated. Please log in again.", 401)
                                response.update({"action": "logout"})
                                return JSONResponse(content=response, status_code=status)
                    else:
                        # Compare string values
                        if str(provided).strip() != str(db_val).strip():
                            log.warning(action="account_check_field_mismatch", trace_info=record["user_id"], message=f"Field mismatch: {col}: {hash_sensitive_data(str(provided))} != {hash_sensitive_data(str(db_val))}", secure=False)
                            response, status = send_json_response("Session invalidated. Please log in again.", 401)
                            response.update({"action": "logout"})
                            return JSONResponse(content=response, status_code=status)
                
                # Check device limit
                is_device_allowed, device_limit_error = await check_device_limit(record["user_id"], device_id)
                if not is_device_allowed:
                    log.warning(action="account_check_device_limit_exceeded", trace_info=record["user_id"], message=f"Device limit exceeded during account check for user: {record['user_id']}", secure=False)
                    response, status = send_json_response(device_limit_error, 403)
                    response.update({"action": "logout"})
                    return JSONResponse(content=response, status_code=status)
                
                # Track device interaction
                await cursor.execute(
                    """INSERT INTO device_interactions (user_id, device_id, interaction_type, ip_address)
                    VALUES (%s, %s, 'check', %s)""",
                    (record["user_id"], device_id, ip_address)
                )
                await conn.commit()
                
                log.info(action="account_check_successful", trace_info=ip_address, message=f"Account check successful for user: {record['user_id']}", secure=False)
                
                response, status = send_json_response("Account is valid", 200)
                response.update({"user_id": record["user_id"]})
                return JSONResponse(content=response, status_code=status)
                
    except Exception as e:
        log.critical(action="account_check_error", trace_info="system", message=f"Account check error: {str(e)}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['internal_error'], 500)
        return JSONResponse(content=response, status_code=status)

# ─── Advanced Security and Monitoring Functions ─────────────────────────────────

def validate_session_security(session_data: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate session security parameters"""
    required_fields = ['user_id', 'device_id', 'ip_address']
    
    for field in required_fields:
        if not session_data.get(field):
            return False, f"Missing required session field: {field}"
    
    # Validate session age
    session_timestamp = session_data.get('timestamp')
    if session_timestamp:
        try:
            session_time = datetime.fromisoformat(session_timestamp.replace('Z', '+00:00'))
            if (datetime.now(timezone.utc) - session_time).total_seconds() > config.SESSION_TIMEOUT_HOURS * 3600:
                return False, "Session has expired"
        except ValueError:
            return False, "Invalid session timestamp"
    
    return True, ""

async def track_user_activity(user_id: int, activity_type: str, details: Dict[str, Any]) -> None:
    """Track user activity for security monitoring"""
    try:
        activity_data = {
            'user_id': user_id,
            'activity_type': activity_type,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'ip_address': None,  # No request context available in this helper function
            'details': details or {}
        }
        
        # Log activity for monitoring
        log.info(
            action=f"user_activity_{activity_type}",
            trace_info=activity_data['ip_address'],
            message=f"User activity: {activity_type}",
            **activity_data
        )
        
        # Store in cache for rate limiting using KeyDB-backed helper
        from utils.helpers.helpers import set_cached_data
        cache_key = f"user_activity:{user_id}:{activity_type}"
        await set_cached_data(cache_key, activity_data, ttl=3600)
        
    except Exception as e:
                log.critical(action="activity_tracking_error", trace_info="system", message=f"Error tracking user activity: {str(e)}", secure=False)

async def check_account_security_status(user_id: int) -> Dict[str, Any]:
    """Check account security status and return security metrics"""
    try:
        # Get recent login attempts
        from utils.helpers.helpers import get_cached_data
        login_attempts = await get_cached_data(f"login_attempts:{user_id}", default=0)
        
        # Get recent activities
        recent_activities = []
        for activity_type in ['login', 'logout', 'password_change', 'account_modification']:
            activity_data = await get_cached_data(f"user_activity:{user_id}:{activity_type}", default=None)
            if activity_data:
                recent_activities.append(activity_data)
        
        # Calculate security score
        security_score = 100
        
        if login_attempts > 3:
            security_score -= 20
        
        if len(recent_activities) > 10:
            security_score -= 10
        
        return {
            'security_score': max(0, security_score),
            'login_attempts': login_attempts,
            'recent_activities': len(recent_activities),
            'last_activity': recent_activities[-1] if recent_activities else None
        }
        
    except Exception as e:
        log.critical(action="security_status_check_error", trace_info="system", message=f"Error checking security status: {str(e)}", secure=False)
        return {
            'security_score': 0,
            'login_attempts': 0,
            'recent_activities': 0,
            'last_activity': None
        }