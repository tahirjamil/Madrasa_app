from typing import Optional
import os
import time

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# OTLP gRPC exporters (defaults to http://localhost:4317)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter


def init_otel(service_name: str, environment: Optional[str] = None, service_version: Optional[str] = None) -> None:
    """Initialize OpenTelemetry tracing (and metrics if available) with OTLP exporters.

    - Endpoint defaults to localhost:4317; override via OTEL_EXPORTER_OTLP_* env vars.
    - Minimal, safe defaults suitable for local development.
    """
    # Resource attributes identify your service in the backend
    resource_attrs = {
        "service.name": service_name,
    }
    if environment:
        resource_attrs["deployment.environment"] = environment
    if service_version:
        resource_attrs["service.version"] = service_version

    resource = Resource.create(resource_attrs)

    # Traces
    tracer_provider = TracerProvider(resource=resource)
    span_exporter = OTLPSpanExporter()  # honors OTEL_EXPORTER_OTLP_ENDPOINT
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    # Metrics (optional)
    try:
        # Import here to ensure they're available when used
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        
        metric_exporter = OTLPMetricExporter()
        reader = PeriodicExportingMetricReader(metric_exporter)
        meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(meter_provider)
    except Exception:
        print("Metrics exporter not available")
        pass

    # If strict mode is requested, verify exporter connectivity up-front to fail fast
    otel_strict = os.getenv("OTEL_STRICT", "true").lower() in ("1", "true", "yes", "on")
    if otel_strict:
        # Create a quick test span and force a flush; if exporter is unavailable, the SDK exporter
        # will raise or log errors synchronously in flush path shortly thereafter.
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("otel.startup.healthcheck"):
            pass
        # Give the BatchSpanProcessor a brief moment to export, then shutdown to surface errors
        # (shutdown flushes processors synchronously)
        try:
            # Try a very short sleep to allow background batch to kick in
            time.sleep(0.05)
            # Explicit provider shutdown ensures exporter connectivity gets exercised now
            provider = trace.get_tracer_provider()
            if isinstance(provider, TracerProvider):
                provider.shutdown()
        except Exception as exc:  # pragma: no cover
            # Re-raise so the app can fail fast when strict mode is on
            raise RuntimeError(f"OpenTelemetry strict startup check failed: {exc}")
        finally:
            # Recreate provider after shutdown for normal runtime (since we shut it down above)
            tracer_provider = TracerProvider(resource=resource)
            span_exporter = OTLPSpanExporter()
            tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
            trace.set_tracer_provider(tracer_provider)


