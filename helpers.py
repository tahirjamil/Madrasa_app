"""
Advanced Helper Functions for Madrasha Application

"""
import asyncio, re, secrets
import json, os, random, smtplib, time, hashlib
from secrets import compare_digest
from cryptography.fernet import Fernet
import base64
from contextlib import asynccontextmanager
from datetime import datetime
from email.mime.text import MIMEText
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple, Callable
from password_validator import PasswordValidator

import aiomysql
import phonenumbers
import requests
from aiomysql import IntegrityError
from dotenv import load_dotenv
from phonenumbers.phonenumberutil import NumberParseException
from quart import jsonify, request
from quart_babel import gettext as _
from werkzeug.datastructures import FileStorage

from config import Config
from database.database_utils import get_db_connection
from logger import log_error, log_critical, log_warning, log_info

# Load environment variables
load_dotenv()

# ─── Configuration and Constants ───────────────────────────────────────────────

class AppConfig:
    """Centralized application configuration with validation"""
    
    def __init__(self):
        self.exam_dir = Config.EXAM_DIR
        self.exam_result_index_file = os.path.join(self.exam_dir, 'index.json')
        self.allowed_exam_extensions = Config.ALLOWED_EXAM_EXTENSIONS
        
        self.notices_dir = Config.NOTICES_DIR
        self.notices_index_file = os.path.join(self.notices_dir, 'index.json')
        self.allowed_notice_extensions = Config.ALLOWED_NOTICE_EXTENSIONS
        
        # Security settings
        self.max_login_attempts = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
        self.lockout_duration = int(os.getenv("LOCKOUT_DURATION_MINUTES", "5")) * 60
        self.rate_limit_window = int(os.getenv("RATE_LIMIT_WINDOW_HOURS", "1")) * 3600
        self.max_requests_per_hour = int(os.getenv("MAX_REQUESTS_PER_HOUR", "1000"))
        
        # Communication settings
        self.sms_provider_url = os.getenv("SMS_PROVIDER_URL", "https://textbelt.com/text")
        self.sms_api_key = os.getenv("TEXTBELT_KEY")
        self.email_host = os.getenv("EMAIL_HOST", "smtp.gmail.com")
        self.email_port = int(os.getenv("EMAIL_PORT", "587"))
        self.email_address = os.getenv("EMAIL_ADDRESS", "fallback-email")
        self.email_password = os.getenv("EMAIL_PASSWORD", "fallback-pass")
        
        # Verification settings
        self.code_expiry_minutes = int(os.getenv("CODE_EXPIRY_MINUTES", "10"))
        self.code_length = int(os.getenv("CODE_LENGTH", "6"))
        
        # Development settings
        self.dev_email = os.getenv("DEV_EMAIL")
        self.madrasa_email = os.getenv("EMAIL_ADDRESS")
        self.dev_phone = os.getenv("DEV_PHONE")
        self.madrasa_phone = os.getenv("MADRASA_PHONE")
        
        # Initialize directories
        self._initialize_directories()
    
    def _initialize_directories(self):
        """Initialize required directories and files"""
        os.makedirs(self.exam_dir, exist_ok=True)
        os.makedirs(self.notices_dir, exist_ok=True)
        
        # Initialize index files if they don't exist
        for index_file in [self.exam_result_index_file, self.notices_index_file]:
            if not os.path.exists(index_file):
                with open(index_file, 'w') as f:
                    json.dump([], f)

# Global configuration instance
config = AppConfig()

# ─── Caching and Performance ─────────────────────────────────────────────────

