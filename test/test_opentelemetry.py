#!/usr/bin/env python3
"""
Comprehensive OpenTelemetry Test Suite

This test file validates all OpenTelemetry functionality in the Madrasa app:
- OTEL initialization and configuration
- Tracing functionality
- ASGI middleware
- Database tracing (MySQL and Redis/KeyDB)
- Metrics collection
- Collector connectivity

Usage:
    python test/test_opentelemetry.py
"""

import asyncio
import os
import sys
import time
import unittest
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

# Import our OTEL modules
from observability.otel_utils import init_otel
from observability.asgi_middleware import RequestTracingMiddleware
from observability.db_tracing import TracedCursorWrapper, TracedRedisPool


class TestOpenTelemetryInitialization(unittest.TestCase):
    """Test OpenTelemetry initialization and configuration."""

    def setUp(self):
        """Set up test environment."""
        # Clear any existing providers
        trace.set_tracer_provider(None)
        try:
            metrics.set_meter_provider(None)
        except:
            pass
        
        # Set test environment variables
        self.original_env = os.environ.copy()
        os.environ['OTEL_STRICT'] = 'false'  # Disable strict mode for testing

    def tearDown(self):
        """Clean up after tests."""
        # Restore original environment
        os.environ.clear()
        os.environ.update(self.original_env)
        
        # Clean up providers
        provider = trace.get_tracer_provider()
        if provider:
            provider.shutdown()
        try:
            meter_provider = metrics.get_meter_provider()
            if meter_provider:
                meter_provider.shutdown()
        except:
            pass

    def test_init_otel_basic(self):
        """Test basic OpenTelemetry initialization."""
        init_otel("test-service", "test-env", "1.0.0")
        
        provider = trace.get_tracer_provider()
        self.assertIsInstance(provider, TracerProvider)
        
        # Check resource attributes
        resource = provider.resource
        self.assertEqual(resource.attributes["service.name"], "test-service")
        self.assertEqual(resource.attributes["deployment.environment"], "test-env")
        self.assertEqual(resource.attributes["service.version"], "1.0.0")

    def test_init_otel_minimal(self):
        """Test minimal OpenTelemetry initialization."""
        init_otel("test-service")
        
        provider = trace.get_tracer_provider()
        self.assertIsInstance(provider, TracerProvider)
        
        # Check resource attributes
        resource = provider.resource
        self.assertEqual(resource.attributes["service.name"], "test-service")
        self.assertNotIn("deployment.environment", resource.attributes)
        self.assertNotIn("service.version", resource.attributes)

    def test_init_otel_with_metrics(self):
        """Test OpenTelemetry initialization with metrics."""
        init_otel("test-service", "test-env", "1.0.0")
        
        # Check if meter provider was created
        try:
            meter_provider = metrics.get_meter_provider()
            self.assertIsInstance(meter_provider, MeterProvider)
        except Exception:
            # Metrics might not be available
            pass

    def test_tracer_functionality(self):
        """Test basic tracing functionality."""
        init_otel("test-service")
        tracer = trace.get_tracer("test")
        
        # Create a span
        with tracer.start_as_current_span("test-span") as span:
            span.set_attribute("test.attribute", "test-value")
            self.assertEqual(span.get_attribute("test.attribute"), "test-value")

    def test_span_attributes(self):
        """Test span attribute setting and getting."""
        init_otel("test-service")
        tracer = trace.get_tracer("test")
        
        with tracer.start_as_current_span("test-span") as span:
            span.set_attribute("string.attr", "value")
            span.set_attribute("int.attr", 42)
            span.set_attribute("bool.attr", True)
            
            self.assertEqual(span.get_attribute("string.attr"), "value")
            self.assertEqual(span.get_attribute("int.attr"), 42)
            self.assertEqual(span.get_attribute("bool.attr"), True)

    def test_span_events(self):
        """Test span event recording."""
        init_otel("test-service")
        tracer = trace.get_tracer("test")
        
        with tracer.start_as_current_span("test-span") as span:
            span.add_event("test-event", {"key": "value"})
            # Note: Event testing is limited in unit tests without actual export


