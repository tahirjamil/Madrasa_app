#!/usr/bin/env python3
"""
Start Server for Testing
========================

This script starts the server for integration testing.
"""

import os
import sys
import subprocess

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def start_server():
    """Start the server for testing"""
    print("🚀 Starting server for testing...")
    
    # Set test mode environment
    os.environ['TEST_MODE'] = 'true'
    os.environ['DUMMY_FULLNAME'] = 'test_user'
    os.environ['DUMMY_PHONE'] = '01712345678'
    os.environ['DUMMY_PASSWORD'] = 'TestPassword123!'
    os.environ['DUMMY_EMAIL'] = 'test@example.com'
    
    try:
        # Start the server
        print("Starting server on http://localhost:8000")
        print("Press Ctrl+C to stop the server")
        
        # Run the server
        subprocess.run([
            sys.executable, 
            "run_server.py"
        ], cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
    finally:
        # Clean up environment
        os.environ.pop('TEST_MODE', None)
        os.environ.pop('DUMMY_FULLNAME', None)
        os.environ.pop('DUMMY_PHONE', None)
        os.environ.pop('DUMMY_PASSWORD', None)
        os.environ.pop('DUMMY_EMAIL', None)

if __name__ == "__main__":
    start_server() 