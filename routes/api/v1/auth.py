from enum import Enum
from datetime import datetime, timedelta, timezone
import datetime as dt
from typing import Optional

import aiomysql
from fastapi import Request, Depends
from fastapi.responses import JSONResponse
from pydantic import field_validator
from werkzeug.security import generate_password_hash, check_password_hash

from utils.helpers.improved_functions import get_env_var, send_json_response

# Local imports
from routes.api import api
from utils.mysql.database_utils import get_traced_db_cursor
from config import config
from utils.helpers.helpers import (
    check_code, get_global_id, validate_device_limit, format_phone_number, generate_code, get_id, 
    record_login_attempt, send_sms, send_email, 
    get_email, encrypt_sensitive_data, hash_sensitive_data,
    validate_email, validate_login_attempts, validate_password_strength,
    handle_async_errors
)
from utils.helpers.logger import log
from utils.helpers.fastapi_helpers import (
    BaseAuthRequest, ClientInfo, validate_device_dependency,
    rate_limit
)

# ─── Pydantic Models ───────────────────────────────────────────
class RegisterRequest(BaseAuthRequest):
    """Registration request model extending base auth request"""
    password: str
    code: int
    email: Optional[str] = None
    
    @field_validator('password')
    def validate_password_field(cls, v):
        validate_password_strength(v)
        return v
    
    @field_validator('email')
    def validate_email_field(cls, v):
        if v:
            validate_email(v)
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
    code: Optional[int] = None

    @field_validator('new_password')
    def validate_new_password_field(cls, v):
        if v:
            validate_password_strength(v)
        return v

class AccountCheckRequest(BaseAuthRequest):
    """Account check request"""
    email: Optional[str] = None
    member_id: Optional[int] = None
    student_id: str | int | None = None
    name_en: Optional[str] = None
    name_bn: Optional[str] = None
    name_ar: Optional[str] = None
    date_of_birth: datetime | str | None = None
    birth_certificate: str | int | None = None
    national_id: str | int | None = None
    blood_group: Optional[str] = None
    gender: Optional[str] = None
    title1: Optional[str] = None
    title2: Optional[str] = None
    source: Optional[str] = None
    present_address: Optional[str] = None
    address_en: Optional[str] = None
    address_bn: Optional[str] = None
    address_ar: Optional[str] = None
    permanent_address: Optional[str] = None
    father_or_spouse: Optional[str] = None
    father_en: Optional[str] = None
    father_bn: Optional[str] = None
    father_ar: Optional[str] = None
    mother_en: Optional[str] = None
    mother_bn: Optional[str] = None
    mother_ar: Optional[str] = None
    class_name: Optional[str] = None
    guardian_number: Optional[str] = None
    degree: Optional[str] = None
    image_path: Optional[str] = None

class ManageAccountPageType(str, Enum):
    deactivate = "deactivate"
    delete = "delete"

