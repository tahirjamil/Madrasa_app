#!/usr/bin/env python3
"""
Quick test script to verify FastAPI migration is working
"""

import asyncio
import httpx
import sys

async def test_fastapi_server():
    """Test basic FastAPI functionality"""
    
    print("Testing FastAPI server...")
    
    # Test endpoints
    base_url = "http://localhost:8000"
    
    async with httpx.AsyncClient() as client:
        try:
            # Test health endpoint
            print("\n1. Testing /health endpoint...")
            response = await client.get(f"{base_url}/health")
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.json()}")
            assert response.status_code == 200
            
            # Test OpenAPI docs
            print("\n2. Testing /docs endpoint...")
            response = await client.get(f"{base_url}/docs")
            print(f"   Status: {response.status_code}")
            assert response.status_code == 200
            
            # Test OpenAPI schema
            print("\n3. Testing /openapi.json endpoint...")
            response = await client.get(f"{base_url}/openapi.json")
            print(f"   Status: {response.status_code}")
            openapi = response.json()
            print(f"   API Title: {openapi.get('info', {}).get('title')}")
            print(f"   API Version: {openapi.get('info', {}).get('version')}")
            assert response.status_code == 200
            
            # Test favicon
            print("\n4. Testing /favicon.ico endpoint...")
            response = await client.get(f"{base_url}/favicon.ico")
            print(f"   Status: {response.status_code}")
            assert response.status_code == 200
            
            print("\n✅ All basic tests passed!")
            print("\nFastAPI Features Available:")
            print("- Interactive API docs: http://localhost:8000/docs")
            print("- Alternative API docs: http://localhost:8000/redoc")
            print("- OpenAPI schema: http://localhost:8000/openapi.json")
            
        except httpx.ConnectError:
            print("\n❌ Could not connect to server. Make sure it's running on http://localhost:8000")
            print("\nTo start the server, run:")
            print("  python run_server.py --dev")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            sys.exit(1)

if __name__ == "__main__":
    print("FastAPI Migration Test")
    print("=" * 50)
    asyncio.run(test_fastapi_server())