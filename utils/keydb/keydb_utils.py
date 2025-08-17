import asyncio
import os
from typing import Any, Optional, Tuple, TypedDict, cast

# Removed Quart import - using FastAPI app state instead

# Import config when needed to avoid circular imports
# from utils.otel.db_tracing import TracedRedisPool  # Import when needed to avoid circular imports

# Redis asyncio client (redis-py >= 4.2 / 5.x)
import redis.asyncio as redis

from utils.helpers.improved_functions import get_env_var
from utils.helpers.logger import log

from config import config


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
    from config import config
    
    # Check if Redis cache is enabled
    use_redis_cache = get_env_var('USE_REDIS_CACHE', 'false').lower() in ('1', 'true', 'yes', 'on')
    if not use_redis_cache:
        log.info(action="redis_cache_disabled", trace_info="system", message="Redis cache is disabled", secure=False)
        return None
    
    # URL first (supports redis://, rediss://)
    url = config.get_keydb_url(include_password=True)  # Only include password for actual connection
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


async def connect_to_keydb() -> Optional[redis.Redis]:
    """
    Establish connection to KeyDB with proper error handling
    """
    try:
        # Create connection
        keydb_client = redis.Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            password=config.REDIS_PASSWORD,
            decode_responses=True,
            socket_keepalive=True,
            socket_connect_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30
        )
        
        # Test connection
        await keydb_client.ping()
        
        # Log success
        from utils.helpers.logger import log
        log.info(action="keydb_connected", trace_info="system", message="Successfully connected to KeyDB", secure=False)
        
        return keydb_client
        
    except redis.ConnectionError as e:
        from utils.helpers.logger import log
        log.error(action="keydb_connection_failed", trace_info="system", message=f"Failed to connect to KeyDB: {str(e)}", secure=False)
        return None
    except Exception as e:
        from utils.helpers.logger import log
        log.critical(action="keydb_error", trace_info="system", message=f"Unexpected KeyDB error: {str(e)}", secure=False)
        return None


async def get_keydb_connection(max_retries: int = 3) -> Any:
    """Get KeyDB connection with retry/backoff similar to DB utils."""
    for attempt in range(max_retries):
        try:
            # This function is deprecated in favor of get_keydb_from_app
            # For backward compatibility, return None
            return None
        except Exception:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(0.1 * (attempt + 1))

    raise Exception("KeyDB connection failed")


async def close_keydb(keydb_client: Optional[redis.Redis]) -> None:
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


def get_keydb_from_app(app) -> Optional[redis.Redis]:
    """
    Get KeyDB client from FastAPI app state
    This replaces the Quart current_app usage
    """
    if hasattr(app, 'state') and hasattr(app.state, 'keydb'):
        return app.state.keydb
    return None