class ManageAccountRequest(BaseAuthRequest):
    """Manage account request (deactivate/delete)"""
    password: str

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
    
    try:
        # Data is already validated by Pydantic, client info by dependency
        fullname = data.fullname
        email = data.email
        phone = data.phone
        password = data.password
        user_code = data.code
        ip_address = client_info.ip_address
        madrasa_name = data.madrasa_name or get_env_var("MADRASA_NAME")

        # Verify code
        await check_code(user_code, phone)

        # Hash password with salt
        hashed_password = generate_password_hash(str(password))
        hashed_phone = hash_sensitive_data(phone)
        encrypted_phone = encrypt_sensitive_data(phone)
        encrypted_email = encrypt_sensitive_data(email) if email else None
        hashed_email = hash_sensitive_data(email) if email else None
                
        # Insert user into database
        
        try:
            async with get_traced_db_cursor() as cursor:
                # Check if user already exists
                existing_user = await get_global_id(phone, fullname)
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
                    (fullname, phone, hashed_phone, encrypted_phone, 
                    hashed_password, email, hashed_email, encrypted_email, ip_address)
                )
                
                # Get new user ID
                user_id = await get_global_id(phone, fullname)
                
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
                    (fullname, phone)
                )
                people_result = await cursor.fetchone()
                
                # Update people record with user_id if found
                if people_result:
                    await cursor.execute(
                        "UPDATE peoples SET user_id = %s WHERE LOWER(name) = LOWER(%s) AND phone = %s",
                        (user_id, fullname, phone)
                    )
                
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
        
    # Extract and sanitize data
    fullname = data.fullname
    phone = data.phone
    password = data.password
    device_id = client_info.device_id
    ip_address = client_info.ip_address
    madrasa_name = data.madrasa_name or get_env_var("MADRASA_NAME")
    
    # Check login attempts
    await validate_login_attempts(phone, fullname, request)    
    
    try: 
        async with get_traced_db_cursor() as cursor:
                # Get user by phone and name
                await cursor.execute(
                    f"SELECT * FROM {madrasa_name}.peoples WHERE phone = %s AND LOWER(name) = LOWER(%s)",
                    (phone, fullname)
                )
                user = await cursor.fetchone()
                
                if not user:
                    await record_login_attempt(phone, fullname, False)
                    log.error(action="login_user_not_found", trace_info=phone, message=f"User not found: {fullname}", secure=True)
                    response, status = send_json_response(ERROR_MESSAGES['account_not_found'], 404)
                    return JSONResponse(content=response, status_code=status)
                
                # Check password
                if not check_password_hash(user["password_hash"], password or ""):
                    await record_login_attempt(phone, fullname, False)
                    log.warning(action="login_incorrect_password", trace_info=phone, message="Incorrect password", secure=True)
                    response, status = send_json_response(ERROR_MESSAGES['invalid_credentials'], 401)
                    return JSONResponse(content=response, status_code=status)
                
                # Check if account is deactivated
                if user["deactivated_at"] is not None:
                    log.warning(action="login_account_deactivated", trace_info=phone, message="Account is deactivated", secure=True)
                    response, status = send_json_response(ERROR_MESSAGES['account_deactivated'], 403)
                    response.update({"action": "deactivate"})
                    return JSONResponse(content=response, status_code=status)
                
                # Check device limit
                await validate_device_limit(device_id, ip_address, request)
                
                # Record successful login
                await record_login_attempt(phone, fullname, True)
                
                # Get user's profile information
                await cursor.execute(
                    f"SELECT * FROM {madrasa_name}.peoples WHERE user_id = %s",
                    (user["user_id"],)
                )
                profile = await cursor.fetchone()
                
                if not profile:
                    log.critical(action="login_profile_not_found", trace_info=phone, message="User profile not found", secure=True)
                    response, status = send_json_response(ERROR_MESSAGES['internal_error'], 500)
                    return JSONResponse(content=response, status_code=status)
                                
                # Check if profile is incomplete
                # TODO: Implement profile completeness check
                
                # Remove sensitive information
                profile.pop("password", None)
                profile.pop("password_hash", None)
                
                # TODO: Update last login
                # await cursor.execute(
                #     "UPDATE people SET last_login = %s WHERE user_id = %s",
                #     (datetime.now(timezone.utc), user["user_id"])
                # )
                
                # TODO: Track device
                # await cursor.execute("""
                #     INSERT INTO device_interactions (user_id, device_id, interaction_type, ip_address)
                #     VALUES (%s, %s, 'login', %s)
                # """, (user["user_id"], device_id, ip_address))
                
                log.info(action="login_successful", trace_info=ip_address, message=f"User logged in successfully: {fullname}", secure=False)
                
                response, status = send_json_response("Login successful", 200)
                response.update({"info": profile})
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
    
    try:
        # Extract and sanitize data
        phone = data.phone
        fullname = data.fullname
        password = data.password
        email = data.email
        ip_address = client_info.ip_address
        madrasa_name = data.madrasa_name or get_env_var("MADRASA_NAME")

        if not email:
            email = await get_email(phone=phone, fullname=fullname)
        
        # Check if user already exists
        async with get_traced_db_cursor() as cursor:
                # Check if user exists (for registration)
                existing_user = await get_id(phone, fullname, madrasa_name)
                if existing_user:
                    log.warning(action="send_code_user_exists", trace_info=ip_address, message=f"User already exists: {fullname}", secure=False)
                    response, status = send_json_response(ERROR_MESSAGES['user_already_exists'], 409)
                    return JSONResponse(content=response, status_code=status)
                
                # Check rate limit for verification codes
                await cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM global.verifications
                    WHERE phone = %s
                    AND created_at > DATE_SUB(NOW(), INTERVAL 1 HOUR)
                """, (phone,))
                
                result = await cursor.fetchone()
                count = result[0] if result else 0
                
                # Check rate limits
                max_limit = max(config.SMS_LIMIT_PER_HOUR, config.EMAIL_LIMIT_PER_HOUR)
                if count >= max_limit:
                    log.warning(action="send_code_rate_limited", trace_info=ip_address, message=f"Rate limit exceeded for phone: {phone}", secure=False)
                    response, status = send_json_response(ERROR_MESSAGES['rate_limit_exceeded'], 429)
                    return JSONResponse(content=response, status_code=status)
                
                # Generate and send verification code
                code = generate_code()
                
                # Try SMS first
                if count < config.SMS_LIMIT_PER_HOUR:
                    log.info(action="send_code_attempting_sms", trace_info=ip_address, message=f"Attempting to send SMS to: {phone}, code: {code}", secure=False)
                    sms_sent = await send_sms(
                        phone=phone,
                        msg=f"Your verification code is: {code}"
                    )
                    
                    log.info(action="send_code_sms_result", trace_info=ip_address, message=f"SMS send result: {sms_sent} (type: {type(sms_sent)})", secure=False)
                    
                    if sms_sent:
                        # Store in database
                        await cursor.execute("""
                            INSERT INTO global.verifications (phone, code, ip_address, expires_at)
                            VALUES (%s, %s, %s, DATE_ADD(NOW(), INTERVAL 10 MINUTE))
                        """, (phone, code, ip_address))
                        
                        log.info(action="verification_code_sent_sms", trace_info=ip_address, message=f"Verification code sent via SMS to: {phone}", secure=False)
                        
                        response, status = send_json_response(f"Verification code sent to {phone}", 200)
                        return JSONResponse(content=response, status_code=status)
                    else:
                        log.warning(action="send_code_sms_failed", trace_info=ip_address, message=f"SMS sending failed for phone: {phone}", secure=False)
                
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
                            INSERT INTO global.verifications (phone, code, ip_address, expires_at)
                            VALUES (%s, %s, %s, DATE_ADD(NOW(), INTERVAL 10 MINUTE))
                        """, (phone, code, ip_address))
                        
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
        madrasa_name = data.madrasa_name or get_env_var("MADRASA_NAME")
                
        # If old password is not provided, use code verification
        if not old_password:
            await check_code(code or 0, phone)
            if not new_password:
                response, status = send_json_response("Code successfully matched", 200)
                return JSONResponse(content=response, status_code=status)        
        
        async with get_traced_db_cursor() as cursor:
                # Get user
                await cursor.execute(
                    f"SELECT * FROM {madrasa_name}.peoples WHERE phone = %s AND LOWER(fullname) = LOWER(%s)",
                    (phone, fullname)
                )
                user = await cursor.fetchone()
                
                if not user:
                    log.error(action="reset_password_user_not_found", trace_info=phone, message=f"User not found: {fullname}", secure=True)
                    response, status = send_json_response(ERROR_MESSAGES['account_not_found'], 404)
                    return JSONResponse(content=response, status_code=status)
                
                # Check device limit
                await validate_device_limit(device_id, ip_address, request)
                
                # If old password is provided, verify it
                if old_password:
                    if not check_password_hash(user['password_hash'], old_password):
                        log.warning(action="reset_password_incorrect_old_password", trace_info=phone, message="Incorrect old password", secure=True)
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
                
                # TODO: Track password reset event
                # await cursor.execute("""
                #     INSERT INTO logs.password_reset_logs (user_id, ip_address, reset_method)
                #     VALUES (%s, %s, %s)
                # """, (user['user_id'], ip_address, 'code' if code else 'old_password'))
                
                log.info(action="password_reset_successful", trace_info=ip_address, message=f"Password reset successful for: {fullname}", secure=False)
                
                response, status = send_json_response("Password Reset Successful", 201)
                return JSONResponse(content=response, status_code=status)
                
    except Exception as e:
        log.critical(action="reset_password_error", trace_info="system", message=f"Password reset error: {str(e)}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['internal_error'], 500)
        return JSONResponse(content=response, status_code=status)

@api.post("/account/{page_type}", name="manage_account")
@rate_limit(max_requests=10, window=60)
@handle_async_errors
async def manage_account(
    page_type: ManageAccountPageType,
    data: ManageAccountRequest,
    client_info: ClientInfo = Depends(validate_device_dependency)
) -> JSONResponse:
    """Manage account (deactivate/delete) with enhanced security"""
    try:
        # Extract and sanitize data
        phone = data.phone
        fullname = data.fullname
        password = data.password
        madrasa_name = data.madrasa_name or get_env_var("MADRASA_NAME")

        # Authenticate user
        async with get_traced_db_cursor() as cursor:
                # Get user
                await cursor.execute(
                    f"SELECT * FROM s WHERE phone = %s AND fullname = %s",
                    (phone, fullname)
                )
                user = await cursor.fetchone()
                
                if not user or not check_password_hash(user["password_hash"], password or ""):
                    log.error(action="manage_account_invalid_credentials", trace_info=phone, message="Invalid credentials for account management", secure=True)
                    response, status = send_json_response("Invalid login details", 401)
                    return JSONResponse(content=response, status_code=status)
                
                # Prepare confirmation message
                deletion_days = config.ACCOUNT_DELETION_DAYS
                if page_type == ManageAccountPageType.delete:
                    subject = "Account Deletion Confirmation"
                    msg = f"Your account will be permanently deleted in {deletion_days} days. To cancel, log in and reactivate."
                else:
                    subject = "Account Deactivation Confirmation"
                    msg = "Your account has been deactivated. You can reactivate it anytime by logging in."
                
                # Send confirmation via SMS
                errors = 0
                if not await send_sms(phone=phone, msg=msg):
                    errors += 1
                
                # Send confirmation via email if available
                email = await get_email(fullname=fullname, phone=phone)
                if email:
                    if not await send_email(to_email=email, subject=subject, body=msg):
                        errors += 1
                else:
                    errors += 1
                
                if errors > 1:
                    log.critical(action="manage_account_notification_failed", trace_info=phone, message="Could not send confirmation notifications", secure=True)
                    response, status = send_json_response("Could not send confirmation. Try again later.", 500)
                    return JSONResponse(content=response, status_code=status)
                
                # Schedule deactivation/deletion
                now = datetime.now(timezone.utc)
                scheduled_deletion = now + timedelta(days=deletion_days) if page_type == ManageAccountPageType.delete else None
                
                await cursor.execute(
                    f"""UPDATE {madrasa_name}.peoples SET 
                    deactivated_at = %s, 
                    scheduled_deletion_at = %s,
                    updated_at = %s
                    WHERE user_id = %s""",
                    (now, scheduled_deletion, now, user["user_id"])
                )
                
                # TODO: Log the action
                # action = "delete" if page_type == ManageAccountPageType.delete else "deactivate"
                # await cursor.execute(
                #     """INSERT INTO account_actions (user_id, action_type, ip_address)
                #     VALUES (%s, %s, %s)""",
                #     (user["user_id"], action, client_info.ip_address)
                # )
                
                
                if page_type == ManageAccountPageType.delete:
                    log.warning(action="account_deletion_scheduled", trace_info=phone, message=f"User {hash_sensitive_data(fullname)} scheduled for deletion", secure=True)
                    response, status = send_json_response("Account deletion initiated. Check your messages.", 200)
                    return JSONResponse(content=response, status_code=status)
                else:
                    log.warning(action="account_deactivated", trace_info=phone, message=f"User {hash_sensitive_data(fullname)} deactivated", secure=True)
                    response, status = send_json_response("Account deactivated successfully.", 200)
                    return JSONResponse(content=response, status_code=status)
                    
    except Exception as e:
        log.critical(action="manage_account_error", trace_info="system", message=f"Account management error: {str(e)}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['internal_error'], 500)
        return JSONResponse(content=response, status_code=status)

@api.post("/account/reactivate")
@rate_limit(max_requests=10, window=60)
@handle_async_errors
async def reactivate_account(
    data: BaseAuthRequest,
    client_info: ClientInfo = Depends(validate_device_dependency)
) -> JSONResponse:
    """Reactivate a deactivated account with enhanced validation"""
    try:
        # Extract and sanitize data
        phone = data.phone
        fullname = data.fullname
        ip_address = client_info.ip_address
        madrasa_name = data.madrasa_name or get_env_var("MADRASA_NAME")
        
        async with get_traced_db_cursor() as cursor:
                # Get deactivated user
                await cursor.execute(
                    f"""SELECT * FROM {madrasa_name}.peoples 
                    WHERE phone = %s AND fullname = %s AND deactivated_at IS NOT NULL""",
                    (phone, fullname)
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
                    f"""UPDATE {madrasa_name}.peoples SET 
                    deactivated_at = NULL, 
                    scheduled_deletion_at = NULL,
                    updated_at = %s
                    WHERE user_id = %s""",
                    (datetime.now(timezone.utc), user["user_id"])
                )
                
                
                # TODO: Log the reactivation
                # await cursor.execute(
                #     f"""INSERT INTO {madrasa_name}.account_actions (user_id, action_type, ip_address)
                #     VALUES (%s, 'reactivate', %s)""",
                #     (user["user_id"], ip_address)
                # )
                
                
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
    try:
        # Extract and validate device information
        device_id = client_info.device_id
        device_brand = client_info.device_brand
        ip_address = client_info.ip_address
        
        # Get other fields
        phone = data.phone
        fullname = data.fullname
        madrasa_name = data.madrasa_name or get_env_var("MADRASA_NAME")
        
        # Validate madrasa name
        
        # Define fields to check
        checks = {
            "email": data.email,
            "member_id": data.member_id,
            "student_id": data.student_id,
            "name_en": fullname,
            "name_bn": data.name_bn,
            "name_ar": data.name_ar,
            "date_of_birth": data.date_of_birth,
            "birth_certificate": data.birth_certificate,
            "national_id": data.national_id,
            "blood_group": data.blood_group,
            "gender": data.gender,
            "title1": data.title1,
            "title2": data.title2,
            "source": data.source,
            "present_address": data.present_address,
            "address_en": data.address_en,
            "address_bn": data.address_bn,
            "address_ar": data.address_ar,
            "permanent_address": data.permanent_address,
            "father_or_spouse": data.father_or_spouse,
            "father_en": data.father_en,
            "father_bn": data.father_bn,
            "father_ar": data.father_ar,
            "mother_en": data.mother_en,
            "mother_bn": data.mother_bn,
            "mother_ar": data.mother_ar,
            "class": data.class_name,
            "guardian_number": data.guardian_number,
            "degree": data.degree,
            "image_path": data.image_path,
        }
        
        # Check for missing required fields (properly handle None vs empty string)
        for field_name, field_value in checks.items():
            if field_value is None or field_value == "":
                log.info(action="account_check_missing_field", trace_info=ip_address, message=f"Field {field_name} is missing", secure=False)
                response, status = send_json_response("Session invalidated. Please log in again.", 400)
                response.update({"action": "logout"})
                return JSONResponse(content=response, status_code=status)
        
        # Validate account in database
        
        async with get_traced_db_cursor() as cursor:
                # Get user record
                await cursor.execute(f"""
                SELECT u.deactivated_at, u.email, p.*, 
                    tname.translation_text AS name_en, tname.bn_text AS name_bn, tname.ar_text AS name_ar,
                    taddress.translation_text AS address_en, taddress.bn_text AS address_bn, taddress.ar_text AS address_ar,
                    tfather.translation_text AS father_en, tfather.bn_text AS father_bn, tfather.ar_text AS father_ar,
                    tmother.translation_text AS mother_en, tmother.bn_text AS mother_bn, tmother.ar_text AS mother_ar
                    FROM global.users u
                    JOIN {madrasa_name}.peoples p ON p.user_id = u.user_id
                    JOIN global.translations tname ON tname.translation_text = p.name
                    LEFT JOIN global.translations taddress ON taddress.translation_text = p.address
                    LEFT JOIN global.translations tfather ON tfather.translation_text = p.father_name
                    LEFT JOIN global.translations tmother ON tmother.translation_text = p.mother_name
                    WHERE u.phone = %s AND LOWER(u.fullname) = LOWER(%s)
            """, (phone, fullname))
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
                    if provided is None:
                        continue  # skip fields not sent by client
                    
                    db_val = record.get(col)
                    
                    # Special handling for dates: compare only date part
                    if col == "date_of_birth" and isinstance(db_val, (dt.datetime, dt.date)):
                        try:
                            provided_date = datetime.fromisoformat(provided).date()
                        except Exception:
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
                await validate_device_limit(device_id, ip_address, request)
                
                # Track device interaction
                await cursor.execute(
                    "SELECT open_times FROM global.interactions WHERE device_id = %s AND device_brand = %s AND user_id = %s LIMIT 1",
                    (device_id, device_brand, record["user_id"])
                )
                open_times = await cursor.fetchone()
                
                if not open_times:
                    # Create new interaction record
                    await cursor.execute("""
                        INSERT INTO global.interactions 
                        (device_id, ip_address, device_brand, user_id)
                        VALUES (%s, %s, %s, %s)
                    """, (device_id, ip_address, device_brand, record["user_id"]))
                else:
                    # Update existing interaction record
                    opened = open_times['open_times'] if open_times else 0
                    opened += 1
                    await cursor.execute("""
                        UPDATE global.interactions SET open_times = %s
                        WHERE device_id = %s AND device_brand = %s AND user_id = %s
                    """, (opened, device_id, device_brand, record["user_id"]))
                
                
                log.info(action="account_check_successful", trace_info=ip_address, message=f"Account check successful for user: {record['user_id']}", secure=False)
                
                response, status = send_json_response("Account is valid", 200)
                response.update({"user_id": record["user_id"]})
                return JSONResponse(content=response, status_code=status)
                
    except Exception as e:
        log.critical(action="account_check_error", trace_info="system", message=f"Account check error: {str(e)}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['internal_error'], 500)
        return JSONResponse(content=response, status_code=status)

# ─── Advanced Security and Monitoring Functions ─────────────────────────────────

# TODO: Track user activity
# async def track_user_activity(user_id: int, activity_type: str, details: Dict[str, Any]) -> None: