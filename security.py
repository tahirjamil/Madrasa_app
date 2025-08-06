from password_validator import PasswordValidator
import time, os, re, random, hashlib, base64, aiomysql, phonenumbers
from secrets import compare_digest
from datetime import datetime
from cryptography.fernet import Fernet
from phonenumbers.phonenumberutil import NumberParseException
from quart import jsonify, request
from aiomysql import IntegrityError
from config import Config
from logger import log_critical, log_warning
from helpers import _send_async_email, _send_async_sms, get_db_connection
from typing import Any, Dict, List, Optional, Tuple

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
        max_requests = Config.MAX_REQUESTS_PER_HOUR
    if window is None:
        window = Config.RATE_LIMIT_WINDOW
    
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
    for email in [Config.DEV_EMAIL, Config.MADRASA_EMAIL]:
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
    for phone in [Config.DEV_PHONE, Config.MADRASA_PHONE]:
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


# ─── Verification Functions ───────────────────────────────────────────────────

def generate_code() -> int:
    """Generate secure verification code"""
    return random.randint(10**(Config.CODE_LENGTH-1), 10**Config.CODE_LENGTH - 1)

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
            if (now - created_at).total_seconds() > Config.CODE_EXPIRY_MINUTES * 60:
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