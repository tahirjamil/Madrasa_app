import asyncio
import os
from typing import Any, Optional, Tuple, TypedDict, Union, cast

from quart import current_app

from myapp import MyApp
from config import config
from observability.db_tracing import TracedRedisPool

try:
    import aioredis  # type: ignore
except Exception as _e:  # pragma: no cover
    aioredis = None  # Fallback to allow import-time safety; runtime will raise


class AioredisConnectConfig(TypedDict, total=False):
    """Connection options for aioredis.create_redis_pool."""

    url: str
    address: Tuple[str, int]
    db: int
    password: Optional[str]
    ssl: bool
    encoding: str
    minsize: int
    maxsize: int
    timeout: float


def get_keydb_config() -> AioredisConnectConfig:
    """Build KeyDB/Redis connection config from config/env with sane defaults."""
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

    cfg: AioredisConnectConfig = {
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
    """Create a global KeyDB/Redis pool connection using aioredis."""
    # Check if redis is disabled
    if os.getenv("USE_REDIS_CACHE", "true").lower() in ("false", "no", "0"):
        print("Redis cache is disabled via USE_REDIS_CACHE=false")
        return None
    
    if aioredis is None:  # pragma: no cover
        print("Warning: aioredis is not available, skipping Redis connection")
        return None

    cfg = get_keydb_config()

    try:
        # Prefer URL if provided, otherwise address tuple
        if "url" in cfg:
            pool = await aioredis.create_redis_pool(
                cfg["url"],
                db=cfg.get("db"),
                encoding=cfg.get("encoding", "utf-8"),
                minsize=cfg.get("minsize"),
                maxsize=cfg.get("maxsize"),
                timeout=cfg.get("timeout"),
                ssl=cfg.get("ssl"),
            )
        else:
            address: Union[str, Tuple[str, int]] = cfg.get("address", ("localhost", 6379))  # type: ignore[assignment]
            pool = await aioredis.create_redis_pool(  # type: ignore[attr-defined]
                address,
                db=cfg.get("db"),
                password=cfg.get("password"),
                encoding=cfg.get("encoding", "utf-8"),
                minsize=cfg.get("minsize"),
                maxsize=cfg.get("maxsize"),
                timeout=cfg.get("timeout"),
                ssl=cfg.get("ssl"),
            )

        return TracedRedisPool(pool)

    except Exception as e:
        print(f"KeyDB connection failed: {e}")
        return None


async def get_keydb():
    """Get the KeyDB pool from the app context."""
    app = cast(MyApp, current_app)
    if not hasattr(app, "keydb") or app.keydb is None:
        raise RuntimeError("KeyDB connection not available")
    return app.keydb


async def get_keydb_connection(max_retries: int = 3) -> Any:
    """Get KeyDB connection with retry/backoff similar to DB utils."""
    for attempt in range(max_retries):
        try:
            return await get_keydb()
        except Exception:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(0.1 * (attempt + 1))

    raise Exception("KeyDB connection failed")


async def close_keydb(pool: Any) -> None:
    """Gracefully close the KeyDB pool if it follows aioredis 1.x semantics."""
    try:
        if hasattr(pool, "close"):
            pool.close()  # type: ignore[func-returns-value]
        if hasattr(pool, "wait_closed"):
            await pool.wait_closed()  # type: ignore[attr-defined]
    except Exception as e:  # pragma: no cover
        print(f"Error closing KeyDB connection: {e}")


async def ping_keydb(timeout: float = 1.0) -> bool:
    """Simple health-check for KeyDB connection."""
    try:
        pool = await get_keydb_connection()
        # In aioredis 1.x, pool executes commands directly
        pong = await pool.ping()  # type: ignore[attr-defined]
        return bool(pong)
    except Exception:
        try:
            await asyncio.wait_for(asyncio.sleep(0), timeout=timeout)
        except Exception:
            pass
        return False


