from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# OTLP gRPC exporters (defaults to http://localhost:4317)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Metrics are optional; if exporter not available, we skip
try:  # pragma: no cover - optional metrics setup
    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    _METRICS_AVAILABLE = True
except Exception:  # pragma: no cover
    _METRICS_AVAILABLE = False


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
    if _METRICS_AVAILABLE:
        try:
            metric_exporter = OTLPMetricExporter()
            reader = PeriodicExportingMetricReader(metric_exporter)
            meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
            metrics.set_meter_provider(meter_provider)
        except Exception:
            # Metrics are optional; tracing remains active
            pass


