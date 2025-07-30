#!/usr/bin/env python3
"""
External Access Test Script
==========================
This script helps diagnose external access issues by testing various connection scenarios.
"""

import requests
import socket
import subprocess
import sys
import time

def get_local_ip():
    """Get the local IP address"""
    try:
        # Connect to a remote address to determine local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception as e:
        print(f"Error getting local IP: {e}")
        return None

def test_connection(host, port, description):
    """Test connection to a specific host and port"""
    try:
        response = requests.get(f"http://{host}:{port}/health", timeout=5)
        if response.status_code == 200:
            print(f"✅ {description}: SUCCESS (Status: {response.status_code})")
            return True
        else:
            print(f"❌ {description}: FAILED (Status: {response.status_code})")
            return False
    except requests.exceptions.ConnectionError:
        print(f"❌ {description}: CONNECTION REFUSED")
        return False
    except requests.exceptions.Timeout:
        print(f"❌ {description}: TIMEOUT")
        return False
    except Exception as e:
        print(f"❌ {description}: ERROR - {e}")
        return False

def check_firewall():
    """Check if Windows Firewall might be blocking the connection"""
    try:
        result = subprocess.run(
            ["netsh", "advfirewall", "show", "currentprofile"], 
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print("🔍 Windows Firewall Status:")
            print(result.stdout)
        else:
            print("⚠️ Could not check Windows Firewall status")
    except Exception as e:
        print(f"⚠️ Error checking firewall: {e}")

def main():
    print("🌐 External Access Diagnostic Tool")
    print("=" * 50)
    
    # Get local IP
    local_ip = get_local_ip()
    print(f"📡 Local IP Address: {local_ip}")
    print(f"🖥️  Hostname: {socket.gethostname()}")
    print()
    
    # Test various connection scenarios
    tests = [
        ("localhost", 8000, "Localhost access"),
        ("127.0.0.1", 8000, "Loopback access"),
        (local_ip, 8000, f"Local IP access ({local_ip})"),
        ("0.0.0.0", 8000, "All interfaces access"),
    ]
    
    print("🔍 Testing Connections:")
    print("-" * 30)
    
    for host, port, description in tests:
        test_connection(host, port, description)
        time.sleep(1)
    
    print()
    print("🔧 Network Information:")
    print("-" * 30)
    
    # Check if port is listening on all interfaces
    try:
        result = subprocess.run(
            ["netstat", "-an"], 
            capture_output=True, text=True
        )
        if ":8000" in result.stdout:
            print("✅ Port 8000 is listening")
            for line in result.stdout.split('\n'):
                if ":8000" in line and "LISTENING" in line:
                    print(f"   {line.strip()}")
        else:
            print("❌ Port 8000 is not listening")
    except Exception as e:
        print(f"⚠️ Error checking netstat: {e}")
    
    print()
    print("🛡️ Firewall Check:")
    print("-" * 30)
    check_firewall()
    
    print()
    print("💡 Troubleshooting Tips:")
    print("-" * 30)
    print("1. If localhost works but external IP doesn't:")
    print("   - Check Windows Firewall settings")
    print("   - Ensure port 8000 is allowed for inbound connections")
    print("   - Try running as administrator")
    print()
    print("2. If VM access doesn't work:")
    print("   - Check VM network adapter settings")
    print("   - Ensure VM can reach the host network")
    print("   - Try using the host's IP address from VM")
    print()
    print("3. To allow external access in Windows Firewall:")
    print("   - Open Windows Defender Firewall")
    print("   - Add new inbound rule for port 8000")
    print("   - Allow connections from any IP")

if __name__ == "__main__":
    main() 