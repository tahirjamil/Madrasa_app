"""
Security Tests
==============

Tests for security features including SQL injection prevention,
XSS protection, CSRF protection, and authentication.
"""

import os
import sys
import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSQLInjectionPrevention(unittest.TestCase):
    """Test SQL injection prevention measures"""
    
    def test_parameterized_queries(self):
        """Test that queries use parameterization"""
        # This is more of a code review test - checking patterns
        import re
        from pathlib import Path
        
        # Patterns that indicate potential SQL injection
        dangerous_patterns = [
            r'f["\']\s*SELECT.*{',  # f-string SQL
            r'\.format\(.*SELECT',   # format string SQL
            r'\+\s*["\']\s*SELECT',  # String concatenation SQL
            r'%\s*\(.*SELECT',       # Old-style formatting
        ]
        
        # Files to check
        files_to_check = [
            'routes/admin_routes/views.py',
            'routes/api/core.py',
            'routes/api/auth.py',
            'routes/api/payments.py',
            'database/database_utils.py',
            'utils/helpers.py'
        ]
        
        issues_found = []
        
        for file_path in files_to_check:
            full_path = Path(file_path)
            if full_path.exists():
                content = full_path.read_text()
                for pattern in dangerous_patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    if matches:
                        issues_found.append((file_path, pattern, len(matches)))
        
        # Report findings
        if issues_found:
            print("\nPotential SQL injection vulnerabilities found:")
            for file_path, pattern, count in issues_found:
                print(f"  - {file_path}: {count} matches for pattern {pattern}")
        
        # We've already fixed most issues, so this should pass
        self.assertEqual(len(issues_found), 0, "SQL injection vulnerabilities found")
    
    def test_admin_dashboard_sql_validation(self):
        """Test admin dashboard SQL validation"""
        from routes.admin_routes.views import _FORBIDDEN_RE
        
        # Test dangerous SQL patterns are blocked
        dangerous_queries = [
            "DROP TABLE users",
            "ALTER TABLE users ADD COLUMN hack",
            "TRUNCATE TABLE payments",
            "DELETE FROM users",
            "CREATE DATABASE hack",
            "GRANT ALL PRIVILEGES",
        ]
        
        for query in dangerous_queries:
            self.assertTrue(_FORBIDDEN_RE.search(query), f"Query should be blocked: {query}")
        
        # Test safe queries are allowed
        safe_queries = [
            "SELECT * FROM users WHERE id = 1",
            "UPDATE users SET name = 'test' WHERE id = 1",
            "INSERT INTO logs (message) VALUES ('test')",
        ]
        
        for query in safe_queries:
            self.assertFalse(_FORBIDDEN_RE.search(query), f"Query should be allowed: {query}")


class TestXSSProtection(unittest.TestCase):
    """Test XSS protection measures"""
    
    def test_xss_detection_patterns(self):
        """Test XSS detection in security manager"""
        # Import after adding to path
        from utils.helpers import security_manager
        
        # Test various XSS patterns
        xss_patterns = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
            "<iframe src='javascript:alert(1)'>",
            "javascript:alert('xss')",
            "<body onload=alert('xss')>",
            "<svg onload=alert('xss')>",
            "';alert('xss');//",
            '"><script>alert("xss")</script>',
        ]
        
        for pattern in xss_patterns:
            self.assertTrue(
                security_manager.detect_xss(pattern),
                f"XSS pattern should be detected: {pattern}"
            )
        
        # Test safe patterns
        safe_patterns = [
            "This is a normal text",
            "user@example.com",
            "Hello <world>",  # Angle brackets in normal context
            "Math: 2 < 3 and 4 > 2",
        ]
        
        for pattern in safe_patterns:
            self.assertFalse(
                security_manager.detect_xss(pattern),
                f"Safe pattern should not be detected as XSS: {pattern}"
            )
    
    def test_input_sanitization(self):
        """Test input sanitization"""
        from utils.helpers import security_manager
        
        # Test HTML entity encoding
        dangerous_input = '<script>alert("xss")</script>'
        sanitized = security_manager.sanitize_input(dangerous_input)
        self.assertNotIn('<script>', sanitized)
        self.assertNotIn('</script>', sanitized)
        
        # Test that safe input is preserved
        safe_input = "Normal text with numbers 123"
        self.assertEqual(security_manager.sanitize_input(safe_input), safe_input)


