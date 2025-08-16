import asyncio
import os
from datetime import datetime, timedelta, timezone
import datetime as dt
from typing import Any, Dict, Tuple

import aiomysql
from quart import (
    jsonify, request, render_template,
    Response
)
from werkzeug.security import generate_password_hash, check_password_hash

# Local imports
from . import api
from utils.mysql.database_utils import get_db_connection
from config import config
from utils.helpers.helpers import (
    check_code, check_device_limit, check_login_attempts, format_phone_number, generate_code, 
    get_client_info, record_login_attempt, secure_data, send_sms, send_email, 
    get_email, rate_limit, encrypt_sensitive_data, hash_sensitive_data,
    handle_async_errors, validate_device_info, validate_email, validate_fullname, validate_password_strength,
)
from quart_babel import gettext as _
from utils.helpers.logger import log

# ─── Errors ───────────────────────────────────────────────
ERROR_MESSAGES = {
        'missing_fields': _("All required fields are missing"),
        'invalid_credentials': _("Invalid login credentials"),
        'account_deactivated': _("Account is deactivated"),
        'account_not_found': _("Account not found"),
        'device_unsafe': _("Unknown device detected"),
        'device_limit_exceeded': _("Maximum devices reached. Please remove an existing device to add this one."),
        'rate_limit_exceeded': _("Too many attempts. Please try again later."),
        'verification_failed': _("Verification code is invalid or expired"),
        'password_mismatch': _("Passwords do not match"),
        'weak_password': _("Password is too weak"),
        'invalid_email': _("Invalid email format"),
        'invalid_phone': _("Invalid phone number format"),
        'user_already_exists': _("User already exists"),
        'session_expired': _("Session has expired"),
        'maintenance_mode': _("Application is currently in maintenance mode"),
        'unauthorized': _("Unauthorized access"),
        'internal_error': _("An internal error occurred"),
        'validation_error': _("Validation error"),
        'database_error': _("Database operation failed")
    }


# ─── Enhanced Authentication Routes ───────────────────────────────────────────

@api.route("/register", methods=["POST"])
@rate_limit(max_requests=10, window=60)
@handle_async_errors
async def register() -> Tuple[Response, int]:
    """Register a new user with comprehensive validation and security"""
    # Check maintenance mode
    if config.is_maintenance():
        return jsonify({"error": ERROR_MESSAGES['maintenance_mode']}), 503
    
    # Get client info for logging
    client_info = get_client_info()
    
    # Test mode handling
    if config.is_testing():
        return jsonify({
            "success": True, 
            "message": "Ignored because in test mode",
            "info": None
        }), 201
    
    try:
        # Get and validate request data
        data, error = await secure_data(required_fields=['fullname', 'phone', 'password', 'code'])
        if not data:
            return jsonify({"message": error}), 400
        
        # Extract and sanitize data
        fullname = data.get("fullname")
        email = data.get("email") if data.get("email") else None
        phone = data.get("phone")
        password = data.get("password")
        user_code = data.get("code")
        device_id = data.get("device_id") # TODO: get device id from client
        ip_address = data.get("ip_address") # TODO: get ip address from client
        
        # Validate device information
        is_valid_device, device_error = await validate_device_info(device_id, ip_address)
        if not is_valid_device:
            log.warning(action="register_invalid_device", trace_info=ip_address, message=f"Invalid device: {device_error}", secure=False)
            return jsonify({"message": device_error}), 400
        
        # Validate fullname
        is_valid_name, name_error = validate_fullname(fullname)
        if not is_valid_name:
            return jsonify({"message": name_error}), 400
        
        # Validate and format phone number
        formatted_phone, phone_error = format_phone_number(phone)
        if not formatted_phone:
            return jsonify({"message": phone_error}), 400
        
        # Validate password strength
        is_valid_password, password_error = validate_password_strength(password)
        if not is_valid_password:
            return jsonify({"message": password_error}), 400
        
        # Validate email if provided
        if email:
            is_valid_email, email_error = validate_email(email)
            if not is_valid_email:
                return jsonify({"message": email_error}), 400
        
        # Verify code
        validate_code_result = await check_code(user_code, formatted_phone)
        if validate_code_result:
            return validate_code_result
        
        # Hash and encrypt sensitive data
        hashed_password = generate_password_hash(password)
        hashed_phone = hash_sensitive_data(formatted_phone)
        encrypted_phone = encrypt_sensitive_data(formatted_phone)
        encrypted_email = encrypt_sensitive_data(email) if email else None
        hashed_email = hash_sensitive_data(email) if email else None
        
        # Insert user into database
        madrasa_name = os.getenv("MADRASA_NAME")
        conn = await get_db_connection()
        
        try:
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
                    return jsonify({"message": ERROR_MESSAGES['user_already_exists']}), 409
                
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
                        return jsonify({
                            "message": device_limit_error
                        }), 403
                
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
                
                return jsonify({
                    "success": True, 
                    "message": _("Registration successful"),
                    "info": people_result
                }), 201
                
        except aiomysql.IntegrityError as e:
            await conn.rollback()
            log.critical(action="register_integrity_error", trace_info=ip_address, message=f"Database integrity error: {str(e)}", secure=False)
            return jsonify({"message": ERROR_MESSAGES['user_already_exists']}), 409
            
        except Exception as e:
            await conn.rollback()
            log.critical(action="register_database_error", trace_info=ip_address, message=f"Database error during registration: {str(e)}", secure=False)
            return jsonify({"message": ERROR_MESSAGES['database_error']}), 500
            
    except Exception as e:
        log.critical(action="register_error", trace_info="system", message=f"Registration error: {str(e)}", secure=False)
        return jsonify({"message": ERROR_MESSAGES['internal_error']}), 500

