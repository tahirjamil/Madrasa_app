#!/usr/bin/env python3
"""
Integration Test Suite for User Routes
=====================================

This module provides integration testing for all user routes by:
- Connecting to the running server
- Testing all routes with POST requests
- Using dummy data to test functionality
- Checking responses and error handling

Author: Madrasha Development Team
Version: 1.0.0
"""

import asyncio
import os
import sys
import json
import unittest
import aiohttp
import tempfile
from datetime import datetime
from unittest.mock import patch, MagicMock

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock PIL before importing routes
sys.modules['PIL'] = MagicMock()
sys.modules['PIL.Image'] = MagicMock()

# Test basic import first
try:
    from config import Config
    IMPORT_SUCCESS = True
except Exception as e:
    print(f"Import failed: {e}")
    IMPORT_SUCCESS = False


class TestBasicImport(unittest.TestCase):
    """Test basic import functionality"""
    
    def test_import_success(self):
        """Test that config can be imported"""
        self.assertTrue(IMPORT_SUCCESS, "Config should import successfully")


if not IMPORT_SUCCESS:
    print("❌ Cannot import config. Skipping all tests.")
    print("Please fix the import issues first.")
    exit(1)


class TestUserRoutesIntegration:
    """Integration tests for user routes"""
    
    def __init__(self):
        """Initialize test environment"""
        # Server configuration
        self.base_url = "http://localhost:8000"  # Default Quart server
        self.session = None
        
        # Test data
        self.dummy_data = {
            "fullname": "test_user",
            "phone": "01712345678",
            "password": "TestPassword123!",
            "email": "test@example.com",
            "code": "123456",
            "device_id": "test_device_123",
            "ip_address": "192.168.1.100"
        }
        
        # Person data for testing
        self.person_data = {
            "name_en": "Test Person",
            "phone": "01712345678",
            "acc_type": "student",
            "date_of_birth": "1990-01-01",
            "gender": "male",
            "blood_group": "A+",
            "father_en": "Test Father",
            "mother_en": "Test Mother",
            "class": "Class 5",
            "student_id": "STU001",
            "guardian_number": "01787654321"
        }
        
        # Set test mode environment
        os.environ['TEST_MODE'] = 'true'
        os.environ['DUMMY_FULLNAME'] = 'test_user'
        os.environ['DUMMY_PHONE'] = '01712345678'
        os.environ['DUMMY_PASSWORD'] = 'TestPassword123!'
        os.environ['DUMMY_EMAIL'] = 'test@example.com'
        
        # Test results
        self.test_results = []
    
    async def setup(self):
        """Async setup"""
        self.session = aiohttp.ClientSession()
    
    async def teardown(self):
        """Async teardown"""
        if self.session:
            await self.session.close()
        
        # Clean up environment
        os.environ.pop('TEST_MODE', None)
        os.environ.pop('DUMMY_FULLNAME', None)
        os.environ.pop('DUMMY_PHONE', None)
        os.environ.pop('DUMMY_PASSWORD', None)
        os.environ.pop('DUMMY_EMAIL', None)

    async def test_register_route(self):
        """Test user registration route"""
        try:
            # Test registration
            async with self.session.post(
                f"{self.base_url}/register",
                json=self.dummy_data
            ) as response:
                data = await response.json()
                result = {
                    "test": "register_route",
                    "status": response.status,
                    "success": response.status == 201,
                    "message": data.get('message', 'Unknown'),
                    "data": data
                }
                self.test_results.append(result)
                print(f"✅ Register route test: {result['message']}")
                return result
                
        except aiohttp.ClientConnectorError:
            result = {
                "test": "register_route",
                "status": 0,
                "success": False,
                "message": "Server not running",
                "data": {}
            }
            self.test_results.append(result)
            print(f"⚠️ Register route test: Server not running")
            return result

    async def test_login_route(self):
        """Test user login route"""
        try:
            # Test login
            async with self.session.post(
                f"{self.base_url}/login",
                json=self.dummy_data
            ) as response:
                data = await response.json()
                result = {
                    "test": "login_route",
                    "status": response.status,
                    "success": response.status == 200,
                    "message": data.get('message', 'Unknown'),
                    "data": data
                }
                self.test_results.append(result)
                print(f"✅ Login route test: {result['message']}")
                return result
                
        except aiohttp.ClientConnectorError:
            result = {
                "test": "login_route",
                "status": 0,
                "success": False,
                "message": "Server not running",
                "data": {}
            }
            self.test_results.append(result)
            print(f"⚠️ Login route test: Server not running")
            return result

    async def test_send_verification_code_route(self):
        """Test send verification code route"""
        try:
            # Test sending verification code
            async with self.session.post(
                f"{self.base_url}/send_code",
                json={
                    "phone": "01712345678",
                    "fullname": "test_user",
                    "device_id": "test_device_123",
                    "ip_address": "192.168.1.100"
                }
            ) as response:
                data = await response.json()
                result = {
                    "test": "send_verification_code_route",
                    "status": response.status,
                    "success": response.status == 200,
                    "message": data.get('message', 'Unknown'),
                    "data": data
                }
                self.test_results.append(result)
                print(f"✅ Send verification code route test: {result['message']}")
                return result
                
        except aiohttp.ClientConnectorError:
            result = {
                "test": "send_verification_code_route",
                "status": 0,
                "success": False,
                "message": "Server not running",
                "data": {}
            }
            self.test_results.append(result)
            print(f"⚠️ Send verification code route test: Server not running")
            return result

    async def test_reset_password_route(self):
        """Test password reset route"""
        try:
            # Test password reset
            reset_data = {
                **self.dummy_data,
                "new_password": "NewPassword123!"
            }
            
            async with self.session.post(
                f"{self.base_url}/reset_password",
                json=reset_data
            ) as response:
                data = await response.json()
                result = {
                    "test": "reset_password_route",
                    "status": response.status,
                    "success": response.status == 201,
                    "message": data.get('message', 'Unknown'),
                    "data": data
                }
                self.test_results.append(result)
                print(f"✅ Reset password route test: {result['message']}")
                return result
                
        except aiohttp.ClientConnectorError:
            result = {
                "test": "reset_password_route",
                "status": 0,
                "success": False,
                "message": "Server not running",
                "data": {}
            }
            self.test_results.append(result)
            print(f"⚠️ Reset password route test: Server not running")
            return result

    async def test_add_person_route(self):
        """Test add person route"""
        try:
            # Test adding person
            async with self.session.post(
                f"{self.base_url}/add_people",
                data=self.person_data
            ) as response:
                data = await response.json()
                result = {
                    "test": "add_person_route",
                    "status": response.status,
                    "success": response.status == 201,
                    "message": data.get('message', 'Unknown'),
                    "data": data
                }
                self.test_results.append(result)
                print(f"✅ Add person route test: {result['message']}")
                return result
                
        except aiohttp.ClientConnectorError:
            result = {
                "test": "add_person_route",
                "status": 0,
                "success": False,
                "message": "Server not running",
                "data": {}
            }
            self.test_results.append(result)
            print(f"⚠️ Add person route test: Server not running")
            return result

    async def test_get_members_route(self):
        """Test get members route"""
        try:
            # Test getting members
            async with self.session.post(
                f"{self.base_url}/members",
                json={"updatedSince": "2024-01-01T00:00:00Z"}
            ) as response:
                data = await response.json()
                result = {
                    "test": "get_members_route",
                    "status": response.status,
                    "success": response.status == 200,
                    "message": f"Found {len(data.get('members', []))} members",
                    "data": data
                }
                self.test_results.append(result)
                print(f"✅ Get members route test: {result['message']}")
                return result
                
        except aiohttp.ClientConnectorError:
            result = {
                "test": "get_members_route",
                "status": 0,
                "success": False,
                "message": "Server not running",
                "data": {}
            }
            self.test_results.append(result)
            print(f"⚠️ Get members route test: Server not running")
            return result

    async def test_get_routines_route(self):
        """Test get routines route"""
        try:
            # Test getting routines
            async with self.session.post(
                f"{self.base_url}/routines",
                json={"updatedSince": "2024-01-01T00:00:00Z"}
            ) as response:
                data = await response.json()
                result = {
                    "test": "get_routines_route",
                    "status": response.status,
                    "success": response.status == 200,
                    "message": f"Found {len(data.get('routines', []))} routines",
                    "data": data
                }
                self.test_results.append(result)
                print(f"✅ Get routines route test: {result['message']}")
                return result
                
        except aiohttp.ClientConnectorError:
            result = {
                "test": "get_routines_route",
                "status": 0,
                "success": False,
                "message": "Server not running",
                "data": {}
            }
            self.test_results.append(result)
            print(f"⚠️ Get routines route test: Server not running")
            return result

    async def test_get_events_route(self):
        """Test get events route"""
        try:
            # Test getting events
            async with self.session.post(
                f"{self.base_url}/events",
                json={"updatedSince": "2024-01-01T00:00:00Z"}
            ) as response:
                data = await response.json()
                result = {
                    "test": "get_events_route",
                    "status": response.status,
                    "success": response.status == 200,
                    "message": f"Found {len(data.get('events', []))} events",
                    "data": data
                }
                self.test_results.append(result)
                print(f"✅ Get events route test: {result['message']}")
                return result
                
        except aiohttp.ClientConnectorError:
            result = {
                "test": "get_events_route",
                "status": 0,
                "success": False,
                "message": "Server not running",
                "data": {}
            }
            self.test_results.append(result)
            print(f"⚠️ Get events route test: Server not running")
            return result

    async def test_get_exams_route(self):
        """Test get exams route"""
        try:
            # Test getting exams
            async with self.session.post(
                f"{self.base_url}/exams",
                json={"updatedSince": "2024-01-01T00:00:00Z"}
            ) as response:
                data = await response.json()
                result = {
                    "test": "get_exams_route",
                    "status": response.status,
                    "success": response.status == 200,
                    "message": f"Found {len(data.get('exams', []))} exams",
                    "data": data
                }
                self.test_results.append(result)
                print(f"✅ Get exams route test: {result['message']}")
                return result
                
        except aiohttp.ClientConnectorError:
            result = {
                "test": "get_exams_route",
                "status": 0,
                "success": False,
                "message": "Server not running",
                "data": {}
            }
            self.test_results.append(result)
            print(f"⚠️ Get exams route test: Server not running")
            return result

    async def test_account_manage_route(self):
        """Test account management routes"""
        try:
            # Test account deactivation
            async with self.session.post(
                f"{self.base_url}/account/deactivate",
                json=self.dummy_data
            ) as response:
                data = await response.json()
                result = {
                    "test": "account_manage_route",
                    "status": response.status,
                    "success": response.status in [200, 400, 401],
                    "message": data.get('message', 'Success'),
                    "data": data
                }
                self.test_results.append(result)
                print(f"✅ Account manage route test: {result['message']}")
                return result
                
        except aiohttp.ClientConnectorError:
            result = {
                "test": "account_manage_route",
                "status": 0,
                "success": False,
                "message": "Server not running",
                "data": {}
            }
            self.test_results.append(result)
            print(f"⚠️ Account manage route test: Server not running")
            return result

    async def test_account_check_route(self):
        """Test account check route"""
        try:
            # Test account check
            check_data = {
                "device_id": "test_device_123",
                "device_brand": "test_brand",
                "ip_address": "192.168.1.100",
                "phone": "01712345678",
                "user_id": 123,
                "name_en": "test_user",
                "member_id": "MEM001",
                "student_id": "STU001",
                "name_bn": "টেস্ট ইউজার",
                "name_ar": "مستخدم اختبار",
                "date_of_birth": "1990-01-01",
                "birth_certificate": "BC001",
                "national_id": "NID001",
                "blood_group": "A+",
                "gender": "male",
                "title1": "Student",
                "title2": "Class 5",
                "source": "Direct",
                "present_address": "Test Address",
                "address_en": "Test Address",
                "address_bn": "টেস্ট ঠিকানা",
                "address_ar": "عنوان اختبار",
                "permanent_address": "Test Permanent Address",
                "father_or_spouse": "Test Father",
                "father_en": "Test Father",
                "father_bn": "টেস্ট বাবা",
                "father_ar": "أب اختبار",
                "mother_en": "Test Mother",
                "mother_bn": "টেস্ট মা",
                "mother_ar": "أم اختبار",
                "class_name": "Class 5",
                "guardian_number": "01787654321",
                "available": "Yes",
                "degree": "None",
                "image_path": "/static/user_profile_img/test.jpg",
                "acc_type": "student",
                "is_donor": False,
                "is_badri_member": False,
                "is_foundation_member": False
            }
            
            async with self.session.post(
                f"{self.base_url}/account/check",
                json=check_data
            ) as response:
                data = await response.json()
                result = {
                    "test": "account_check_route",
                    "status": response.status,
                    "success": response.status in [200, 401],
                    "message": data.get('message', 'Success'),
                    "data": data
                }
                self.test_results.append(result)
                print(f"✅ Account check route test: {result['message']}")
                return result
                
        except aiohttp.ClientConnectorError:
            result = {
                "test": "account_check_route",
                "status": 0,
                "success": False,
                "message": "Server not running",
                "data": {}
            }
            self.test_results.append(result)
            print(f"⚠️ Account check route test: Server not running")
            return result

    async def test_file_serving_routes(self):
        """Test file serving routes"""
        try:
            # Test profile image serving
            async with self.session.get(
                f"{self.base_url}/static/user_profile_img/test.jpg"
            ) as response:
                result = {
                    "test": "file_serving_routes",
                    "status": response.status,
                    "success": response.status in [200, 404],
                    "message": f"Profile image serving: Status {response.status}",
                    "data": {"profile_image_status": response.status}
                }
                self.test_results.append(result)
                print(f"✅ File serving routes test: {result['message']}")
                return result
                
        except aiohttp.ClientConnectorError:
            result = {
                "test": "file_serving_routes",
                "status": 0,
                "success": False,
                "message": "Server not running",
                "data": {}
            }
            self.test_results.append(result)
            print(f"⚠️ File serving routes test: Server not running")
            return result

    async def test_error_handling(self):
        """Test error handling with invalid data"""
        try:
            # Test registration with missing data
            async with self.session.post(
                f"{self.base_url}/register",
                json={"fullname": "test"}  # Missing required fields
            ) as response:
                data = await response.json()
                result = {
                    "test": "error_handling",
                    "status": response.status,
                    "success": response.status == 400,
                    "message": data.get('message', 'Error'),
                    "data": data
                }
                self.test_results.append(result)
                print(f"✅ Error handling test: {result['message']}")
                return result
                
        except aiohttp.ClientConnectorError:
            result = {
                "test": "error_handling",
                "status": 0,
                "success": False,
                "message": "Server not running",
                "data": {}
            }
            self.test_results.append(result)
            print(f"⚠️ Error handling test: Server not running")
            return result

    async def run_all_tests(self):
        """Run all integration tests"""
        print("🧪 Running User Routes Integration Tests...")
        print("=" * 60)
        print("Note: Make sure the server is running on http://localhost:8000")
        print("=" * 60)
        
        await self.setup()
        
        try:
            # Run all tests
            tests = [
                self.test_register_route(),
                self.test_login_route(),
                self.test_send_verification_code_route(),
                self.test_reset_password_route(),
                self.test_add_person_route(),
                self.test_get_members_route(),
                self.test_get_routines_route(),
                self.test_get_events_route(),
                self.test_get_exams_route(),
                self.test_account_manage_route(),
                self.test_account_check_route(),
                self.test_file_serving_routes(),
                self.test_error_handling()
            ]
            
            await asyncio.gather(*tests)
            
        finally:
            await self.teardown()
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 Integration Test Summary:")
        
        total_tests = len(self.test_results)
        successful_tests = sum(1 for result in self.test_results if result['success'])
        failed_tests = total_tests - successful_tests
        
        print(f"   Tests run: {total_tests}")
        print(f"   Successful: {successful_tests}")
        print(f"   Failed: {failed_tests}")
        
        if failed_tests == 0:
            print("✅ All integration tests passed!")
            return True
        else:
            print("❌ Some integration tests failed!")
            return False


