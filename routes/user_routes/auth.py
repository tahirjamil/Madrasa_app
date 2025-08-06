import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

import aiomysql
from quart import (
    jsonify, request, render_template,
    Response
)
from werkzeug.security import generate_password_hash, check_password_hash

# Local imports
from . import user_routes
from database.database_utils import get_db_connection
from config import Config
from helpers import (
    send_sms, is_test_mode, send_email, 
    get_email, rate_limit, encrypt_sensitive_data, hash_sensitive_data, 
    handle_async_errors, cache, performance_monitor, metrics_collector
)
from security import (
    security_manager, is_maintenance_mode, is_valid_api_key, 
    format_phone_number, is_device_unsafe, validate_fullname, validate_email, validate_password_strength,
    check_rate_limit, get_client_info as get_security_client_info, generate_code, check_code, _send_security_notifications
)
from quart_babel import gettext as _
from logger import log_critical, log_error, log_info, log_warning

# ─── Configuration and Constants ───────────────────────────────────────────────

class AuthConfig:
    """Centralized configuration for authentication routes"""
    
    # Rate limiting configuration
    SMS_LIMIT_PER_HOUR = int(os.getenv("SMS_LIMIT_PER_HOUR", "5"))
    EMAIL_LIMIT_PER_HOUR = int(os.getenv("EMAIL_LIMIT_PER_HOUR", "15"))
    LOGIN_ATTEMPTS_LIMIT = int(os.getenv("LOGIN_ATTEMPTS_LIMIT", "5"))
    LOGIN_LOCKOUT_MINUTES = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))
    
    # Account management
    ACCOUNT_DELETION_DAYS = int(os.getenv("ACCOUNT_DELETION_DAYS", "30"))
    ACCOUNT_REACTIVATION_DAYS = int(os.getenv("ACCOUNT_REACTIVATION_DAYS", "14"))
    
    # Security settings
    PASSWORD_MIN_LENGTH = 8
    SESSION_TIMEOUT_HOURS = 24
    MAX_DEVICES_PER_USER = 3
    
    # Validation patterns
    PHONE_PATTERN = re.compile(r'^\+?[1-9]\d{1,14}$')
    EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    NAME_PATTERN = re.compile(r'^[A-Za-z\s\'-]+$')
    
    # Error messages
    ERROR_MESSAGES = {
        'missing_fields': _("All required fields are missing"),
        'invalid_credentials': _("Invalid login credentials"),
        'account_deactivated': _("Account is deactivated"),
        'account_not_found': _("Account not found"),
        'device_unsafe': _("Unknown device detected"),
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

# Global configuration instance
auth_config = AuthConfig()

# ─── Security and Validation Functions ───────────────────────────────────────

def validate_auth_request_data(data: Dict[str, Any], required_fields: List[str]) -> Tuple[bool, List[str]]:
    """Validate authentication request data"""
    missing_fields = []
    for field in required_fields:
        if not data.get(field):
            missing_fields.append(field)
    return len(missing_fields) == 0, missing_fields

def validate_device_info(device_id: str, ip_address: str, device_brand: str = None) -> Tuple[bool, str]:
    """Validate device information for security"""
    if not device_id or not ip_address:
        return False, "Device information is required"
    
    # Validate IP address format
    ip_pattern = re.compile(r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$')
    if not ip_pattern.match(ip_address):
        return False, "Invalid IP address format"
    
    # Check for suspicious device patterns
    suspicious_patterns = [
        r'^(test|dummy|fake|null|undefined)$',
        r'[<>"\']',
        r'\.\.',
        r'javascript:',
        r'<script'
    ]
    
    for pattern in suspicious_patterns:
        if re.search(pattern, device_id, re.IGNORECASE):
            _send_security_notifications(ip_address, device_id, "Suspicious device identifier detected")
            return False, "Suspicious device identifier detected"
    
    return True, ""

def sanitize_user_input(input_str: str, max_length: int = 100) -> str:
    """Sanitize user input for security"""
    if not input_str:
        return ""
    
    # Remove potentially dangerous characters
    sanitized = re.sub(r'[<>"\']', '', input_str)
    
    # Limit length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    
    return sanitized.strip()

def check_login_attempts(identifier: str) -> Tuple[bool, int]:
    """Check login attempts and return if allowed and remaining attempts"""
    cache_key = f"login_attempts:{identifier}"
    attempts = cache.get(cache_key, 0)
    
    if attempts >= auth_config.LOGIN_ATTEMPTS_LIMIT:
        return False, 0
    
    return True, auth_config.LOGIN_ATTEMPTS_LIMIT - attempts

def record_login_attempt(identifier: str, success: bool) -> None:
    """Record login attempt for rate limiting"""
    cache_key = f"login_attempts:{identifier}"
    
    if success:
        cache.delete(cache_key)
    else:
        attempts = cache.get(cache_key, 0) + 1
        cache.set(cache_key, attempts, ttl=auth_config.LOGIN_LOCKOUT_MINUTES * 60)

# ─── Enhanced Authentication Routes ───────────────────────────────────────────

@user_routes.route("/register", methods=["POST"])
@rate_limit(max_requests=10, window=60)
@handle_async_errors
async def register() -> Response:
    """
    Register a new user with comprehensive validation and security
    
    Returns:
        JSON response with registration status and user information
    """
    # Check maintenance mode
    if is_maintenance_mode():
        return jsonify({
            "error": auth_config.ERROR_MESSAGES['maintenance_mode']
        }), 503
    
    # Get client info for logging
    # client_info = get_security_client_info()
    
    # Test mode handling
    if is_test_mode():
        return jsonify({
            "success": True, 
            "message": "Ignored because in test mode",
            "info": None
        }), 201
    
    try:
        # Get and validate request data
        data = await request.get_json()
        if not data:
            return jsonify({"error": "Invalid request data"}), 400
        
        # Extract and validate required fields
        required_fields = ['fullname', 'phone', 'password', 'code']
        is_valid, missing_fields = validate_auth_request_data(data, required_fields)
        
        if not is_valid:
            log_warning(
                action="register_missing_fields",
                trace_info=data.get("ip_address", ""),
                message=f"Missing fields: {missing_fields}"
            )
            return jsonify({
                "message": _("Missing required fields: %(fields)s") % {"fields": ", ".join(missing_fields)}
            }), 400
        
        # Extract and sanitize data
        fullname = sanitize_user_input(data.get("fullname", ""))
        email = sanitize_user_input(data.get("email", "")) if data.get("email") else None
        phone = data.get("phone", "").strip()
        password = data.get("password", "").strip()
        user_code = data.get("code", "").strip()
        device_id = data.get("device_id", "") # TODO: get device id from client
        ip_address = data.get("ip_address", "") # TODO: get ip address from client
        
        # Validate device information
        is_valid_device, device_error = validate_device_info(device_id, ip_address)
        if not is_valid_device:
            log_warning(
                action="register_invalid_device",
                trace_info=ip_address,
                message=f"Invalid device: {device_error}"
            )
            return jsonify({"message": device_error}), 400
        
        # Check device safety
        if is_device_unsafe(ip_address=ip_address, device_id=device_id, info=phone or email or fullname):
            log_warning(
                action="register_unsafe_device",
                trace_info=ip_address,
                message="Unsafe device detected during registration"
            )
            return jsonify({"message": auth_config.ERROR_MESSAGES['device_unsafe']}), 400
        
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
        validate_code_result = check_code(user_code, formatted_phone)
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
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                # Check if user already exists
                await cursor.execute(
                    "SELECT user_id FROM global.users WHERE phone = %s OR LOWER(fullname) = LOWER(%s)",
                    (formatted_phone, fullname)
                )
                existing_user = await cursor.fetchone()
                
                if existing_user:
                    log_warning(
                        action="register_user_exists",
                        trace_info=ip_address,
                        message=f"User already exists: {fullname}"
                    )
                    return jsonify({"message": auth_config.ERROR_MESSAGES['user_already_exists']}), 409
                
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
                log_info(
                    action="user_registered_successfully",
                    trace_info=ip_address,
                    message=f"User registered successfully: {fullname}"
                )
                
                return jsonify({
                    "success": True, 
                    "message": _("Registration successful"),
                    "info": people_result
                }), 201
                
        except aiomysql.IntegrityError as e:
            await conn.rollback()
            log_critical(
                action="register_integrity_error",
                trace_info=ip_address,
                trace_info_hash=hash_sensitive_data(formatted_phone),
                trace_info_encrypted=encrypt_sensitive_data(formatted_phone),
                message=f"Database integrity error: {str(e)}"
            )
            return jsonify({"message": auth_config.ERROR_MESSAGES['user_already_exists']}), 409
            
        except Exception as e:
            await conn.rollback()
            log_critical(
                action="register_database_error",
                trace_info=ip_address,
                trace_info_hash=hash_sensitive_data(formatted_phone),
                trace_info_encrypted=encrypt_sensitive_data(formatted_phone),
                message=f"Database error during registration: {str(e)}"
            )
            return jsonify({"message": auth_config.ERROR_MESSAGES['database_error']}), 500
            
    except Exception as e:
        log_critical(
            action="register_error",
            trace_info=ip_address,
            trace_info_hash=hash_sensitive_data(phone or "unknown"),
            trace_info_encrypted=encrypt_sensitive_data(phone or "unknown"),
            message=f"Registration error: {str(e)}"
        )
        return jsonify({"message": auth_config.ERROR_MESSAGES['internal_error']}), 500

@user_routes.route("/login", methods=["POST"])
@rate_limit(max_requests=10, window=60)
@handle_async_errors
async def login() -> Response:
    """
    Authenticate user login with enhanced security and validation
    
    Returns:
        JSON response with login status and user information
    """
    # Check maintenance mode
    if is_maintenance_mode():
        return jsonify({
            "error": auth_config.ERROR_MESSAGES['maintenance_mode']
        }), 503
    
    # Get client info for logging
    # client_info = get_security_client_info()
    
    # Test mode handling
    if is_test_mode():
        fullname = Config.DUMMY_FULLNAME
        phone = Config.DUMMY_PHONE
        password = Config.DUMMY_PASSWORD
    else:
        # Get and validate request data
        data = await request.get_json()
        if not data:
            return jsonify({"error": "Invalid request data"}), 400
        
        # Extract and validate required fields
        required_fields = ['fullname', 'phone', 'password']
        is_valid, missing_fields = validate_auth_request_data(data, required_fields)
        
        if not is_valid:
            log_warning(
                action="login_missing_fields",
                trace_info=data.get("ip_address", ""),
                message=f"Missing fields: {missing_fields}"
            )
            return jsonify({
                "message": _("Missing required fields: %(fields)s") % {"fields": ", ".join(missing_fields)}
            }), 400
        
        # Extract and sanitize data
        fullname = sanitize_user_input(data.get("fullname", ""))
        phone = data.get("phone", "").strip()
        password = data.get("password", "").strip()
        device_id = data.get("device_id", "") # TODO: get device id from client
        ip_address = data.get("ip_address", "") # TODO: get ip address from client
        
        # Validate device information
        is_valid_device, device_error = validate_device_info(device_id, ip_address)
        if not is_valid_device:
            log_warning(
                action="login_invalid_device",
                trace_info=ip_address,
                message=f"Invalid device: {device_error}"
            )
            return jsonify({"message": device_error}), 400
        
        # Check device safety
        if is_device_unsafe(ip_address=ip_address, device_id=device_id, info=phone or fullname):
            log_warning(
                action="login_unsafe_device",
                trace_info=ip_address,
                message="Unsafe device detected during login"
            )
            return jsonify({"message": auth_config.ERROR_MESSAGES['device_unsafe']}), 400
        
        # Validate and format phone number
        formatted_phone, phone_error = format_phone_number(phone)
        if not formatted_phone:
            log_error(
                action="login_invalid_phone",
                trace_info=phone,
                trace_info_hash=hash_sensitive_data(phone),
                trace_info_encrypted=encrypt_sensitive_data(phone),
                message="Invalid phone format"
            )
            return jsonify({"message": phone_error}), 400
        
        # Check login attempts
        identifier = f"{formatted_phone}:{fullname}"
        is_allowed, remaining_attempts = check_login_attempts(identifier)
        
        if not is_allowed:
            log_warning(
                action="login_rate_limited",
                trace_info=ip_address,
                message=f"Login rate limited for: {fullname} remaining attempts: {remaining_attempts}"
            )
            return jsonify({
                "message": auth_config.ERROR_MESSAGES['rate_limit_exceeded']
            }), 429
    
    try:
        # Authenticate user
        madrasa_name = os.getenv("MADRASA_NAME")
        conn = await get_db_connection()
        
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # Get user information
            await cursor.execute(
                "SELECT user_id, deactivated_at, password_hash FROM global.users WHERE phone = %s AND LOWER(fullname) = LOWER(%s)",
                (formatted_phone, fullname)
            )
            user = await cursor.fetchone()
            
            if not user:
                record_login_attempt(identifier, False)
                log_error(
                    action="login_user_not_found",
                    trace_info=formatted_phone,
                    trace_info_hash=hash_sensitive_data(formatted_phone),
                    trace_info_encrypted=encrypt_sensitive_data(formatted_phone),
                    message=f"User not found: {fullname}"
                )
                return jsonify({"message": auth_config.ERROR_MESSAGES['account_not_found']}), 404
            
            # Check password
            if not check_password_hash(user["password_hash"], password):
                record_login_attempt(identifier, False)
                log_warning(
                    action="login_incorrect_password",
                    trace_info=formatted_phone,
                    trace_info_hash=hash_sensitive_data(formatted_phone),
                    trace_info_encrypted=encrypt_sensitive_data(formatted_phone),
                    message="Incorrect password"
                )
                return jsonify({"message": auth_config.ERROR_MESSAGES['invalid_credentials']}), 401
            
            # Check if account is deactivated
            if user["deactivated_at"] is not None:
                log_warning(
                    action="login_account_deactivated",
                    trace_info=formatted_phone,
                    trace_info_hash=hash_sensitive_data(formatted_phone),
                    trace_info_encrypted=encrypt_sensitive_data(formatted_phone),
                    message="Account is deactivated"
                )
                return jsonify({
                    "action": "deactivate", 
                    "message": auth_config.ERROR_MESSAGES['account_deactivated']
                }), 403
            
            # Record successful login
            record_login_attempt(identifier, True)
            
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
            info = await cursor.fetchone()
            
            if not info or not info.get("phone") or not info.get("user_id"):
                log_warning(
                    action="login_incomplete_profile",
                    trace_info=formatted_phone,
                    trace_info_hash=hash_sensitive_data(formatted_phone),
                    trace_info_encrypted=encrypt_sensitive_data(formatted_phone),
                    message="Missing profile info"
                )
                return jsonify({
                    "error": "incomplete_profile", 
                    "message": _("Additional info required")
                }), 422
            
            # Remove sensitive information
            info.pop("password", None)
            info.pop("password_hash", None)
            
            # Format date of birth
            dob = info.get("date_of_birth")
            if isinstance(dob, (datetime.date, datetime.datetime)):
                info["date_of_birth"] = dob.strftime("%d/%m/%Y")
            
            # Log successful login
            log_info(
                action="user_logged_in_successfully",
                trace_info=ip_address,
                message=f"User logged in successfully: {fullname}"
            )
            
            return jsonify({
                "success": True, 
                "message": _("Login successful"), 
                "info": info
            }), 200
            
    except Exception as e:
        log_critical(
            action="login_error",
            trace_info=ip_address,
            trace_info_hash=hash_sensitive_data(phone or "unknown"),
            trace_info_encrypted=encrypt_sensitive_data(phone or "unknown"),
            message=f"Login error: {str(e)}"
        )
        return jsonify({"message": auth_config.ERROR_MESSAGES['internal_error']}), 500

@user_routes.route("/send_code", methods=["POST"])
@rate_limit(max_requests=10, window=60)
@handle_async_errors
async def send_verification_code() -> Response:
    """
    Send verification code via SMS or email with enhanced security
    
    Returns:
        JSON response with verification status
    """
    # Check maintenance mode
    if is_maintenance_mode():
        return jsonify({
            "error": auth_config.ERROR_MESSAGES['maintenance_mode']
        }), 503
    
    # Get client info for logging
    # client_info = get_security_client_info()
    
    # Test mode handling
    if is_test_mode():
        return jsonify({
            "success": True, 
            "message": _("Verification code sent to %(target)s") % {"target": Config.DUMMY_EMAIL}
        }), 200
    
    try:
        # Get and validate request data
        data = await request.get_json()
        if not data:
            return jsonify({"error": "Invalid request data"}), 400
        
        # Extract and validate required fields
        required_fields = ['phone', 'fullname']
        is_valid, missing_fields = validate_auth_request_data(data, required_fields)
        
        if not is_valid:
            log_warning(
                action="send_code_missing_fields",
                trace_info=data.get("ip_address", ""),
                message=f"Missing fields: {missing_fields}"
            )
            return jsonify({
                "message": _("Missing required fields: %(fields)s") % {"fields": ", ".join(missing_fields)}
            }), 400
        
        # Extract and sanitize data
        phone = data.get("phone", "").strip()
        fullname = sanitize_user_input(data.get("fullname", ""))
        password = sanitize_user_input(data.get("password", "")) if data.get("password") else None
        email = sanitize_user_input(data.get("email", "")) if data.get("email") else None
        lang = data.get("language", "en")
        signature = data.get("app_signature", "")
        device_id = data.get("device_id", "") # TODO: get device id from client
        ip_address = data.get("ip_address", "") # TODO: get ip address from client
        
        # Validate device information
        is_valid_device, device_error = validate_device_info(device_id, ip_address)
        if not is_valid_device:
            log_warning(
                action="send_code_invalid_device",
                trace_info=ip_address,
                message=f"Invalid device: {device_error}"
            )
            return jsonify({"message": device_error}), 400
        
        # Check device safety
        if is_device_unsafe(ip_address=ip_address, device_id=device_id, info=phone or email or fullname):
            log_warning(
                action="send_code_unsafe_device",
                trace_info=ip_address,
                message="Unsafe device detected during code sending"
            )
            return jsonify({"message": auth_config.ERROR_MESSAGES['device_unsafe']}), 400
        
        # Validate and format phone number
        formatted_phone, phone_error = format_phone_number(phone)
        if not formatted_phone:
            log_error(
                action="send_code_invalid_phone",
                trace_info=phone,
                trace_info_hash=hash_sensitive_data(phone),
                trace_info_encrypted=encrypt_sensitive_data(phone),
                message="Invalid phone format"
            )
            return jsonify({"message": phone_error}), 400
        
        # Validate fullname if provided
        if fullname:
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
        
        # Get email if not provided
        if not email:
            email = await get_email(phone=formatted_phone, fullname=fullname)
        
        # Check rate limiting
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # Check existing user if password provided
            if password and fullname:
                await cursor.execute(
                    "SELECT user_id FROM global.users WHERE phone = %s AND LOWER(fullname) = LOWER(%s)",
                    (formatted_phone, fullname)
                )
                existing_user = await cursor.fetchone()
                
                if existing_user:
                    log_warning(
                        action="send_code_user_exists",
                        trace_info=ip_address,
                        message=f"User already exists: {fullname}"
                    )
                    return jsonify({"message": auth_config.ERROR_MESSAGES['user_already_exists']}), 409
            
            # Check rate limit for verification codes
            await cursor.execute("""
                SELECT COUNT(*) AS recent_count 
                FROM global.verifications 
                WHERE phone = %s AND created_at > NOW() - INTERVAL 1 HOUR
            """, (formatted_phone,))
            result = await cursor.fetchone()
            count = result["recent_count"] if result else 0
            
            # Check if rate limit exceeded
            max_limit = max(auth_config.SMS_LIMIT_PER_HOUR, auth_config.EMAIL_LIMIT_PER_HOUR)
            if count >= max_limit:
                log_warning(
                    action="send_code_rate_limited",
                    trace_info=ip_address,
                    message=f"Rate limit exceeded for phone: {formatted_phone}"
                )
                return jsonify({"message": auth_config.ERROR_MESSAGES['rate_limit_exceeded']}), 429
            
            # Generate and send verification code
            code = generate_code()
            hashed_phone = hash_sensitive_data(formatted_phone)
            encrypted_phone = encrypt_sensitive_data(formatted_phone)
            
            # Try SMS first if under SMS limit
            if count < auth_config.SMS_LIMIT_PER_HOUR:
                if send_sms(phone=formatted_phone, signature=signature, code=code):
                    await cursor.execute(
                        "INSERT INTO global.verifications (phone, phone_hash, phone_encrypted, code, ip_address) VALUES (%s, %s, %s, %s, %s)",
                        (formatted_phone, hashed_phone, encrypted_phone, code, ip_address)
                    )
                    await conn.commit()
                    
                    log_info(
                        action="verification_code_sent_sms",
                        trace_info=ip_address,
                        message=f"Verification code sent via SMS to: {formatted_phone}"
                    )
                    
                    return jsonify({
                        "success": True, 
                        "message": _("Verification code sent to %(target)s") % {"target": formatted_phone}
                    }), 200
            
            # Try email if SMS failed or limit reached
            if email and count < auth_config.EMAIL_LIMIT_PER_HOUR:
                if send_email(to_email=email, code=code, lang=lang):
                    await cursor.execute(
                        "INSERT INTO global.verifications (phone, phone_hash, phone_encrypted, code, ip_address) VALUES (%s, %s, %s, %s, %s)",
                        (formatted_phone, hashed_phone, encrypted_phone, code, ip_address)
                    )
                    await conn.commit()
                    
                    log_info(
                        action="verification_code_sent_email",
                        trace_info=ip_address,
                        message=f"Verification code sent via email to: {email}"
                    )
                    
                    return jsonify({
                        "success": True, 
                        "message": _("Verification code sent to %(target)s") % {"target": email}
                    }), 200
            
            # If both methods failed
            log_critical(
                action="verification_code_failed",
                trace_info=ip_address,
                trace_info_hash=hash_sensitive_data(formatted_phone),
                trace_info_encrypted=encrypt_sensitive_data(formatted_phone),
                message="Failed to send verification code via any method"
            )
            return jsonify({"message": "Failed to send verification code"}), 500
            
    except Exception as e:
        log_critical(
            action="send_code_error",
            trace_info=ip_address,
            trace_info_hash=hash_sensitive_data(phone or "unknown"),
            trace_info_encrypted=encrypt_sensitive_data(phone or "unknown"),
            message=f"Error sending verification code: {str(e)}"
        )
        return jsonify({"message": auth_config.ERROR_MESSAGES['internal_error']}), 500

@user_routes.route("/reset_password", methods=["POST"])
@handle_async_errors
async def reset_password() -> Response:
    """
    Reset user password with enhanced security validation
    
    Returns:
        JSON response with password reset status
    """
    # Check maintenance mode
    if is_maintenance_mode():
        return jsonify({
            "error": auth_config.ERROR_MESSAGES['maintenance_mode']
        }), 503
    
    # Get client info for logging
    # client_info = get_security_client_info()
    
    # Test mode handling
    if is_test_mode():
        if not request.get_json().get("new_password"):
            return jsonify({"success": True, "message": "App in test mode"}), 200
        else:
            return jsonify({"success": True, "message": "App in test mode"}), 201
    
    try:
        # Get and validate request data
        data = await request.get_json()
        if not data:
            return jsonify({"error": "Invalid request data"}), 400
        
        # Extract and validate required fields
        required_fields = ['phone', 'fullname']
        is_valid, missing_fields = validate_auth_request_data(data, required_fields)
        
        if not is_valid:
            log_warning(
                action="reset_password_missing_fields",
                trace_info=data.get("ip_address", ""),
                message=f"Missing fields: {missing_fields}"
            )
            return jsonify({
                "message": _("Missing required fields: %(fields)s") % {"fields": ", ".join(missing_fields)}
            }), 400
        
        # Extract and sanitize data
        phone = data.get("phone", "").strip()
        fullname = sanitize_user_input(data.get("fullname", ""))
        user_code = data.get("code", "").strip()
        old_password = sanitize_user_input(data.get("old_password", "")) if data.get("old_password") else None
        new_password = sanitize_user_input(data.get("new_password", "")) if data.get("new_password") else None
        device_id = data.get("device_id", "") # TODO: get device id from client
        ip_address = data.get("ip_address", "") # TODO: get ip address from client
        
        # Validate device information
        is_valid_device, device_error = validate_device_info(device_id, ip_address)
        if not is_valid_device:
            log_warning(
                action="reset_password_invalid_device",
                trace_info=ip_address,
                message=f"Invalid device: {device_error}"
            )
            return jsonify({"message": device_error}), 400
        
        # Check device safety
        if is_device_unsafe(ip_address=ip_address, device_id=device_id, info=phone or fullname):
            log_warning(
                action="reset_password_unsafe_device",
                trace_info=ip_address,
                message="Unsafe device detected during password reset"
            )
            return jsonify({"message": auth_config.ERROR_MESSAGES['device_unsafe']}), 400
        
        # Validate and format phone number
        formatted_phone, phone_error = format_phone_number(phone)
        if not formatted_phone:
            log_error(
                action="reset_password_invalid_phone",
                trace_info=phone,
                trace_info_hash=hash_sensitive_data(phone),
                trace_info_encrypted=encrypt_sensitive_data(phone),
                message="Invalid phone format"
            )
            return jsonify({"message": phone_error}), 400
        
        # If old password is not provided, use code verification
        if not old_password:
            validate_code_result = check_code(user_code, formatted_phone)
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
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # Get user information
            await cursor.execute(
                "SELECT user_id, password_hash FROM global.users WHERE phone = %s AND LOWER(fullname) = LOWER(%s)",
                (formatted_phone, fullname)
            )
            user = await cursor.fetchone()
            
            if not user:
                log_error(
                    action="reset_password_user_not_found",
                    trace_info=formatted_phone,
                    trace_info_hash=hash_sensitive_data(formatted_phone),
                    trace_info_encrypted=encrypt_sensitive_data(formatted_phone),
                    message=f"User not found: {fullname}"
                )
                return jsonify({"message": auth_config.ERROR_MESSAGES['account_not_found']}), 404
            
            # If old password is provided, verify it
            if old_password:
                if not check_password_hash(user['password_hash'], old_password):
                    log_warning(
                        action="reset_password_incorrect_old_password",
                        trace_info=formatted_phone,
                        trace_info_hash=hash_sensitive_data(formatted_phone),
                        trace_info_encrypted=encrypt_sensitive_data(formatted_phone),
                        message="Incorrect old password"
                    )
                    return jsonify({"message": _("Incorrect old password")}), 401
            
            # Hash new password
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
            log_info(
                action="password_reset_successful",
                trace_info=ip_address,
                message=f"Password reset successful for: {fullname}"
            )
            
            return jsonify({"success": True, "message": _("Password Reset Successful")}), 201
            
    except Exception as e:
        log_critical(
            action="reset_password_error",
            trace_info=ip_address,
            trace_info_hash=hash_sensitive_data(phone or "unknown"),
            trace_info_encrypted=encrypt_sensitive_data(phone or "unknown"),
            message=f"Password reset error: {str(e)}"
        )
        return jsonify({"message": auth_config.ERROR_MESSAGES['internal_error']}), 500

@user_routes.route("/account/<page_type>", methods=["GET", "POST"])
@rate_limit(max_requests=10, window=60)
@handle_async_errors
async def manage_account(page_type: str) -> Response:
    """
    Manage account (deactivate/delete) with enhanced security
    
    Args:
        page_type: The type of account management (remove, deactivate, delete)
        
    Returns:
        JSON response with account management status
    """
    # Validate page type
    if page_type not in ("remove", "deactivate", "delete"):
        return jsonify({"message": _("Invalid page type")}), 400
    
    # Check maintenance mode
    if is_maintenance_mode():
        return jsonify({
            "error": auth_config.ERROR_MESSAGES['maintenance_mode']
        }), 503
    
    # Get client info for logging
    # client_info = get_security_client_info()
    
    # Handle GET request (render form)
    if request.method == "GET":
        return render_template(
            "account_manage.html",
            page_type=page_type.capitalize()
        )
    
    # Handle POST request
    try:
        # Get and validate request data
        data = await request.get_json() if request.method == "POST" else await request.form
        if not data:
            return jsonify({"error": "Invalid request data"}), 400
        
        # Extract and validate required fields
        required_fields = ['phone', 'fullname', 'password']
        is_valid, missing_fields = validate_auth_request_data(data, required_fields)
        
        if not is_valid:
            log_warning(
                action="manage_account_missing_fields",
                trace_info=data.get("ip_address", ""),
                message=f"Missing fields: {missing_fields}"
            )
            return jsonify({
                "message": _("Missing required fields: %(fields)s") % {"fields": ", ".join(missing_fields)}
            }), 400
        
        # Extract and sanitize data
        phone = data.get("phone", "").strip()
        fullname = sanitize_user_input(data.get("fullname", ""))
        password = sanitize_user_input(data.get("password", ""))
        email = sanitize_user_input(data.get("email", "")) if data.get("email") else None
        
        # Test mode handling
        if is_test_mode():
            fullname = Config.DUMMY_FULLNAME
            phone = Config.DUMMY_PHONE
            password = Config.DUMMY_PASSWORD
        
        # Validate and format phone number
        formatted_phone, phone_error = format_phone_number(phone)
        if not formatted_phone:
            log_error(
                action="manage_account_invalid_phone",
                trace_info=phone,
                trace_info_hash=hash_sensitive_data(phone),
                trace_info_encrypted=encrypt_sensitive_data(phone),
                message="Invalid phone format"
            )
            return jsonify({"message": phone_error}), 400
        
        # Authenticate user
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                "SELECT user_id, password_hash FROM global.users WHERE phone = %s AND LOWER(fullname) = LOWER(%s)",
                (formatted_phone, fullname)
            )
            user = await cursor.fetchone()
            
            if not user or not check_password_hash(user["password_hash"], password):
                log_error(
                    action="manage_account_invalid_credentials",
                    trace_info=formatted_phone,
                    trace_info_hash=hash_sensitive_data(formatted_phone),
                    trace_info_encrypted=encrypt_sensitive_data(formatted_phone),
                    message="Invalid credentials for account management"
                )
                return jsonify({"message": _("Invalid login details")}), 401
            
            # Prepare confirmation message
            deletion_days = auth_config.ACCOUNT_DELETION_DAYS
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
                if not send_email(to_email=email, subject=subject, body=msg):
                    errors += 1
            else:
                errors += 1
            
            if not send_sms(phone=formatted_phone, msg=msg):
                errors += 1
            
            if errors > 1:
                log_critical(
                    action="manage_account_notification_failed",
                    trace_info=formatted_phone,
                    trace_info_hash=hash_sensitive_data(formatted_phone),
                    trace_info_encrypted=encrypt_sensitive_data(formatted_phone),
                    message="Could not send confirmation notifications"
                )
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
                log_warning(
                    action="account_deletion_scheduled",
                    trace_info=formatted_phone,
                    trace_info_hash=hash_sensitive_data(formatted_phone),
                    trace_info_encrypted=encrypt_sensitive_data(formatted_phone),
                    message=f"User {hash_sensitive_data(fullname)} scheduled for deletion"
                )
                return jsonify({"success": True, "message": _("Account deletion initiated. Check your messages.")}), 200
            else:
                log_warning(
                    action="account_deactivated",
                    trace_info=formatted_phone,
                    trace_info_hash=hash_sensitive_data(formatted_phone),
                    trace_info_encrypted=encrypt_sensitive_data(formatted_phone),
                    message=f"User {hash_sensitive_data(fullname)} deactivated"
                )
                return jsonify({"success": True, "message": _("Account deactivated successfully.")}), 200
                
    except Exception as e:
        log_critical(
            action="manage_account_error",
            trace_info=data.get("ip_address", ""),
            trace_info_hash=hash_sensitive_data(phone or "unknown"),
            trace_info_encrypted=encrypt_sensitive_data(phone or "unknown"),
            message=f"Account management error: {str(e)}"
        )
        return jsonify({"message": auth_config.ERROR_MESSAGES['internal_error']}), 500

@user_routes.route("/account/reactivate", methods=['POST'])
@rate_limit(max_requests=10, window=60)
@handle_async_errors
async def undo_remove() -> Response:
    """
    Reactivate a deactivated account with enhanced validation
    
    Returns:
        JSON response with reactivation status
    """
    # Check maintenance mode
    if is_maintenance_mode():
        return jsonify({
            "error": auth_config.ERROR_MESSAGES['maintenance_mode']
        }), 503
    
    # Get client info for logging
    # client_info = get_security_client_info()
    
    # Test mode handling
    if is_test_mode():
        return jsonify({"success": True, "message": "App in test mode"}), 200
    
    try:
        # Get and validate request data
        data = await request.get_json()
        if not data:
            return jsonify({"error": "Invalid request data"}), 400
        
        # Extract and validate required fields
        required_fields = ['phone', 'fullname']
        is_valid, missing_fields = validate_auth_request_data(data, required_fields)
        
        if not is_valid:
            log_warning(
                action="reactivate_missing_fields",
                trace_info=data.get("ip_address", ""),
                message=f"Missing fields: {missing_fields}"
            )
            return jsonify({
                "message": _("Missing required fields: %(fields)s") % {"fields": ", ".join(missing_fields)}
            }), 400
        
        # Extract and sanitize data
        phone = data.get("phone", "").strip()
        fullname = sanitize_user_input(data.get("fullname", ""))
        
        # Validate and format phone number
        formatted_phone, phone_error = format_phone_number(phone)
        if not formatted_phone:
            log_error(
                action="reactivate_invalid_phone",
                trace_info=phone,
                trace_info_hash=hash_sensitive_data(phone),
                trace_info_encrypted=encrypt_sensitive_data(phone),
                message="Invalid phone format"
            )
            return jsonify({"message": phone_error}), 400
        
        # Reactivate account
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                "SELECT user_id, deactivated_at, scheduled_deletion_at FROM global.users WHERE phone = %s AND LOWER(fullname) = LOWER(%s)",
                (formatted_phone, fullname)
            )
            user = await cursor.fetchone()
            
            if not user or not user["deactivated_at"]:
                log_warning(
                    action="reactivate_no_deactivated_account",
                    trace_info=data.get("ip_address", ""),
                    message=f"No deactivated account found for: {fullname}"
                )
                return jsonify({"message": "No deactivated account found"}), 404
            
            # Check if reactivation period has expired
            deactivated_at = user["deactivated_at"]
            if (datetime.now(timezone.utc) - deactivated_at).days > auth_config.ACCOUNT_REACTIVATION_DAYS and user["scheduled_deletion_at"]:
                log_warning(
                    action="reactivate_period_expired",
                    trace_info=data.get("ip_address", ""),
                    message=f"Reactivation period expired for: {fullname}"
                )
                return jsonify({"message": "Undo period expired"}), 403
            
            # Reactivate account
            await cursor.execute(
                "UPDATE global.users SET deactivated_at = NULL, scheduled_deletion_at = NULL, ip_address = %s WHERE user_id = %s",
                (data.get("ip_address", ""), user["user_id"]) # TODO: get ip address from client
            )
            await conn.commit()
            
            # Log successful reactivation
            log_info(
                action="account_reactivated_successfully",
                trace_info=data.get("ip_address", ""),
                message=f"Account reactivated successfully for: {fullname}"
            )
            
            return jsonify({"success": True, "message": _("Account reactivated.")}), 200
            
    except Exception as e:
        log_critical(
            action="reactivate_error",
            trace_info=data.get("ip_address", ""),
            trace_info_hash=hash_sensitive_data(phone or "unknown"),
            trace_info_encrypted=encrypt_sensitive_data(phone or "unknown"),
            message=f"Account reactivation error: {str(e)}"
        )
        return jsonify({"message": auth_config.ERROR_MESSAGES['internal_error']}), 500