@api.route("/login", methods=["POST"])
@rate_limit(max_requests=10, window=60)
@handle_async_errors
async def login() -> Tuple[Response, int] | None:
    """Authenticate user login with enhanced security and validation"""
    # Get and validate request data
    data, error = await secure_data(required_fields=['fullname', 'phone', 'password'])
    if not data:
        return jsonify({"error": error}), 400
    
    if config.is_testing():
        return jsonify({
            "success": True, 
            "message": "Ignored because in test mode",
            "info": None
        }), 201
        
    # Extract and sanitize data
    fullname = data.get("fullname")
    phone = data.get("phone")
    password = data.get("password")
    device_id = data.get("device_id")
    ip_address = data.get("ip_address")
        
    # Validate and format phone number
    formatted_phone, phone_error = format_phone_number(phone)
    if not formatted_phone:
        return jsonify({"message": phone_error}), 400
        
    # Check login attempts
    identifier = f"{formatted_phone}:{fullname}"
    is_allowed, remaining_attempts = await check_login_attempts(identifier)
        
    if not is_allowed:
        log.warning(action="login_rate_limited", trace_info=ip_address, message=f"Login rate limited for: {fullname} remaining attempts: {remaining_attempts}", secure=False)
        return jsonify({
            "message": ERROR_MESSAGES['rate_limit_exceeded']
        }), 429
    
    # Authenticate user
    madrasa_name = data.get("madrasa_name") or os.getenv("MADRASA_NAME")
    conn = await get_db_connection()
    
    try: 
        async with conn.cursor(aiomysql.DictCursor) as _cursor:
            from utils.otel.db_tracing import TracedCursorWrapper
            cursor = TracedCursorWrapper(_cursor)
            # Get user information
            await cursor.execute(
                "SELECT user_id, deactivated_at, password_hash FROM global.users WHERE phone = %s AND LOWER(fullname) = LOWER(%s)",
                (formatted_phone, fullname)
            )
            user = await cursor.fetchone()
            
            if not user:
                await record_login_attempt(identifier, False)
                log.error(action="login_user_not_found", trace_info=formatted_phone, message=f"User not found: {fullname}", secure=True)
                return jsonify({"message": ERROR_MESSAGES['account_not_found']}), 404
            
            # Check password
            if not check_password_hash(user["password_hash"], password):
                await record_login_attempt(identifier, False)
                log.warning(action="login_incorrect_password", trace_info=formatted_phone, message="Incorrect password", secure=True)
                return jsonify({"message": ERROR_MESSAGES['invalid_credentials']}), 401
            
            # Check if account is deactivated
            if user["deactivated_at"] is not None:
                log.warning(action="login_account_deactivated", trace_info=formatted_phone, message="Account is deactivated", secure=True)
                return jsonify({
                    "action": "deactivate", 
                    "message": ERROR_MESSAGES['account_deactivated']
                }), 403
            
            # Check device limit
            is_device_allowed, device_limit_error = await check_device_limit(user["user_id"], device_id)
            if not is_device_allowed:
                log.warning(action="login_device_limit_exceeded", trace_info=formatted_phone, message=f"Device limit exceeded for user: {fullname}", secure=True)
                return jsonify({
                    "message": device_limit_error
                }), 403
            
            # Record successful login
            await record_login_attempt(identifier, True)
            
            # Get complete user information
            await cursor.execute(
                f"""SELECT u.user_id, u.fullname, u.phone, p.acc_type AS userType, p.*,
                    a.main_type AS acc_type, a.teacher, a.student, a.staff, a.donor, 
                    a.badri_member, a.special_member,
                    tname.translation_text AS name_en, tname.bn_text AS name_bn, tname.ar_text AS name_ar,
                    taddress.translation_text AS address_en, taddress.bn_text AS address_bn, taddress.ar_text AS address_ar,
                    tfather.translation_text AS father_en, tfather.bn_text AS father_bn, tfather.ar_text AS father_ar,
                    tmother.translation_text AS mother_en, tmother.bn_text AS mother_bn, tmother.ar_text AS mother_ar
                    FROM global.users u
                    JOIN {madrasa_name}.peoples p ON p.user_id = u.user_id
                    JOIN global.acc_types a ON a.user_id = u.user_id
                    JOIN global.translations tname ON tname.translation_text = p.name
                    LEFT JOIN global.translations taddress ON taddress.translation_text = p.address
                    JOIN global.translations tfather ON tfather.translation_text = p.father_name
                    LEFT JOIN global.translations tmother ON tmother.translation_text = p.mother_name
                    WHERE u.user_id = %s AND p.phone = %s AND p.name = %s""",
                (user["user_id"], formatted_phone, fullname)
            )
            info = await cursor.fetchone() if cursor.fetchone() else None
            
            if not info or not info.get("phone") or not info.get("user_id"):
                log.warning(action="login_incomplete_profile", trace_info=formatted_phone, message="Missing profile info", secure=True)
                return jsonify({
                    "error": "incomplete_profile",
                    "message": _("Additional info required"),
                    "info" : info
                }), 422
            
            # Remove sensitive information
            info.pop("password", None)
            info.pop("password_hash", None)
            
            # Format date of birth
            dob = info.get("date_of_birth")
            if isinstance(dob, (dt.date, dt.datetime)):
                info["date_of_birth"] = dob.strftime("%d/%m/%Y")
            
            # Log successful login
            log.info(action="user_logged_in_successfully", trace_info=ip_address, message=f"User logged in successfully: {fullname}", secure=False)
            
            return jsonify({
                "success": True, 
                "message": _("Login successful"), 
                "info": info
            }), 200
            
    except Exception as e:
        log.critical(action="login_error", trace_info=ip_address, message=f"Login error: {str(e)}", secure=False)
        return jsonify({"message": ERROR_MESSAGES['internal_error']}), 500

