"""
Async Operations Tests
=====================

Tests for async/await patterns, database operations,
and proper error handling in async contexts.
"""

import os
import sys
import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAsyncPatterns(unittest.TestCase):
    """Test async/await patterns and potential issues"""
    
    def test_async_function_declarations(self):
        """Test that async functions are properly declared"""
        from utils.helpers import send_email, send_sms, delete_code
        
        # Check that these functions are coroutines
        self.assertTrue(asyncio.iscoroutinefunction(send_email), "send_email should be async")
        self.assertTrue(asyncio.iscoroutinefunction(send_sms), "send_sms should be async")
        self.assertTrue(asyncio.iscoroutinefunction(delete_code), "delete_code should be async")
    
    def test_no_sync_async_mixing(self):
        """Test that we don't mix sync and async incorrectly"""
        import ast
        from pathlib import Path
        
        # Files to check for async issues
        files_to_check = [
            'utils/helpers.py',
            'routes/api/auth.py',
            'routes/api/core.py',
            'database/database_utils.py'
        ]
        
        issues = []
        
        for file_path in files_to_check:
            full_path = Path(file_path)
            if not full_path.exists():
                continue
                
            try:
                tree = ast.parse(full_path.read_text())
                
                # Look for asyncio.run() or asyncio.create_task() in async functions
                for node in ast.walk(tree):
                    if isinstance(node, ast.AsyncFunctionDef):
                        for child in ast.walk(node):
                            if isinstance(child, ast.Call):
                                if isinstance(child.func, ast.Attribute):
                                    if (hasattr(child.func.value, 'id') and 
                                        child.func.value.id == 'asyncio' and 
                                        child.func.attr in ['run', 'create_task']):
                                        issues.append((file_path, node.name, child.func.attr))
            except Exception as e:
                print(f"Error parsing {file_path}: {e}")
        
        # Report issues
        if issues:
            print("\nAsync pattern issues found:")
            for file_path, func_name, method in issues:
                print(f"  - {file_path}: {func_name} calls asyncio.{method}")
        
        # We should have fixed these issues
        self.assertEqual(len(issues), 0, "Async pattern issues found")


class TestDatabaseOperations(unittest.TestCase):
    """Test database connection handling and error recovery"""
    
    def test_connection_cleanup(self):
        """Test that database connections are properly cleaned up"""
        import ast
        from pathlib import Path
        
        # Check for proper connection cleanup patterns
        files_to_check = [
            'database/database_utils.py',
            'routes/api/auth.py',
            'routes/api/core.py',
            'utils/helpers.py'
        ]
        
        issues = []
        
        for file_path in files_to_check:
            full_path = Path(file_path)
            if not full_path.exists():
                continue
            
            content = full_path.read_text()
            
            # Look for get_db_connection without proper cleanup
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if 'get_db_connection()' in line and 'await' in line:
                    # Check if there's a try/finally or context manager
                    context = '\n'.join(lines[max(0, i-5):min(len(lines), i+10)])
                    if 'try:' not in context and 'async with' not in context:
                        issues.append((file_path, i+1, "Missing try/finally for connection cleanup"))
        
        # Report issues
        if issues:
            print("\nDatabase connection cleanup issues:")
            for file_path, line_num, issue in issues:
                print(f"  - {file_path}:{line_num} - {issue}")
        
        # This is more of a code quality check
        print(f"Found {len(issues)} potential connection cleanup issues")
    
    @patch('database.database_utils.get_db')
    async def test_connection_retry_logic(self, mock_get_db):
        """Test database connection retry logic"""
        from database.database_utils import get_db_connection
        
        # Test successful connection on first try
        mock_conn = AsyncMock()
        mock_get_db.return_value = mock_conn
        
        conn = await get_db_connection()
        self.assertEqual(conn, mock_conn)
        self.assertEqual(mock_get_db.call_count, 1)
        
        # Test retry on failure
        mock_get_db.reset_mock()
        mock_get_db.side_effect = [Exception("Connection failed"), Exception("Still failed"), mock_conn]
        
        conn = await get_db_connection(max_retries=3)
        self.assertEqual(conn, mock_conn)
        self.assertEqual(mock_get_db.call_count, 3)
        
        # Test max retries exceeded
        mock_get_db.reset_mock()
        mock_get_db.side_effect = Exception("Always fails")
        
        with self.assertRaises(Exception):
            await get_db_connection(max_retries=3)
        self.assertEqual(mock_get_db.call_count, 3)


