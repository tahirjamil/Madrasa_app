"""
Comprehensive Test Suite for Enhanced Helper Functions
====================================================

This module provides thorough testing for all helper functions including:
- Security features (API key validation, threat detection)
- Caching system (TTL, memory management)
- Rate limiting (sliding window algorithm)
- Validation functions (email, phone, password, file upload)
- Performance monitoring
- Database operations
- File management
- Communication functions

Author: Madrasha Development Team
Version: 1.0.0
"""

import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timedelta

# Test basic import first
try:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from helpers import *
    IMPORT_SUCCESS = True
except Exception as e:
    print(f"Import failed: {e}")
    IMPORT_SUCCESS = False


class TestBasicImport(unittest.TestCase):
    """Test basic import functionality"""
    
    def test_import_success(self):
        """Test that helpers module can be imported"""
        self.assertTrue(IMPORT_SUCCESS, "Helpers module should import successfully")


if not IMPORT_SUCCESS:
    print("❌ Cannot import helpers module. Skipping all tests.")
    print("Please fix the import issues first.")
    exit(1)


class TestSecurityFunctions(unittest.TestCase):
    """Test security-related functions"""
    
    def setUp(self):
        """Set up test environment"""
        # Clear any existing environment variables
        os.environ.pop('TEST_MODE', None)
        os.environ.pop('API_KEY', None)
        os.environ.pop('MADRASA_API_KEY', None)
    
    def test_is_valid_api_key(self):
        """Test API key validation"""
        # Test with no API key set
        self.assertTrue(is_valid_api_key("any_key"))
        
        # Test with API key set
        os.environ['API_KEY'] = 'test_key_123'
        self.assertTrue(is_valid_api_key('test_key_123'))
        self.assertFalse(is_valid_api_key('wrong_key'))
        self.assertFalse(is_valid_api_key(''))
        self.assertFalse(is_valid_api_key(None))
        
        # Test in test mode
        os.environ['TEST_MODE'] = 'true'
        self.assertTrue(is_valid_api_key("any_key"))
        # Clear test mode after testing
        os.environ.pop('TEST_MODE', None)
    
    def test_is_maintenance_mode(self):
        """Test maintenance mode detection"""
        # Test default (not in maintenance)
        self.assertFalse(config.is_maintenance)
        
        # Test various true values
        for value in ['true', 'True', 'TRUE', 'yes', 'Yes', 'YES', 'on', 'On', 'ON']:
            os.environ['MAINTENANCE_MODE'] = value
            self.assertTrue(config.is_maintenance)
        
        # Test false values
        for value in ['false', 'False', 'FALSE', 'no', 'No', 'NO', 'off', 'Off', 'OFF', '']:
            os.environ['MAINTENANCE_MODE'] = value
            self.assertFalse(config.is_maintenance)
    
    def test_is_test_mode(self):
        """Test test mode detection"""
        # Test default (not in test mode)
        self.assertFalse(config.is_testing())
        
        # Test various true values
        for value in ['true', 'True', 'TRUE', 'yes', 'Yes', 'YES', 'on', 'On', 'ON']:
            os.environ['TEST_MODE'] = value
            self.assertTrue(config.is_testing())
        
        # Test false values
        for value in ['false', 'False', 'FALSE', 'no', 'No', 'NO', 'off', 'Off', 'OFF', '']:
            os.environ['TEST_MODE'] = value
            self.assertFalse(config.is_testing())