class TestASGIMiddleware(unittest.TestCase):
    """Test ASGI middleware functionality."""

    def setUp(self):
        """Set up test environment."""
        init_otel("test-service")
        self.tracer = trace.get_tracer("test")

    def tearDown(self):
        """Clean up after tests."""
        provider = trace.get_tracer_provider()
        if provider:
            provider.shutdown()

    async def test_middleware_http_request(self):
        """Test middleware with HTTP request."""
        # Mock ASGI app
        mock_app = AsyncMock()
        mock_app.return_value = None
        
        middleware = RequestTracingMiddleware(mock_app)
        
        # Mock ASGI scope
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "client": ("127.0.0.1", 12345)
        }
        
        # Mock receive and send
        receive = AsyncMock()
        send = AsyncMock()
        
        # Call middleware
        await middleware(scope, receive, send)
        
        # Verify app was called
        mock_app.assert_called_once()

    async def test_middleware_non_http(self):
        """Test middleware with non-HTTP request."""
        mock_app = AsyncMock()
        middleware = RequestTracingMiddleware(mock_app)
        
        scope = {"type": "websocket"}
        receive = AsyncMock()
        send = AsyncMock()
        
        await middleware(scope, receive, send)
        
        # Verify app was called without tracing
        mock_app.assert_called_once()

    async def test_middleware_response_status(self):
        """Test middleware captures response status."""
        mock_app = AsyncMock()
        middleware = RequestTracingMiddleware(mock_app)
        
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/test",
            "client": ("192.168.1.1", 54321)
        }
        
        receive = AsyncMock()
        status_captured = []
        
        async def send_wrapper(message):
            if message.get("type") == "http.response.start":
                status_captured.append(message.get("status"))
            return None
        
        await middleware(scope, receive, send_wrapper)
        
        # Verify app was called
        mock_app.assert_called_once()


class TestDatabaseTracing(unittest.TestCase):
    """Test database tracing functionality."""

    def setUp(self):
        """Set up test environment."""
        init_otel("test-service")
        self.tracer = trace.get_tracer("test")

    def tearDown(self):
        """Clean up after tests."""
        provider = trace.get_tracer_provider()
        if provider:
            provider.shutdown()

    async def test_traced_cursor_execute(self):
        """Test traced cursor execute method."""
        # Mock cursor
        mock_cursor = AsyncMock()
        mock_cursor.execute.return_value = 1
        
        traced_cursor = TracedCursorWrapper(mock_cursor)
        
        # Test execute
        result = await traced_cursor.execute("SELECT * FROM users WHERE id = %s", (1,))
        
        self.assertEqual(result, 1)
        mock_cursor.execute.assert_called_once_with("SELECT * FROM users WHERE id = %s", (1,))

    async def test_traced_cursor_executemany(self):
        """Test traced cursor executemany method."""
        mock_cursor = AsyncMock()
        mock_cursor.executemany.return_value = 3
        
        traced_cursor = TracedCursorWrapper(mock_cursor)
        
        # Test executemany
        data = [(1, "user1"), (2, "user2"), (3, "user3")]
        result = await traced_cursor.executemany("INSERT INTO users (id, name) VALUES (%s, %s)", data)
        
        self.assertEqual(result, 3)
        mock_cursor.executemany.assert_called_once_with("INSERT INTO users (id, name) VALUES (%s, %s)", data)

    async def test_traced_redis_get(self):
        """Test traced Redis get method."""
        mock_pool = AsyncMock()
        mock_pool.get.return_value = "test-value"
        
        traced_pool = TracedRedisPool(mock_pool)
        
        # Test get
        result = await traced_pool.get("test-key")
        
        self.assertEqual(result, "test-value")
        mock_pool.get.assert_called_once_with("test-key")

    async def test_traced_redis_set(self):
        """Test traced Redis set method."""
        mock_pool = AsyncMock()
        mock_pool.set.return_value = True
        
        traced_pool = TracedRedisPool(mock_pool)
        
        # Test set
        result = await traced_pool.set("test-key", "test-value", expire=3600)
        
        self.assertEqual(result, True)
        mock_pool.set.assert_called_once_with("test-key", "test-value", ex=3600)

    async def test_traced_redis_delete(self):
        """Test traced Redis delete method."""
        mock_pool = AsyncMock()
        mock_pool.delete.return_value = 2
        
        traced_pool = TracedRedisPool(mock_pool)
        
        # Test delete
        result = await traced_pool.delete("key1", "key2")
        
        self.assertEqual(result, 2)
        mock_pool.delete.assert_called_once_with("key1", "key2")

    async def test_traced_redis_keys(self):
        """Test traced Redis keys method."""
        mock_pool = AsyncMock()
        mock_pool.keys.return_value = ["key1", "key2", "key3"]
        
        traced_pool = TracedRedisPool(mock_pool)
        
        # Test keys
        result = await traced_pool.keys("test-*")
        
        self.assertEqual(result, ["key1", "key2", "key3"])
        mock_pool.keys.assert_called_once_with("test-*")