class CacheManager:
    """Advanced caching system with TTL and memory management"""
    
    def __init__(self):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._max_size = 1000
        self._cleanup_interval = 5 * 60  # 5 minutes
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value from cache if not expired"""
        if key in self._cache:
            value, expiry = self._cache[key]
            if time.time() < expiry:
                return value
            else:
                del self._cache[key]
        return default
    
    def set(self, key: str, value: Any, ttl: int = 1 * 3600) -> None:
        """Set value in cache with TTL"""
        if len(self._cache) >= self._max_size:
            self._cleanup()
        
        expiry = time.time() + ttl
        self._cache[key] = (value, expiry)
    
    def delete(self, key: str) -> None:
        """Delete key from cache"""
        self._cache.pop(key, None)
    
    def clear(self) -> None:
        """Clear all cache entries"""
        self._cache.clear()
    
    def _cleanup(self) -> None:
        """Remove expired entries and oldest entries if needed"""
        current_time = time.time()
        expired_keys = [
            key for key, (_, expiry) in self._cache.items()
            if current_time >= expiry
        ]
        
        for key in expired_keys:
            del self._cache[key]
        
        # If still too many items, remove oldest
        if len(self._cache) > self._max_size // 2:
            sorted_items = sorted(
                self._cache.items(),
                key=lambda x: x[1][1]  # Sort by expiry time
            )
            items_to_remove = len(sorted_items) - self._max_size // 2
            for key, _ in sorted_items[:items_to_remove]:
                del self._cache[key]

# Global cache instance
cache = CacheManager()

# ─── Rate Limiting ───────────────────────────────────────────────────────────

class RateLimiter:
    """Advanced rate limiting with sliding window"""
    
    def __init__(self):
        self._requests: Dict[str, List[float]] = {}
        self._cleanup_interval = 1 * 3600  # 1 hour
        self._last_cleanup = time.time()
    
    def is_allowed(self, identifier: str, max_requests: int, window: int) -> bool:
        """Check if request is allowed based on rate limit"""
        current_time = time.time()
        
        # Cleanup old entries periodically
        if current_time - self._last_cleanup > self._cleanup_interval:
            self._cleanup()
            self._last_cleanup = current_time
        
        # Get request history for this identifier
        requests = self._requests.get(identifier, [])
        
        # Remove requests outside the window
        window_start = current_time - window
        requests = [req_time for req_time in requests if req_time > window_start]
        
        # Check if under limit
        if len(requests) < max_requests:
            requests.append(current_time)
            self._requests[identifier] = requests
            return True
        
        return False
    
    def _cleanup(self) -> None:
        """Remove old request records"""
        current_time = time.time()
        old_identifiers = []
        
        for identifier, requests in self._requests.items():
            # Keep only recent requests (within last hour)
            recent_requests = [req for req in requests if current_time - req < 3600]
            if recent_requests:
                self._requests[identifier] = recent_requests
            else:
                old_identifiers.append(identifier)
        
        for identifier in old_identifiers:
            del self._requests[identifier]

# Global rate limiter instance
rate_limiter = RateLimiter()

# ─── Security Functions ───────────────────────────────────────────────────────
from secrets import compare_digest
from quart import request
from config import Config

def is_valid_api_key(api_key: str) -> bool:
    """Validate API key securely based on request method"""

    if is_test_mode():
        return True

    if not api_key:
        return False

    return any(compare_digest(api_key, key) for key in Config.API_KEYS)

def is_maintenance_mode() -> bool:
    """Check if application is in maintenance mode"""
    verify = os.getenv("MAINTENANCE_MODE", "")
    return verify is True or (isinstance(verify, str) and verify.lower() in ("true", "yes", "on"))

def is_dummy_mode(fullname: str = None, phone: str = None, password: str = None, email: str = None, code: str = None) -> bool:
    """Check if application is in dummy mode"""
    if fullname and fullname == "dummy":
        return True
    
    if phone and phone == "+8801000000000":
        return True
    
    if password and password == "Dummy@123":
        return True
    
    return False

def is_test_mode() -> bool:
    """Check if application is in test mode"""
    verify = os.getenv("TEST_MODE", "")
    return verify is True or (isinstance(verify, str) and verify.lower() in ("true", "yes", "on"))

async def check_rate_limit(identifier: str, max_requests: int = None, window: int = None) -> bool:
    """Check rate limit for given identifier"""
    if max_requests is None:
        max_requests = config.max_requests_per_hour
    if window is None:
        window = config.rate_limit_window
    
    return rate_limiter.is_allowed(identifier, max_requests, window)

async def block_check(info: str) -> Optional[bool]:
    """Check if IP/device is blocked with enhanced security"""
    conn = await get_db_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT COUNT(*) AS blocked FROM global.blocklist WHERE threat_level = 'high'"
            )
            result = await cursor.fetchone()
            need_check = result["blocked"] if result else 0
            
            return need_check > 3
    except IntegrityError as e:
        log_critical(action="check_blocklist_failed", trace_info=info, trace_info_hash="N/A", trace_info_encrypted="N/A", message=f"IntegrityError: {e}")
        return None
    except Exception as e:
        log_critical(action="check_blocklist_failed", trace_info=info, trace_info_hash="N/A", trace_info_encrypted="N/A", message=f"Error: {e}")
        return None

async def is_device_unsafe(ip_address: str, device_id: str, info: str = None) -> bool:
    """Enhanced device safety check with comprehensive logging"""
    if is_test_mode():
        return False
    
    # Validate inputs
    if not ip_address or not device_id:
        log_critical(action="security_breach", trace_info=ip_address or device_id or info, trace_info_hash="N/A", trace_info_encrypted="N/A", message="Missing device information")
        
        # Send notifications
        await _send_security_notifications(ip_address, device_id, info)
        
        # Update blocklist
        await _update_blocklist(ip_address, device_id, info)
        return True
    
    return False

async def _send_security_notifications(ip_address: str, device_id: str, info: str) -> None:
    """Send security breach notifications"""
    notification_data = {
        "ip_address": ip_address,
        "device_id": device_id,
        "info": info,
        "timestamp": datetime.now().isoformat()
    }
    
    # Send emails
    for email in [config.dev_email, config.madrasa_email]:
        if email:
            await _send_async_email(
                to_email=email,
                subject="Security Breach Alert",
                body=f"""Security Breach Detected

An unknown device attempted to access the application.

Details:
- IP Address: {ip_address}
- Device ID: {device_id}
- Additional Info: {info}
- Timestamp: {notification_data['timestamp']}

Please review and take appropriate action.

@An-Nur.app"""
            )
    
    # Send SMS
    for phone in [config.dev_phone, config.madrasa_phone]:
        if phone:
            await _send_async_sms(
                phone=phone,
                msg=f"""Security Breach Alert

Unknown device access attempt:
IP: {ip_address}
Device: {device_id}
Info: {info}