@api.route("/send_code", methods=["POST"])
@rate_limit(max_requests=10, window=60)
@handle_async_errors
async def send_verification_code() -> Tuple[Response, int]:
    """Send verification code via SMS or email with enhanced security"""
    # Test mode handling
    if config.is_testing():
        return jsonify({
            "success": True, 
            "message": _("Verification code sent to %(target)s") % {"target": config.DUMMY_EMAIL}
        }), 200
    
    try:
        # Get and validate request data
        data, error = await secure_data(required_fields=['phone', 'fullname'])
        if not data:
            return jsonify({"error": error}), 400

        # Extract and sanitize data
        phone = data.get("phone")
        fullname = data.get("fullname")
        password = data.get("password") if data.get("password") else None
        email = data.get("email") if data.get("email") else None
        signature = data.get("app_signature")
        ip_address = data.get("ip_address")
        
        # Validate and format phone number
        formatted_phone, phone_error = format_phone_number(phone)
        if not formatted_phone:
            return jsonify({"message": phone_error}), 400
        
        # Validate fullname if provided
        is_valid_name, name_error = validate_fullname(fullname)
        if not is_valid_name:
            return jsonify({"message": name_error}), 400
        
        # Validate password if provided
        if password:
            is_valid_password, password_error = validate_password_strength(password)
            if not is_valid_password:
                return jsonify({"message": password_error}), 400
        
        # Validate email if provided
        if email:
            is_valid_email, email_error = validate_email(email)
            if not is_valid_email:
                return jsonify({"message": email_error}), 400
        else:
            email = await get_email(phone=formatted_phone, fullname=fullname)
        
        # Check rate limiting
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as _cursor:
            from utils.otel.db_tracing import TracedCursorWrapper
            cursor = TracedCursorWrapper(_cursor)
            # Check existing user if password provided
            if password and fullname:
                await cursor.execute(
                    "SELECT user_id FROM global.users WHERE phone = %s AND LOWER(fullname) = LOWER(%s)",
                    (formatted_phone, fullname)
                )
                existing_user = await cursor.fetchone()
                
                if existing_user:
                    log.warning(action="send_code_user_exists", trace_info=ip_address, message=f"User already exists: {fullname}", secure=False)
                    return jsonify({"message": ERROR_MESSAGES['user_already_exists']}), 409
            
            # Check rate limit for verification codes
            await cursor.execute("""
                SELECT COUNT(*) AS recent_count 
                FROM global.verifications 
                WHERE phone = %s AND created_at > NOW() - INTERVAL 1 HOUR
            """, (formatted_phone,))
            result = await cursor.fetchone()
            count = result["recent_count"] if result else 0
            
            # Check if rate limit exceeded
            max_limit = max(config.SMS_LIMIT_PER_HOUR, config.EMAIL_LIMIT_PER_HOUR)
            if count >= max_limit:
                log.warning(action="send_code_rate_limited", trace_info=ip_address, message=f"Rate limit exceeded for phone: {formatted_phone}", secure=False)
                return jsonify({"message": ERROR_MESSAGES['rate_limit_exceeded']}), 429
            
            # Generate and send verification code
            code = generate_code()
            hashed_phone = hash_sensitive_data(formatted_phone)
            encrypted_phone = encrypt_sensitive_data(formatted_phone)
            
            # Try SMS first if under SMS limit
            if count < config.SMS_LIMIT_PER_HOUR:
                if await send_sms(phone=formatted_phone, msg=_("Verification code sent to %(target)s") % {"target": formatted_phone} + f"\n{_('Your code is: %(code)s') % {'code': code}}" + f"\n\n@An-Nur.app\nAppSignature: {signature}"):
                    await cursor.execute(
                        "INSERT INTO global.verifications (phone, phone_hash, phone_encrypted, code, ip_address) VALUES (%s, %s, %s, %s, %s)",
                        (formatted_phone, hashed_phone, encrypted_phone, code, ip_address)
                    )
                    await conn.commit()
                    
                    log.info(action="verification_code_sent_sms", trace_info=ip_address, message=f"Verification code sent via SMS to: {formatted_phone}", secure=False)
                    
                    return jsonify({
                        "success": True, 
                        "message": _("Verification code sent to %(target)s") % {"target": formatted_phone}
                    }), 200
            
            # Try email if SMS failed or limit reached
            if email and count < config.EMAIL_LIMIT_PER_HOUR:
                if await send_email(to_email=email, body= f"\n{_('Your code is: %(code)s') % {'code': code}}" + "\n\n@An-Nur.app", subject=  _("Verification Email")):
                    await cursor.execute(
                        "INSERT INTO global.verifications (phone, phone_hash, phone_encrypted, code, ip_address) VALUES (%s, %s, %s, %s, %s)",
                        (formatted_phone, hashed_phone, encrypted_phone, code, ip_address)
                    )
                    await conn.commit()
                    
                    log.info(action="verification_code_sent_email", trace_info=ip_address, message=f"Verification code sent via email to: {email}", secure=False)
                    
                    return jsonify({
                        "success": True, 
                        "message": _("Verification code sent to %(target)s") % {"target": email}
                    }), 200
            
            # If both methods failed
            log.critical(action="verification_code_failed", trace_info=ip_address, message="Failed to send verification code via any method", secure=False)
            return jsonify({"message": "Failed to send verification code"}), 500
            
    except Exception as e:
        log.critical(action="send_code_error", trace_info="system", message=f"Error sending verification code: {str(e)}", secure=False)
        return jsonify({"message": ERROR_MESSAGES['internal_error']}), 500