class TestValidationFunctions(unittest.TestCase):
    """Test validation functions"""
    
    def test_validate_email(self):
        """Test email validation"""
        # Valid emails
        valid_emails = [
            'test@example.com',
            'user.name@domain.co.uk',
            'user+tag@example.org',
            '123@test.com'
        ]
        
        for email in valid_emails:
            is_valid, message = validate_email(email)
            self.assertTrue(is_valid, f"Email {email} should be valid: {message}")
        
        # Invalid emails
        invalid_emails = [
            '',
            'invalid-email',
            '@example.com',
            'user@',
            'user@.com',
            'user@example.',
            'user name@example.com',
            'user@example..com'
        ]
        
        for email in invalid_emails:
            is_valid, message = validate_email(email)
            self.assertFalse(is_valid, f"Email {email} should be invalid: {message}")
    
    def test_validate_phone_international(self):
        """Test international phone number validation"""
        # Valid phone numbers
        valid_phones = [
            '+8801712345678',
            '+1234567890',
            '+447911123456'
        ]
        
        for phone in valid_phones:
            is_valid, message = validate_phone_international(phone)
            self.assertTrue(is_valid, f"Phone {phone} should be valid: {message}")
        
        # Invalid phone numbers
        invalid_phones = [
            '',
            '123',
            '+123',
            'not-a-phone',
            '+88017123456789',  # Too long
            '+880171234567'     # Too short
        ]
        
        for phone in invalid_phones:
            is_valid, message = validate_phone_international(phone)
            self.assertFalse(is_valid, f"Phone {phone} should be invalid: {message}")
    
    def test_validate_password(self):
        """Test password validation"""
        # Valid passwords
        valid_passwords = [
            'Password123',
            'MySecurePass1',
            'ComplexP@ss1'
        ]
        
        for password in valid_passwords:
            is_valid, message = validate_password(password)
            self.assertTrue(is_valid, f"Password should be valid: {message}")
        
        # Invalid passwords
        invalid_passwords = [
            '',  # Empty
            'short',  # Too short
            'nouppercase123',  # No uppercase
            'NOLOWERCASE123',  # No lowercase
            'NoNumbers',  # No numbers
            'Password 123',  # Contains space
            'pass123'  # Too short and no uppercase
        ]
        
        for password in invalid_passwords:
            is_valid, message = validate_password(password)
            self.assertFalse(is_valid, f"Password should be invalid: {message}")
    
    def test_validate_fullname(self):
        """Test fullname validation"""
        # Valid fullnames
        valid_names = [
            'John Doe',
            'Mary Jane Watson',
            'O\'Connor'
        ]
        
        for name in valid_names:
            is_valid, message = validate_fullname(name)
            self.assertTrue(is_valid, f"Name {name} should be valid: {message}")
        
        # Invalid fullnames
        invalid_names = [
            '',  # Empty
            'john doe',  # No uppercase
            'John123',  # Contains digits
            'John@Doe',  # Contains special chars
            'John_Doe',  # Contains underscore
            '123John',  # Starts with digits
            'John@Doe',  # Contains @
        ]
        
        for name in invalid_names:
            is_valid, message = validate_fullname(name)
            self.assertFalse(is_valid, f"Name {name} should be invalid: {message}")
    
    def test_validate_file_upload(self):
        """Test file upload validation"""
        allowed_extensions = ['jpg', 'png', 'pdf', 'doc']
        
        # Valid filenames
        valid_files = [
            'document.pdf',
            'image.jpg',
            'file.PNG',
            'test.doc'
        ]
        
        for filename in valid_files:
            is_valid, message = validate_file_upload(filename, allowed_extensions)
            self.assertTrue(is_valid, f"File {filename} should be valid: {message}")
        
        # Invalid filenames
        invalid_files = [
            '',  # Empty
            'file.txt',  # Wrong extension
            '../file.pdf',  # Directory traversal
            'file<>.pdf',  # Invalid characters
            'CON.pdf',  # Reserved name
            'file.pdf.exe',  # Double extension
            'file..pdf',  # Double dots
        ]
        
        for filename in invalid_files:
            is_valid, message = validate_file_upload(filename, allowed_extensions)
            self.assertFalse(is_valid, f"File {filename} should be invalid: {message}")


class TestCachingSystem(unittest.TestCase):
    """Test caching system"""
    
    def setUp(self):
        """Set up cache for testing"""
        self.cache = CacheManager()
    
    def test_cache_basic_operations(self):
        """Test basic cache operations"""
        # Test set and get
        self.cache.set('test_key', 'test_value', ttl=3600)
        self.assertEqual(self.cache.get('test_key'), 'test_value')
        
        # Test default value
        self.assertIsNone(self.cache.get('non_existent'))
        self.assertEqual(self.cache.get('non_existent', 'default'), 'default')
        
        # Test delete
        self.cache.delete('test_key')
        self.assertIsNone(self.cache.get('test_key'))
        
        # Test clear
        self.cache.set('key1', 'value1')
        self.cache.set('key2', 'value2')
        self.cache.clear()
        self.assertIsNone(self.cache.get('key1'))
        self.assertIsNone(self.cache.get('key2'))
    
    def test_cache_ttl(self):
        """Test cache TTL functionality"""
        # Set with short TTL
        self.cache.set('expire_key', 'expire_value', ttl=1)
        self.assertEqual(self.cache.get('expire_key'), 'expire_value')
        
        # Wait for expiration
        import time
        time.sleep(1.1)
        self.assertIsNone(self.cache.get('expire_key'))
    
    def test_cache_cleanup(self):
        """Test cache cleanup functionality"""
        # Fill cache beyond max size
        for i in range(1100):
            self.cache.set(f'key_{i}', f'value_{i}')
        
        # Should trigger cleanup
        self.assertLess(len(self.cache._cache), 1000)