@An-Nur.app"""
            )

async def _update_blocklist(ip_address: str, device_id: str, info: str) -> None:
    """Update blocklist with security breach information"""
    conn = await get_db_connection()
    basic_info = ip_address or device_id or "Basic Info Breached"
    additional_info = info or "NULL"
    
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "INSERT INTO global.blocklist (basic_info, additional_info) VALUES (%s, %s)",
                (basic_info, additional_info)
            )
            await conn.commit()
    except Exception as e:
        log_critical(action="update_blocklist_failed", trace_info=info, trace_info_hash="N/A", trace_info_encrypted="N/A", message=f"Failed to update blocklist: {e}")

# ─── Communication Functions ──────────────────────────────────────────────────

async def _send_async_email(to_email: str, subject: str, body: str) -> bool:
    """Send email asynchronously"""
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = config.email_address
        msg['To'] = to_email
        
        # Use asyncio to run SMTP in thread pool
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send_smtp_email, msg, to_email)
        return True
    except Exception as e:
        log_critical(action="email_error", trace_info=to_email, trace_info_hash="N/A", trace_info_encrypted="N/A", message=str(e))
        return False

def _send_smtp_email(msg: MIMEText, to_email: str) -> None:
    """Send email via SMTP (blocking)"""
    server = smtplib.SMTP(config.email_host, config.email_port)
    server.starttls()
    server.login(config.email_address, config.email_password)
    server.sendmail(config.email_address, to_email, msg.as_string())
    server.quit()

def send_email(to_email: str, code: str = None, subject: str = None, 
               body: str = None) -> bool:
    """Send email with enhanced error handling"""
    asyncio.create_task(delete_code())
    
    if not subject:
        subject = _("Verification Email")
    if not body:
        body = ""
        if code:
            body += f"\n{_('Your code is: %(code)s') % {'code': code}}"
        body += "\n\n@An-Nur.app"
    
    return asyncio.run(_send_async_email(to_email, subject, body))

async def _send_async_sms(phone: str, msg: str) -> bool:
    """Send SMS asynchronously"""
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _send_sms_request, phone, msg)
        return result
    except Exception as e:
        log_critical(action="sms_error", trace_info=phone, trace_info_hash="N/A", trace_info_encrypted="N/A", message=str(e))
        return False

def _send_sms_request(phone: str, msg: str) -> bool:
    """Send SMS request (blocking)"""
    response = requests.post(config.sms_provider_url, {
        'phone': phone,
        'message': msg,
        'key': config.sms_api_key
    })
    
    try:
        result = response.json()
        return result.get("success", False)
    except Exception as e:
        log_critical(action="sms_parse_error", trace_info=phone, trace_info_hash="N/A", trace_info_encrypted="N/A", message=str(e))
        return False

def send_sms(phone: str, signature: str = None, code: str = None, 
             msg: str = None, lang: str = "en") -> bool:
    """Send SMS with enhanced error handling"""
    asyncio.create_task(delete_code())
    
    if not msg:
        msg = _("Verification code sent to %(target)s") % {"target": phone}
        if code:
            msg += f"\n{_('Your code is: %(code)s') % {'code': code}}"
        msg += f"\n\n@An-Nur.app\nAppSignature: {signature}"
    
    return asyncio.run(_send_async_sms(phone, msg))

# ─── Verification Functions ───────────────────────────────────────────────────

def generate_code() -> int:
    """Generate secure verification code"""
    return random.randint(10**(config.code_length-1), 10**config.code_length - 1)

async def check_code(user_code: str, phone: str) -> Optional[Tuple[Dict, int]]:
    """Enhanced code verification with security features"""
    conn = await get_db_connection()
    
    if is_test_mode():
        return None
    
    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
                SELECT code, created_at FROM global.verifications
                WHERE phone = %s
                ORDER BY created_at DESC
                LIMIT 1
            """, (phone,))
            result = await cursor.fetchone()
            
            if not result:
                return jsonify({"message": "No verification code found"}), 404
            
            db_code = result["code"]
            created_at = result["created_at"]
            now = datetime.now()
            
            # Check expiration
            if (now - created_at).total_seconds() > config.code_expiry_minutes * 60:
                return jsonify({"message": "Verification code expired"}), 410
            
            # Constant-time comparison
            if int(user_code) == db_code:
                await delete_code()
                return None
            else:
                log_warning(action="verification_failed", trace_info=phone, message="Code mismatch")
                return jsonify({"message": "Verification code mismatch"}), 400
    
    except Exception as e:
        log_critical(action="verification_error", trace_info=phone, trace_info_hash="N/A", trace_info_encrypted="N/A", message=str(e))
        return jsonify({"message": f"Error: {str(e)}"}), 500

