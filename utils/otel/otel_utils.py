from typing import Any, Callable, Iterable, Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# OTLP gRPC exporters (defaults to http://localhost:4317)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from utils.helpers.improved_functions import get_env_var


def init_otel(service_name: str, environment: Optional[str] = None, service_version: Optional[str] = None) -> None:
    """Initialize OpenTelemetry tracing (and metrics if available) with OTLP exporters."""
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


# ─── Middleware ──────────────────────────────────────────────────────

class RequestTracingMiddleware:
    """Basic ASGI middleware to create a request span per incoming request."""

    def __init__(self, app: Callable) -> None:
        self._app = app
        self._tracer = trace.get_tracer(__name__)

    async def __call__(self, scope, receive, send):  # type: ignore[override]
        if scope.get("type") != "http":
            return await self._app(scope, receive, send)

        method = scope.get("method", "").upper()
        path = scope.get("path", "")
        client = scope.get("client") or (None, None)
        client_ip = client[0] if isinstance(client, tuple) else None

        span_name = f"HTTP {method} {path}"
        with self._tracer.start_as_current_span(span_name) as span:
            if client_ip:
                span.set_attribute("client.ip", client_ip)
            span.set_attribute("http.method", method)
            span.set_attribute("http.target", path)

            status_code_container = {"status": 0}

            async def send_wrapper(message):
                if message.get("type") == "http.response.start":
                    status = int(message.get("status", 0))
                    status_code_container["status"] = status
                    span.set_attribute("http.status_code", status)
                return await send(message)

            try:
                await self._app(scope, receive, send_wrapper)
            except Exception as exc:
                span.record_exception(exc)
                span.set_attribute("error", True)
                raise

# ─── DB Tracing ──────────────────────────────────────────────────────

_tracer = trace.get_tracer(__name__)


class TracedCursorWrapper:
    """Wrap an aiomysql cursor object to create spans for execute/fetch."""

    def __init__(self, cursor) -> None:
        self._cursor = cursor

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)

    async def execute(self, query: str, args: Optional[Iterable[Any]] = None) -> Any:
        with _tracer.start_as_current_span("sql.execute") as span:
            span.set_attribute("db.system", "mysql")
            span.set_attribute("db.statement", query)
            try:
                return await self._cursor.execute(query, args)
            except Exception as exc:
                span.record_exception(exc)
                raise

    async def executemany(self, query: str, args: Iterable[Iterable[Any]]) -> Any:
        with _tracer.start_as_current_span("sql.executemany") as span:
            span.set_attribute("db.system", "mysql")
            span.set_attribute("db.statement", query)
            try:
                return await self._cursor.executemany(query, args)
            except Exception as exc:
                span.record_exception(exc)
                raise


class TracedRedisPool:
    """Wrap a KeyDB/aioredis pool with spans for basic commands used by the app."""

    def __init__(self, pool) -> None:
        self._pool = pool

    def __getattr__(self, name: str) -> Any:
        return getattr(self._pool, name)

    async def get(self, key: str) -> Any:
        with _tracer.start_as_current_span("redis.get") as span:
            span.set_attribute("db.system", "redis")
            span.set_attribute("db.operation", "get")
            span.set_attribute("db.redis.key", key)
            try:
                return await self._pool.get(key)
            except Exception as exc:
                span.record_exception(exc)
                raise

    async def set(self, key: str, value: Any, *args, **kwargs) -> Any:
        with _tracer.start_as_current_span("redis.set") as span:
            span.set_attribute("db.system", "redis")
            span.set_attribute("db.operation", "set")
            span.set_attribute("db.redis.key", key)
            try:
                # Map aioredis-style "expire" kwarg to redis-py "ex"
                if "expire" in kwargs and "ex" not in kwargs:
                    kwargs = {**kwargs}
                    kwargs["ex"] = kwargs.pop("expire")
                return await self._pool.set(key, value, *args, **kwargs)
            except Exception as exc:
                span.record_exception(exc)
                raise

    async def delete(self, *keys: str) -> Any:
        with _tracer.start_as_current_span("redis.delete") as span:
            span.set_attribute("db.system", "redis")
            span.set_attribute("db.operation", "delete")
            span.set_attribute("db.redis.keys", ",".join(keys))
            try:
                return await self._pool.delete(*keys)
            except Exception as exc:
                span.record_exception(exc)
                raise

    async def keys(self, pattern: str) -> Any:
        with _tracer.start_as_current_span("redis.keys") as span:
            span.set_attribute("db.system", "redis")
            span.set_attribute("db.operation", "keys")
            span.set_attribute("db.redis.pattern", pattern)
            try:
                return await self._pool.keys(pattern)
            except Exception as exc:
                span.record_exception(exc)
                raise

    async def execute(self, *args) -> Any:
        """Compatibility shim: map execute(...) to redis-py's execute_command."""
        with _tracer.start_as_current_span("redis.execute") as span:
            span.set_attribute("db.system", "redis")
            try:
                # redis.asyncio exposes execute_command
                return await getattr(self._pool, "execute_command")(*args)
            except Exception as exc:
                span.record_exception(exc)
                raise