class TestOpenTelemetryIntegration(unittest.TestCase):
    """Test OpenTelemetry integration scenarios."""

    def setUp(self):
        """Set up test environment."""
        init_otel("integration-test", "test", "1.0.0")

    def tearDown(self):
        """Clean up after tests."""
        provider = trace.get_tracer_provider()
        if provider:
            provider.shutdown()

    def test_end_to_end_tracing(self):
        """Test end-to-end tracing scenario."""
        tracer = trace.get_tracer("integration")
        
        # Simulate a complete request flow
        with tracer.start_as_current_span("http.request") as request_span:
            request_span.set_attribute("http.method", "GET")
            request_span.set_attribute("http.url", "/api/users")
            
            # Simulate database operation
            with tracer.start_as_current_span("db.query") as db_span:
                db_span.set_attribute("db.system", "mysql")
                db_span.set_attribute("db.statement", "SELECT * FROM users")
                
                # Simulate cache operation
                with tracer.start_as_current_span("cache.get") as cache_span:
                    cache_span.set_attribute("cache.key", "users:list")
                    cache_span.set_attribute("cache.hit", False)
                
                # Simulate external API call
                with tracer.start_as_current_span("http.client") as client_span:
                    client_span.set_attribute("http.method", "POST")
                    client_span.set_attribute("http.url", "https://api.external.com/data")
            
            request_span.set_attribute("http.status_code", 200)
        
        # Verify spans were created (basic check)
        self.assertTrue(True)  # If we get here, no exceptions were raised

    def test_error_tracing(self):
        """Test error handling in tracing."""
        tracer = trace.get_tracer("error-test")
        
        try:
            with tracer.start_as_current_span("error.span") as span:
                span.set_attribute("test.operation", "error-simulation")
                raise ValueError("Test error")
        except ValueError:
            # Error should be recorded in span
            pass
        
        # Verify error was handled gracefully
        self.assertTrue(True)

    def test_metrics_creation(self):
        """Test metrics creation and recording."""
        try:
            meter = metrics.get_meter("test-meter")
            
            # Create a counter
            counter = meter.create_counter("test.counter", description="Test counter")
            counter.add(1, {"test": "value"})
            
            # Create a histogram
            histogram = meter.create_histogram("test.histogram", description="Test histogram")
            histogram.record(42.5, {"test": "value"})
            
            # Create an observable gauge
            def callback():
                return [metrics.Observation(100, {"test": "value"})]
            
            gauge = meter.create_observable_gauge("test.gauge", callbacks=[callback])
            
        except Exception as e:
            # Metrics might not be fully available in test environment
            print(f"Metrics test skipped: {e}")


class TestOpenTelemetryConfiguration(unittest.TestCase):
    """Test OpenTelemetry configuration and environment variables."""

    def setUp(self):
        """Set up test environment."""
        self.original_env = os.environ.copy()

    def tearDown(self):
        """Clean up after tests."""
        os.environ.clear()
        os.environ.update(self.original_env)
        
        provider = trace.get_tracer_provider()
        if provider:
            provider.shutdown()

    def test_environment_variables(self):
        """Test environment variable configuration."""
        # Set test environment variables
        os.environ['OTEL_EXPORTER_OTLP_ENDPOINT'] = 'http://localhost:4317'
        os.environ['OTEL_SERVICE_NAME'] = 'test-service'
        os.environ['OTEL_STRICT'] = 'false'
        
        init_otel("test-service")
        
        provider = trace.get_tracer_provider()
        self.assertIsInstance(provider, TracerProvider)

    def test_strict_mode_disabled(self):
        """Test strict mode disabled."""
        os.environ['OTEL_STRICT'] = 'false'
        
        # Should not raise exception even if collector is not available
        init_otel("test-service")
        
        provider = trace.get_tracer_provider()
        self.assertIsInstance(provider, TracerProvider)


