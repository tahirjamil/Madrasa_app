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
    # Check if already initialized to avoid override errors
    try:
        current_provider = trace.get_tracer_provider()
        if not isinstance(current_provider, TracerProvider):
            # Already initialized with a real provider, skip
            return
    except Exception:
        pass
    
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
        
        # Check if metrics provider already exists
        try:
            current_meter_provider = metrics.get_meter_provider()
            if not isinstance(current_meter_provider, MeterProvider):
                # Already initialized with a real provider, skip
                pass
            else:
                metric_exporter = OTLPMetricExporter()
                reader = PeriodicExportingMetricReader(metric_exporter)
                meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
                metrics.set_meter_provider(meter_provider)
        except Exception:
            # No existing provider, create new one
            metric_exporter = OTLPMetricExporter()
            reader = PeriodicExportingMetricReader(metric_exporter)
            meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
            metrics.set_meter_provider(meter_provider)
    except Exception:
        print("Metrics exporter not available")
        pass

    # If strict mode is requested, verify exporter connectivity up-front to fail fast
    otel_strict = get_env_var("OTEL_STRICT", "false").lower() in ("1", "true", "yes", "on")
    if otel_strict:
        try:
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span("otel.startup.healthcheck"):
                pass
        except Exception as exc:  # pragma: no cover
            # Re-raise so the app can fail fast when strict mode is on
            raise RuntimeError(f"OpenTelemetry strict startup check failed: {exc}")


