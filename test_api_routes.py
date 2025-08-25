#!/usr/bin/env python3
"""
Test script for API routes with proper headers and authentication
"""
import asyncio
import time
import aiohttp
import json
from typing import Dict, Any

# API Configuration
BASE_URL = "http://localhost"
API_KEYS = {
    "mobile": "madrasasecretappkey",
    "web": "madrasasecretwebkey", 
    "admin": "madrasasecretadminkey"
}

# Default headers for all requests
DEFAULT_HEADERS = {
    "X-API-Key": API_KEYS["mobile"],  # Change this to test different client types
    "X-Device-ID": "test-device-123",
    "X-Device-Model": "Test Device",
    "X-Device-Brand": "Test Brand", 
    "X-Device-OS": "Test OS",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

async def test_api_endpoint(session: aiohttp.ClientSession, method: str, endpoint: str, 
                           data: Dict[str, Any] | None = None, headers: Dict[str, str] | None = None) -> Dict[str, Any]:
    """Test an API endpoint with proper headers"""
    url = f"{BASE_URL}{endpoint}"
    request_headers = {**DEFAULT_HEADERS, **(headers or {})}
    
    print(f"\n{'='*60}")
    print(f"Testing: {method.upper()} {endpoint}")
    print(f"Headers: {json.dumps(request_headers, indent=2)}")
    if data:
        print(f"Data: {json.dumps(data, indent=2)}")
    print(f"{'='*60}")
    
    try:
        if method.upper() == "GET":
            async with session.get(url, headers=request_headers) as response:
                result = await response.json()
        elif method.upper() == "POST":
            async with session.post(url, headers=request_headers, json=data) as response:
                result = await response.json()
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        print(f"Status: {response.status}")
        print(f"Response: {json.dumps(result, indent=2)}")
        time.sleep(2)
        return {"status": response.status, "data": result}
        
    except Exception as e:
        print(f"Error: {e}")
        return {"status": "error", "data": str(e)}

async def test_web_endpoints():
    """Test the health endpoint (no authentication required)"""
    async with aiohttp.ClientSession() as session:
        await test_api_endpoint(session, "GET", "/health")
        await test_api_endpoint(session, "GET", "/")
        await test_api_endpoint(session, "GET", "/donate")
        await test_api_endpoint(session, "GET", "/terms")
        await test_api_endpoint(session, "GET", "/privacy")

async def test_auth_endpoints():
    """Test authentication endpoints"""
    async with aiohttp.ClientSession() as session:
        
        # Test registration
        send_code_data = {
            "fullname": "Test User",
            "email": "tahirjamil01910@gmail.com",
            "phone": "+8801712345678",
            "madrasa_name": "annur"
        }
        await test_api_endpoint(session, "POST", "/send_code", send_code_data)

        register_data = {
            "fullname": "Test User",
            "phone": "+8801712345678",
            "password": "Testpassword@1234",
            "code": 123456,
            "madrasa_name": "annur"
        }
        await test_api_endpoint(session, "POST", "/register", register_data)

        # Test Add people
        add_people_data = {
            "name_en": "Test User",
            "phone": "+8801712345678",
            "acc_type": "guest",
            "date_of_birth": "2025-01-01",
            "father_or_spouse": "father",
            "madrasa_name": "annur"
        }
        await test_api_endpoint(session, "POST", "/add_people", add_people_data)
        
        # Test login
        login_data = {
            "fullname": "Test User", 
            "phone": "+8801712345678",
            "password": "Testpassword@123",
            "madrasa_name": "annur"
        }
        await test_api_endpoint(session, "POST", "/login", login_data)


        reset_password_data = {
            "fullname": "Test User",
            "phone": "+8801712345678",
            "new_password": "Testpassword@123",
            "code": 123456,
            "madrasa_name": "annur"
        }
        await test_api_endpoint(session, "POST", "/reset_password", reset_password_data)

async def test_core_endpoints():
    """Test core API endpoints"""
    async with aiohttp.ClientSession() as session:
        
        # Test get members
        members_data = {
            "madrasa_name": "annur",
            "updatedSince": None
        }
        await test_api_endpoint(session, "POST", "/members", members_data)

        routine_data = {
            "madrasa_name": "annur",
            "updatedSince": None
        }
        await test_api_endpoint(session, "POST", "/routines", routine_data)

async def test_payment_endpoints():
    """Test payment endpoints"""
    async with aiohttp.ClientSession() as session:
        
        # Test payment calculation
        payment_data = {
            "madrasa_name": "annur",
            "fullname": "Test User",
            "phone": "+8801712345678",
        }
        await test_api_endpoint(session, "POST", "/due_payments", payment_data)

        # Test get Transactions
        transactions_data = {
            "madrasa_name": "annur",
            "fullname": "Test User",
            "phone": "+8801712345678",
        }
        await test_api_endpoint(session, "POST", "/transaction_history", transactions_data)

async def test_files_endpoints():
    """Test files endpoints"""
    async with aiohttp.ClientSession() as session:
        await test_api_endpoint(session, "GET", "/files")
        await test_api_endpoint(session, "GET", "/uploads/exam_results/index.json")
        await test_api_endpoint(session, "GET", "/uploads/notice/index.json")

async def main():
    """Main test function"""
    print("🚀 Starting API Route Tests")
    print(f"Base URL: {BASE_URL}")
    print(f"Using API Key: {DEFAULT_HEADERS['X-API-Key']}")
    
    # Test health endpoint (no auth required)
    print("\n📊 Testing Health Endpoint...")
    await test_web_endpoints()
    
    # Test auth endpoints
    print("\n🔐 Testing Authentication Endpoints...")
    await test_auth_endpoints()
    
    # Test core endpoints
    print("\n📋 Testing Core Endpoints...")
    await test_core_endpoints()
    
    # Test payment endpoints
    print("\n💰 Testing Payment Endpoints...")
    await test_payment_endpoints()
    
    print("\n✅ All tests completed!")

if __name__ == "__main__":
    asyncio.run(main())
