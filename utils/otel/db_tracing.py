from typing import Any, Iterable, Optional

from opentelemetry import trace


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


