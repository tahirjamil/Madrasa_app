"""
Environment Variable Validator
=============================

Validates all required environment variables at application startup
to prevent runtime errors and security issues.
"""

import os
import sys
from typing import Dict, List, Tuple, Optional
from pathlib import Path


class EnvValidator:
    """Validates environment variables and configuration"""
    
    # Required environment variables with their descriptions
    REQUIRED_VARS = {
        # Database
        'MYSQL_HOST': 'MySQL database host',
        'MYSQL_USER': 'MySQL database user',
        'MYSQL_PASSWORD': 'MySQL database password',
        'MYSQL_DB': 'MySQL database name',
        
        # KeyDB/Redis
        'KEYDB_HOST': 'KeyDB/Redis host',
        'KEYDB_PORT': 'KeyDB/Redis port',
        'KEYDB_PASSWORD': 'KeyDB/Redis password',
        
        # Admin credentials
        'ADMIN_USERNAME': 'Admin panel username',
        'ADMIN_PASSWORD': 'Admin panel password',
        
        # Application
        'MADRASA_NAME': 'Madrasa name for database schema',
        'SECRET_KEY': 'Flask/Quart secret key for sessions',
        
        # Email configuration
        'EMAIL_ADDRESS': 'Email address for sending emails',
        'EMAIL_PASSWORD': 'Email password',
        
        # SMS configuration
        'TEXTBELT_KEY': 'Textbelt API key for SMS',
    }
    
    # Optional but recommended variables
    OPTIONAL_VARS = {
        'OPENTELEMETRY_ENDPOINT': 'OpenTelemetry collector endpoint',
        'BUSINESS_EMAIL': 'Business email address',
        'BUSINESS_PHONE': 'Business phone number',
        'APP_NAME': 'Application name',
        'APP_VERSION': 'Application version',
        'MAX_CONTENT_LENGTH': 'Maximum file upload size',
        'REDIS_EXPIRATION': 'Redis cache expiration time',
    }
    
    # Variables that should not be empty
    NON_EMPTY_VARS = [
        'MYSQL_PASSWORD', 'KEYDB_PASSWORD', 'ADMIN_PASSWORD', 
        'SECRET_KEY', 'EMAIL_PASSWORD'
    ]
    
    @classmethod
    def validate(cls) -> Tuple[bool, List[str]]:
        """
        Validate all required environment variables
        
        Returns:
            Tuple of (success: bool, errors: List[str])
        """
        errors = []
        
        # Check required variables
        for var, description in cls.REQUIRED_VARS.items():
            value = os.getenv(var)
            if value is None:
                errors.append(f"Missing required env var: {var} ({description})")
            elif var in cls.NON_EMPTY_VARS and not value.strip():
                errors.append(f"Empty value for required env var: {var}")
        
        # Validate specific formats
        errors.extend(cls._validate_formats())
        
        # Check file permissions
        errors.extend(cls._validate_file_permissions())
        
        # Validate database schema name
        madrasa_name = os.getenv('MADRASA_NAME')
        if madrasa_name and not cls._is_valid_identifier(madrasa_name):
            errors.append(f"Invalid MADRASA_NAME '{madrasa_name}': must be a valid SQL identifier")
        
        return len(errors) == 0, errors
    
    @classmethod
    def _validate_formats(cls) -> List[str]:
        """Validate specific environment variable formats"""
        errors = []
        
        # Validate port numbers
        keydb_port = os.getenv('KEYDB_PORT')
        if keydb_port:
            try:
                port = int(keydb_port)
                if not 1 <= port <= 65535:
                    errors.append(f"Invalid KEYDB_PORT {keydb_port}: must be between 1-65535")
            except ValueError:
                errors.append(f"Invalid KEYDB_PORT {keydb_port}: must be a number")
        
        # Validate email format
        email = os.getenv('EMAIL_ADDRESS')
        if email and '@' not in email:
            errors.append(f"Invalid EMAIL_ADDRESS format: {email}")
        
        # Validate secret key strength
        secret_key = os.getenv('SECRET_KEY')
        if secret_key and len(secret_key) < 32:
            errors.append("SECRET_KEY should be at least 32 characters for security")
        
        return errors
    
    @classmethod
    def _validate_file_permissions(cls) -> List[str]:
        """Check required directories exist and are writable"""
        errors = []
        required_dirs = ['uploads', 'logs', 'temp']
        
        for dir_name in required_dirs:
            dir_path = Path(dir_name)
            if not dir_path.exists():
                try:
                    dir_path.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    errors.append(f"Cannot create directory {dir_name}: {e}")
            elif not os.access(dir_path, os.W_OK):
                errors.append(f"Directory {dir_name} is not writable")
        
        return errors
    
    @staticmethod
    def _is_valid_identifier(name: str) -> bool:
        """Check if name is a valid SQL identifier"""
        import re
        # Allow alphanumeric and underscore, must start with letter or underscore
        return bool(re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name))
    
    @classmethod
    def print_report(cls, errors: List[str]) -> None:
        """Print validation report"""
        if errors:
            print("❌ Environment validation failed:")
            print("-" * 50)
            for error in errors:
                print(f"  • {error}")
            print("-" * 50)
            print(f"Total errors: {len(errors)}")
        else:
            print("✅ Environment validation passed")
    
    @classmethod
    def get_safe_config(cls) -> Dict[str, Optional[str]]:
        """Get configuration with safe defaults for optional variables"""
        config = {}
        
        # Add all required variables
        for var in cls.REQUIRED_VARS:
            config[var] = os.getenv(var)
        
        # Add optional variables with defaults
        config['OPENTELEMETRY_ENDPOINT'] = os.getenv('OPENTELEMETRY_ENDPOINT', 'http://localhost:4317')
        config['APP_NAME'] = os.getenv('APP_NAME', 'Madrasa App')
        config['APP_VERSION'] = os.getenv('APP_VERSION', '1.0.0')
        config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_CONTENT_LENGTH', '16777216'))  # 16MB default
        config['REDIS_EXPIRATION'] = int(os.getenv('REDIS_EXPIRATION', '3600'))  # 1 hour default
        
        return config


def validate_environment() -> bool:
    """
    Main validation function to be called at startup
    
    Returns:
        bool: True if validation passed, False otherwise
    """
    success, errors = EnvValidator.validate()
    EnvValidator.print_report(errors)
    
    if not success and not os.getenv('SKIP_ENV_VALIDATION'):
        print("\n⚠️  Set SKIP_ENV_VALIDATION=1 to bypass validation (not recommended)")
        return False
    
    return True


if __name__ == '__main__':
    # Run validation when script is executed directly
    if not validate_environment():
        sys.exit(1)
    else:
        print("\n✅ All environment variables are properly configured")