@user_routes.route("/account/check", methods=['POST'])
@handle_async_errors
async def get_account_status() -> Response:
    """
    Check account status and validate session with enhanced security
    
    Returns:
        JSON response with account status and validation results
    """
    # Check maintenance mode
    if is_maintenance_mode():
        return jsonify({
            "error": auth_config.ERROR_MESSAGES['maintenance_mode']
        }), 503
    
    # Get client info for logging
    # client_info = get_security_client_info()
    
    # Test mode handling
    if is_test_mode():
        return jsonify({"success": True, "message": "App in test mode"}), 200
    
    try:
        # Get and validate request data
        data = await request.get_json()
        if not data:
            return jsonify({"error": "Invalid request data"}), 400
        
        # Extract and validate device information
        device_id = data.get("device_id", "") # TODO: get device id from client
        device_brand = data.get("device_brand", "") # TODO: get device brand from client
        ip_address = data.get("ip_address", "") # TODO: get ip address from client
        
        # Validate device information
        is_valid_device, device_error = validate_device_info(device_id, ip_address, device_brand)
        if not is_valid_device:
            log_warning(
                action="account_check_invalid_device",
                trace_info=ip_address,
                message=f"Invalid device: {device_error}"
            )
            return jsonify({"action": "block", "message": _("Unknown device detected")}), 400
        
        # Extract user information
        phone = data.get("phone", "").strip()
        user_id = data.get("user_id", "")
        fullname = sanitize_user_input(data.get("name_en", ""))
        madrasa_name = os.getenv("MADRASA_NAME")
        
        # Check if account information is provided
        if not phone or not fullname:
            log_info(
                action="account_check_no_info",
                trace_info=ip_address,
                message="No account information provided"
            )
            return jsonify({"success": True, "message": _("No account information provided.")}), 200
        
        # Validate and format phone number
        formatted_phone, phone_error = format_phone_number(phone)
        if not formatted_phone:
            log_error(
                action="account_check_invalid_phone",
                trace_info=phone,
                trace_info_hash=hash_sensitive_data(phone),
                trace_info_encrypted=encrypt_sensitive_data(phone),
                message="Invalid phone format"
            )
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
                log_info(
                    action="account_check_missing_field",
                    trace_info=ip_address,
                    message=f"Field {field_name} is missing"
                )
                return jsonify({
                    "action": "logout", 
                    "message": _("Session invalidated. Please log in again.")
                }), 400
        
        # Validate account in database
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
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
                log_error(
                    action="account_check_not_found",
                    trace_info=ip_address,
                    trace_info_hash=hash_sensitive_data(formatted_phone),
                    trace_info_encrypted=encrypt_sensitive_data(formatted_phone),
                    message="No matching user found"
                )
                return jsonify({
                    "action": "logout", 
                    "message": _("Session invalidated. Please log in again.")
                }), 401
            
            # Check if account is deactivated
            if record.get("deactivated_at"):
                log_warning(
                    action="account_check_deactivated",
                    trace_info=record["user_id"],
                    trace_info_hash=hash_sensitive_data(record["user_id"]),
                    trace_info_encrypted=encrypt_sensitive_data(record["user_id"]),
                    message="Account is deactivated"
                )
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
                if col == "date_of_birth" and isinstance(db_val, (datetime.datetime, datetime.date)):
                    try:
                        provided_date = datetime.fromisoformat(provided).date()
                    except Exception:
                        log_error(
                            action="account_check_bad_date",
                            trace_info=record["user_id"],
                            trace_info_hash=hash_sensitive_data(record["user_id"]),
                            trace_info_encrypted=encrypt_sensitive_data(record["user_id"]),
                            message=f"Bad date format: {provided}"
                        )
                        return jsonify({
                            "action": "logout", 
                            "message": _("Session invalidated. Please log in again.")
                        }), 401
                    
                    if db_val:
                        db_date = db_val.date() if isinstance(db_val, datetime.datetime) else db_val
                        if db_date != provided_date:
                            log_warning(
                                action="account_check_date_mismatch",
                                trace_info=record["user_id"],
                                trace_info_hash=hash_sensitive_data(record["user_id"]),
                                trace_info_encrypted=encrypt_sensitive_data(record["user_id"]),
                                message=f"Date mismatch: {col}: {provided_date} != {db_date}"
                            )
                            return jsonify({
                                "action": "logout", 
                                "message": _("Session invalidated. Please log in again.")
                            }), 401
                else:
                    # Compare string values
                    if str(provided).strip() != str(db_val).strip():
                        log_warning(
                            action="account_check_field_mismatch",
                            trace_info=record["user_id"],
                            trace_info_hash=hash_sensitive_data(record["user_id"]),
                            trace_info_encrypted=encrypt_sensitive_data(record["user_id"]),
                            message=f"Field mismatch: {col}: {hash_sensitive_data(str(provided))} != {hash_sensitive_data(str(db_val))}"
                        )
                        return jsonify({
                            "action": "logout", 
                            "message": _("Session invalidated. Please log in again.")
                        }), 401
            
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
            log_info(
                action="account_check_successful",
                trace_info=ip_address,
                message=f"Account check successful for: {fullname}"
            )
            
            return jsonify({
                "success": True, 
                "message": _("Account is valid"), 
                "user_id": record["user_id"]
            }), 200
            
    except Exception as e:
        log_critical(
            action="account_check_error",
            trace_info=ip_address,
            trace_info_hash=hash_sensitive_data(phone or "unknown"),
            trace_info_encrypted=encrypt_sensitive_data(phone or "unknown"),
            message=f"Account check error: {str(e)}"
        )
        return jsonify({"message": auth_config.ERROR_MESSAGES['internal_error']}), 500

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
            if (datetime.now(timezone.utc) - session_time).total_seconds() > auth_config.SESSION_TIMEOUT_HOURS * 3600:
                return False, "Session has expired"
        except ValueError:
            return False, "Invalid session timestamp"
    
    return True, ""