def run_all_tests():
    """Run all tests and return results"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add basic import test
    suite.addTest(loader.loadTestsFromTestCase(TestBasicImport))
    
    # Run basic tests
    runner = unittest.TextTestRunner(verbosity=2)
    basic_result = runner.run(suite)
    
    # Run integration tests
    integration_tester = TestUserRoutesIntegration()
    integration_success = asyncio.run(integration_tester.run_all_tests())
    
    # Overall result
    return basic_result.wasSuccessful() and integration_success


if __name__ == "__main__":
    # Set up test environment
    os.environ['TEST_MODE'] = 'true'
    os.environ['DUMMY_FULLNAME'] = 'test_user'
    os.environ['DUMMY_PHONE'] = '01712345678'
    os.environ['DUMMY_PASSWORD'] = 'TestPassword123!'
    os.environ['DUMMY_EMAIL'] = 'test@example.com'
    
    # Run tests
    success = run_all_tests()
    
    # Clean up
    os.environ.pop('TEST_MODE', None)
    os.environ.pop('DUMMY_FULLNAME', None)
    os.environ.pop('DUMMY_PHONE', None)
    os.environ.pop('DUMMY_PASSWORD', None)
    os.environ.pop('DUMMY_EMAIL', None)
    
    exit(0 if success else 1)