@api.route("/reset_password", methods=["POST"])
@handle_async_errors
async def reset_password() -> Tuple[Response, int]:
    """Reset user password with enhanced security validation"""
    # Check maintenance mode
    if config.is_maintenance:
        return jsonify({
            "error": ERROR_MESSAGES['maintenance_mode']
        }), 503
    
    # Get client info for logging
    # client_info = get_security_client_info()
    
    try:
        # Get and validate request data
        data, error = await secure_data(required_fields=['phone', 'fullname'])
        if not data:
            return jsonify({"error": error}), 400
        
        # Extract and sanitize data
        phone = data.get("phone")
        fullname = data.get("fullname")
        user_code = data.get("code")
        old_password = data.get("old_password") if data.get("old_password") else None
        new_password = data.get("new_password") if data.get("new_password") else None
        device_id = data.get("device_id")
        ip_address = data.get("ip_address")

        # Test mode handling
        if config.is_testing():
            if not new_password:
                return jsonify({"success": True, "message": "App in test mode"}), 200
            else:
                return jsonify({"success": True, "message": "App in test mode"}), 201
        
        # Validate and format phone number
        formatted_phone, phone_error = format_phone_number(phone)
        if not formatted_phone:
            return jsonify({"message": phone_error}), 400
        
        # If old password is not provided, use code verification
        if not old_password:
            validate_code_result = await check_code(user_code, formatted_phone)
            if validate_code_result:
                return validate_code_result
            elif not new_password:
                return jsonify({"success": True, "message": _("Code successfully matched")}), 200
        
        # Validate new password if provided
        if new_password:
            is_valid_password, password_error = validate_password_strength(new_password)
            if not is_valid_password:
                return jsonify({"message": password_error}), 400
        
        # Authenticate user and update password
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as _cursor:
            from utils.otel.db_tracing import TracedCursorWrapper
            cursor = TracedCursorWrapper(_cursor)
            # Get user information
            await cursor.execute(
                "SELECT user_id, password_hash FROM global.users WHERE phone = %s AND LOWER(fullname) = LOWER(%s)",
                (formatted_phone, fullname)
            )
            user = await cursor.fetchone()
            
            if not user:
                log.error(action="reset_password_user_not_found", trace_info=formatted_phone, message=f"User not found: {fullname}", secure=True)
                return jsonify({"message": ERROR_MESSAGES['account_not_found']}), 404
            
            # Check device limit
            is_device_allowed, device_limit_error = await check_device_limit(user["user_id"], device_id)
            if not is_device_allowed:
                log.warning(action="reset_password_device_limit_exceeded", trace_info=formatted_phone, message=f"Device limit exceeded during password reset for user: {fullname}", secure=True)
                return jsonify({
                    "message": device_limit_error
                }), 403
            
            # If old password is provided, verify it
            if old_password:
                if not check_password_hash(user['password_hash'], old_password):
                    log.warning(action="reset_password_incorrect_old_password", trace_info=formatted_phone, message="Incorrect old password", secure=True)
                    return jsonify({"message": _("Incorrect old password")}), 401
            
            # Hash new password
            if not new_password:
                return jsonify({"message": _("New password is required")}), 400
            hashed_password = generate_password_hash(new_password)
            
            # Check if new password is same as current
            if check_password_hash(user['password_hash'], new_password):
                return jsonify({"message": _("New password cannot be the same as the current password.")}), 400
            
            # Update password
            await cursor.execute(
                "UPDATE global.users SET password_hash = %s, ip_address = %s WHERE LOWER(fullname) = LOWER(%s) AND phone = %s",
                (hashed_password, ip_address, fullname, formatted_phone)
            )
            await conn.commit()
            
            # Log successful password reset
            log.info(action="password_reset_successful", trace_info=ip_address, message=f"Password reset successful for: {fullname}", secure=False)
            
            return jsonify({"success": True, "message": _("Password Reset Successful")}), 201
            
    except Exception as e:
        log.critical(action="reset_password_error", trace_info="system", message=f"Password reset error: {str(e)}", secure=False)
        return jsonify({"message": ERROR_MESSAGES['internal_error']}), 500