async def delete_code() -> None:
    """Delete expired verification codes"""
    conn = await get_db_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
                DELETE FROM global.verifications
                WHERE created_at < NOW() - INTERVAL 1 DAY
            """)
        await conn.commit()
    except Exception as e:
        log_critical(action="failed_to_delete_verifications", trace_info="Null", trace_info_hash="N/A", trace_info_encrypted="N/A", message=f"Database Error {str(e)}")

# ─── Validation Functions ────────────────────────────────────────────────────

def format_phone_number(phone: str) -> Tuple[Optional[str], str]:
    """Format and validate phone number to international E.164 format"""
    if is_test_mode():
        phone = os.getenv("DUMMY_PHONE")

    if not phone:
        return None, "Phone number is required"
    phone = phone.strip().replace(" ", "").replace("-", "")

    # Normalize BD formats
    if phone.startswith("8801") and len(phone) == 13:
        phone = "+" + phone
    elif phone.startswith("01") and len(phone) == 11:
        phone = "+88" + phone
    elif not phone.startswith("+"):
        return None, "Phone number must start with + or be a valid local format"

    try:
        number = phonenumbers.parse(phone, None)
        if not phonenumbers.is_valid_number(number):
            return None, "Invalid phone number"

        number_type = phonenumbers.number_type(number)
        if number_type not in [phonenumbers.PhoneNumberType.MOBILE, phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE]:
            return None, "Phone number must be a mobile or landline number"
        formatted = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
        return formatted, ""

    except NumberParseException:
        return None, "Invalid phone number format"

def validate_password(pwd: str) -> Tuple[bool, str]:
    """Enhanced password validation with security requirements"""
    if is_test_mode():
        return True, ""
    
    schema = PasswordValidator()
    schema.min(8).has().uppercase().has().lowercase().has().digits().has().no().spaces()
    
    if not schema.validate(pwd):
        return False, "Password must be at least 8 characters with uppercase, lowercase, digit, and no spaces"
    
    return True, ""

def validate_fullname(fullname: str) -> Tuple[bool, str]:
    """Enhanced fullname validation with comprehensive checks"""
    # Allow letters, spaces, apostrophes, and hyphens
    _FULLNAME_RE = re.compile(
        r"^(?!.*[\d])"                     # no digits
        r"(?!.*[!@#$%^&*()_+=-])"           # no forbidden special chars
        r"([A-Z][a-z']+)"               # first word (allow ' and -)
        r"(?: [A-Z][a-z']+)*$"          # additional words
    )
    fullname = fullname.strip()
    if re.search(r'\d', fullname):
        return False, "Fullname shouldn't contain digits"
    if re.search(r'[!@#$%^&*()_+=-]', fullname):
        return False, "Fullname shouldn't contain special characters"
    if not _FULLNAME_RE.match(fullname):
        return False, "Fullname must be words starting with uppercase, followed by lowercase letters, apostrophes, or hyphens"
    return True, ""

# ─── Database Functions ──────────────────────────────────────────────────────

@asynccontextmanager
async def get_db_context():
    """Database connection context manager"""
    conn = await get_db_connection()
    try:
        yield conn
    finally:
        conn.close()

async def get_email(fullname: str, phone: str) -> Optional[str]:
    """Get user email with caching"""
    cache_key = f"email:{fullname}:{phone}"
    cached_email = cache.get(cache_key)
    if cached_email:
        return cached_email
    
    if is_test_mode():
        return os.getenv("DUMMY_EMAIL", "")
    
    async with get_db_context() as conn:
        try:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(
                    "SELECT email FROM global.users WHERE fullname = %s AND phone = %s",
                    (fullname, phone)
                )
                result = await cursor.fetchone()
                
                email = result['email'] if result else None
                if email:
                    cache.set(cache_key, email, ttl=3600)  # Cache for 1 hour
                return email
        except Exception as e:
            log_critical(action="db_error with get_email", trace_info=email,trace_info_hash=hash_sensitive_data(email),trace_info_encrypted=encrypt_sensitive_data(email), message=str(e))
            return None

async def get_id(phone: str, fullname: str) -> Optional[int]:
    """Get user ID with caching"""
    cache_key = f"user_id:{phone}:{fullname}"
    cached_id = cache.get(cache_key)
    if cached_id:
        return cached_id
    
    if is_test_mode():
        fullname = os.getenv("DUMMY_FULLNAME")
        phone = os.getenv("DUMMY_PHONE")
    
    async with get_db_context() as conn:
        try:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(
                    "SELECT user_id FROM global.users WHERE phone = %s AND fullname = %s",
                    (phone, fullname)
                )
                result = await cursor.fetchone()
                
                user_id = result['user_id'] if result else None
                if user_id:
                    cache.set(cache_key, user_id, ttl=3600)  # Cache for 1 hour
                return user_id
        except Exception as e:
            log_critical(action="get_id_error", trace_info=phone,trace_info_hash=hash_sensitive_data(phone),trace_info_encrypted=encrypt_sensitive_data(phone), message=str(e))
            return None

async def upsert_translation(conn, translation_text: str, bn_text: str = None, ar_text: str = None, context: str = None) -> str:
    """
    Insert or update a translation entry in the global.translations table
    Returns the translation_text that should be used as foreign key reference
    """
    if not translation_text or not translation_text.strip():
        return None
        
    translation_text = translation_text.strip()
    
    async with conn.cursor(aiomysql.DictCursor) as cursor:
        # Upsert translation entry
        sql = """
            INSERT INTO global.translations (translation_text, bn_text, ar_text, context)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                bn_text = COALESCE(VALUES(bn_text), bn_text),
                ar_text = COALESCE(VALUES(ar_text), ar_text),
                context = COALESCE(VALUES(context), context)
        """
        await cursor.execute(sql, (translation_text, bn_text, ar_text, context))
        return translation_text

async def process_multilingual_field(conn, field_base: str, data: dict) -> str:
    """
    Process multilingual field data and insert into translations table
    Returns the translation_text to use as foreign key reference
    """
    translation_text = data.get(f"{field_base}_en")
    bn_text = data.get(f"{field_base}_bn") 
    ar_text = data.get(f"{field_base}_ar")
    
    # Use English text as the primary translation_text key
    if not translation_text:
        return None
        
    translation_text = translation_text.strip()
    return await upsert_translation(conn, translation_text, bn_text, ar_text)

async def insert_person(madrasa_name: str, fields: Dict[str, Any], acc_type: str, phone: str) -> None:
    """Enhanced person insertion with translation handling and error handling"""
    if is_test_mode():
        return None

    fields = {k: v.strip() if isinstance(v, str) else v for k, v in fields.items()}
    
    async with get_db_context() as conn:
        try:
            # Handle translations first for foreign key fields
            translation_fields = {}
            
            # Process name translations
            if any(k.startswith('name_') for k in fields.keys()):
                name_translation = await process_multilingual_field(conn, 'name', fields)
                if name_translation:
                    translation_fields['name'] = name_translation
                    # Remove individual language fields
                    fields = {k: v for k, v in fields.items() if not k.startswith('name_')}
            
            # Process father name translations  
            if any(k.startswith('father_') for k in fields.keys()):
                father_translation = await process_multilingual_field(conn, 'father', fields)
                if father_translation:
                    translation_fields['father_name'] = father_translation
                    # Remove individual language fields
                    fields = {k: v for k, v in fields.items() if not k.startswith('father_')}
            
            # Process mother name translations
            if any(k.startswith('mother_') for k in fields.keys()):
                mother_translation = await process_multilingual_field(conn, 'mother', fields)
                if mother_translation:
                    translation_fields['mother_name'] = mother_translation
                    # Remove individual language fields
                    fields = {k: v for k, v in fields.items() if not k.startswith('mother_')}
            
            # Handle address field - use present_address as the main address
            if 'present_address' in fields and fields['present_address']:
                address_text = fields['present_address'].strip().lower()
                address_translation = await upsert_translation(conn, address_text, fields['present_address'])
                if address_translation:
                    translation_fields['address'] = address_translation

            # Handle address field - use present_address as the main address
            if 'permanent_address' in fields and fields['permanent_address']:
                address_text = fields['permanent_address'].strip().lower()
                address_translation = await upsert_translation(conn, address_text, fields['present_address'])
                if address_translation:
                    translation_fields['address'] = address_translation

            # Handle address field - use present_address as the main address
            if 'address' in fields and fields['address']:
                address_text = fields['address'].strip().lower()
                address_translation = await upsert_translation(conn, address_text, fields['address'])
                if address_translation:
                    translation_fields['address'] = address_translation
            
            # Merge translation fields with other fields
            fields.update(translation_fields)
            
            # Separate acc_type fields from peoples fields
            acc_type_fields = {}
            peoples_fields = {}
            
            for key, value in fields.items():
                if key in ['teacher', 'student', 'staff', 'donor', 'badri_member', 'special_member']:
                    acc_type_fields[key] = value
                else:
                    peoples_fields[key] = value
            
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                # Insert into acc_types table FIRST if user_id exists
                if 'user_id' in peoples_fields and peoples_fields['user_id']:
                    user_id = peoples_fields['user_id']
                    
                    # Use boolean values from route (they already have correct defaults)
                    acc_type_data = {
                        'user_id': user_id,
                        'main_type': acc_type,
                        'teacher': int(acc_type_fields.get('teacher', False)),
                        'student': int(acc_type_fields.get('student', False)),
                        'staff': int(acc_type_fields.get('staff', False)),
                        'donor': int(acc_type_fields.get('donor', False)),
                        'badri_member': int(acc_type_fields.get('badri_member', False)),
                        'special_member': int(acc_type_fields.get('special_member', False))
                    }
                    
                    acc_columns = ', '.join(acc_type_data.keys())
                    acc_placeholders = ', '.join(['%s'] * len(acc_type_data))
                    acc_updates = ', '.join([f"{col} = VALUES({col})" for col in acc_type_data.keys() if col != 'user_id'])
                    
                    # UPSERT for acc_types
                    acc_sql = f"""
                        INSERT INTO global.acc_types ({acc_columns})
                        VALUES ({acc_placeholders})
                        ON DUPLICATE KEY UPDATE {acc_updates}
                    """
                    await cursor.execute(acc_sql, list(acc_type_data.values()))
                
                # Insert into peoples table AFTER acc_types
                columns = ', '.join(peoples_fields.keys())
                placeholders = ', '.join(['%s'] * len(peoples_fields))
                
                # Only update non-identity or safe fields
                updatable_fields = [
                    col for col in peoples_fields.keys() 
                    if col not in ('user_id', 'created_at', 'updated_at')
                ]
                updates = ', '.join([f"{col} = VALUES({col})" for col in updatable_fields])
                
                # UPSERT for peoples
                sql = f"""
                    INSERT IGNORE INTO {madrasa_name}.peoples ({columns}) 
                    VALUES ({placeholders}) AS new
                    ON DUPLICATE KEY UPDATE {updates}
                """
                await cursor.execute(sql, list(peoples_fields.values()))
                
            await conn.commit()
            log_info(action="insert_success", trace_info=phone, trace_info_hash=hash_sensitive_data(phone),trace_info_encrypted=encrypt_sensitive_data(phone), message="Upserted into peoples with translations")
        except Exception as e:
            await conn.rollback()
            log_critical(action="db_insert_error", trace_info=phone,trace_info_hash=hash_sensitive_data(phone),trace_info_encrypted=encrypt_sensitive_data(phone), message=str(e))
            raise

async def delete_users(madrasa_name: str, uid: int = None, acc_type: str = None) -> bool:
    """Enhanced user deletion with comprehensive cleanup"""
    async with get_db_context() as conn:
        try:
            if not uid and not acc_type:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(f"""
                        SELECT u.user_id, p.acc_type 
                        FROM global.users u
                        JOIN {madrasa_name}.peoples p ON u.user_id = p.user_id
                        WHERE u.scheduled_deletion_at IS NOT NULL
                        AND u.scheduled_deletion_at < NOW()
                    """)
                    users_to_delete = await cursor.fetchall()
            else:
                users_to_delete = [{'user_id': uid, 'acc_type': acc_type}]
            
            for user in users_to_delete:
                uid = user["user_id"]
                acc_type = user["acc_type"]
                
                if acc_type not in ['students', 'teachers', 'staffs', 'admins', 'badri_members']:
                    await cursor.execute(f"DELETE FROM {madrasa_name}.peoples WHERE user_id = %s", (uid,))
                else:
                    await cursor.execute(f"""
                        UPDATE {madrasa_name}.peoples SET 
                            date_of_birth = NULL,
                            birth_certificate = NULL,
                            national_id = NULL,
                            source = NULL,
                            present_address = NULL,
                            permanent_address = NULL,
                            father_or_spouse = NULL,
                            mother_en = NULL,
                            mother_bn = NULL,
                            mother_ar = NULL,
                            guardian_number = NULL,
                            available = NULL,
                            is_donor = NULL,
                            is_badri_member = NULL,
                            is_foundation_member = NULL
                        WHERE user_id = %s
                    """, (uid,))
                
                await cursor.execute(f"DELETE FROM global.transactions WHERE user_id = %s", (uid,))
                await cursor.execute(f"DELETE FROM global.verifications WHERE user_id = %s", (uid,))
                await cursor.execute(f"DELETE FROM global.users WHERE user_id = %s", (uid,))
            
            await conn.commit()
            return True
            
        except IntegrityError as e:
            log_critical(action="auto_delete_error", trace_info="Null", trace_info_hash="N/A", trace_info_encrypted="N/A", message=f"IntegrityError: {e}")
            return True
        except Exception as e:
            log_critical(action="auto_delete_error", trace_info="Null", trace_info_hash="N/A", trace_info_encrypted="N/A", message=str(e))
            return True

# ─── Business Logic Functions ────────────────────────────────────────────────

def calculate_fees(class_name: str, gender: str, special_food: int, 
                  reduced_fee: int, food: int) -> int:
    """Calculate fees with comprehensive pricing logic"""
    total = 0
    class_lower = class_name.lower()
    
    if is_test_mode():
        return 9999
    
    # Food charges
    if food == 1:
        total += 2400
    if special_food == 1:
        total += 3000
    
    # Base fees by gender and class
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
    
    # Apply fee reduction
    if reduced_fee:
        total -= reduced_fee
    
    return max(0, total)  # Ensure non-negative total

# ─── File Management Functions ───────────────────────────────────────────────

def load_results() -> List[Dict[str, Any]]:
    """Load exams results with error handling"""
    try:
        with open(config.exam_result_index_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_results(data: List[Dict[str, Any]]) -> None:
    """Save exam results with atomic write"""
    temp_file = config.exam_result_index_file + '.tmp'
    try:
        with open(temp_file, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(temp_file, config.exam_result_index_file)
    except Exception as e:
        log_critical(action="save_results_error", trace_info="file_ops", trace_info_hash="N/A", trace_info_encrypted="N/A", message=str(e))
        if os.path.exists(temp_file):
            os.remove(temp_file)

def allowed_exam_file(filename: str) -> bool:
    """Check if exam file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in config.allowed_exam_extensions

