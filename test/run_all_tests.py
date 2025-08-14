#!/usr/bin/env python3
"""
Test Runner for Madrasa Application
===================================

Runs all tests and provides a summary report.
"""

import os
import sys
import subprocess
import time
from pathlib import Path

# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(message):
    """Print a formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{message:^60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")


def print_success(message):
    """Print success message"""
    print(f"{Colors.OKGREEN}✓ {message}{Colors.ENDC}")


def print_error(message):
    """Print error message"""
    print(f"{Colors.FAIL}✗ {message}{Colors.ENDC}")


def print_info(message):
    """Print info message"""
    print(f"{Colors.OKBLUE}ℹ {message}{Colors.ENDC}")


def check_dependencies():
    """Check if required dependencies are available"""
    print_header("Checking Dependencies")
    
    dependencies = {
        'python3': 'Python 3',
        'pip3': 'pip',
    }
    
    missing = []
    for cmd, name in dependencies.items():
        try:
            subprocess.run([cmd, '--version'], capture_output=True, check=True)
            print_success(f"{name} is installed")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print_error(f"{name} is not installed")
            missing.append(name)
    
    # Check Python modules
    modules = ['unittest', 'asyncio', 'pathlib']
    for module in modules:
        try:
            __import__(module)
            print_success(f"Module '{module}' is available")
        except ImportError:
            print_error(f"Module '{module}' is not available")
            missing.append(module)
    
    return len(missing) == 0


def run_test_file(test_file):
    """Run a single test file and return results"""
    print(f"\n{Colors.OKCYAN}Running {test_file.name}...{Colors.ENDC}")
    
    start_time = time.time()
    
    try:
        # Run the test
        result = subprocess.run(
            [sys.executable, str(test_file)],
            capture_output=True,
            text=True,
            timeout=60  # 60 second timeout per test file
        )
        
        duration = time.time() - start_time
        
        if result.returncode == 0:
            # Extract test count from output
            test_count = 0
            for line in result.stderr.split('\n'):
                if 'Ran' in line and 'test' in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            test_count = int(parts[1])
                        except ValueError:
                            pass
            
            print_success(f"{test_file.name} - {test_count} tests passed in {duration:.2f}s")
            return True, test_count, duration, None
        else:
            # Extract error information
            error_lines = []
            for line in result.stderr.split('\n'):
                if 'FAILED' in line or 'ERROR' in line:
                    error_lines.append(line)
            
            error_msg = '\n'.join(error_lines) if error_lines else result.stderr
            print_error(f"{test_file.name} - Tests failed in {duration:.2f}s")
            return False, 0, duration, error_msg
            
    except subprocess.TimeoutExpired:
        print_error(f"{test_file.name} - Timeout after 60s")
        return False, 0, 60, "Test timed out"
    except Exception as e:
        print_error(f"{test_file.name} - Error: {str(e)}")
        return False, 0, 0, str(e)


def run_all_tests():
    """Run all test files in the test directory"""
    print_header("Running All Tests")
    
    test_dir = Path(__file__).parent
    test_files = sorted(test_dir.glob("test_*.py"))
    
    if not test_files:
        print_error("No test files found!")
        return False
    
    print_info(f"Found {len(test_files)} test files")
    
    results = []
    total_tests = 0
    total_duration = 0
    
    for test_file in test_files:
        success, test_count, duration, error = run_test_file(test_file)
        results.append({
            'file': test_file.name,
            'success': success,
            'test_count': test_count,
            'duration': duration,
            'error': error
        })
        total_tests += test_count
        total_duration += duration
    
    # Print summary
    print_header("Test Summary")
    
    passed_files = sum(1 for r in results if r['success'])
    failed_files = len(results) - passed_files
    
    print(f"Total test files: {len(results)}")
    print(f"Passed: {Colors.OKGREEN}{passed_files}{Colors.ENDC}")
    print(f"Failed: {Colors.FAIL}{failed_files}{Colors.ENDC}")
    print(f"Total tests run: {total_tests}")
    print(f"Total duration: {total_duration:.2f}s")
    
    # Show failed tests details
    if failed_files > 0:
        print(f"\n{Colors.FAIL}Failed Tests:{Colors.ENDC}")
        for result in results:
            if not result['success']:
                print(f"\n{Colors.WARNING}{result['file']}:{Colors.ENDC}")
                if result['error']:
                    print(f"  {result['error']}")
    
    return failed_files == 0


def check_environment():
    """Check environment setup"""
    print_header("Environment Check")
    
    # Check if we're in the right directory
    if not Path("app.py").exists():
        print_error("Not in the Madrasa app directory!")
        return False
    
    print_success("In correct directory")
    
    # Check if environment validator exists
    env_validator = Path("config/env_validator.py")
    if env_validator.exists():
        print_success("Environment validator found")
        
        # Run environment validation
        print_info("Running environment validation...")
        result = subprocess.run(
            [sys.executable, str(env_validator)],
            env={'SKIP_ENV_VALIDATION': '1'},  # Skip to see all errors
            capture_output=True,
            text=True
        )
        
        if "✅" in result.stdout:
            print_success("Environment validation completed")
        else:
            print_warning("Environment validation has issues (this is expected without .env)")
    else:
        print_error("Environment validator not found")
        return False
    
    return True


def main():
    """Main test runner"""
    print_header("Madrasa Application Test Suite")
    
    # Change to workspace directory
    os.chdir(Path(__file__).parent.parent)
    
    # Check environment
    if not check_environment():
        print_error("\nEnvironment check failed!")
        sys.exit(1)
    
    # Check dependencies
    if not check_dependencies():
        print_error("\nDependency check failed!")
        print_info("Please install missing dependencies")
        sys.exit(1)
    
    # Run all tests
    success = run_all_tests()
    
    if success:
        print(f"\n{Colors.OKGREEN}{Colors.BOLD}All tests passed! 🎉{Colors.ENDC}")
        sys.exit(0)
    else:
        print(f"\n{Colors.FAIL}{Colors.BOLD}Some tests failed! 😞{Colors.ENDC}")
        sys.exit(1)


if __name__ == "__main__":
    main()
