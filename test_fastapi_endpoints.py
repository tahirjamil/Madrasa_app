#!/usr/bin/env python3
"""
Test script for FastAPI endpoints after migration fixes
Tests for the specific errors that were reported:
1. Static route errors
2. SessionMiddleware errors on /admin/login
3. Internal server errors on /contact
"""

import requests
import json
import sys
from datetime import datetime

# Server configuration
BASE_URL = "http://localhost:5111"
TIMEOUT = 5

# Color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_test_header(test_name):
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Testing: {test_name}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")

def print_result(success, message):
    if success:
        print(f"{GREEN}✓ {message}{RESET}")
    else:
        print(f"{RED}✗ {message}{RESET}")

def test_endpoint(method, path, expected_status=200, data=None, check_json=True):
    """Test a single endpoint"""
    url = f"{BASE_URL}{path}"
    try:
        if method.upper() == "GET":
            response = requests.get(url, timeout=TIMEOUT)
        elif method.upper() == "POST":
            response = requests.post(url, data=data, timeout=TIMEOUT)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        # Check status code
        status_ok = response.status_code == expected_status
        print_result(status_ok, f"{method} {path} - Status: {response.status_code} (expected: {expected_status})")
        
        # Check for common error patterns
        content = response.text.lower()
        errors = []
        
        if "internal server error" in content and expected_status != 500:
            errors.append("Contains 'internal server error'")
        if "nomatchfound" in content:
            errors.append("Contains 'NoMatchFound' error")
        if "sessionmiddleware must be installed" in content:
            errors.append("SessionMiddleware error")
        if "nonetype" in content and "split" in content:
            errors.append("NoneType split error")
        if "traceback" in content:
            errors.append("Contains Python traceback")
        
        if errors:
            print_result(False, f"  Error patterns found: {', '.join(errors)}")
        
        # Check JSON response if expected
        if check_json and response.headers.get('content-type', '').startswith('application/json'):
            try:
                json_data = response.json()
                print_result(True, f"  Valid JSON response")
                
                # Check for error flags in JSON
                if isinstance(json_data, dict):
                    if json_data.get('error') and not json_data.get('success'):
                        print_result(False, f"  JSON indicates error: {json_data.get('message', 'Unknown error')}")
            except json.JSONDecodeError:
                print_result(False, f"  Invalid JSON in response")
        
        return response, status_ok and not errors
        
    except requests.exceptions.Timeout:
        print_result(False, f"{method} {path} - Timeout after {TIMEOUT}s")
        return None, False
    except requests.exceptions.ConnectionError:
        print_result(False, f"{method} {path} - Connection refused (is the server running?)")
        return None, False
    except Exception as e:
        print_result(False, f"{method} {path} - Error: {str(e)}")
        return None, False

def test_static_files():
    """Test static file serving"""
    print_test_header("Static Files")
    
    # Test favicon (common static file)
    response, success = test_endpoint("GET", "/favicon.ico", check_json=False)
    if response and response.status_code == 200:
        print_result(True, "  Static file serving works")
    
    # Test static directory
    response, success = test_endpoint("GET", "/static/favicon.ico", check_json=False)
    
    return success

def test_health_endpoint():
    """Test health check endpoint"""
    print_test_header("Health Check")
    
    response, success = test_endpoint("GET", "/health")
    if response and success:
        try:
            data = response.json()
            print(f"  {YELLOW}Server version: {data.get('version', 'Unknown')}{RESET}")
            print(f"  {YELLOW}Status: {data.get('status', 'Unknown')}{RESET}")
            print(f"  {YELLOW}Uptime: {data.get('uptime', 0):.2f}s{RESET}")
        except:
            pass
    
    return success

def test_admin_routes():
    """Test admin routes"""
    print_test_header("Admin Routes")
    
    # Test login page (GET)
    response, success1 = test_endpoint("GET", "/admin/login", check_json=False)
    if response and response.status_code == 200:
        # Check if it's HTML and contains expected elements
        if "<!DOCTYPE html>" in response.text:
            print_result(True, "  Login page returns HTML")
            
            # Check for url_for('static') usage
            if "href=\"/static/" in response.text or "src=\"/static/" in response.text:
                print_result(True, "  Static URLs properly resolved in template")
            else:
                print_result(False, "  No static URLs found in template")
        else:
            print_result(False, "  Login page doesn't return HTML")
    
    # Test login POST (with invalid credentials to test form handling)
    login_data = {
        "username": "test",
        "password": "test",
        "g-recaptcha-response": ""
    }
    response, success2 = test_endpoint("POST", "/admin/login", expected_status=200, data=login_data, check_json=False)
    
    return success1 and success2

def test_web_routes():
    """Test public web routes"""
    print_test_header("Web Routes")
    
    routes = [
        ("/", "Home page"),
        ("/contact", "Contact page"),
        ("/donate", "Donate page"),
        ("/privacy", "Privacy page"),
        ("/terms", "Terms page")
    ]
    
    all_success = True
    for route, name in routes:
        response, success = test_endpoint("GET", route, check_json=False)
        if response and response.status_code == 200:
            if "<!DOCTYPE html>" in response.text:
                print_result(True, f"  {name} returns HTML")
            else:
                print_result(False, f"  {name} doesn't return HTML")
        all_success = all_success and success
    
    return all_success

def test_api_routes():
    """Test API routes"""
    print_test_header("API Routes")
    
    # Test a basic API endpoint
    response, success = test_endpoint("GET", "/api/v1/health", expected_status=200)
    
    return success

def test_contact_form():
    """Test contact form submission"""
    print_test_header("Contact Form POST")
    
    # Test with valid data
    contact_data = {
        "fullname": "Test User",
        "email_or_phone": "test@example.com",
        "description": "This is a test message"
    }
    
    response, success = test_endpoint("POST", "/contact", data=contact_data, check_json=False)
    
    return success

def main():
    """Run all tests"""
    print(f"{BLUE}FastAPI Migration Test Suite{RESET}")
    print(f"{BLUE}Testing server at: {BASE_URL}{RESET}")
    print(f"{BLUE}Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{RESET}")
    
    # Check if server is running
    print_test_header("Server Connection")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        print_result(True, "Server is responding")
    except:
        print_result(False, "Server is not responding. Please start the server first.")
        print(f"\n{YELLOW}To start the server, run:{RESET}")
        print(f"  export TEST_MODE=true")
        print(f"  python3 run_server.py")
        print(f"\n{YELLOW}Or with uvicorn:{RESET}")
        print(f"  export TEST_MODE=true")
        print(f"  uvicorn app:app --host 0.0.0.0 --port 5111")
        return 1
    
    # Run all tests
    test_results = {
        "Health Check": test_health_endpoint(),
        "Static Files": test_static_files(),
        "Admin Routes": test_admin_routes(),
        "Web Routes": test_web_routes(),
        "Contact Form": test_contact_form(),
    }
    
    # Summary
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Test Summary{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")
    
    passed = sum(1 for v in test_results.values() if v)
    total = len(test_results)
    
    for test_name, result in test_results.items():
        status = f"{GREEN}PASSED{RESET}" if result else f"{RED}FAILED{RESET}"
        print(f"{test_name}: {status}")
    
    print(f"\n{BLUE}Total: {passed}/{total} tests passed{RESET}")
    
    if passed == total:
        print(f"\n{GREEN}All tests passed! The FastAPI migration fixes are working correctly.{RESET}")
        return 0
    else:
        print(f"\n{RED}Some tests failed. Please check the errors above.{RESET}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