@api.route("/account/<page_type>", methods=["GET", "POST"])
@rate_limit(max_requests=10, window=60)
@handle_async_errors
async def manage_account(page_type: str): # -> Tuple[Response, int] TODO: remove get
    """Manage account (deactivate/delete) with enhanced security"""
    # Validate page type
    if page_type not in ("remove", "deactivate", "delete"):
        return jsonify({"message": _("Invalid page type")}), 400
    
    # Handle GET request (render form)
    if request.method == "GET":
        return await render_template(
            "account_manage.html",
            page_type=page_type.capitalize()
        )
    
    # Handle POST request
    try:
        # Get and validate request data
        data, error = await secure_data(required_fields=['phone', 'fullname', 'password'])
        if not data:
            return jsonify({"error": error}), 400

        # Extract and sanitize data
        phone = data.get("phone")
        fullname = data.get("fullname")
        password = data.get("password")
        email = data.get("email") if data.get("email") else None

        # Validate and format phone number
        formatted_phone, phone_error = format_phone_number(phone)
        if not formatted_phone:
            return jsonify({"message": phone_error}), 400
        
        # Authenticate user
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as _cursor:
            from utils.otel.db_tracing import TracedCursorWrapper
            cursor = TracedCursorWrapper(_cursor)
            await cursor.execute(
                "SELECT user_id, password_hash FROM global.users WHERE phone = %s AND LOWER(fullname) = LOWER(%s)",
                (formatted_phone, fullname)
            )
            user = await cursor.fetchone()
            
            if not user or not check_password_hash(user["password_hash"], password):
                log.error(action="manage_account_invalid_credentials", trace_info=formatted_phone, message="Invalid credentials for account management", secure=True)
                return jsonify({"message": _("Invalid login details")}), 401
            
            # Prepare confirmation message
            deletion_days = config.ACCOUNT_DELETION_DAYS
            if page_type in ["remove", "delete"]:
                msg = _("Your account has been successfully put for deletion.\nIt will take %(days)d days to fully delete your account.\nIf it wasn't you, please contact us for account recovery.\n\n@An-Nur.app") % {"days": deletion_days}
                subject = _("Account Deletion Confirmation")
            else:  # deactivate
                msg = _("Your account has been successfully deactivated.\nYou can reactivate it within our app.\nIf it wasn't you, please contact us immediately.\n\n@An-Nur.app")
                subject = _("Account Deactivation Confirmation")
            
            # Send notifications
            errors = 0
            if email:
                is_valid_email, email_error = validate_email(email)
                if not is_valid_email:
                    return jsonify({"message": email_error}), 400
                if not await send_email(to_email=email, subject=subject, body=msg):
                    errors += 1
            else:
                errors += 1
            
            if not await send_sms(phone=formatted_phone, msg=msg):
                errors += 1
            
            if errors > 1:
                log.critical(action="manage_account_notification_failed", trace_info=formatted_phone, message="Could not send confirmation notifications", secure=True)
                return jsonify({"message": _("Could not send confirmation. Try again later.")}), 500
            
            # Schedule deactivation/deletion
            now = datetime.now(timezone.utc)
            scheduled = now + timedelta(days=deletion_days)
            
            sql = "UPDATE global.users SET deactivated_at = %s"
            params = [now]
            
            if page_type in ["remove", "delete"]:
                sql += ", scheduled_deletion_at = %s"
                params.append(scheduled)
            
            sql += " WHERE user_id = %s"
            params.append(user["user_id"])
            
            await cursor.execute(sql, params)
            await conn.commit()
            
            # Log account management action
            if page_type in ["remove", "delete"]:
                log.warning(action="account_deletion_scheduled", trace_info=formatted_phone, message=f"User {hash_sensitive_data(fullname)} scheduled for deletion", secure=True)
                return jsonify({"success": True, "message": _("Account deletion initiated. Check your messages.")}), 200
            else:
                log.warning(action="account_deactivated", trace_info=formatted_phone, message=f"User {hash_sensitive_data(fullname)} deactivated", secure=True)
                return jsonify({"success": True, "message": _("Account deactivated successfully.")}), 200
                
    except Exception as e:
        log.critical(action="manage_account_error", trace_info="system", message=f"Account management error: {str(e)}", secure=False)
        return jsonify({"message": ERROR_MESSAGES['internal_error']}), 500

