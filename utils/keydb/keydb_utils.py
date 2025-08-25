import asyncio
from typing import Optional, Tuple, TypedDict, Union
from fastapi import Request
import redis.asyncio as redis

from utils.helpers.logger import log

from config.config import MadrasaConfig
from utils.otel.otel_utils import TracedRedisPool


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
    # Import config here to avoid circular imports
    from config.config import config
    
    # Check if Redis cache is enabled
    use_redis_cache = config.USE_KEYDB_CACHE or "true"
    if not use_redis_cache.lower() in ("1", "true", "yes", "on") or not use_redis_cache:
        log.info(action="redis_cache_disabled", trace_info="system", message="Redis cache is disabled", secure=False)
        return None
    
    # URL first (supports redis://, rediss://)
    url = MadrasaConfig.get_keydb_url(include_password=True)  # Only include password for actual connection
    password = config.KEYDB_PASSWORD if config.KEYDB_PASSWORD else None

    # DB index
    db_idx = config.KEYDB_DB if config.KEYDB_DB else 0

    # Host/Port fallbacks if URL not provided
    host = config.KEYDB_HOST
    port = config.KEYDB_PORT

    # SSL toggle (for rediss or TLS proxies)
    ssl_flag_raw = config.KEYDB_SSL
    ssl_flag = str(ssl_flag_raw).lower() in ("1", "true", "yes", "on")

    # Pool sizing and timeout
    minsize = config.KEYDB_MINSIZE or 1
    maxsize = config.KEYDB_MAXSIZE or 10
    timeout = config.KEYDB_TIMEOUT or 10.0
    encoding = config.KEYDB_ENCODING or "utf-8"

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

async def connect_to_keydb(max_retries: int = 3, retry_delay: float = 0.5) -> Union[redis.Redis, TracedRedisPool] | None:
    """Create a global KeyDB/Redis client using redis.asyncio (redis-py) with retries."""
    try:
        cfg = get_keydb_config()
    except RuntimeError:
        log.info(
            action="keydb_connection_skipped",
            trace_info="system",
            message="KeyDB connection skipped - cache disabled",
            secure=False
        )
        return None

    for attempt in range(1, max_retries + 1):
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

            # Import TracedRedisPool here to avoid circular imports
            from utils.otel.otel_utils import TracedRedisPool
            return TracedRedisPool(client)

        except Exception as e:
            log.warning(
                action="keydb_connection_retry",
                trace_info="system",
                message=f"Attempt {attempt} failed: {type(e).__name__} - {str(e)}",
                secure=False
            )
            if attempt < max_retries:
                await asyncio.sleep(retry_delay * attempt)
            else:
                log.error(
                    action="keydb_connection_failed",
                    trace_info="system",
                    message=f"All {max_retries} attempts to connect to KeyDB failed: {type(e).__name__}",
                    secure=False
                )
                return None

async def close_keydb(keydb_client: Union[redis.Redis, TracedRedisPool, None]) -> None:
    """
    Close KeyDB connection gracefully
    """
    if keydb_client:
        try:
            await keydb_client.close()
            await keydb_client.connection_pool.disconnect()
            from utils.helpers.logger import log
            log.info(action="keydb_disconnected", trace_info="system", message="Successfully disconnected from KeyDB", secure=False)
        except Exception as e:
            from utils.helpers.logger import log
            log.error(action="keydb_disconnect_error", trace_info="system", message=f"Error disconnecting from KeyDB: {str(e)}", secure=False)


async def ping_keydb(request: Request | None, timeout: float = 1.0) -> bool:
    """Simple health-check for KeyDB connection."""
    try:
        pool = get_keydb_from_app(request)
        pong = await pool.ping() if pool else None
        return bool(pong)
    except Exception:
        await asyncio.sleep(timeout)
        return False

_keydb_instance: redis.Redis | TracedRedisPool | None= None

def set_global_keydb(client: redis.Redis | TracedRedisPool | None) -> None:
    global _keydb_instance
    _keydb_instance = client

def get_keydb_from_app(request: Request | None) -> redis.Redis | TracedRedisPool | None:
    """Get KeyDB client from FastAPI app state"""
    if not request:
        return _keydb_instance
    return getattr(request.app.state, "keydb", None)