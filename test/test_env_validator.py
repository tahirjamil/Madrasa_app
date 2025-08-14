"""
Test Environment Validator
=========================

Tests for the environment variable validation system.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.env_validator import EnvValidator, validate_environment


class TestEnvValidator(unittest.TestCase):
    """Test environment validation functionality"""
    
    def setUp(self):
        """Set up test environment"""
        self.original_env = os.environ.copy()
    
    def tearDown(self):
        """Clean up after tests"""
        # Restore original environment
        os.environ.clear()
        os.environ.update(self.original_env)
    
    def test_missing_required_variables(self):
        """Test detection of missing required variables"""
        # Clear all environment variables
        os.environ.clear()
        
        success, errors = EnvValidator.validate()
        self.assertFalse(success)
        self.assertTrue(len(errors) >= len(EnvValidator.REQUIRED_VARS))
        
        # Check that each required var is reported as missing
        for var in EnvValidator.REQUIRED_VARS:
            self.assertTrue(any(var in error for error in errors))
    
    def test_empty_sensitive_variables(self):
        """Test detection of empty sensitive variables"""
        # Set all required vars but make sensitive ones empty
        for var in EnvValidator.REQUIRED_VARS:
            os.environ[var] = " " if var in EnvValidator.NON_EMPTY_VARS else "test_value"
        
        success, errors = EnvValidator.validate()
        self.assertFalse(success)
        
        # Check that empty sensitive vars are reported
        for var in EnvValidator.NON_EMPTY_VARS:
            self.assertTrue(any(var in error and "Empty" in error for error in errors))
    
    def test_invalid_formats(self):
        """Test validation of specific formats"""
        # Set all required vars with some invalid formats
        for var in EnvValidator.REQUIRED_VARS:
            os.environ[var] = "test_value"
        
        # Test invalid port
        os.environ['KEYDB_PORT'] = "99999"
        
        # Test invalid email
        os.environ['EMAIL_ADDRESS'] = "invalid-email"
        
        # Test weak secret key
        os.environ['SECRET_KEY'] = "short"
        
        success, errors = EnvValidator.validate()
        self.assertFalse(success)
        
        # Check specific format errors
        self.assertTrue(any("KEYDB_PORT" in error and "65535" in error for error in errors))
        self.assertTrue(any("EMAIL_ADDRESS" in error for error in errors))
        self.assertTrue(any("SECRET_KEY" in error and "32 characters" in error for error in errors))
    
    def test_invalid_sql_identifier(self):
        """Test validation of SQL identifier for MADRASA_NAME"""
        for var in EnvValidator.REQUIRED_VARS:
            os.environ[var] = "test_value"
        
        # Test invalid SQL identifiers
        invalid_names = ["123start", "name-with-dash", "name with space", "drop;table"]
        
        for invalid_name in invalid_names:
            os.environ['MADRASA_NAME'] = invalid_name
            success, errors = EnvValidator.validate()
            self.assertFalse(success)
            self.assertTrue(any("MADRASA_NAME" in error and "SQL identifier" in error for error in errors))
    
    def test_valid_configuration(self):
        """Test validation passes with valid configuration"""
        # Set all required variables with valid values
        valid_config = {
            'MYSQL_HOST': 'localhost',
            'MYSQL_USER': 'root',
            'MYSQL_PASSWORD': 'secure_password_123',
            'MYSQL_DB': 'test_db',
            'KEYDB_HOST': 'localhost',
            'KEYDB_PORT': '6379',
            'KEYDB_PASSWORD': 'redis_password_456',
            'ADMIN_USERNAME': 'admin',
            'ADMIN_PASSWORD': 'admin_password_789',
            'MADRASA_NAME': 'test_madrasa',
            'SECRET_KEY': 'a' * 32,  # 32 character key
            'EMAIL_ADDRESS': 'test@example.com',
            'EMAIL_PASSWORD': 'email_password_321',
            'TEXTBELT_KEY': 'textbelt_key_654'
        }
        
        for key, value in valid_config.items():
            os.environ[key] = value
        
        # Mock directory checks to pass
        with patch('os.access', return_value=True):
            with patch('pathlib.Path.exists', return_value=True):
                success, errors = EnvValidator.validate()
                self.assertTrue(success)
                self.assertEqual(len(errors), 0)
    
    def test_directory_permissions(self):
        """Test directory permission checks"""
        # Set all required vars
        for var in EnvValidator.REQUIRED_VARS:
            os.environ[var] = "test_value"
        
        # Mock directory doesn't exist
        with patch('pathlib.Path.exists', return_value=False):
            with patch('pathlib.Path.mkdir', side_effect=PermissionError("No permission")):
                errors = EnvValidator._validate_file_permissions()
                self.assertTrue(any("Cannot create directory" in error for error in errors))
        
        # Mock directory not writable
        with patch('pathlib.Path.exists', return_value=True):
            with patch('os.access', return_value=False):
                errors = EnvValidator._validate_file_permissions()
                self.assertTrue(any("not writable" in error for error in errors))
    
    def test_get_safe_config(self):
        """Test getting configuration with safe defaults"""
        # Set minimal required vars
        for var in EnvValidator.REQUIRED_VARS:
            os.environ[var] = f"value_for_{var}"
        
        config = EnvValidator.get_safe_config()
        
        # Check required vars are included
        for var in EnvValidator.REQUIRED_VARS:
            self.assertEqual(config[var], f"value_for_{var}")
        
        # Check defaults are applied
        self.assertEqual(config['APP_NAME'], 'Madrasa App')
        self.assertEqual(config['APP_VERSION'], '1.0.0')
        self.assertEqual(config['MAX_CONTENT_LENGTH'], 16777216)
        self.assertEqual(config['REDIS_EXPIRATION'], 3600)
    
    def test_skip_validation_flag(self):
        """Test SKIP_ENV_VALIDATION flag"""
        # Clear all environment variables
        os.environ.clear()
        os.environ['SKIP_ENV_VALIDATION'] = '1'
        
        # Should return True even with errors
        result = validate_environment()
        self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()
