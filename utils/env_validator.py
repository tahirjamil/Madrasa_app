"""
Environment Variable Validator
=============================

Validates required environment variables at application startup.
This version is adapted to commonly-used names in your .env:
- supports REDIS_* or KEYDB_* naming
- accepts ADMIN_KEY as admin credential (instead of ADMIN_USERNAME/ADMIN_PASSWORD)
- accepts BUSINESS_EMAIL / MADRASA_EMAIL / DEV_EMAIL as an email sender
- accepts SMS_API_KEY in place of TEXTBELT_KEY
"""

import os
import sys
import re
from typing import Dict, List, Tuple, Optional
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class EnvValidator:
    """Validates environment variables and configuration (more flexible / tolerant)"""

    # Core required variables (must exist in some form)
    CORE_REQUIRED = {
        'MYSQL_HOST': 'MySQL database host',
        'MYSQL_USER': 'MySQL database user',
        'MYSQL_PASSWORD': 'MySQL database password',
        'MYSQL_DB': 'MySQL database name',
        'MADRASA_NAME': 'Madrasa name for DB/schema',
        'SECRET_KEY': 'Flask/Quart secret key for sessions',
        'EMAIL_PASSWORD': 'Email account password used to send emails',
    }

    # Optional but recommended
    OPTIONAL_VARS = {
        'BUSINESS_EMAIL': 'Business email address',
        'MADRASA_EMAIL': 'Madrasa contact email',
        'DEV_EMAIL': 'Developer contact email',
        'RECAPTCHA_SITE_KEY': 'reCAPTCHA site key',
        'RECAPTCHA_SECRET_KEY': 'reCAPTCHA secret key',
        'SSLCOMMERZ_STORE_ID': 'SSLCOMMERZ store id',
    }

    # Variables that must not be empty if present / required
    NON_EMPTY = {'MYSQL_PASSWORD', 'SECRET_KEY', 'EMAIL_PASSWORD'}

    @classmethod
    def validate(cls) -> Tuple[bool, List[str]]:
        errors: List[str] = []

        # 1) Check core required variables exist (basic presence)
        for var, desc in cls.CORE_REQUIRED.items():
            val = os.getenv(var)
            if val is None:
                errors.append(f"Missing required env var: {var} ({desc})")
            elif var in cls.NON_EMPTY and not val.strip():
                errors.append(f"Empty value for required env var: {var}")

        # 2) Validate admin credentials presence: accept ADMIN_KEY OR ADMIN_USERNAME+ADMIN_PASSWORD
        admin_key = os.getenv('ADMIN_KEY')
        admin_user = os.getenv('ADMIN_USERNAME')
        admin_pass = os.getenv('ADMIN_PASSWORD')

        if not admin_key:
            if not (admin_user and admin_pass):
                errors.append(
                    "Admin credentials missing: set ADMIN_KEY or ADMIN_USERNAME and ADMIN_PASSWORD."
                )
            else:
                if not admin_user.strip() or not admin_pass.strip():
                    errors.append("ADMIN_USERNAME and ADMIN_PASSWORD must not be empty")

        # 3) Validate that at least one sender email address exists
        email_candidates = {
            'EMAIL_ADDRESS': os.getenv('EMAIL_ADDRESS'),
            'BUSINESS_EMAIL': os.getenv('BUSINESS_EMAIL'),
            'MADRASA_EMAIL': os.getenv('MADRASA_EMAIL'),
            'DEV_EMAIL': os.getenv('DEV_EMAIL'),
        }
        if not any(email_candidates.values()):
            errors.append(
                "No sender email configured: provide EMAIL_ADDRESS or BUSINESS_EMAIL or MADRASA_EMAIL or DEV_EMAIL"
            )
        else:
            # validate format for any provided email(s)
            for name, val in email_candidates.items():
                if val:
                    if not cls._looks_like_email(val):
                        errors.append(f"Invalid email format in {name}: {val}")

        # 4) Redis / KeyDB support: if USE_REDIS_CACHE true, require REDIS_HOST/PORT (or KEYDB_*)
        use_cache = os.getenv('USE_REDIS_CACHE', 'false').lower() in ('1', 'true', 'yes')
        if use_cache:
            # accept either REDIS_* or KEYDB_*
            redis_host = os.getenv('REDIS_HOST') or os.getenv('KEYDB_HOST')
            redis_port = os.getenv('REDIS_PORT') or os.getenv('KEYDB_PORT')
            redis_db = os.getenv('REDIS_DB')
            if not redis_host:
                errors.append("USE_REDIS_CACHE enabled but REDIS_HOST / KEYDB_HOST is not set")
            if not redis_port:
                errors.append("USE_REDIS_CACHE enabled but REDIS_PORT / KEYDB_PORT is not set")
            else:
                try:
                    p = int(redis_port)
                    if not (1 <= p <= 65535):
                        errors.append(f"Invalid REDIS_PORT / KEYDB_PORT: {redis_port}")
                except ValueError:
                    errors.append(f"REDIS_PORT / KEYDB_PORT must be an integer: {redis_port}")
            if redis_db:
                try:
                    int(redis_db)
                except ValueError:
                    errors.append(f"REDIS_DB must be an integer: {redis_db}")

        # 5) SMS provider key: accept SMS_API_KEY or TEXTBELT_KEY
        if not (os.getenv('SMS_API_KEY') or os.getenv('TEXTBELT_KEY')):
            # If the app needs SMS at startup, consider this an error; otherwise keep as warning.
            # We'll treat as required because your .env contains SMS_API_KEY.
            errors.append("SMS API key missing: set SMS_API_KEY or TEXTBELT_KEY")

        # 6) Validate formats and lengths
        errors.extend(cls._validate_formats())

        # 7) Check file permissions / directories
        errors.extend(cls._validate_file_permissions())

        # 8) Validate madrasa name as SQL identifier
        madrasa_name = os.getenv('MADRASA_NAME')
        if madrasa_name and not cls._is_valid_identifier(madrasa_name):
            errors.append(f"Invalid MADRASA_NAME '{madrasa_name}': must be a valid SQL identifier (letters, digits, underscore; start with letter or underscore)")

        return (len(errors) == 0), errors

    @classmethod
    def _validate_formats(cls) -> List[str]:
        errors: List[str] = []

        # SECRET_KEY strength recommendation
        secret = os.getenv('SECRET_KEY') or ''
        if not secret.strip():
            errors.append("SECRET_KEY is empty; set a secure random value (required for sessions).")
        else:
            if len(secret) < 32:
                errors.append("SECRET_KEY should be at least 32 characters for production security")

        # EMAIL_PASSWORD presence checked earlier, check simple sanity
        email_pw = os.getenv('EMAIL_PASSWORD')
        if email_pw is None or not email_pw.strip():
            errors.append("EMAIL_PASSWORD not set or empty")

        # REDIS boolean flags (typo-proof)
        if os.getenv('REDIS_SLL'):
            val = os.getenv('REDIS_SLL').lower()
            if val not in ('true', 'false', '0', '1', 'yes', 'no'):
                errors.append("REDIS_SLL must be a boolean-like value (true/false)")

        # Validate numeric port for optional SSLCOMMERZ? not necessary here

        # Recaptcha keys (if one present, both must be present)
        site_key = os.getenv('RECAPTCHA_SITE_KEY')
        secret_key = os.getenv('RECAPTCHA_SECRET_KEY')
        if (site_key and not secret_key) or (secret_key and not site_key):
            errors.append("Both RECAPTCHA_SITE_KEY and RECAPTCHA_SECRET_KEY should be provided together")

        # Validate phone number basic format for DEV_PHONE / BUSINESS_PHONE if present
        for phone_var in ('DEV_PHONE', 'BUSINESS_PHONE', 'MADRASA_PHONE'):
            phone = os.getenv(phone_var)
            if phone and not re.match(r'^[\d\+\-\s\(\)]+$', phone):
                errors.append(f"{phone_var} looks invalid: {phone}")

        return errors

    @classmethod
    def _validate_file_permissions(cls) -> List[str]:
        """Create/check useful runtime directories (uploads, logs, temp)"""
        errors: List[str] = []
        required_dirs = ['uploads', 'logs', 'temp']

        for dir_name in required_dirs:
            dir_path = Path(dir_name)
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create directory {dir_name}: {e}")
                continue

            # now verify writability
            if not os.access(dir_path, os.W_OK):
                errors.append(f"Directory {dir_name} is not writable by the current user")

        return errors

    @staticmethod
    def _is_valid_identifier(name: str) -> bool:
        """Check SQL identifier rules: start with letter or underscore; contain letters, digits, underscore"""
        return bool(re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name))

    @staticmethod
    def _looks_like_email(value: str) -> bool:
        # simple regex for presence of @ and domain-like part (not exhaustive)
        return bool(re.match(r'^[^@]+@[^@]+\.[^@]+$', value))

    @classmethod
    def print_report(cls, errors: List[str]) -> None:
        """Print validation report"""
        if errors:
            print("❌ Environment validation failed:")
            print("-" * 60)
            for err in errors:
                print(f"  • {err}")
            print("-" * 60)
            print(f"Total errors: {len(errors)}")
            # Helpful hints
            print("\nHints:")
            print(" - Ensure SECRET_KEY is set to a secure random 32+ character string for production.")
            print(" - If you're intentionally skipping validation (not recommended), set SKIP_ENV_VALIDATION=1.")
        else:
            print("✅ Environment validation passed")

    @classmethod
    def get_safe_config(cls) -> Dict[str, Optional[str]]:
        """Return a config dict with defaults for optional values"""
        cfg: Dict[str, Optional[str]] = {}
        # include core keys
        for k in cls.CORE_REQUIRED:
            cfg[k] = os.getenv(k)

        # pick a sender email (first available)
        cfg['SENDER_EMAIL'] = (
            os.getenv('EMAIL_ADDRESS') or
            os.getenv('BUSINESS_EMAIL') or
            os.getenv('MADRASA_EMAIL') or
            os.getenv('DEV_EMAIL')
        )

        cfg['USE_REDIS_CACHE'] = os.getenv('USE_REDIS_CACHE', 'false')
        cfg['REDIS_HOST'] = os.getenv('REDIS_HOST') or os.getenv('KEYDB_HOST')
        cfg['REDIS_PORT'] = os.getenv('REDIS_PORT') or os.getenv('KEYDB_PORT') or '6379'
        cfg['REDIS_DB'] = os.getenv('REDIS_DB', '0')

        # reasonable defaults
        cfg['OPENTELEMETRY_ENDPOINT'] = os.getenv('OPENTELEMETRY_ENDPOINT', 'http://localhost:4317')
        cfg['APP_NAME'] = os.getenv('APP_NAME', 'Madrasa App')
        cfg['APP_VERSION'] = os.getenv('APP_VERSION', '1.0.0')
        cfg['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_CONTENT_LENGTH', '16777216'))  # 16MB
        cfg['REDIS_EXPIRATION'] = int(os.getenv('REDIS_EXPIRATION', '3600'))  # 1 hour

        return cfg


def validate_environment() -> bool:
    """
    Main validation function to be called at startup.

    Returns True on success, False on failure (unless SKIP_ENV_VALIDATION=1 is set).
    """
    success, errors = EnvValidator.validate()
    EnvValidator.print_report(errors)

    if not success and not os.getenv('SKIP_ENV_VALIDATION'):
        print("\n⚠️  Set SKIP_ENV_VALIDATION=1 to bypass validation (not recommended)")
        return False

    return True


if __name__ == '__main__':
    ok = validate_environment()
    if not ok:
        sys.exit(1)
    else:
        print("\n✅ All environment variables are properly configured")