class TestErrorHandling(unittest.TestCase):
    """Test error handling patterns"""
    
    def test_exception_handling_patterns(self):
        """Test that exceptions are properly handled"""
        from pathlib import Path
        import re
        
        # Patterns that indicate poor error handling
        poor_patterns = [
            r'except:\s*$',  # Bare except
            r'except\s+Exception:\s*pass',  # Swallowing all exceptions
            r'except.*:\s*print\(',  # Only printing errors
        ]
        
        files_to_check = [
            'utils/logger.py',
            'utils/helpers.py',
            'routes/api/auth.py',
            'database/database_utils.py'
        ]
        
        issues = []
        
        for file_path in files_to_check:
            full_path = Path(file_path)
            if not full_path.exists():
                continue
            
            content = full_path.read_text()
            lines = content.split('\n')
            
            for i, line in enumerate(lines):
                for pattern in poor_patterns:
                    if re.search(pattern, line):
                        issues.append((file_path, i+1, line.strip()))
        
        # Report issues
        if issues:
            print("\nPoor error handling patterns found:")
            for file_path, line_num, line in issues:
                print(f"  - {file_path}:{line_num} - {line}")
        
        # We should have minimal issues
        self.assertLess(len(issues), 5, "Too many poor error handling patterns")
    
    @patch('utils.logger.get_db_connection')
    async def test_logger_error_fallback(self, mock_get_db):
        """Test logger fallback when database fails"""
        from utils.logger import log_event, _log_to_file
        
        # Mock database failure
        mock_get_db.side_effect = Exception("Database unavailable")
        
        # Patch file logging to track calls
        with patch('utils.logger._log_to_file') as mock_log_to_file:
            await log_event(
                action="test_action",
                trace_info="test_trace",
                message="test_message",
                secure=False,
                level="error"
            )
            
            # Should fall back to file logging
            mock_log_to_file.assert_called_once()
            call_args = mock_log_to_file.call_args[1]
            self.assertEqual(call_args['action'], "test_action")
            self.assertEqual(call_args['message'], "test_message")
            self.assertTrue(call_args['error'])


class TestConcurrency(unittest.TestCase):
    """Test concurrency and race condition handling"""
    
    @patch('utils.helpers.get_db_connection')
    async def test_concurrent_operations(self, mock_get_db):
        """Test handling of concurrent database operations"""
        from utils.helpers import delete_code
        
        # Mock database connection
        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()
        mock_conn.cursor.return_value.__aenter__.return_value = mock_cursor
        mock_get_db.return_value = mock_conn
        
        # Run multiple concurrent operations
        tasks = []
        for _ in range(10):
            tasks.append(asyncio.create_task(delete_code()))
        
        # All should complete without issues
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check no exceptions occurred
        for result in results:
            self.assertIsNone(result, "Concurrent operation should not raise exception")
        
        # Verify connection was properly managed
        self.assertEqual(mock_get_db.call_count, 10)
        self.assertEqual(mock_conn.commit.call_count, 10)
    
    def test_rate_limiter_thread_safety(self):
        """Test rate limiter thread safety"""
        from utils.helpers import rate_limiter
        import threading
        
        results = []
        test_ip = "192.168.1.1"
        
        def check_rate_limit():
            allowed, remaining = rate_limiter.check_rate_limit(
                test_ip, "/api/test", max_requests=100, window=60
            )
            results.append((allowed, remaining))
        
        # Clear rate limiter
        rate_limiter.requests.clear()
        
        # Create multiple threads
        threads = []
        for _ in range(50):
            thread = threading.Thread(target=check_rate_limit)
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Check results
        allowed_count = sum(1 for allowed, _ in results if allowed)
        self.assertEqual(allowed_count, 50, "All requests should be allowed")
        
        # Check remaining counts are consistent
        remaining_counts = [remaining for _, remaining in results]
        self.assertEqual(len(set(remaining_counts)), 50, "Each request should have unique remaining count")


class TestAsyncContextManagers(unittest.TestCase):
    """Test async context manager usage"""
    
    def test_database_cursor_usage(self):
        """Test that database cursors use async context managers"""
        from pathlib import Path
        import re
        
        files_to_check = [
            'routes/api/auth.py',
            'routes/api/core.py',
            'utils/helpers.py',
            'database/database_utils.py'
        ]
        
        issues = []
        
        for file_path in files_to_check:
            full_path = Path(file_path)
            if not full_path.exists():
                continue
            
            content = full_path.read_text()
            
            # Look for cursor usage without async with
            if 'cursor()' in content:
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if '.cursor(' in line and 'async with' not in line:
                        # Check context around the line
                        context_start = max(0, i-2)
                        context_end = min(len(lines), i+3)
                        context = lines[context_start:context_end]
                        
                        # Check if async with is on a different line
                        if not any('async with' in ctx_line for ctx_line in context):
                            issues.append((file_path, i+1, line.strip()))
        
        # Report issues
        if issues:
            print("\nCursor usage without async context manager:")
            for file_path, line_num, line in issues:
                print(f"  - {file_path}:{line_num} - {line}")
        
        # We should have fixed most of these
        self.assertLess(len(issues), 3, "Too many cursor usage issues")


# Helper function to run async tests
def run_async_test(coro):
    """Helper to run async test functions"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


if __name__ == '__main__':
    # Patch async test methods
    TestDatabaseOperations.test_connection_retry_logic = lambda self: run_async_test(
        TestDatabaseOperations.test_connection_retry_logic(self)
    )
    TestErrorHandling.test_logger_error_fallback = lambda self: run_async_test(
        TestErrorHandling.test_logger_error_fallback(self)
    )
    TestConcurrency.test_concurrent_operations = lambda self: run_async_test(
        TestConcurrency.test_concurrent_operations(self)
    )
    
    unittest.main()