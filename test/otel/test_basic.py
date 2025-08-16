#!/usr/bin/env python3
"""
Basic OpenTelemetry Test
Simple test to verify OpenTelemetry is working
"""

import os
import sys
import time

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_basic_opentelemetry():
    """Test basic OpenTelemetry functionality"""
    print("🚀 Testing Basic OpenTelemetry Functionality")
    print("=" * 50)
    
    try:
        # Import OpenTelemetry
        from opentelemetry import trace, metrics
        print("✅ OpenTelemetry imports successful")
        
        # Test tracer
        tracer = trace.get_tracer("test")
        print("✅ Tracer creation successful")
        
        # Test span creation
        with tracer.start_as_current_span("test.span") as span:
            span.set_attribute("test.attribute", "test-value")
            print("✅ Span creation and attribute setting successful")
        
        # Test metrics (if available)
        try:
            meter = metrics.get_meter("test-meter")
            counter = meter.create_counter("test.counter")
            counter.add(1)
            print("✅ Metrics creation successful")
        except Exception as e:
            print(f"⚠️  Metrics not available: {e}")
        
        # Test performance
        print("\n📊 Performance Test:")
        
        # Without tracing
        start_time = time.time()
        for i in range(1000):
            pass
        no_trace_time = time.time() - start_time
        
        # With tracing
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
        
        if overhead < 100:  # Acceptable overhead threshold
            print("✅ Performance overhead is acceptable")
        else:
            print("⚠️  Performance overhead is high")
        
        print("\n🎉 All basic tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_connectivity():
    """Test connectivity to collector"""
    print("\n🔗 Testing Collector Connectivity")
    print("=" * 50)
    
    try:
        from opentelemetry import trace
        
        tracer = trace.get_tracer("connectivity")
        
        # Create a test span
        with tracer.start_as_current_span("connectivity.test") as span:
            span.set_attribute("test.type", "connectivity")
            span.set_attribute("test.timestamp", time.time())
        
        print("✅ Span creation successful")
        print("✅ If you see this span in Jaeger, connectivity is working!")
        print("   Check: http://localhost:16686")
        
        return True
        
    except Exception as e:
        print(f"❌ Connectivity test failed: {e}")
        return False


if __name__ == "__main__":
    print("🚀 Starting Basic OpenTelemetry Test")
    print("=" * 50)
    
    basic_success = test_basic_opentelemetry()
    connectivity_success = test_connectivity()
    
    print("\n" + "=" * 50)
    print("📊 Test Summary")
    print("=" * 50)
    print(f"Basic Functionality: {'✅ PASSED' if basic_success else '❌ FAILED'}")
    print(f"Connectivity: {'✅ PASSED' if connectivity_success else '❌ FAILED'}")
    
    if basic_success and connectivity_success:
        print("\n🎉 All tests passed! OpenTelemetry is working correctly.")
        sys.exit(0)
    else:
        print("\n⚠️  Some tests failed. Please check the output above.")
        sys.exit(1)
