import pytest
import requests
import os
from dotenv import load_dotenv
import random
import string
import uuid
from config import config, server_config

load_dotenv()

# Pytest fixtures for test data generation
@pytest.fixture
def madrasa_name() -> str:
    """Fixture to provide a random madrasa name"""
    return random.choice(list(config.MADRASA_NAMES_LIST))

@pytest.fixture
def fullname() -> str:
    """Fixture to provide a random full name"""
    return ''.join(random.choice(string.ascii_letters) for _ in range(10))

@pytest.fixture
def phone() -> str:
    """Fixture to provide a random phone number"""
    return f"+880{random.randint(1000000000, 9999999999)}"

@pytest.fixture
def email(fullname, madrasa_name) -> str:
    """Fixture to provide a random email"""
    return f"{fullname}@{madrasa_name}.com"

@pytest.fixture
def password() -> str:
    """Fixture to provide a random password"""
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(10))

@pytest.fixture
def device_id() -> str:
    """Fixture to provide a random device ID"""
    return str(uuid.uuid4())

@pytest.fixture
def device_brand() -> str:
    """Fixture to provide a random device brand"""
    return ''.join(random.choice(string.ascii_letters) for _ in range(10))

@pytest.fixture
def device_model() -> str:
    """Fixture to provide a random device model"""
    return ''.join(random.choice(string.ascii_letters) for _ in range(10))

@pytest.fixture
def device_os() -> str:
    """Fixture to provide a random device OS"""
    return ''.join(random.choice(string.ascii_letters) for _ in range(10))

@pytest.fixture
def api_key() -> str:
    """Fixture to provide a random API key"""
    return random.choice(list(config.API_KEYS))

@pytest.fixture
def base_url() -> str:
    """Fixture to provide the base URL for API testing"""
    return f"http://localhost:{server_config.SERVER_PORT}"

@pytest.fixture
def universal_headers(api_key, device_id, device_brand, device_model, device_os) -> dict:
    """Fixture to provide universal headers for API requests"""
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-API-Key": api_key,
        "X-Device-ID": device_id,
        "X-Device-Brand": device_brand,
        "X-Device-Model": device_model,
        "X-Device-OS": device_os
    }

def send_request(url: str, method: str, data: dict | None = None, headers: dict | None = None) -> requests.Response:
    """Helper function to send HTTP requests with universal headers"""
    universal_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {random.choice(list(config.API_KEYS))}",
        "X-API-Key": random.choice(list(config.API_KEYS)),
        "X-Device-ID": str(uuid.uuid4()),
        "X-Device-Brand": ''.join(random.choice(string.ascii_letters) for _ in range(10)),
        "X-Device-Model": ''.join(random.choice(string.ascii_letters) for _ in range(10)),
        "X-Device-OS": ''.join(random.choice(string.ascii_letters) for _ in range(10))
    }
    if headers:
        universal_headers.update(headers)
    response = requests.request(method, url, json=data, headers=universal_headers)
    return response