def track_user_activity(user_id: int, activity_type: str, details: Dict[str, Any] = None) -> None:
    """Track user activity for security monitoring"""
    try:
        activity_data = {
            'user_id': user_id,
            'activity_type': activity_type,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'ip_address': get_security_client_info()["ip_address"] or None, # TODO: get ip address from client
            'details': details or {}
        }
        
        # Log activity for monitoring
        log_info(
            action=f"user_activity_{activity_type}",
            trace_info=activity_data['ip_address'],
            message=f"User activity: {activity_type}",
            **activity_data
        )
        
        # Store in cache for rate limiting
        cache_key = f"user_activity:{user_id}:{activity_type}"
        cache.set(cache_key, activity_data, ttl=3600)  # 1 hour
        
    except Exception as e:
        log_critical(
            action="activity_tracking_error",
            trace_info="system",
            trace_info_hash="N/A",
            trace_info_encrypted="N/A",
            message=f"Error tracking user activity: {str(e)}"
        )

def validate_device_fingerprint(device_data: Dict[str, Any]) -> bool:
    """Validate device fingerprint for security"""
    required_device_fields = ['device_id', 'device_brand', 'ip_address']
    
    for field in required_device_fields:
        if not device_data.get(field):
            return False
    
    # Check for suspicious device patterns
    device_id = device_data['device_id']
    suspicious_patterns = [
        r'^(test|dummy|fake|null|undefined)$',
        r'[<>"\']',
        r'\.\.',
        r'javascript:',
        r'<script'
    ]
    
    for pattern in suspicious_patterns:
        if re.search(pattern, device_id, re.IGNORECASE):
            _send_security_notifications(device_data['ip_address'], device_data['device_id'], "Suspicious device identifier detected")
            return False
    
    return True

