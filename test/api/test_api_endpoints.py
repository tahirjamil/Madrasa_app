#!/usr/bin/env python3
"""
API Endpoint Testing Suite
=========================

Comprehensive testing of all API endpoints using actual HTTP requests.
Tests various scenarios including success cases, error cases, and edge cases.
"""
import sys
import time
import random
import string
import asyncio
import aiohttp
from typing import Dict, Any, List, Optional
from utils.helpers.improved_functions import get_project_root

# Add project root to path to import modules
sys.path.append(str(get_project_root()))

class Colors:
    """Terminal colors for output"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class APITester:
    """Comprehensive API endpoint tester"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = None
        self.results = []
        self.auth_token = None
        self.test_user_phone = None
        self.test_user_fullname = None
        
    async def setup(self):
        """Initialize session"""
        self.session = aiohttp.ClientSession()
        
    async def teardown(self):
        """Clean up session"""
        if self.session:
            await self.session.close()
    
    def generate_test_data(self) -> Dict[str, Any]:
        """Generate random test data"""
        random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        phone = f"017{random.randint(10000000, 99999999)}"
        
        return {
            "fullname": f"test_user_{random_suffix}",
            "phone": phone,
            "password": "TestPass123!@#",
            "email": f"test_{random_suffix}@example.com",
            "device_id": f"device_{random_suffix}",
            "ip_address": f"192.168.1.{random.randint(1, 255)}"
        }
    
    async def test_endpoint(self, method: str, path: str, data: Optional[Dict[str, Any]] = None, 
                          headers: Optional[Dict[str, Any]] = None, expected_status: Optional[List[int]] = None) -> Dict[str, Any]:
        """Test a single endpoint"""
        url = f"{self.base_url}{path}"
        
        if expected_status is None:
            expected_status = [x for x in range(200, 300)]
        
        try:
            start_time = time.time()

            if not self.session:
                raise RuntimeError("Session not initialized")
            
            # Make request
            async with self.session.request(
                method=method,
                url=url,
                json=data,
                headers=headers or {}
            ) as response:
                duration = time.time() - start_time
                
                # Get response data
                try:
                    response_data = await response.json()
                except:
                    response_data = await response.text()
                
                result = {
                    "endpoint": f"{method} {path}",
                    "status": response.status,
                    "success": response.status in expected_status,
                    "duration": duration,
                    "data": response_data,
                    "headers": dict(response.headers)
                }
                
                # Print result
                if result["success"]:
                    print(f"{Colors.OKGREEN}✓{Colors.ENDC} {method} {path} - {response.status} ({duration:.2f}s)")
                else:
                    print(f"{Colors.FAIL}✗{Colors.ENDC} {method} {path} - {response.status} ({duration:.2f}s)")
                    if isinstance(response_data, dict) and "message" in response_data:
                        print(f"  {Colors.WARNING}→ {response_data['message']}{Colors.ENDC}")
                
                self.results.append(result)
                return result
                
        except aiohttp.ClientConnectorError:
            result = {
                "endpoint": f"{method} {path}",
                "status": 0,
                "success": False,
                "duration": 0,
                "data": {"error": "Connection failed - is the server running?"},
                "headers": {}
            }
            print(f"{Colors.FAIL}✗{Colors.ENDC} {method} {path} - Connection failed")
            self.results.append(result)
            return result
        except Exception as e:
            result = {
                "endpoint": f"{method} {path}",
                "status": 0,
                "success": False,
                "duration": 0,
                "data": {"error": str(e)},
                "headers": {}
            }
            print(f"{Colors.FAIL}✗{Colors.ENDC} {method} {path} - Error: {str(e)}")
            self.results.append(result)
            return result
    
    async def test_auth_flow(self):
        """Test complete authentication flow"""
        print(f"\n{Colors.HEADER}=== Testing Authentication Flow ==={Colors.ENDC}")
        
        # Generate test user data
        test_data = self.generate_test_data()
        self.test_user_phone = test_data["phone"]
        self.test_user_fullname = test_data["fullname"]
        
        # 1. Test registration
        print(f"\n{Colors.OKBLUE}1. Testing Registration{Colors.ENDC}")
        register_result = await self.test_endpoint(
            "POST", "/register",
            data=test_data,
            expected_status=[201, 409]  # 409 if already exists
        )
        
        # 2. Test login
        print(f"\n{Colors.OKBLUE}2. Testing Login{Colors.ENDC}")
        login_data = {
            "phone": test_data["phone"],
            "password": test_data["password"],
            "device_id": test_data["device_id"]
        }
        login_result = await self.test_endpoint(
            "POST", "/login",
            data=login_data,
            expected_status=[200, 401]
        )
        
        # Save auth token if login successful
        if login_result["success"] and isinstance(login_result["data"], dict):
            self.auth_token = login_result["data"].get("token")
        
        # 3. Test send code
        print(f"\n{Colors.OKBLUE}3. Testing Send Verification Code{Colors.ENDC}")
        await self.test_endpoint(
            "POST", "/send_code",
            data={"phone": test_data["phone"]},
            expected_status=[200, 429]  # 429 if rate limited
        )
        
        # 4. Test reset password
        print(f"\n{Colors.OKBLUE}4. Testing Reset Password{Colors.ENDC}")
        reset_data = {
            "phone": test_data["phone"],
            "new_password": "NewPass123!@#",
            "code": "123456"  # Would need real code in production
        }
        await self.test_endpoint(
            "POST", "/reset_password",
            data=reset_data,
            expected_status=[200, 400, 401]
        )
        
        # 5. Test account check
        print(f"\n{Colors.OKBLUE}5. Testing Account Check{Colors.ENDC}")
        await self.test_endpoint(
            "POST", "/account/check",
            data={"phone": test_data["phone"]},
            expected_status=[200]
        )
    
    async def test_data_endpoints(self):
        """Test data retrieval endpoints"""
        print(f"\n{Colors.HEADER}=== Testing Data Endpoints ==={Colors.ENDC}")
        
        # Test with auth headers if we have a token
        headers = {"Authorization": f"Bearer {self.auth_token}"} if self.auth_token else {}
        
        # 1. Test members endpoint
        print(f"\n{Colors.OKBLUE}1. Testing Members Endpoint{Colors.ENDC}")
        await self.test_endpoint(
            "POST", "/members",
            data={"updatedSince": None},
            headers=headers,
            expected_status=[200]
        )
        
        # 2. Test routines endpoint
        print(f"\n{Colors.OKBLUE}2. Testing Routines Endpoint{Colors.ENDC}")
        await self.test_endpoint(
            "POST", "/routines",
            data={"updatedSince": None},
            headers=headers,
            expected_status=[200]
        )
        
        # 3. Test events endpoint
        print(f"\n{Colors.OKBLUE}3. Testing Events Endpoint{Colors.ENDC}")
        await self.test_endpoint(
            "POST", "/events",
            data={"updatedSince": None},
            headers=headers,
            expected_status=[200]
        )
        
        # 4. Test exams endpoint
        print(f"\n{Colors.OKBLUE}4. Testing Exams Endpoint{Colors.ENDC}")
        await self.test_endpoint(
            "POST", "/exams",
            data={"updatedSince": None},
            headers=headers,
            expected_status=[200]
        )
    
    async def test_payment_endpoints(self):
        """Test payment-related endpoints"""
        print(f"\n{Colors.HEADER}=== Testing Payment Endpoints ==={Colors.ENDC}")
        
        if not self.test_user_phone:
            print(f"{Colors.WARNING}Skipping payment tests - no test user created{Colors.ENDC}")
            return
        
        # 1. Test due payments
        print(f"\n{Colors.OKBLUE}1. Testing Due Payments{Colors.ENDC}")
        await self.test_endpoint(
            "POST", "/due_payments",
            data={
                "phone": self.test_user_phone,
                "fullname": self.test_user_fullname
            },
            expected_status=[200, 404]
        )
        
        # 2. Test get transactions
        print(f"\n{Colors.OKBLUE}2. Testing Get Transactions{Colors.ENDC}")
        await self.test_endpoint(
            "POST", "/get_transactions",
            data={
                "phone": self.test_user_phone,
                "fullname": self.test_user_fullname
            },
            expected_status=[200]
        )
    
    async def test_error_handling(self):
        """Test error handling and edge cases"""
        print(f"\n{Colors.HEADER}=== Testing Error Handling ==={Colors.ENDC}")
        
        # 1. Test missing required fields
        print(f"\n{Colors.OKBLUE}1. Testing Missing Required Fields{Colors.ENDC}")
        await self.test_endpoint(
            "POST", "/register",
            data={"phone": "01712345678"},  # Missing other required fields
            expected_status=[400]
        )
        
        # 2. Test invalid data formats
        print(f"\n{Colors.OKBLUE}2. Testing Invalid Data Formats{Colors.ENDC}")
        await self.test_endpoint(
            "POST", "/register",
            data={
                "fullname": "test",
                "phone": "invalid_phone",
                "password": "weak",
                "email": "not-an-email"
            },
            expected_status=[400]
        )
        
        # 3. Test SQL injection attempts
        print(f"\n{Colors.OKBLUE}3. Testing SQL Injection Protection{Colors.ENDC}")
        await self.test_endpoint(
            "POST", "/login",
            data={
                "phone": "' OR '1'='1",
                "password": "' OR '1'='1"
            },
            expected_status=[400, 401]
        )
        
        # 4. Test XSS attempts
        print(f"\n{Colors.OKBLUE}4. Testing XSS Protection{Colors.ENDC}")
        await self.test_endpoint(
            "POST", "/add_people",
            data={
                "name_en": "<script>alert('xss')</script>",
                "phone": "01712345678",
                "acc_type": "student"
            },
            expected_status=[400, 401]
        )
        
        # 5. Test rate limiting
        print(f"\n{Colors.OKBLUE}5. Testing Rate Limiting{Colors.ENDC}")
        for i in range(12):  # Exceed typical rate limit
            result = await self.test_endpoint(
                "POST", "/send_code",
                data={"phone": "01712345678"},
                expected_status=[200, 429]
            )
            if result["status"] == 429:
                print(f"  {Colors.OKGREEN}→ Rate limiting working correctly{Colors.ENDC}")
                break
    
    async def test_file_endpoints(self):
        """Test file serving endpoints"""
        print(f"\n{Colors.HEADER}=== Testing File Endpoints ==={Colors.ENDC}")
        
        # Test various file endpoints
        file_tests = [
            ("/uploads/profile_img/test.jpg", [404]),
            ("/uploads/notices/test.pdf", [404]),
            ("/uploads/exam_results/test.pdf", [404]),
            ("/uploads/gallery/male/hifz/test.jpg", [404]),
        ]
        
        for path, expected_status in file_tests:
            await self.test_endpoint("GET", path, expected_status=expected_status)
    
    async def test_web_routes(self):
        """Test web page routes"""
        print(f"\n{Colors.HEADER}=== Testing Web Routes ==={Colors.ENDC}")
        
        web_routes = [
            ("/", [200]),
            ("/donate", [200]),
            ("/contact", [200]),
            ("/privacy", [200]),
            ("/terms", [200]),
        ]
        
        for path, expected_status in web_routes:
            await self.test_endpoint("GET", path, expected_status=expected_status)
    
    def print_summary(self):
        """Print test summary"""
        print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
        print(f"{Colors.HEADER}{'TEST SUMMARY':^60}{Colors.ENDC}")
        print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}\n")
        
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r["success"])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {Colors.OKGREEN}{passed_tests}{Colors.ENDC}")
        print(f"Failed: {Colors.FAIL}{failed_tests}{Colors.ENDC}")
        
        # Show response time statistics
        response_times = [r["duration"] for r in self.results if r["duration"] > 0]
        if response_times:
            avg_time = sum(response_times) / len(response_times)
            max_time = max(response_times)
            min_time = min(response_times)
            print(f"\nResponse Times:")
            print(f"  Average: {avg_time:.3f}s")
            print(f"  Min: {min_time:.3f}s")
            print(f"  Max: {max_time:.3f}s")
        
        # Show failed endpoints
        if failed_tests > 0:
            print(f"\n{Colors.FAIL}Failed Endpoints:{Colors.ENDC}")
            for result in self.results:
                if not result["success"]:
                    print(f"  - {result['endpoint']} (Status: {result['status']})")
                    if isinstance(result["data"], dict) and "error" in result["data"]:
                        print(f"    Error: {result['data']['error']}")
        
        # Check if server is running
        connection_failures = sum(1 for r in self.results if r["status"] == 0)
        if connection_failures > 0:
            print(f"\n{Colors.WARNING}⚠️  Server Connection Issues:{Colors.ENDC}")
            print(f"  {connection_failures} requests failed to connect")
            print(f"  Make sure the server is running on {self.base_url}")
        
        return passed_tests == total_tests


async def main():
    """Run all API tests"""
    print(f"{Colors.HEADER}{Colors.BOLD}")
    print("╔════════════════════════════════════════════════════════════╗")
    print("║              API ENDPOINT TESTING SUITE                    ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print(f"{Colors.ENDC}")
    
    # Check if custom URL is provided
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    print(f"Testing server at: {Colors.OKBLUE}{base_url}{Colors.ENDC}")
    
    # Create tester
    tester = APITester(base_url)
    
    try:
        await tester.setup()
        
        # Run all test suites
        await tester.test_web_routes()
        await tester.test_auth_flow()
        await tester.test_data_endpoints()
        await tester.test_payment_endpoints()
        await tester.test_file_endpoints()
        await tester.test_error_handling()
        
        # Print summary
        success = tester.print_summary()
        
        if success:
            print(f"\n{Colors.OKGREEN}{Colors.BOLD}✅ All tests passed!{Colors.ENDC}")
        else:
            print(f"\n{Colors.FAIL}{Colors.BOLD}❌ Some tests failed!{Colors.ENDC}")
        
        return success
        
    finally:
        await tester.teardown()


if __name__ == "__main__":
    # Run the async main function
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