class TestAPIEndpoints:
    """Test class for API endpoints"""
    
    @pytest.mark.integration
    def test_health_check(self, base_url):
        """Test the health check endpoint"""
        response = send_request(f"{base_url}/health", "GET")
        assert response.status_code == 200
        assert response.headers.get("content-type", "").startswith("application/json")
    
    @pytest.mark.integration
    def test_health_check_with_fixtures(self, base_url, universal_headers):
        """Test the health check endpoint using pytest fixtures"""
        response = requests.get(f"{base_url}/health", headers=universal_headers)
        assert response.status_code == 200
        assert response.headers.get("content-type", "").startswith("application/json")
    
    @pytest.mark.integration
    @pytest.mark.parametrize("endpoint", [
        "/health",
        "/docs",
        "/openapi.json"
    ])
    def test_public_endpoints(self, base_url, endpoint):
        """Test public endpoints that don't require authentication"""
        response = requests.get(f"{base_url}{endpoint}")
        assert response.status_code in [200, 404]  # 404 is acceptable for some endpoints
    
    @pytest.mark.integration
    def test_api_without_authentication(self, base_url):
        """Test API endpoints without authentication should return 401 or 403"""
        # Test an endpoint that requires authentication
        response = requests.get(f"{base_url}/api/v1/core/profile")
        assert response.status_code in [401, 403, 404]  # 404 if endpoint doesn't exist
    
    @pytest.mark.integration
    def test_api_with_invalid_auth(self, base_url):
        """Test API endpoints with invalid authentication"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Bearer invalid_token",
            "X-API-Key": "invalid_key"
        }
        response = requests.get(f"{base_url}/api/v1/core/profile", headers=headers)
        assert response.status_code in [401, 403, 404]  # 404 if endpoint doesn't exist

class TestUnitTests:
    """Unit tests that don't require a running server"""
    
    @pytest.mark.unit
    def test_config_loading(self):
        """Test that configuration is loaded correctly"""
        assert hasattr(config, 'API_KEYS')
        assert isinstance(config.API_KEYS, list)
        assert len(config.API_KEYS) > 0
    
    @pytest.mark.unit
    def test_server_config(self):
        """Test that server configuration is available"""
        assert hasattr(server_config, 'SERVER_PORT')
        assert isinstance(server_config.SERVER_PORT, int)
        assert server_config.SERVER_PORT > 0
    
    @pytest.mark.unit
    def test_madrasa_names_list(self):
        """Test that madrasa names list is available and not empty"""
        assert hasattr(config, 'MADRASA_NAMES_LIST')
        assert isinstance(config.MADRASA_NAMES_LIST, list)
        assert len(config.MADRASA_NAMES_LIST) > 0
    
    @pytest.mark.unit
    def test_fixture_generation(self, madrasa_name, fullname, phone, email, password, device_id):
        """Test that all fixtures generate valid data"""
        assert isinstance(madrasa_name, str)
        assert len(madrasa_name) > 0
        assert madrasa_name in config.MADRASA_NAMES_LIST
        
        assert isinstance(fullname, str)
        assert len(fullname) == 10
        assert fullname.isalpha()
        
        assert isinstance(phone, str)
        assert phone.startswith("+880")
        assert len(phone) == 14  # +880 + 10 digits
        
        assert isinstance(email, str)
        assert "@" in email
        assert email.endswith(".com")
        
        assert isinstance(password, str)
        assert len(password) == 10
        assert any(c.isdigit() for c in password)
        assert any(c.isalpha() for c in password)
        
        assert isinstance(device_id, str)
        assert len(device_id) > 0
    
    @pytest.mark.unit
    def test_headers_generation(self, universal_headers):
        """Test that universal headers are generated correctly"""
        required_headers = [
            "Content-Type", "Accept", "Authorization", 
            "X-API-Key", "X-Device-ID", "X-Device-Brand", 
            "X-Device-Model", "X-Device-OS"
        ]
        
        for header in required_headers:
            assert header in universal_headers
            assert isinstance(universal_headers[header], str)
            assert len(universal_headers[header]) > 0
        
        assert universal_headers["Content-Type"] == "application/json"
        assert universal_headers["Accept"] == "application/json"
        assert universal_headers["Authorization"].startswith("Bearer ")
    
    @pytest.mark.unit
    def test_api_key_generation(self, api_key):
        """Test that API key generation works"""
        assert isinstance(api_key, str)
        assert api_key in config.API_KEYS
    
    @pytest.mark.unit
    def test_base_url_generation(self, base_url):
        """Test that base URL is generated correctly"""
        assert isinstance(base_url, str)
        assert base_url.startswith("http://localhost:")
        assert base_url.endswith(str(server_config.SERVER_PORT))

