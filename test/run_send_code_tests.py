#!/usr/bin/env python3
"""
Simple script to run send_code endpoint tests for debugging
"""

import subprocess
import sys
import os

def run_test(test_file, test_name=None):
    """Run a specific test with verbose output"""
    cmd = ["python", "-m", "pytest", test_file, "-v", "-s"]
    
    if test_name:
        cmd.extend(["-k", test_name])
    
    print(f"\n{'='*80}")
    print(f"Running: {' '.join(cmd)}")
    print(f"{'='*80}")
    
    try:
        result = subprocess.run(cmd, cwd=os.path.dirname(os.path.dirname(__file__)))
        return result.returncode == 0
    except Exception as e:
        print(f"Error running test: {e}")
        return False

def main():
    """Main function to run tests"""
    print("🧪 Send Code Endpoint Testing Suite")
    print("=" * 50)
    
    # Check if server is running
    print("\n1. Checking if server is running...")
    try:
        import requests
        from config import server_config
        response = requests.get(f"http://localhost:{server_config.SERVER_PORT}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Server is running")
        else:
            print("❌ Server is not responding correctly")
            return
    except Exception as e:
        print(f"❌ Server is not running: {e}")
        print("Please start the server first with: python run_server.py")
        return
    
    # Run the debug test first
    print("\n2. Running debug test with exact mobile app data...")
    success = run_test("test/api/test_send_code_debug.py", "test_send_code_exact_mobile_request")
    
    if not success:
        print("\n❌ Debug test failed. Check the output above for details.")
        return
    
    # Run step-by-step debugging
    print("\n3. Running step-by-step debugging...")
    run_test("test/api/test_send_code_debug.py", "test_send_code_step_by_step")
    
    # Run configuration check
    print("\n4. Running configuration check...")
    run_test("test/api/test_send_code_debug.py", "test_send_code_configuration_check")
    
    # Run comprehensive tests
    print("\n5. Running comprehensive send_code tests...")
    run_test("test/api/test_api_endpoints.py", "TestSendCodeEndpoint")
    
    print("\n🎉 Testing completed!")
    print("\nNext steps:")
    print("1. Check the output above for any errors")
    print("2. Look for specific error messages in the logs")
    print("3. Fix any configuration issues identified")
    print("4. Run the tests again to verify fixes")

if __name__ == "__main__":
    main()