class TestRateLimiting(unittest.TestCase):
    """Test rate limiting system"""
    
    def setUp(self):
        """Set up rate limiter for testing"""
        self.rate_limiter = RateLimiter()
    
    def test_rate_limiting_basic(self):
        """Test basic rate limiting"""
        identifier = 'test_user'
        max_requests = 5
        window = 60
        
        # Should allow first 5 requests
        for i in range(5):
            self.assertTrue(self.rate_limiter.is_allowed(identifier, max_requests, window))
        
        # 6th request should be blocked
        self.assertFalse(self.rate_limiter.is_allowed(identifier, max_requests, window))
    
    def test_rate_limiting_window(self):
        """Test rate limiting with time window"""
        identifier = 'test_user'
        max_requests = 3
        window = 1  # 1 second window
        
        # Make 3 requests
        for i in range(3):
            self.assertTrue(self.rate_limiter.is_allowed(identifier, max_requests, window))
        
        # 4th should be blocked
        self.assertFalse(self.rate_limiter.is_allowed(identifier, max_requests, window))
        
        # Wait for window to expire
        import time
        time.sleep(1.1)
        
        # Should allow again
        self.assertTrue(self.rate_limiter.is_allowed(identifier, max_requests, window))


class TestSecurityManager(unittest.TestCase):
    """Test security manager"""
    
    def setUp(self):
        """Set up security manager for testing"""
        self.security_manager = SecurityManager()
    
    def test_detect_sql_injection(self):
        """Test SQL injection detection"""
        # Malicious inputs
        malicious_inputs = [
            "'; DROP TABLE users; --",
            "UNION SELECT * FROM users",
            "1' OR '1'='1",
            "admin'--",
            "'; INSERT INTO users VALUES ('hacker', 'pass'); --"
        ]
        
        for input_str in malicious_inputs:
            self.assertTrue(self.security_manager.detect_sql_injection(input_str))
        
        # Safe inputs
        safe_inputs = [
            "normal text",
            "user@example.com",
            "John Doe",
            "12345",
            "Hello World"
        ]
        
        for input_str in safe_inputs:
            self.assertFalse(self.security_manager.detect_sql_injection(input_str))
    
    def test_detect_xss(self):
        """Test XSS detection"""
        # Malicious inputs
        malicious_inputs = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "<iframe src='http://evil.com'></iframe>",
            "onclick=alert('xss')"
        ]
        
        for input_str in malicious_inputs:
            self.assertTrue(self.security_manager.detect_xss(input_str))
        
        # Safe inputs
        safe_inputs = [
            "normal text",
            "Hello <strong>World</strong>",
            "user@example.com",
            "12345"
        ]
        
        for input_str in safe_inputs:
            self.assertFalse(self.security_manager.detect_xss(input_str))
    
    def test_sanitize_input(self):
        """Test input sanitization"""
        # Test dangerous characters removal
        dangerous_input = "<script>alert('xss')</script>"
        sanitized = self.security_manager.sanitize_input(dangerous_input)
        self.assertNotIn('<', sanitized)
        self.assertNotIn('>', sanitized)
        self.assertNotIn('"', sanitized)
        self.assertNotIn("'", sanitized)
        
        # Test safe input
        safe_input = "Hello World"
        sanitized = self.security_manager.sanitize_input(safe_input)
        self.assertEqual(sanitized, "Hello World")
        
        # Test empty input
        self.assertEqual(self.security_manager.sanitize_input(""), "")
        self.assertEqual(self.security_manager.sanitize_input(None), "")