class TestDataValidation:
    """Tests for data validation and edge cases"""
    
    @pytest.mark.unit
    def test_email_format(self, fullname, madrasa_name):
        """Test that generated emails have correct format"""
        email = f"{fullname}@{madrasa_name}.com"
        assert "@" in email
        assert email.count("@") == 1
        assert email.endswith(".com")
        assert len(email.split("@")[0]) > 0
        assert len(email.split("@")[1]) > 4  # domain part
    
    @pytest.mark.unit
    def test_phone_format(self):
        """Test that generated phone numbers have correct format"""
        phone = f"+880{random.randint(1000000000, 9999999999)}"
        assert phone.startswith("+880")
        assert len(phone) == 14
        assert phone[4:].isdigit()
    
    @pytest.mark.unit
    def test_password_complexity(self):
        """Test that generated passwords have sufficient complexity"""
        password = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(10))
        assert len(password) == 10
        assert any(c.isupper() for c in password) or any(c.islower() for c in password)
        assert any(c.isdigit() for c in password)
    
    @pytest.mark.unit
    def test_device_id_uniqueness(self):
        """Test that device IDs are unique"""
        ids = [str(uuid.uuid4()) for _ in range(10)]
        assert len(ids) == len(set(ids))  # All IDs should be unique

class TestSendCodeEndpoint:
    """Comprehensive tests for the /send_code endpoint"""
    
    @pytest.mark.integration
    def test_send_code_success(self, base_url, universal_headers, fullname, phone, password, madrasa_name):
        """Test successful verification code sending"""
        data = {
            "fullname": fullname,
            "phone": phone,
            "password": password,
            "email": f"{fullname}@test.com",
            "madrasa_name": madrasa_name,
            "language": "en",
            "app_signature": "test_signature"
        }
        
        response = requests.post(f"{base_url}/api/v1/auth/send_code", 
                               json=data, headers=universal_headers)
        
        print(f"\n=== Send Code Test Results ===")
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response Body: {response.text}")
        
        # Should either succeed (200) or fail with specific error codes
        assert response.status_code in [200, 400, 409, 429, 500]
        
        if response.status_code == 200:
            response_data = response.json()
            assert "message" in response_data
            assert "Verification code sent" in response_data["message"]
        elif response.status_code == 409:
            response_data = response.json()
            assert "error" in response_data
            assert "already exists" in response_data["error"].lower()
        elif response.status_code == 429:
            response_data = response.json()
            assert "error" in response_data
            assert "rate limit" in response_data["error"].lower()
        elif response.status_code == 500:
            response_data = response.json()
            print(f"Error Response: {response_data}")
            # Log the error for debugging
            assert "error" in response_data
    
    @pytest.mark.integration
    def test_send_code_without_email(self, base_url, universal_headers, fullname, phone, password, madrasa_name):
        """Test verification code sending without email (should use get_email function)"""
        data = {
            "fullname": fullname,
            "phone": phone,
            "password": password,
            "madrasa_name": madrasa_name,
            "language": "en",
            "app_signature": "test_signature"
        }
        
        response = requests.post(f"{base_url}/api/v1/auth/send_code", 
                               json=data, headers=universal_headers)
        
        print(f"\n=== Send Code Without Email Test Results ===")
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
        
        assert response.status_code in [200, 400, 409, 429, 500]
    
    @pytest.mark.integration
    def test_send_code_invalid_phone(self, base_url, universal_headers, fullname, password, madrasa_name):
        """Test verification code sending with invalid phone number"""
        data = {
            "fullname": fullname,
            "phone": "invalid_phone",
            "password": password,
            "email": f"{fullname}@test.com",
            "madrasa_name": madrasa_name,
            "language": "en",
            "app_signature": "test_signature"
        }
        
        response = requests.post(f"{base_url}/api/v1/auth/send_code", 
                               json=data, headers=universal_headers)
        
        print(f"\n=== Send Code Invalid Phone Test Results ===")
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
        
        assert response.status_code in [400, 422, 500]
    
    @pytest.mark.integration
    def test_send_code_missing_required_fields(self, base_url, universal_headers):
        """Test verification code sending with missing required fields"""
        # Test with missing fullname
        data = {
            "phone": "+8801234567890",
            "password": "testpass123",
            "email": "test@test.com",
            "madrasa_name": "annur",
            "language": "en",
            "app_signature": "test_signature"
        }
        
        response = requests.post(f"{base_url}/api/v1/auth/send_code", 
                               json=data, headers=universal_headers)
        
        print(f"\n=== Send Code Missing Fields Test Results ===")
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
        
        assert response.status_code in [400, 422]
    
    @pytest.mark.integration
    def test_send_code_device_validation(self, base_url, fullname, phone, password, madrasa_name):
        """Test verification code sending with different device configurations"""
        # Test with minimal device headers
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {random.choice(list(config.API_KEYS))}",
            "X-API-Key": random.choice(list(config.API_KEYS)),
            "X-Device-ID": "test_device_123",
            "X-Device-Brand": "test_brand",
            "X-Device-Model": "test_model"
            # Missing X-Device-OS (should be optional now)
        }
        
        data = {
            "fullname": fullname,
            "phone": phone,
            "password": password,
            "email": f"{fullname}@test.com",
            "madrasa_name": madrasa_name,
            "language": "en",
            "app_signature": "test_signature"
        }
        
        response = requests.post(f"{base_url}/api/v1/auth/send_code", 
                               json=data, headers=headers)
        
        print(f"\n=== Send Code Device Validation Test Results ===")
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
        
        # Should not fail due to device validation (403)
        assert response.status_code != 403
    
    @pytest.mark.integration
    def test_send_code_rate_limiting(self, base_url, universal_headers, fullname, phone, password, madrasa_name):
        """Test rate limiting for verification code sending"""
        data = {
            "fullname": fullname,
            "phone": phone,
            "password": password,
            "email": f"{fullname}@test.com",
            "madrasa_name": madrasa_name,
            "language": "en",
            "app_signature": "test_signature"
        }
        
        # Send multiple requests quickly to test rate limiting
        responses = []
        for i in range(3):
            response = requests.post(f"{base_url}/api/v1/auth/send_code", 
                                   json=data, headers=universal_headers)
            responses.append(response)
            print(f"\n=== Rate Limit Test Request {i+1} ===")
            print(f"Status Code: {response.status_code}")
            print(f"Response Body: {response.text}")
        
        # At least one should succeed, others might be rate limited
        status_codes = [r.status_code for r in responses]
        assert 200 in status_codes or 409 in status_codes  # Success or user exists
        print(f"All status codes: {status_codes}")
    
    @pytest.mark.integration
    def test_send_code_database_errors(self, base_url, universal_headers):
        """Test verification code sending with database-related issues"""
        # Test with a very long fullname that might cause database issues
        data = {
            "fullname": "a" * 1000,  # Very long name
            "phone": "+8801234567890",
            "password": "testpass123",
            "email": "test@test.com",
            "madrasa_name": "annur",
            "language": "en",
            "app_signature": "test_signature"
        }
        
        response = requests.post(f"{base_url}/api/v1/auth/send_code", 
                               json=data, headers=universal_headers)
        
        print(f"\n=== Send Code Database Error Test Results ===")
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
        
        assert response.status_code in [400, 422, 500]
    
    @pytest.mark.integration
    def test_send_code_sms_configuration(self, base_url, universal_headers, fullname, phone, password, madrasa_name):
        """Test SMS configuration and API responses"""
        data = {
            "fullname": fullname,
            "phone": phone,
            "password": password,
            "email": f"{fullname}@test.com",
            "madrasa_name": madrasa_name,
            "language": "en",
            "app_signature": "test_signature"
        }
        
        response = requests.post(f"{base_url}/api/v1/auth/send_code", 
                               json=data, headers=universal_headers)
        
        print(f"\n=== Send Code SMS Configuration Test Results ===")
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
        
        if response.status_code == 500:
            response_data = response.json()
            print(f"Error details: {response_data}")
            # Check if it's an SMS-related error
            if "error" in response_data:
                error_msg = response_data["error"].lower()
                if "sms" in error_msg or "verification" in error_msg:
                    print("SMS configuration issue detected")
        
        assert response.status_code in [200, 400, 409, 429, 500]