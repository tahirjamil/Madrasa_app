#!/usr/bin/env python3
"""CSRF Protection Module"""

import secrets, hashlib, time, logging

class CSRFProtect:
    """Enhanced CSRF protection with better security and logging"""
    
    def __init__(self):
        # Import config here to avoid circular import
        from config import config
        self.secret_key = config.WTF_CSRF_SECRET_KEY
        self.logger = logging.getLogger(__name__)
        
        # Validate secret key
        if not self.secret_key or len(self.secret_key) < 32:
            self.logger.error("CSRF secret key is missing or too short (minimum 32 characters)")
            raise ValueError("CSRF protection requires a secure secret key")
        
    def generate_csrf(self):
        """Generate a secure CSRF token with timestamp and signature"""
        try:
            token = secrets.token_urlsafe(32)
            timestamp = str(int(time.time()))
            data = f"{token}:{timestamp}"
            signature = hashlib.sha256(f"{data}:{self.secret_key}".encode()).hexdigest()
            return f"{data}:{signature}"
        except Exception as e:
            self.logger.error(f"CSRF token generation failed: {type(e).__name__}")
            return None
    
    def validate_csrf(self, token):
        """Validate a CSRF token with enhanced security checks"""
        try:
            if not token:
                self.logger.warning("CSRF validation failed: No token provided")
                return False
                
            parts = token.split(':')
            if len(parts) != 3:
                self.logger.warning("CSRF validation failed: Invalid token format")
                return False
                
            data, timestamp, signature = parts
            
            # Validate signature
            expected_signature = hashlib.sha256(f"{data}:{timestamp}:{self.secret_key}".encode()).hexdigest()
            if not secrets.compare_digest(signature, expected_signature):
                self.logger.warning("CSRF validation failed: Invalid signature")
                return False
                
            # Check token expiration (1 hour)
            current_time = int(time.time())
            token_time = int(timestamp)
            if current_time - token_time > 3600:
                self.logger.warning("CSRF validation failed: Token expired")
                return False
                
            # Additional security: check if token is too old (replay attack protection)
            if current_time - token_time < 0:
                self.logger.warning("CSRF validation failed: Token timestamp in future")
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"CSRF validation error: {type(e).__name__}")
            return False
    
    def refresh_token(self, old_token):
        """Refresh an existing token if it's about to expire"""
        try:
            if not self.validate_csrf(old_token):
                return self.generate_csrf()
                
            parts = old_token.split(':')
            if len(parts) != 3:
                return self.generate_csrf()
                
            data, timestamp, signature = parts
            token_time = int(timestamp)
            current_time = int(time.time())
            
            # Refresh if token is older than 30 minutes
            if current_time - token_time > 1800:
                return self.generate_csrf()
                
            return old_token
            
        except Exception as e:
            self.logger.error(f"CSRF token refresh failed: {type(e).__name__}")
            return self.generate_csrf()
    
    def get_token_info(self, token):
        """Get information about a CSRF token (for debugging)"""
        try:
            if not token:
                return {"valid": False, "reason": "No token provided"}
                
            parts = token.split(':')
            if len(parts) != 3:
                return {"valid": False, "reason": "Invalid token format"}
                
            data, timestamp, signature = parts
            current_time = int(time.time())
            token_time = int(timestamp)
            
            return {
                "valid": self.validate_csrf(token),
                "created_at": token_time,
                "age_seconds": current_time - token_time,
                "expires_in": 3600 - (current_time - token_time),
                "will_expire_soon": (current_time - token_time) > 1800
            }
            
        except Exception as e:
            return {"valid": False, "reason": "Token validation error"}

# Global CSRF instance (lazy initialization)
_csrf_instance = None

def _get_csrf():
    """Get or create CSRF instance"""
    global _csrf_instance
    if _csrf_instance is None:
        _csrf_instance = CSRFProtect()
    return _csrf_instance

# Convenience functions
def generate_csrf_token():
    """Generate a new CSRF token"""
    return _get_csrf().generate_csrf()

def validate_csrf_token(token):
    """Validate a CSRF token"""
    return _get_csrf().validate_csrf(token)

def refresh_csrf_token(token):
    """Refresh a CSRF token if needed"""
    return _get_csrf().refresh_token(token)

def get_csrf_token_info(token):
    """Get information about a CSRF token"""
    return _get_csrf().get_token_info(token) 