def check_account_security_status(user_id: int) -> Dict[str, Any]:
    """Check account security status and return security metrics"""
    try:
        # Get recent login attempts
        login_attempts = cache.get(f"login_attempts:{user_id}", 0)
        
        # Get recent activities
        recent_activities = []
        for activity_type in ['login', 'logout', 'password_change', 'account_modification']:
            activity_data = cache.get(f"user_activity:{user_id}:{activity_type}")
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
        log_critical(
            action="security_status_check_error",
            trace_info="system",
            trace_info_hash="N/A",
            trace_info_encrypted="N/A",
            message=f"Error checking security status: {str(e)}"
        )
        return {
            'security_score': 0,
            'login_attempts': 0,
            'recent_activities': 0,
            'last_activity': None
        }

# ─── Configuration Validation ───────────────────────────────────────────────

def validate_auth_config() -> List[str]:
    """Validate authentication configuration and return any issues"""
    issues = []
    
    # Check required environment variables
    required_vars = ['MADRASA_NAME', 'SMS_LIMIT_PER_HOUR', 'EMAIL_LIMIT_PER_HOUR']
    for var in required_vars:
        if not os.getenv(var):
            issues.append(f"Missing required environment variable: {var}")
    
    # Validate configuration values
    if auth_config.SMS_LIMIT_PER_HOUR <= 0:
        issues.append("SMS_LIMIT_PER_HOUR must be greater than 0")
    
    if auth_config.EMAIL_LIMIT_PER_HOUR <= 0:
        issues.append("EMAIL_LIMIT_PER_HOUR must be greater than 0")
    
    if auth_config.LOGIN_ATTEMPTS_LIMIT <= 0:
        issues.append("LOGIN_ATTEMPTS_LIMIT must be greater than 0")
    
    return issues