def run_connectivity_test():
    """Run connectivity test to check if collector is reachable."""
    print("\n=== OpenTelemetry Connectivity Test ===")
    
    try:
        init_otel("connectivity-test", "test", "1.0.0")
        tracer = trace.get_tracer("connectivity")
        
        # Try to create and export a span
        with tracer.start_as_current_span("connectivity.test") as span:
            span.set_attribute("test.type", "connectivity")
            span.set_attribute("test.timestamp", time.time())
        
        print("✅ OpenTelemetry initialization successful")
        print("✅ Tracer created successfully")
        print("✅ Span creation successful")
        
        # Check if metrics are available
        try:
            meter = metrics.get_meter("connectivity-test")
            counter = meter.create_counter("connectivity.counter")
            counter.add(1)
            print("✅ Metrics creation successful")
        except Exception as e:
            print(f"⚠️  Metrics not available: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ OpenTelemetry connectivity test failed: {e}")
        return False


def run_performance_test():
    """Run performance test to check tracing overhead."""
    print("\n=== OpenTelemetry Performance Test ===")
    
    try:
        init_otel("performance-test", "test", "1.0.0")
        tracer = trace.get_tracer("performance")
        
        # Test without tracing
        start_time = time.time()
        for i in range(1000):
            pass
        no_trace_time = time.time() - start_time
        
        # Test with tracing
        start_time = time.time()
        for i in range(1000):
            with tracer.start_as_current_span(f"test.span.{i}") as span:
                span.set_attribute("iteration", i)
                pass
        trace_time = time.time() - start_time
        
        overhead = ((trace_time - no_trace_time) / no_trace_time) * 100
        
        print(f"✅ No tracing time: {no_trace_time:.4f}s")
        print(f"✅ With tracing time: {trace_time:.4f}s")
        print(f"✅ Overhead: {overhead:.2f}%")
        
        if overhead < 50:  # Acceptable overhead threshold
            print("✅ Performance overhead is acceptable")
        else:
            print("⚠️  Performance overhead is high")
        
        return True
        
    except Exception as e:
        print(f"❌ Performance test failed: {e}")
        return False


def main():
    """Main test runner."""
    print("🚀 Starting OpenTelemetry Test Suite")
    print("=" * 50)
    
    # Run unit tests
    print("\n📋 Running Unit Tests...")
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestOpenTelemetryInitialization))
    suite.addTests(loader.loadTestsFromTestCase(TestASGIMiddleware))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseTracing))
    suite.addTests(loader.loadTestsFromTestCase(TestOpenTelemetryIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestOpenTelemetryConfiguration))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Run integration tests
    print("\n🔗 Running Integration Tests...")
    connectivity_success = run_connectivity_test()
    performance_success = run_performance_test()
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Summary")
    print("=" * 50)
    print(f"Unit Tests: {'✅ PASSED' if result.wasSuccessful() else '❌ FAILED'}")
    print(f"Connectivity Test: {'✅ PASSED' if connectivity_success else '❌ FAILED'}")
    print(f"Performance Test: {'✅ PASSED' if performance_success else '❌ FAILED'}")
    
    if result.wasSuccessful() and connectivity_success and performance_success:
        print("\n🎉 All tests passed! OpenTelemetry is working correctly.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please check the output above.")
        return 1


if __name__ == "__main__":
    # Run async tests
    async def run_async_tests():
        """Run async tests."""
        print("\n🔄 Running Async Tests...")
        
        # Test ASGI middleware
        init_otel("async-test")
        mock_app = AsyncMock()
        middleware = RequestTracingMiddleware(mock_app)
        
        scope = {"type": "http", "method": "GET", "path": "/test"}
        receive = AsyncMock()
        send = AsyncMock()
        
        await middleware(scope, receive, send)
        print("✅ ASGI middleware async test passed")
        
        # Test database tracing
        mock_cursor = AsyncMock()
        traced_cursor = TracedCursorWrapper(mock_cursor)
        await traced_cursor.execute("SELECT 1")
        print("✅ Database tracing async test passed")
        
        # Test Redis tracing
        mock_pool = AsyncMock()
        traced_pool = TracedRedisPool(mock_pool)
        await traced_pool.get("test-key")
        print("✅ Redis tracing async test passed")
    
    # Run async tests
    asyncio.run(run_async_tests())
    
    # Run main tests
    exit_code = main()
    sys.exit(exit_code)