class TestPerformanceMonitor(unittest.TestCase):
    """Test performance monitoring"""
    
    def setUp(self):
        """Set up performance monitor for testing"""
        self.performance_monitor = PerformanceMonitor()
    
    def test_record_request_time(self):
        """Test request time recording"""
        self.performance_monitor.record_request_time('/test', 0.5)
        self.performance_monitor.record_request_time('/test', 1.0)
        self.performance_monitor.record_request_time('/test', 0.3)
        
        self.assertEqual(len(self.performance_monitor.request_times), 3)
    
    def test_record_error(self):
        """Test error recording"""
        self.performance_monitor.record_error('validation_error', 'Invalid input')
        self.performance_monitor.record_error('database_error', 'Connection failed')
        self.performance_monitor.record_error('validation_error', 'Another invalid input')
        
        self.assertEqual(self.performance_monitor.error_counts['validation_error'], 2)
        self.assertEqual(self.performance_monitor.error_counts['database_error'], 1)
    
    def test_get_performance_stats(self):
        """Test performance statistics"""
        # Add some test data
        self.performance_monitor.record_request_time('/test1', 0.5)
        self.performance_monitor.record_request_time('/test2', 1.0)
        self.performance_monitor.record_request_time('/test3', 0.3)
        self.performance_monitor.record_error('test_error', 'Test error')
        
        stats = self.performance_monitor.get_performance_stats()
        
        self.assertEqual(stats['total_requests'], 3)
        self.assertIn('average_response_time', stats)
        self.assertIn('min_response_time', stats)
        self.assertIn('max_response_time', stats)
        self.assertIn('uptime_seconds', stats)
        self.assertIn('error_counts', stats)


class TestUtilityFunctions(unittest.TestCase):
    """Test utility functions"""
    
    def test_generate_secure_token(self):
        """Test secure token generation"""
        token1 = generate_secure_token(16)
        token2 = generate_secure_token(16)
        
        self.assertEqual(len(token1), 16)
        self.assertNotEqual(token1, token2)
        
        # Test different lengths
        token3 = generate_secure_token(32)
        self.assertEqual(len(token3), 32)
    
    def test_hash_sensitive_data(self):
        """Test sensitive data hashing"""
        data1 = "password123"
        data2 = "password123"
        data3 = "different_password"
        
        hash1 = hash_sensitive_data(data1)
        hash2 = hash_sensitive_data(data2)
        hash3 = hash_sensitive_data(data3)
        
        self.assertEqual(hash1, hash2)  # Same input should produce same hash
        self.assertNotEqual(hash1, hash3)  # Different input should produce different hash
        self.assertEqual(len(hash1), 8)  # Should be 8 characters
    
    def test_is_safe_filename(self):
        """Test filename safety check"""
        # Safe filenames
        safe_filenames = [
            'document.pdf',
            'image.jpg',
            'file_name.txt',
            'file-name.doc',
            'file123.pdf'
        ]
        
        for filename in safe_filenames:
            self.assertTrue(is_safe_filename(filename))
        
        # Dangerous filenames
        dangerous_filenames = [
            'file<>.txt',
            'file:name.txt',
            'file"name.txt',
            'file|name.txt',
            'file?name.txt',
            'file*name.txt',
            'file\\name.txt',
            'file/name.txt'
        ]
        
        for filename in dangerous_filenames:
            self.assertFalse(is_safe_filename(filename))


class TestBusinessLogicFunctions(unittest.TestCase):
    """Test business logic functions"""
    
    def test_calculate_fees(self):
        """Test fee calculation"""
        # Test male students
        self.assertEqual(calculate_fees('class 3', 'male', 0, 0, 0), 1600)
        self.assertEqual(calculate_fees('hifz', 'male', 0, 0, 0), 1800)
        self.assertEqual(calculate_fees('nursery', 'male', 0, 0, 0), 1300)
        
        # Test female students
        self.assertEqual(calculate_fees('nursery', 'female', 0, 0, 0), 800)
        self.assertEqual(calculate_fees('class 1', 'female', 0, 0, 0), 1000)
        self.assertEqual(calculate_fees('hifz', 'female', 0, 0, 0), 2000)
        
        # Test food charges
        self.assertEqual(calculate_fees('class 3', 'male', 0, 0, 1), 4000)  # 1600 + 2400
        self.assertEqual(calculate_fees('class 3', 'male', 1, 0, 0), 4600)  # 1600 + 3000
        
        # Test fee reduction
        self.assertEqual(calculate_fees('class 3', 'male', 0, 500, 0), 1100)  # 1600 - 500
        
        # Test test mode
        os.environ['TEST_MODE'] = 'true'
        self.assertEqual(calculate_fees('any_class', 'any_gender', 0, 0, 0), 9999)
        os.environ.pop('TEST_MODE', None)


