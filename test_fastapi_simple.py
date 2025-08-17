#!/usr/bin/env python3
"""
Simple test script for FastAPI endpoints using urllib (no external dependencies)
Tests for the specific errors that were reported:
1. Static route errors
2. SessionMiddleware errors on /admin/login
3. Internal server errors on /contact
"""

import urllib.request
import urllib.parse
import urllib.error
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

def test_endpoint(method, path, expected_status=200, data=None):
    """Test a single endpoint"""
    url = f"{BASE_URL}{path}"
    try:
        if method.upper() == "POST" and data:
            # Encode data for POST request
            encoded_data = urllib.parse.urlencode(data).encode('utf-8')
            request = urllib.request.Request(url, data=encoded_data, method=method)
        else:
            request = urllib.request.Request(url, method=method)
        
        try:
            response = urllib.request.urlopen(request, timeout=TIMEOUT)
            status_code = response.getcode()
            content = response.read().decode('utf-8')
            headers = dict(response.headers)
        except urllib.error.HTTPError as e:
            status_code = e.code
            content = e.read().decode('utf-8')
            headers = dict(e.headers)
        
        # Check status code
        status_ok = status_code == expected_status
        print_result(status_ok, f"{method} {path} - Status: {status_code} (expected: {expected_status})")
        
        # Check for common error patterns
        content_lower = content.lower()
        errors = []
        
        if "internal server error" in content_lower and expected_status != 500:
            errors.append("Contains 'internal server error'")
        if "nomatchfound" in content_lower:
            errors.append("Contains 'NoMatchFound' error")
        if "sessionmiddleware must be installed" in content_lower:
            errors.append("SessionMiddleware error")
        if "nonetype" in content_lower and "split" in content_lower:
            errors.append("NoneType split error")
        if "traceback" in content_lower:
            errors.append("Contains Python traceback")
        
        if errors:
            print_result(False, f"  Error patterns found: {', '.join(errors)}")
            print(f"  {YELLOW}First 200 chars of response: {content[:200]}...{RESET}")
        
        # Check JSON response if expected
        if headers.get('content-type', '').startswith('application/json'):
            try:
                json_data = json.loads(content)
                print_result(True, f"  Valid JSON response")
                
                # Check for error flags in JSON
                if isinstance(json_data, dict):
                    if json_data.get('error') and not json_data.get('success'):
                        print_result(False, f"  JSON indicates error: {json_data.get('message', 'Unknown error')}")
                        if json_data.get('details'):
                            print(f"  {YELLOW}Details: {json_data.get('details')}{RESET}")
            except json.JSONDecodeError:
                print_result(False, f"  Invalid JSON in response")
        
        return content, status_ok and not errors
        
    except urllib.error.URLError as e:
        if "Connection refused" in str(e):
            print_result(False, f"{method} {path} - Connection refused (is the server running?)")
        else:
            print_result(False, f"{method} {path} - URLError: {str(e)}")
        return None, False
    except Exception as e:
        print_result(False, f"{method} {path} - Error: {str(e)}")
        return None, False

def test_health():
    """Test health endpoint"""
    print_test_header("Health Check")
    
    content, success = test_endpoint("GET", "/health")
    if content and success:
        try:
            data = json.loads(content)
            print(f"  {YELLOW}Server version: {data.get('version', 'Unknown')}{RESET}")
            print(f"  {YELLOW}Status: {data.get('status', 'Unknown')}{RESET}")
            print(f"  {YELLOW}Uptime: {data.get('uptime', 0):.2f}s{RESET}")
        except:
            pass
    return success

def test_static_files():
    """Test static file serving"""
    print_test_header("Static Files")
    
    # Test favicon (should be served directly)
    content1, success1 = test_endpoint("GET", "/favicon.ico")
    if success1:
        print_result(True, "  Favicon endpoint works")
    
    # Test static directory
    content2, success2 = test_endpoint("GET", "/static/favicon.ico")
    if success2:
        print_result(True, "  Static mount works")
    
    return success1 and success2