@api.route("/account/reactivate", methods=['POST'])
@rate_limit(max_requests=10, window=60)
@handle_async_errors
async def undo_remove() -> Tuple[Response, int]:
    """Reactivate a deactivated account with enhanced validation"""
    # Check maintenance mode
    if config.is_maintenance:
        return jsonify({
            "error": ERROR_MESSAGES['maintenance_mode']
        }), 503
    
    # Get client info for logging
    # client_info = get_security_client_info()
    
    # Test mode handling
    if config.is_testing():
        return jsonify({"success": True, "message": "App in test mode"}), 200
    
    try:
        # Get and validate request data
        data, error = await secure_data(required_fields=['phone', 'fullname'])
        if not data:
            return jsonify({"error": error}), 400
        
        # Extract and sanitize data
        phone = data.get("phone")
        fullname = data.get("fullname")
        
        # Validate and format phone number
        formatted_phone, phone_error = format_phone_number(phone)
        if not formatted_phone:
            return jsonify({"message": phone_error}), 400
        
        # Reactivate account
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as _cursor:
            from utils.otel.db_tracing import TracedCursorWrapper
            cursor = TracedCursorWrapper(_cursor)
            await cursor.execute(
                "SELECT user_id, deactivated_at, scheduled_deletion_at FROM global.users WHERE phone = %s AND LOWER(fullname) = LOWER(%s)",
                (formatted_phone, fullname)
            )
            user = await cursor.fetchone()
            
            if not user or not user["deactivated_at"]:
                log.warning(action="reactivate_no_deactivated_account", trace_info=data.get("ip_address", ""), message=f"No deactivated account found for: {fullname}", secure=False)
                return jsonify({"message": "No deactivated account found"}), 404
            
            # Check if reactivation period has expired
            deactivated_at = user["deactivated_at"]
            if (datetime.now(timezone.utc) - deactivated_at).days > config.ACCOUNT_REACTIVATION_DAYS and user["scheduled_deletion_at"]:
                log.warning(action="reactivate_period_expired", trace_info=data.get("ip_address", ""), message=f"Reactivation period expired for: {fullname}", secure=False)
                return jsonify({"message": "Undo period expired"}), 403
            
            # Reactivate account
            await cursor.execute(
                "UPDATE global.users SET deactivated_at = NULL, scheduled_deletion_at = NULL, ip_address = %s WHERE user_id = %s",
                (data.get("ip_address"), user["user_id"])
            )
            await conn.commit()
            
            # Log successful reactivation
            log.info(action="account_reactivated_successfully", trace_info=data.get("ip_address", ""), message=f"Account reactivated successfully for: {fullname}", secure=False)
            
            return jsonify({"success": True, "message": _("Account reactivated.")}), 200
            
    except Exception as e:
        log.critical(action="reactivate_error", trace_info="system", message=f"Account reactivation error: {str(e)}", secure=False)
        return jsonify({"message": ERROR_MESSAGES['internal_error']}), 500

