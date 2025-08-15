import asyncio
import os
from typing import Any, Optional, Tuple, TypedDict, cast

from quart import current_app

from config import config, MadrasaApp
from observability.db_tracing import TracedRedisPool

# Redis asyncio client (redis-py >= 4.2 / 5.x)
import redis.asyncio as redis


class RedisConnectConfig(TypedDict, total=False):
    """Connection options for redis.asyncio client."""

    url: str
    address: Tuple[str, int]
    db: int
    password: Optional[str]
    ssl: bool
    encoding: str
    minsize: int
    maxsize: int
    timeout: float


def get_keydb_config() -> RedisConnectConfig | None:
    """Build KeyDB/Redis connection config from config/env with sane defaults."""
    # Check if Redis cache is enabled
    use_redis_cache = os.getenv('USE_REDIS_CACHE', 'false').lower() in ('1', 'true', 'yes', 'on')
    if not use_redis_cache:
        print("USE_REDIS_CACHE environment variable is not set to 'true'. KeyDB/Redis cache is disabled.")
        return None
    
    # URL first (supports redis://, rediss://)
    url = config.get_keydb_url()
    password = config.REDIS_PASSWORD if config.REDIS_PASSWORD else None

    # DB index
    db_idx = config.REDIS_DB if config.REDIS_DB else 0

    # Host/Port fallbacks if URL not provided
    host = config.REDIS_HOST
    port = config.REDIS_PORT

    # SSL toggle (for rediss or TLS proxies)
    ssl_flag_raw = config.REDIS_SSL
    ssl_flag = str(ssl_flag_raw).lower() in ("1", "true", "yes", "on")

    # Pool sizing and timeout
    minsize = config.REDIS_MINSIZE or 1
    maxsize = config.REDIS_MAXSIZE or 10
    timeout = config.REDIS_TIMEOUT or 10.0
    encoding = config.REDIS_ENCODING or "utf-8"

    cfg: RedisConnectConfig = {
        "db": db_idx,
        "ssl": ssl_flag,
        "encoding": encoding,
        "minsize": minsize,
        "maxsize": maxsize,
        "timeout": timeout,
    }

    if url:
        cfg["url"] = str(url)
    else:
        cfg["address"] = (str(host), int(port))
        if password:
            cfg["password"] = password

    return cfg


async def connect_to_keydb():
    """Create a global KeyDB/Redis client using redis.asyncio (redis-py)."""
    try:
        cfg = get_keydb_config()
    except RuntimeError as e:
        # Redis cache is disabled
        print(f"KeyDB connection skipped: {e}")
        return None

    try:
        if cfg and "url" in cfg:
            client = redis.from_url(
                cfg["url"],
                db=cfg.get("db", 0),
                encoding=cfg.get("encoding", "utf-8"),
                decode_responses=True,
                socket_connect_timeout=cfg.get("timeout", 10.0),
            )
        elif cfg and "address" in cfg:
            address: Tuple[str, int] = cfg.get("address", ("localhost", 6379))  # type: ignore[assignment]
            client = redis.Redis(
                host=address[0],
                port=address[1],
                db=cfg.get("db", 0),
                password=cfg.get("password"),
                encoding=cfg.get("encoding", "utf-8"),
                decode_responses=True,
                ssl=cfg.get("ssl", False),
                socket_connect_timeout=cfg.get("timeout", 10.0),
            )
        else:
            raise RuntimeError("KeyDB connection failed: No configuration provided")

        return TracedRedisPool(client)

    except Exception as e:
        print(f"KeyDB connection failed: {e}")
        return None


async def get_keydb():
    """Get the KeyDB pool from the app context."""
    app = cast(MadrasaApp, current_app)
    if not hasattr(app, "keydb") or app.keydb is None:
        raise RuntimeError("KeyDB connection not available")
    return app.keydb


async def get_keydb_connection(max_retries: int = 3) -> Any:
    """Get KeyDB connection with retry/backoff similar to DB utils."""
    for attempt in range(max_retries):
        try:
            return await get_keydb()
        except RuntimeError as e:
            print(f"KeyDB/Redis cache is disabled: {e}")
            return None
        except Exception:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(0.1 * (attempt + 1))

    raise Exception("KeyDB connection failed")


async def close_keydb(pool: Any) -> None:
    """Gracefully close the KeyDB client for redis.asyncio and compatibility."""
    try:
        # TracedRedisPool proxies attributes to the underlying client
        target = getattr(pool, "_pool", pool)
        # Prefer async close when available (redis>=5.0)
        aclose_attr = getattr(target, "aclose", None)
        if callable(aclose_attr):
            try:
                maybe_coro = aclose_attr()
                if asyncio.iscoroutine(maybe_coro):
                    await maybe_coro
            except Exception:
                pass
        else:
            close_attr = getattr(target, "close", None)
            if callable(close_attr):
                maybe_coro = close_attr()
                try:
                    if asyncio.iscoroutine(maybe_coro):
                        await maybe_coro
                except Exception:
                    # Some implementations may have sync close()
                    pass
        # Ensure the connection pool is disconnected
        cp = getattr(target, "connection_pool", None)
        if cp is not None and hasattr(cp, "disconnect"):
            try:
                maybe_disc = cp.disconnect()
                if asyncio.iscoroutine(maybe_disc):
                    await maybe_disc
            except Exception:
                pass
    except Exception as e:  # pragma: no cover
        print(f"Error closing KeyDB connection: {e}")


async def ping_keydb(timeout: float = 1.0) -> bool:
    """Simple health-check for KeyDB connection."""
    try:
        pool = await get_keydb_connection()
        # In aioredis 1.x, pool executes commands directly
        pong = await pool.ping()
        return bool(pong)
    except Exception:
        try:
            await asyncio.wait_for(asyncio.sleep(0), timeout=timeout)
        except Exception:
            pass
        return False