# ─── Initialization and Cleanup ─────────────────────────────────────────────

def initialize_auth_module() -> bool:
    """Initialize authentication module with validation"""
    try:
        # Validate configuration
        config_issues = validate_auth_config()
        if config_issues:
            for issue in config_issues:
                log_critical(
                    action="auth_config_error",
                    trace_info="initialization",
                    trace_info_hash="N/A",
                    trace_info_encrypted="N/A",
                    message=issue
                )
            return False
        
        # Initialize security patterns
        security_manager.suspicious_patterns.extend([
            r'(?i)(union(\s+all)?\s+select|select\s+.*from|insert\s+into|update\s+.*set|delete\s+from|drop\s+table|create\s+table|alter\s+table|--|#|;|\bor\b|\band\b|\bexec\b|\bsp_\b|\bxp_\b)',
            r'<script[^>]*>.*?</script>',
            r'javascript:',
            r'on\w+\s*=',
            r'<iframe[^>]*>',
            r'<object[^>]*>',
            r'<embed[^>]*>'
        ])
        
        log_info(
            action="auth_module_initialized",
            trace_info="initialization",
            message="Authentication module initialized successfully"
        )
        return True
        
    except Exception as e:
        log_critical(
            action="auth_init_error",
            trace_info="initialization",
            trace_info_hash="N/A",
            trace_info_encrypted="N/A",
            message=f"Authentication module initialization failed: {str(e)}"
        )
        return False

# Initialize the authentication module
if not initialize_auth_module():
    raise RuntimeError("Failed to initialize authentication module")