@api.route("/account/check", methods=['POST'])
@handle_async_errors
async def get_account_status() -> Tuple[Response, int]:
    """Check account status and validate session with enhanced security"""
    # Test mode handling
    if config.is_testing():
        return jsonify({"success": True, "message": "App in test mode"}), 200
    
    try:
        # Get and validate request data
        data, error = await secure_data(required_fields=['phone', 'fullname'])
        if not data:
            return jsonify({"error": error}), 400
        
        # Extract and validate device information
        device_id = data.get("device_id")
        device_brand = data.get("device_brand")
        ip_address = data.get("ip_address")
        
        # Extract user information
        phone = data.get("phone")
        user_id = data.get("user_id")
        fullname = data.get("name_en")
        madrasa_name = data.get("madrasa_name") or os.getenv("MADRASA_NAME")
        
        # Validate and format phone number
        formatted_phone, phone_error = format_phone_number(phone)
        if not formatted_phone:
            return jsonify({"message": phone_error}), 400
        
        # Define fields to check
        checks = {
            "email": data.get("email"),
            "member_id": data.get("member_id"),
            "student_id": data.get("student_id"),
            "name_en": fullname,
            "name_bn": data.get("name_bn"),
            "name_ar": data.get("name_ar"),
            "date_of_birth": data.get("date_of_birth"),
            "birth_certificate": data.get("birth_certificate"),
            "national_id": data.get("national_id"),
            "blood_group": data.get("blood_group"),
            "gender": data.get("gender"),
            "title1": data.get("title1"),
            "title2": data.get("title2"),
            "source": data.get("source"),
            "present_address": data.get("present_address"),
            "address_en": data.get("address_en"),
            "address_bn": data.get("address_bn"),
            "address_ar": data.get("address_ar"),
            "permanent_address": data.get("permanent_address"),
            "father_or_spouse": data.get("father_or_spouse"),
            "father_en": data.get("father_en"),
            "father_bn": data.get("father_bn"),
            "father_ar": data.get("father_ar"),
            "mother_en": data.get("mother_en"),
            "mother_bn": data.get("mother_bn"),
            "mother_ar": data.get("mother_ar"),
            "class": data.get("class_name"),
            "guardian_number": data.get("guardian_number"),
            "degree": data.get("degree"),
            "image_path": data.get("image_path"),
        }
        
        # Check for missing required fields
        for field_name, field_value in checks.items():
            if field_value is None or field_value == "":
                log.info(action="account_check_missing_field", trace_info=ip_address, message=f"Field {field_name} is missing", secure=False)
                return jsonify({
                    "action": "logout", 
                    "message": _("Session invalidated. Please log in again.")
                }), 400
        
        # Validate account in database
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as _cursor:
            from utils.otel.db_tracing import TracedCursorWrapper
            cursor = TracedCursorWrapper(_cursor)
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
            """, (formatted_phone, fullname))
            record = await cursor.fetchone()
            
            if not record:
                log.error(action="account_check_not_found", trace_info=ip_address, message="No matching user found", secure=False)
                return jsonify({
                    "action": "logout", 
                    "message": _("Session invalidated. Please log in again.")
                }), 401
            
            # Check if account is deactivated
            if record.get("deactivated_at"):
                log.warning(action="account_check_deactivated", trace_info=record["user_id"], message="Account is deactivated", secure=False)
                return jsonify({
                    "action": "deactivate", 
                    "message": _("Account is deactivated")
                }), 401
            
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
                        return jsonify({
                            "action": "logout", 
                            "message": _("Session invalidated. Please log in again.")
                        }), 401
                    
                    if db_val:
                        db_date = db_val.date() if isinstance(db_val, dt.datetime) else db_val
                        if db_date != provided_date:
                            log.warning(action="account_check_date_mismatch", trace_info=record["user_id"], message=f"Date mismatch: {col}: {provided_date} != {db_date}", secure=False)
                            return jsonify({
                                "action": "logout", 
                                "message": _("Session invalidated. Please log in again.")
                            }), 401
                else:
                    # Compare string values
                    if str(provided).strip() != str(db_val).strip():
                        log.warning(action="account_check_field_mismatch", trace_info=record["user_id"], message=f"Field mismatch: {col}: {hash_sensitive_data(str(provided))} != {hash_sensitive_data(str(db_val))}", secure=False)
                        return jsonify({
                            "action": "logout", 
                            "message": _("Session invalidated. Please log in again.")
                        }), 401
            
            # Check device limit
            is_device_allowed, device_limit_error = await check_device_limit(record["user_id"], device_id)
            if not is_device_allowed:
                log.warning(action="account_check_device_limit_exceeded", trace_info=record["user_id"], message=f"Device limit exceeded during account check for user: {record['user_id']}", secure=False)
                return jsonify({
                    "action": "logout", 
                    "message": device_limit_error
                }), 403
            
            # Track device interaction
            await cursor.execute(
                "SELECT open_times FROM global.interactions WHERE device_id = %s AND device_brand = %s AND user_id = %s LIMIT 1",
                (device_id, device_brand, record["user_id"])
            )
            open_times = await cursor.fetchone()
            
            if not open_times:
                # Create new interaction record
                await cursor.execute(f"""
                    INSERT INTO global.interactions 
                    (device_id, ip_address, device_brand, user_id)
                    VALUES (%s, %s, %s, %s)
                """, (device_id, ip_address, device_brand, user_id))
            else:
                # Update existing interaction record
                opened = open_times['open_times'] if open_times else 0
                opened += 1
                await cursor.execute(f"""
                    UPDATE global.interactions SET open_times = %s
                    WHERE device_id = %s AND device_brand = %s AND user_id = %s
                """, (opened, device_id, device_brand, user_id))
            
            await conn.commit()
            
            # Log successful account check
            log.info(action="account_check_successful", trace_info=ip_address, message=f"Account check successful for: {fullname}", secure=False)
            
            return jsonify({
                "success": True, 
                "message": _("Account is valid"), 
                "user_id": record["user_id"]
            }), 200
            
    except Exception as e:
        log.critical(action="account_check_error", trace_info="system", message=f"Account check error: {str(e)}", secure=False)
        return jsonify({"message": ERROR_MESSAGES['internal_error']}), 500

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
            'ip_address': get_client_info()["ip_address"] or None, # TODO: get ip address from client
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