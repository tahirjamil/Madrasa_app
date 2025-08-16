from typing import Callable, Awaitable

from opentelemetry import trace


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


