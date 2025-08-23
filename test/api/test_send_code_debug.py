import pytest
import requests
import os
import json
import time
from dotenv import load_dotenv
import random
import string
import uuid
from config import config, server_config

load_dotenv()

class TestSendCodeDebug:
    """Debug tests for the /send_code endpoint to identify issues"""
    
    @pytest.fixture
    def base_url(self) -> str:
        """Fixture to provide the base URL for API testing"""
        return f"http://localhost:{server_config.SERVER_PORT}"
    
    @pytest.fixture
    def test_headers(self) -> dict:
        """Fixture to provide test headers"""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {random.choice(list(config.API_KEYS))}",
            "X-API-Key": random.choice(list(config.API_KEYS)),
            "X-Device-ID": "BP22.250325.006",  # Use the same device ID from your mobile app
            "X-Device-Brand": "google",
            "X-Device-Model": "sdk_gphone64_x86_64",
            "X-Device-OS": "Android"
        }
    
    @pytest.fixture
    def test_data(self) -> dict:
        """Fixture to provide test data matching your mobile app request"""
        return {
            "fullname": "tareq",
            "phone": "01687877822",
            "password": "Tareq@121",
            "email": "tareqjamil01910@gmail.com",
            "language": "bn",
            "app_signature": "MKhShwSNUoW"
        }
    
    def test_send_code_exact_mobile_request(self, base_url, test_headers, test_data):
        """Test with exact data from your mobile app request"""
        print(f"\n{'='*60}")
        print("TESTING EXACT MOBILE APP REQUEST")
        print(f"{'='*60}")
        print(f"URL: {base_url}/api/v1/auth/send_code")
        print(f"Headers: {json.dumps(test_headers, indent=2)}")
        print(f"Data: {json.dumps(test_data, indent=2)}")
        
        response = requests.post(f"{base_url}/api/v1/auth/send_code", 
                               json=test_data, headers=test_headers)
        
        print(f"\n{'='*60}")
        print("RESPONSE ANALYSIS")
        print(f"{'='*60}")
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response Body: {response.text}")
        
        try:
            response_json = response.json()
            print(f"Parsed JSON: {json.dumps(response_json, indent=2)}")
        except json.JSONDecodeError:
            print("Response is not valid JSON")
        
        # Detailed analysis
        if response.status_code == 200:
            print("✅ SUCCESS: Verification code sent successfully")
        elif response.status_code == 403:
            print("❌ FORBIDDEN: Device validation or authentication issue")
        elif response.status_code == 409:
            print("⚠️ CONFLICT: User already exists")
        elif response.status_code == 429:
            print("⚠️ RATE LIMITED: Too many requests")
        elif response.status_code == 500:
            print("❌ SERVER ERROR: Internal server error")
            if 'error' in response_json:
                print(f"Error details: {response_json['error']}")
        else:
            print(f"❓ UNEXPECTED: Status code {response.status_code}")
        
        # Accept any status code for debugging
        assert True
    
    def test_send_code_step_by_step(self, base_url, test_headers):
        """Test send_code with step-by-step debugging"""
        print(f"\n{'='*60}")
        print("STEP-BY-STEP DEBUGGING")
        print(f"{'='*60}")
        
        # Step 1: Test basic connectivity
        print("\n1. Testing basic connectivity...")
        health_response = requests.get(f"{base_url}/health")
        print(f"Health check status: {health_response.status_code}")
        assert health_response.status_code == 200, "Server is not running"
        
        # Step 2: Test authentication
        print("\n2. Testing authentication...")
        auth_headers = {k: v for k, v in test_headers.items() if k in ['Authorization', 'X-API-Key']}
        print(f"Auth headers: {auth_headers}")
        
        # Step 3: Test device validation
        print("\n3. Testing device validation...")
        device_headers = {k: v for k, v in test_headers.items() if k.startswith('X-Device-')}
        print(f"Device headers: {device_headers}")
        
        # Step 4: Test with minimal data
        print("\n4. Testing with minimal data...")
        minimal_data = {
            "fullname": "test_user",
            "phone": "01687877822",
            "password": "TestPass123",
            "language": "en",
            "app_signature": "test_signature"
        }
        
        response = requests.post(f"{base_url}/api/v1/auth/send_code", 
                               json=minimal_data, headers=test_headers)
        
        print(f"Minimal data test status: {response.status_code}")
        print(f"Response: {response.text}")
        
        # Step 5: Test with full data
        print("\n5. Testing with full data...")
        full_data = {
            "fullname": "test_user",
            "phone": "01687877822",
            "password": "TestPass123",
            "email": "test@example.com",
            "madrasa_name": "annur",
            "language": "en",
            "app_signature": "test_signature"
        }
        
        response = requests.post(f"{base_url}/api/v1/auth/send_code", 
                               json=full_data, headers=test_headers)
        
        print(f"Full data test status: {response.status_code}")
        print(f"Response: {response.text}")
        
        # Step 6: Test database connectivity
        print("\n6. Testing database connectivity...")
        # This will be tested indirectly through the send_code endpoint
        
        # Step 7: Test SMS configuration
        print("\n7. Testing SMS configuration...")
        if response.status_code == 500:
            try:
                response_json = response.json()
                if 'error' in response_json:
                    error_msg = response_json['error'].lower()
                    if 'sms' in error_msg:
                        print("❌ SMS configuration issue detected")
                    elif 'database' in error_msg or 'mysql' in error_msg:
                        print("❌ Database configuration issue detected")
                    else:
                        print(f"❌ Other error: {response_json['error']}")
            except:
                print("❌ Could not parse error response")
        
        assert True
    
    def test_send_code_error_scenarios(self, base_url, test_headers):
        """Test various error scenarios"""
        print(f"\n{'='*60}")
        print("ERROR SCENARIO TESTING")
        print(f"{'='*60}")
        
        scenarios = [
            {
                "name": "Missing fullname",
                "data": {
                    "phone": "01687877822",
                    "password": "TestPass123",
                    "language": "en",
                    "app_signature": "test_signature"
                }
            },
            {
                "name": "Invalid phone format",
                "data": {
                    "fullname": "test_user",
                    "phone": "invalid_phone",
                    "password": "TestPass123",
                    "language": "en",
                    "app_signature": "test_signature"
                }
            },
            {
                "name": "Weak password",
                "data": {
                    "fullname": "test_user",
                    "phone": "01687877822",
                    "password": "123",
                    "language": "en",
                    "app_signature": "test_signature"
                }
            },
            {
                "name": "Invalid email format",
                "data": {
                    "fullname": "test_user",
                    "phone": "01687877822",
                    "password": "TestPass123",
                    "email": "invalid_email",
                    "language": "en",
                    "app_signature": "test_signature"
                }
            }
        ]
        
        for scenario in scenarios:
            print(f"\n--- Testing: {scenario['name']} ---")
            response = requests.post(f"{base_url}/api/v1/auth/send_code", 
                                   json=scenario['data'], headers=test_headers)
            
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
            
            # Should return validation error
            assert response.status_code in [400, 422], f"Expected validation error for {scenario['name']}"
    
    def test_send_code_configuration_check(self, base_url, test_headers, test_data):
        """Check configuration and environment"""
        print(f"\n{'='*60}")
        print("CONFIGURATION CHECK")
        print(f"{'='*60}")
        
        # Check if required environment variables are set
        required_env_vars = [
            'SMS_API_KEY',
            'EMAIL_PASSWORD',
            'BUSINESS_EMAIL',
            'MYSQL_HOST',
            'MYSQL_USER',
            'MYSQL_PASSWORD'
        ]
        
        print("\nEnvironment Variables:")
        for var in required_env_vars:
            value = os.getenv(var)
            if value:
                print(f"✅ {var}: {'*' * len(value)} (set)")
            else:
                print(f"❌ {var}: NOT SET")
        
        # Check API configuration
        print(f"\nAPI Configuration:")
        print(f"SMS API URL: {config.SERVICE_PHONE_URL}")
        print(f"SMS API Key: {'*' * len(config.SERVICE_PHONE_API_KEY) if config.SERVICE_PHONE_API_KEY else 'NOT SET'}")
        print(f"Business Email: {config.BUSINESS_EMAIL}")
        print(f"Email Password: {'*' * len(config.SERVICE_EMAIL_PASSWORD) if config.SERVICE_EMAIL_PASSWORD else 'NOT SET'}")
        
        # Check database configuration
        print(f"\nDatabase Configuration:")
        print(f"MySQL Host: {config.MYSQL_HOST}")
        print(f"MySQL User: {config.MYSQL_USER}")
        print(f"MySQL Password: {'*' * len(config.MYSQL_PASSWORD) if config.MYSQL_PASSWORD else 'NOT SET'}")
        print(f"MySQL Database: {config.MYSQL_DB}")
        
        # Test the endpoint
        response = requests.post(f"{base_url}/api/v1/auth/send_code", 
                               json=test_data, headers=test_headers)
        
        print(f"\nEndpoint Test Result:")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        assert True
    
    def test_send_code_with_different_devices(self, base_url, test_data):
        """Test with different device configurations"""
        print(f"\n{'='*60}")
        print("DEVICE CONFIGURATION TESTING")
        print(f"{'='*60}")
        
        device_configs = [
            {
                "name": "Android Device (Original)",
                "headers": {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {random.choice(list(config.API_KEYS))}",
                    "X-API-Key": random.choice(list(config.API_KEYS)),
                    "X-Device-ID": "BP22.250325.006",
                    "X-Device-Brand": "google",
                    "X-Device-Model": "sdk_gphone64_x86_64",
                    "X-Device-OS": "Android"
                }
            },
            {
                "name": "iOS Device",
                "headers": {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {random.choice(list(config.API_KEYS))}",
                    "X-API-Key": random.choice(list(config.API_KEYS)),
                    "X-Device-ID": "iPhone14,2",
                    "X-Device-Brand": "apple",
                    "X-Device-Model": "iPhone 13 Pro",
                    "X-Device-OS": "iOS"
                }
            },
            {
                "name": "Web Browser",
                "headers": {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {random.choice(list(config.API_KEYS))}",
                    "X-API-Key": random.choice(list(config.API_KEYS)),
                    "X-Device-ID": "web_browser_123",
                    "X-Device-Brand": "chrome",
                    "X-Device-Model": "Chrome/120.0.0.0",
                    "X-Device-OS": "Windows"
                }
            },
            {
                "name": "Minimal Headers (No OS)",
                "headers": {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {random.choice(list(config.API_KEYS))}",
                    "X-API-Key": random.choice(list(config.API_KEYS)),
                    "X-Device-ID": "minimal_device",
                    "X-Device-Brand": "test_brand",
                    "X-Device-Model": "test_model"
                }
            }
        ]
        
        for config in device_configs:
            print(f"\n--- Testing: {config['name']} ---")
            response = requests.post(f"{base_url}/api/v1/auth/send_code", 
                                   json=test_data, headers=config['headers'])
            
            print(f"Status: {response.status_code}")
            if response.status_code == 403:
                print("❌ Device validation failed")
            elif response.status_code == 200:
                print("✅ Device validation passed")
            else:
                print(f"Response: {response.text}")
        
        assert True

if __name__ == "__main__":
    # Run specific test for debugging
    pytest.main([__file__, "-v", "-s", "-k", "test_send_code_exact_mobile_request"])