class TestAuthenticationSecurity(unittest.TestCase):
    """Test authentication security measures"""
    
    def test_password_requirements(self):
        """Test password validation requirements"""
        from utils.helpers import validate_password
        
        # Test weak passwords
        weak_passwords = [
            ("short", "too short"),
            ("alllowercase123", "no uppercase"),
            ("ALLUPPERCASE123", "no lowercase"),
            ("NoNumbers!", "no digits"),
            ("NoSpecialChars123", "no special characters"),
            ("password123!", "common password"),
        ]
        
        for password, reason in weak_passwords:
            is_valid, error = validate_password(password)
            self.assertFalse(is_valid, f"Password should be rejected: {password} ({reason})")
        
        # Test strong passwords
        strong_passwords = [
            "StrongP@ssw0rd123",
            "C0mpl3x!Pass#2023",
            "MyS3cur3P@ssphrase!",
        ]
        
        for password in strong_passwords:
            is_valid, error = validate_password(password)
            self.assertTrue(is_valid, f"Password should be accepted: {password}")
    
    def test_rate_limiting(self):
        """Test rate limiting functionality"""
        from utils.helpers import rate_limiter
        
        test_ip = "192.168.1.100"
        test_endpoint = "/api/login"
        
        # Reset rate limiter
        rate_limiter.requests.clear()
        
        # Test within limits
        for i in range(5):
            allowed, remaining = rate_limiter.check_rate_limit(test_ip, test_endpoint, max_requests=10, window=60)
            self.assertTrue(allowed, f"Request {i+1} should be allowed")
            self.assertEqual(remaining, 10 - i - 1)
        
        # Test exceeding limits
        for i in range(6):
            allowed, remaining = rate_limiter.check_rate_limit(test_ip, test_endpoint, max_requests=10, window=60)
        
        # 11th request should be blocked
        allowed, remaining = rate_limiter.check_rate_limit(test_ip, test_endpoint, max_requests=10, window=60)
        self.assertFalse(allowed, "Request should be blocked after exceeding limit")
        self.assertEqual(remaining, 0)


class TestCSRFProtection(unittest.TestCase):
    """Test CSRF protection"""
    
    def test_csrf_token_generation(self):
        """Test CSRF token generation and validation"""
        from utils.csrf_protection import generate_csrf_token, validate_csrf_token
        
        # Generate token
        token = generate_csrf_token()
        self.assertIsNotNone(token)
        self.assertTrue(len(token) >= 32, "CSRF token should be at least 32 characters")
        
        # Validate token
        is_valid = validate_csrf_token(token, token)
        self.assertTrue(is_valid, "Valid token should pass validation")
        
        # Test invalid token
        is_valid = validate_csrf_token(token, "invalid_token")
        self.assertFalse(is_valid, "Invalid token should fail validation")
    
    def test_csrf_token_uniqueness(self):
        """Test that CSRF tokens are unique"""
        from utils.csrf_protection import generate_csrf_token
        
        tokens = set()
        for _ in range(100):
            token = generate_csrf_token()
            self.assertNotIn(token, tokens, "CSRF tokens should be unique")
            tokens.add(token)


class TestEnvironmentSecurity(unittest.TestCase):
    """Test environment variable security"""
    
    def test_sensitive_env_vars_not_empty(self):
        """Test that sensitive environment variables are validated"""
        from config.env_validator import EnvValidator
        
        sensitive_vars = EnvValidator.NON_EMPTY_VARS
        
        # These should all be validated to not be empty
        expected_sensitive = [
            'MYSQL_PASSWORD',
            'KEYDB_PASSWORD',
            'ADMIN_PASSWORD',
            'SECRET_KEY',
            'EMAIL_PASSWORD'
        ]
        
        for var in expected_sensitive:
            self.assertIn(var, sensitive_vars, f"{var} should be marked as sensitive")


class TestFileUploadSecurity(unittest.TestCase):
    """Test file upload security"""
    
    def test_file_extension_validation(self):
        """Test file extension validation"""
        from utils.helpers import validate_file_upload
        
        # Create mock file objects
        class MockFile:
            def __init__(self, filename, content_type, size=1024):
                self.filename = filename
                self.content_type = content_type
                self.size = size
        
        # Test allowed extensions
        allowed_files = [
            MockFile("image.jpg", "image/jpeg"),
            MockFile("document.pdf", "application/pdf"),
            MockFile("photo.png", "image/png"),
        ]
        
        for file in allowed_files:
            is_valid, error = validate_file_upload(file)
            self.assertTrue(is_valid, f"File should be allowed: {file.filename}")
        
        # Test blocked extensions
        blocked_files = [
            MockFile("script.exe", "application/x-executable"),
            MockFile("hack.php", "application/x-php"),
            MockFile("shell.sh", "text/x-shellscript"),
            MockFile("virus.bat", "application/x-batch"),
        ]
        
        for file in blocked_files:
            is_valid, error = validate_file_upload(file)
            self.assertFalse(is_valid, f"File should be blocked: {file.filename}")
    
    def test_file_size_limits(self):
        """Test file size validation"""
        from utils.helpers import validate_file_upload
        
        class MockFile:
            def __init__(self, filename, size):
                self.filename = filename
                self.content_type = "image/jpeg"
                self.size = size
        
        # Test within limits (assuming 10MB limit)
        small_file = MockFile("small.jpg", 1024 * 1024)  # 1MB
        is_valid, error = validate_file_upload(small_file)
        self.assertTrue(is_valid, "Small file should be allowed")
        
        # Test exceeding limits
        large_file = MockFile("large.jpg", 20 * 1024 * 1024)  # 20MB
        is_valid, error = validate_file_upload(large_file)
        self.assertFalse(is_valid, "Large file should be blocked")


if __name__ == '__main__':
    unittest.main()