class TestFileManagementFunctions(unittest.TestCase):
    """Test file management functions"""
    
    def setUp(self):
        """Set up temporary files for testing"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.temp_dir, 'test.json')
        
        # Create test data
        self.test_data = [
            {'id': 1, 'name': 'Test 1'},
            {'id': 2, 'name': 'Test 2'}
        ]
    
    def tearDown(self):
        """Clean up temporary files"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_load_and_save_results(self):
        """Test loading and saving results"""
        # Test saving
        save_results(self.test_data)
        
        # Test loading
        loaded_data = load_results()
        self.assertEqual(loaded_data, self.test_data)
    
    def test_load_and_save_notices(self):
        """Test loading and saving notices"""
        # Test saving
        save_notices(self.test_data)
        
        # Test loading
        loaded_data = load_notices()
        self.assertEqual(loaded_data, self.test_data)
    
    def test_allowed_file_extensions(self):
        """Test file extension validation"""
        # Test exam files
        self.assertTrue(allowed_exam_file('test.pdf'))
        self.assertTrue(allowed_exam_file('test.PDF'))
        self.assertFalse(allowed_exam_file('test.txt'))
        self.assertFalse(allowed_exam_file('test'))
        
        # Test notice files
        self.assertTrue(allowed_notice_file('notice.pdf'))
        self.assertTrue(allowed_notice_file('notice.PDF'))
        self.assertFalse(allowed_notice_file('notice.txt'))
        self.assertFalse(allowed_notice_file('notice'))


class TestConfigurationValidation(unittest.TestCase):
    """Test configuration validation"""
    
    def test_validate_app_config(self):
        """Test application configuration validation"""
        # Test with missing environment variables
        issues = validate_app_config()
        self.assertIsInstance(issues, list)
        
        # Test with all required variables set
        with patch.dict(os.environ, {
            'EMAIL_ADDRESS': 'test@example.com',
            'EMAIL_PASSWORD': 'password123',
            'TEXTBELT_KEY': 'test_key',
            'MYSQL_HOST': 'localhost',
            'MYSQL_USER': 'user',
            'MYSQL_PASSWORD': 'pass',
            'MYSQL_DB': 'database'
        }):
            issues = validate_app_config()
            # Should have no issues if directories are writable
            self.assertIsInstance(issues, list)


class TestApplicationInitialization(unittest.TestCase):
    """Test application initialization"""
    
    def test_initialize_application(self):
        """Test application initialization"""
        # Test initialization
        result = initialize_application()
        self.assertIsInstance(result, bool)


class TestAsyncFunctions(unittest.TestCase):
    """Test async functions"""
    
    async def test_check_rate_limit(self):
        """Test rate limit checking"""
        # Test rate limiting
        result = await check_rate_limit('test_user', 5, 60)
        self.assertIsInstance(result, bool)
    
    async def test_blocker(self):
        """Test blocker function"""
        # Mock database connection
        with patch('helpers.get_db_connection') as mock_db:
            mock_conn = AsyncMock()
            mock_cursor = AsyncMock()
            mock_cursor.fetchone.return_value = {'blocked': 0}
            mock_conn.cursor.return_value.__aenter__.return_value = mock_cursor
            mock_db.return_value = mock_conn
            
            result = await blocker('test_info')
            self.assertIsInstance(result, (bool, type(None)))


def run_all_tests():
    """Run all tests"""
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add test classes
    test_classes = [
        TestBasicImport,
        TestSecurityFunctions,
        TestValidationFunctions,
        TestCachingSystem,
        TestRateLimiting,
        TestSecurityManager,
        TestPerformanceMonitor,
        TestUtilityFunctions,
        TestBusinessLogicFunctions,
        TestFileManagementFunctions,
        TestConfigurationValidation,
        TestApplicationInitialization,
        TestAsyncFunctions
    ]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # Print summary
    print(f"\n{'='*50}")
    print(f"TESTS SUMMARY")
    print(f"{'='*50}")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    
    if result.failures:
        print(f"\nFAILURES:")
        for test, traceback in result.failures:
            print(f"- {test}: {traceback}")
    
    if result.errors:
        print(f"\nERRORS:")
        for test, traceback in result.errors:
            print(f"- {test}: {traceback}")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    print("🧪 Running Comprehensive Test Suite for Enhanced Helper Functions")
    print("=" * 70)
    
    success = run_all_tests()
    
    if success:
        print("\n✅ All tests passed! Helper functions are working correctly.")
    else:
        print("\n❌ Some tests failed. Please check the output above.")
    
    print("\n" + "=" * 70)