def test_admin_login():
    """Test admin login route"""
    print_test_header("Admin Login Route")
    
    # Test GET request
    content, success = test_endpoint("GET", "/admin/login")
    if content and success:
        # Check if it's HTML
        if "<!DOCTYPE html>" in content or "<html" in content:
            print_result(True, "  Login page returns HTML")
            
            # Check for static URL resolution
            if 'href="/static/' in content or 'src="/static/' in content:
                print_result(True, "  Static URLs properly resolved (url_for works)")
            else:
                print_result(False, "  No static URLs found (url_for might not be working)")
                
            # Check for session-related errors in content
            if "sessionmiddleware" not in content.lower():
                print_result(True, "  No SessionMiddleware errors")
            else:
                print_result(False, "  SessionMiddleware error found in response")
        else:
            print_result(False, "  Login page doesn't return HTML")
            print(f"  {YELLOW}Response type: {content[:100]}...{RESET}")
    
    return success

def test_contact_route():
    """Test contact route"""
    print_test_header("Contact Route")
    
    # Test GET request
    content, success = test_endpoint("GET", "/contact")
    if content and success:
        if "<!DOCTYPE html>" in content or "<html" in content:
            print_result(True, "  Contact page returns HTML")
            
            # Check for NoneType errors
            if "nonetype" not in content.lower():
                print_result(True, "  No NoneType errors")
            else:
                print_result(False, "  NoneType error found in response")
        else:
            print_result(False, "  Contact page doesn't return HTML")
    
    # Test POST request
    contact_data = {
        "fullname": "Test User",
        "email_or_phone": "test@example.com",
        "description": "This is a test message"
    }
    content2, success2 = test_endpoint("POST", "/contact", data=contact_data)
    
    return success and success2

def test_other_routes():
    """Test other main routes"""
    print_test_header("Other Web Routes")
    
    routes = [
        ("/", "Home"),
        ("/donate", "Donate"),
        ("/privacy", "Privacy"),
        ("/terms", "Terms")
    ]
    
    all_success = True
    for path, name in routes:
        content, success = test_endpoint("GET", path)
        if content and "<!DOCTYPE html>" in content:
            print_result(True, f"  {name} page returns HTML")
        all_success = all_success and success
    
    return all_success

def main():
    """Run all tests"""
    print(f"{BLUE}FastAPI Migration Test Suite (Simple){RESET}")
    print(f"{BLUE}Testing server at: {BASE_URL}{RESET}")
    print(f"{BLUE}Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{RESET}")
    
    # Check if server is running
    print_test_header("Server Connection")
    try:
        request = urllib.request.Request(f"{BASE_URL}/health")
        response = urllib.request.urlopen(request, timeout=2)
        print_result(True, "Server is responding")
    except:
        print_result(False, "Server is not responding. Please start the server first.")
        print(f"\n{YELLOW}To start the server, you need to:{RESET}")
        print(f"1. Install dependencies:")
        print(f"   pip install -r requirements.txt")
        print(f"2. Set test mode and run:")
        print(f"   export TEST_MODE=true")
        print(f"   python3 run_server.py")
        print(f"\n{YELLOW}Or with uvicorn directly:{RESET}")
        print(f"   export TEST_MODE=true")
        print(f"   uvicorn app:app --host 0.0.0.0 --port 5111")
        return 1
    
    # Run all tests
    print(f"\n{BLUE}Running tests for reported issues...{RESET}")
    
    test_results = {
        "Health Check": test_health(),
        "Static Files (NoMatchFound fix)": test_static_files(),
        "Admin Login (SessionMiddleware fix)": test_admin_login(),
        "Contact Route (NoneType fix)": test_contact_route(),
        "Other Routes": test_other_routes(),
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
    
    # Specific error check summary
    print(f"\n{BLUE}Specific Error Fixes:{RESET}")
    print(f"1. Static route 'NoMatchFound' error: {'✓ Fixed' if test_results.get('Static Files (NoMatchFound fix)') else '✗ Still present'}")
    print(f"2. SessionMiddleware error: {'✓ Fixed' if test_results.get('Admin Login (SessionMiddleware fix)') else '✗ Still present'}")
    print(f"3. Contact route internal error: {'✓ Fixed' if test_results.get('Contact Route (NoneType fix)') else '✗ Still present'}")
    
    if passed == total:
        print(f"\n{GREEN}All tests passed! The FastAPI migration fixes are working correctly.{RESET}")
        return 0
    else:
        print(f"\n{RED}Some tests failed. Please check the errors above.{RESET}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