def load_notices() -> List[Dict[str, Any]]:
    """Load notices with auto-recovery from corrupted files"""
    try:
        with open(config.notices_index_file, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        # Auto-fix broken JSON
        with open(config.notices_index_file, 'w') as f:
            json.dump([], f)
        return []
    except FileNotFoundError:
        return []

def save_notices(data: List[Dict[str, Any]]) -> None:
    """Save notices with atomic write"""
    temp_file = config.notices_index_file + '.tmp'
    try:
        with open(temp_file, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(temp_file, config.notices_index_file)
    except Exception as e:
        log_critical(action="save_notices_error", trace_info="file_ops", trace_info_hash="N/A", trace_info_encrypted="N/A", message=str(e))
        if os.path.exists(temp_file):
            os.remove(temp_file)

def allowed_notice_file(filename: str) -> bool:
    """Check if notice file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in config.allowed_notice_extensions

# ─── Utility Decorators ─────────────────────────────────────────────────────

def rate_limit(max_requests: int = None, window: int = None):
    """Decorator for rate limiting endpoints"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get client identifier (IP address)
            client_ip = request.remote_addr
            identifier = f"{client_ip}:{func.__name__}"
            
            if not await check_rate_limit(identifier, max_requests, window):
                return jsonify({"error": "Rate limit exceeded"}), 429
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def require_api_key(func):
    """Decorator to require valid API key"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if not is_valid_api_key(api_key):
            return jsonify({"error": "Invalid or missing API key"}), 401
        return await func(*args, **kwargs)
    return wrapper

# ─── Health Check Functions ─────────────────────────────────────────────────

async def check_database_health() -> Dict[str, Any]:
    """Check database connectivity and health"""
    try:
        async with get_db_context() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT 1")
                return {"status": "healthy", "message": "Database connection successful"}
    except Exception as e:
        return {"status": "unhealthy", "message": f"Database error: {str(e)}"}

async def check_file_system_health() -> Dict[str, Any]:
    """Check file system health and permissions"""
    try:
        # Check if directories exist and are writable
        for directory in [config.exam_dir, config.notices_dir]: # TODO: Add more directories to check
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
            
            test_file = os.path.join(directory, '.health_check')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
        
        return {"status": "healthy", "message": "File system accessible"}
    except Exception as e:
        return {"status": "unhealthy", "message": f"File system error: {str(e)}"}

async def get_system_health() -> Dict[str, Any]:
    """Get comprehensive system health status"""
    db_health = await check_database_health()
    fs_health = await check_file_system_health()

    status = "healthy"
    if db_health["status"] == "unhealthy" and fs_health["status"] == "unhealthy":
        status = "critical"
    elif db_health["status"] == "unhealthy" or fs_health["status"] == "unhealthy":
        status = "unhealthy"
    
    return {
        "status": status,
        "version": Config.SERVER_VERSION,
        "timestamp": datetime.now().isoformat(),
        "database": db_health,
        "file_system": fs_health,
        "maintenance_mode": is_maintenance_mode(),
        "test_mode": is_test_mode(),
        "cache_size": len(cache._cache),
        "rate_limiter_size": len(rate_limiter._requests)
    }

# ─── Advanced Security Functions ────────────────────────────────────────────

class SecurityManager:
    """Advanced security management with threat detection"""
    
    def __init__(self):
        self.suspicious_patterns = [
            r"(?i)(union(\s+all)?\s+select|select\s+.*from|insert\s+into|update\s+.*set|delete\s+from|drop\s+table|create\s+table|alter\s+table|--|#|;|\bor\b|\band\b|\bexec\b|\bsp_\b|\bxp_\b)",
            r'<script[^>]*>.*?</script>',
            r'javascript:',
            r'on\w+\s*=',
            r'<iframe[^>]*>',
            r'<object[^>]*>',
            r'<embed[^>]*>'
        ]
        self.blocked_ips = set()
        self.suspicious_activities = {}
    
    def detect_sql_injection(self, input_str: str) -> bool:
        """Detect potential SQL injection attempts"""
        if not input_str:
            return False
        
        input_lower = input_str.lower()
        for pattern in self.suspicious_patterns:
            if re.search(pattern, input_lower, re.IGNORECASE):
                return True
        return False
    
    def detect_xss(self, input_str: str) -> bool:
        """Detect potential XSS attempts"""
        if not input_str:
            return False
        
        xss_patterns = [
            r'<script[^>]*>',
            r'javascript:',
            r'on\w+\s*=',
            r'<iframe[^>]*>',
            r'<object[^>]*>',
            r'<embed[^>]*>'
        ]
        
        for pattern in xss_patterns:
            if re.search(pattern, input_str, re.IGNORECASE):
                return True
        return False
    
    def sanitize_input(self, input_str: str) -> str:
        """Sanitize user input"""
        if not input_str:
            return ""
        
        # Remove potentially dangerous characters
        sanitized = re.sub(r'[<>"\']', '', input_str)
        return sanitized.strip()
    
    def track_suspicious_activity(self, ip_address: str, activity: str) -> None:
        """Track suspicious activities for threat analysis"""
        if ip_address not in self.suspicious_activities:
            self.suspicious_activities[ip_address] = []
        
        self.suspicious_activities[ip_address].append({
            'activity': activity,
            'timestamp': datetime.now().isoformat()
        })
        
        # If too many suspicious activities, block IP
        if len(self.suspicious_activities[ip_address]) > 10:
            self.blocked_ips.add(ip_address)
            log_critical(action="ip_blocked", trace_info=ip_address, trace_info_hash=hash_sensitive_data(ip_address), trace_info_encrypted=encrypt_sensitive_data(ip_address), message=f"Too many suspicious activities: {activity}")

# Global security manager
security_manager = SecurityManager()

# ─── Performance Monitoring ─────────────────────────────────────────────────

class PerformanceMonitor:
    """Monitor application performance and resource usage"""
    
    def __init__(self):
        self.request_times = []
        self.error_counts = {}
        self.start_time = time.time()
    
    def record_request_time(self, endpoint: str, duration: float) -> None:
        """Record request processing time"""
        self.request_times.append({
            'endpoint': endpoint,
            'duration': duration,
            'timestamp': datetime.now().isoformat()
        })
        
        # Keep only last 1000 requests
        if len(self.request_times) > 1000:
            self.request_times = self.request_times[-1000:]
    
    def record_error(self, error_type: str, details: str) -> None:
        """Record error occurrence"""
        if error_type not in self.error_counts:
            self.error_counts[error_type] = 0
        self.error_counts[error_type] += 1
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        if not self.request_times:
            return {"message": "No performance data available"}
        
        durations = [req['duration'] for req in self.request_times]
        return {
            "total_requests": len(self.request_times),
            "average_response_time": sum(durations) / len(durations),
            "min_response_time": min(durations),
            "max_response_time": max(durations),
            "uptime_seconds": time.time() - self.start_time,
            "error_counts": self.error_counts
        }

# Global performance monitor
performance_monitor = PerformanceMonitor()

# ─── Advanced Validation Functions ──────────────────────────────────────────

def validate_email(email: str) -> Tuple[bool, str]:
    """Validate email format with comprehensive checks"""
    if not email:
        return False, "Email is required"
    
    # Basic email pattern
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return False, "Invalid email format"
    # Disallow consecutive dots and leading/trailing dots in local or domain part
    local, _, domain = email.partition('@')
    if '..' in local or '..' in domain:
        return False, "Email cannot contain consecutive dots"
    if local.startswith('.') or local.endswith('.') or domain.startswith('.') or domain.endswith('.'):
        return False, "Email cannot start or end with a dot"
    # Check for suspicious patterns
    if security_manager.detect_xss(email):
        return False, "Email contains suspicious content"
    
    return True, ""

async def validate_file_upload(filename: str, allowed_extensions: List[str], file_size: int) -> Tuple[bool, str]:
    """Validate uploaded file with extension, name, and size checks"""
    if not filename:
        return False, "No file selected"
    
    # Check file extension
    if '.' not in filename:
        return False, "Invalid file format"
    
    extension = filename.rsplit('.', 1)[1].lower()
    if extension not in allowed_extensions:
        return False, f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}"
    
    # Suspicious filename patterns
    suspicious_patterns = [
        r'\.\./', r'\.\.\\', r'[<>:"|?*]',
        r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)',
    ]
    for pattern in suspicious_patterns:
        if re.search(pattern, filename, re.IGNORECASE):
            return False, "Invalid filename"

    if file_size > Config.MAX_CONTENT_LENGTH:
        return False, f"File size exceeds {Config.MAX_CONTENT_LENGTH / 1024 / 1024} MB"
    
    return True, ""

# ─── Advanced Caching Functions ────────────────────────────────────────────

def cache_with_invalidation(func: Callable) -> Callable:
    """Decorator for function result caching with automatic invalidation"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Create cache key from function name and arguments
        cache_key = f"{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
        
        # Try to get from cache
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result
        
        # Execute function and cache result
        result = await func(*args, **kwargs)
        cache.set(cache_key, result, ttl=3600)  # Cache for 1 hour
        return result
    
    return wrapper

def invalidate_cache_pattern(pattern: str) -> None:
    """Invalidate cache entries matching a pattern"""
    keys_to_remove = [key for key in cache._cache.keys() if pattern in key]
    for key in keys_to_remove:
        cache.delete(key)

# ─── Advanced Error Handling ───────────────────────────────────────────────

class AppError(Exception): # TODO: Implement this
    """Base application error class"""
    def __init__(self, message: str, error_code: str = None, details: Dict[str, Any] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}

class ValidationError(AppError):
    """Validation error"""
    pass

class SecurityError(AppError):
    """Security-related error"""
    pass

class DatabaseError(AppError):
    """Database-related error"""
    pass


def handle_async_errors(func: Callable) -> Callable:
    """Decorator for comprehensive async error handling"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except AppError as e:
            log_critical(action="app_error", trace_info="error_handler", trace_info_hash="N/A", trace_info_encrypted="N/A", message=f"{e.error_code}: {e.message}")
            return jsonify({
                "error": e.message,
                "error_code": e.error_code,
                "details": e.details
            }), 400
        except Exception as e:
            log_critical(action="unexpected_error", trace_info="error_handler", trace_info_hash="N/A", trace_info_encrypted="N/A", message=str(e))
            performance_monitor.record_error("unexpected", str(e))
            return jsonify({
                "error": "An unexpected error occurred",
                "error_code": "INTERNAL_ERROR"
            }), 500
    
    return wrapper

# ─── Metrics and Analytics ─────────────────────────────────────────────────

class MetricsCollector: # TODO: Implement this
    """Collect and analyze application metrics"""
    
    def __init__(self):
        self.metrics = {
            'requests': 0,
            'errors': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'database_queries': 0,
            'slow_queries': 0
        }
        self.start_time = time.time()
    
    def increment(self, metric: str, value: int = 1) -> None:
        """Increment a metric counter"""
        if metric in self.metrics:
            self.metrics[metric] += value
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics"""
        uptime = time.time() - self.start_time
        return {
            **self.metrics,
            'uptime_seconds': uptime,
            'requests_per_second': self.metrics['requests'] / uptime if uptime > 0 else 0,
            'error_rate': self.metrics['errors'] / self.metrics['requests'] if self.metrics['requests'] > 0 else 0,
            'cache_hit_rate': self.metrics['cache_hits'] / (self.metrics['cache_hits'] + self.metrics['cache_misses']) if (self.metrics['cache_hits'] + self.metrics['cache_misses']) > 0 else 0
        }

# Global metrics collector
metrics_collector = MetricsCollector()

# ─── Utility Functions ─────────────────────────────────────────────────────
def hash_sensitive_data(data: str) -> str:
    """Hash sensitive data for logging"""
    return hashlib.sha256(data.encode()).hexdigest()[:8]

def get_encryption_key() -> bytes:
    """Get the encryption key from config"""
    key = Config.ENCRYPTION_KEY
    if isinstance(key, str):
        return key.encode()
    return key

def encrypt_sensitive_data(data: str) -> str:
    """Encrypt sensitive data using Fernet encryption"""
    if not data:
        return data
    
    try:
        fernet = Fernet(get_encryption_key())
        encrypted_data = fernet.encrypt(data.encode())
        return base64.urlsafe_b64encode(encrypted_data).decode()
    except Exception as e:
        log_critical(action="encryption_error", trace_info="system", trace_info_hash="N/A", trace_info_encrypted="N/A", message=f"Failed to encrypt data: {str(e)}")
        # In case of encryption failure, return original data (not recommended for production)
        return data

def decrypt_sensitive_data(encrypted_data: str) -> str:
    """Decrypt sensitive data using Fernet encryption"""
    if not encrypted_data:
        return encrypted_data
    
    try:
        fernet = Fernet(get_encryption_key())
        decoded_data = base64.urlsafe_b64decode(encrypted_data.encode())
        decrypted_data = fernet.decrypt(decoded_data)
        return decrypted_data.decode()
    except Exception as e:
        log_critical(action="decryption_error", trace_info="system", trace_info_hash="N/A", trace_info_encrypted="N/A", message=f"Failed to decrypt data: {str(e)}")
        # In case of decryption failure, return original data (might be unencrypted legacy data)
        return encrypted_data

def encrypt_if_needed(data: str, should_encrypt: bool = True) -> str:
    """Conditionally encrypt data based on should_encrypt flag"""
    if should_encrypt and data:
        return encrypt_sensitive_data(data)
    return data

def decrypt_if_needed(data: str, is_encrypted: bool = True) -> str:
    """Conditionally decrypt data based on is_encrypted flag"""
    if is_encrypted and data:
        return decrypt_sensitive_data(data)
    return data

def get_client_info() -> Dict[str, Any]:
    """Get client IP address and device metadata with fallback and proxy support."""
    forwarded_for = request.headers.get('X-Forwarded-For')
    real_ip = request.headers.get('X-Real-IP')

    if real_ip:
        ip_address = real_ip
    elif forwarded_for:
        ip_address = forwarded_for.split(',')[0].strip()
    else:
        ip_address = request.remote_addr

    return {
        "ip_address": ip_address,
        "device_id": request.headers.get('X-Device-ID'),
        "device_brand": request.headers.get('X-Device-Brand'),
        "device_model": request.headers.get('X-Device-Model'),
        "device_os": request.headers.get('X-Device-OS'),
    }

# ─── Configuration Validation ───────────────────────────────────────────────

def validate_app_config() -> List[str]:
    """Validate application configuration and return any issues"""
    issues = []
    
    # Check required environment variables
    required_vars = [
        'EMAIL_ADDRESS', 'EMAIL_PASSWORD', 'TEXTBELT_KEY', 'MYSQL_HOST', 'MYSQL_USER', 'MYSQL_PASSWORD', 'MYSQL_DB'
    ]
    
    for var in required_vars:
        if not os.getenv(var):
            issues.append(f"Missing required environment variable: {var}")
    
    # Check directory permissions
    for directory in [config.exam_dir, config.notices_dir]:
        if not os.path.exists(directory):
            try:
                os.makedirs(directory, exist_ok=True)
            except Exception as e:
                issues.append(f"Cannot create directory {directory}: {e}")
        elif not os.access(directory, os.W_OK):
            issues.append(f"No write permission for directory: {directory}")
    
    return issues

# ─── Application Initialization ────────────────────────────────────────────

def initialize_application() -> bool:
    """Initialize application with all necessary components"""
    try:
        # Validate configuration
        config_issues = validate_app_config()
        if config_issues:
            for issue in config_issues:
                log_critical(action="config_error", trace_info="init", trace_info_hash="N/A", trace_info_encrypted="N/A", message=issue)
            return False
        
        # Initialize cache
        cache.clear()
        
        # Initialize rate limiter
        rate_limiter._requests.clear()
        
        # Log successful initialization  
        log_info(action="app_initialized", trace_info="init", trace_info_hash="N/A", trace_info_encrypted="N/A", message="Application initialized successfully")
        return True
        
    except Exception as e:
        log_critical(action="init_error", trace_info="init", trace_info_hash="N/A", trace_info_encrypted="N/A", message=str(e))
        return False


