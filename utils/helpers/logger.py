import logging
import sys
import aiomysql, asyncio, json
from datetime import datetime
from pathlib import Path

# Basic logging to stderr without exposing sensitive details
def _log_error(msg: str) -> None:
    """Internal error logging without exposing sensitive details"""
    sys.stderr.write(f"[{datetime.now().isoformat()}] Logger: {msg}\n")

# Enhanced logger with better error handling and performance
def get_crypto_funcs(data: str, which: str) -> str | None:
    """Lazily import crypto helpers from utils.helpers to avoid circular imports."""
    if not which in ["hash", "encrypt"]:
        raise ValueError("Invalid which value. Must be 'hash' or 'encrypt'.")
    
    if not data:
        return None
    
    try:
        from utils.helpers.helpers import encrypt_sensitive_data, hash_sensitive_data
        if which == "hash":
            return hash_sensitive_data(data)
        elif which == "encrypt":
            return encrypt_sensitive_data(data)
        else:
            return None
    except Exception as e:
        _log_error(f"Failed to execute crypto function: {type(e).__name__}")
        return None

log_count = 0
log_count_lock = asyncio.Lock()

async def log_event(action: str, trace_info: str, message: str, secure: bool, level: str= "info", metadata=None) -> None:
    """Enhanced logging function with better error handling and metadata support"""
    global log_count

    MAX_ACTION_LEN = 50
    MAX_MESSAGE_LEN = 255
    MAX_TRACE_LEN = 100
    
    # Truncate strings if they exceed max length
    action = action[:MAX_ACTION_LEN]
    trace_info = trace_info[:MAX_TRACE_LEN]
    message = message[:MAX_MESSAGE_LEN]

    from config import config as default_config, server_config
    if not server_config.LOGGING_ENABLED:
        _log_error("Logging is disabled in the configuration")
        return
    # Check if we are in development mode
    if default_config.is_development:
        logger = logging.getLogger("MadrashaServer")
        logger.setLevel(getattr(logging, server_config.LOGGING_LEVEL.upper()))

        logger.info(f"SERVER LOG {level.upper()}: message={message},")
        return
    
    try:
        from utils.mysql.database_utils import get_db_connection
        async with get_db_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as _cursor:
                from utils.otel.otel_utils import TracedCursorWrapper
                cursor = TracedCursorWrapper(_cursor)
                # Prepare metadata
                log_metadata = metadata or {}
                log_metadata.update({
                    "timestamp": datetime.now().isoformat(),
                    "level": level,
                    "action": action,
                    "trace_info": trace_info,
                    "message": message
                })

                sql: str = "INSERT INTO logs (action, trace_info, message, level, metadata, trace_info_hash, trace_info_encrypted) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                params: list[str | None] = [action, trace_info, message, level, json.dumps(log_metadata)]

                if secure:
                    trace_info_hash = get_crypto_funcs(data=trace_info, which="hash")
                    trace_info_encrypted = get_crypto_funcs(data=trace_info, which="encrypt")

                    # If crypto functions fail, fall back to non-secure logging
                    if not trace_info_hash or not trace_info_encrypted:
                        _log_error("Crypto functions failed, falling back to non-secure logging")
                        params.extend([None, None])
                    else:
                        params.extend([trace_info_hash, trace_info_encrypted])
                else:
                    params.extend([None, None])

                await cursor.execute(sql, params)
                await conn.commit()
                
                async with log_count_lock:
                    if log_count > 500:
                        # Enhanced auto-prune with better performance
                        await cursor.execute("SELECT COUNT(*) AS total FROM logs")
                        result = await cursor.fetchone()
                        total = result['total'] if result else 0

                        
                        # If more than 1000, delete oldest (increased from 500)
                        if total > 1000:
                            await conn.commit()
                            await cursor.execute("""
                                DELETE FROM logs 
                                WHERE log_id IN (
                                    SELECT log_id FROM (
                                        SELECT log_id FROM logs 
                                        ORDER BY created_at ASC 
                                        LIMIT %s
                                    ) AS old_logs
                                )
                            """, (total - 1000,))
                            log_count = 0
                        await conn.commit()
                    else:
                        log_count += 1
                
                
    except Exception as e:
        # Fallback to file logging if database fails
        _log_error(f"Database logging failed: {type(e).__name__}")
        await _log_to_file(action=action, trace_info=trace_info, secure=secure,
                            message=message, level=level, metadata=metadata, error=True)

async def _log_to_file(action : str, trace_info: str,  message : str, level, secure: bool, metadata=None, error=False) -> None:
    """Log to file as backup when database logging fails"""
    try:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / f"app_{datetime.now().strftime('%Y%m%d')}.log"
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "action": action,
            "trace_info": trace_info,
            "message": message,
            "metadata": metadata or {},
            "source": "file_backup" if error else "database"
        }

        if secure:
            log_entry.update({
                "trace_info_hash": get_crypto_funcs(trace_info, "hash"),
                "trace_info_encrypted": get_crypto_funcs(trace_info, "encrypt")
            })
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
            
    except Exception as e:
        _log_error(f"File logging also failed: {type(e).__name__}")

def log_event_async(action: str, trace_info: str, message: str, secure: bool, level="info", metadata=None) -> None:
    """Non-blocking wrapper for log_event that schedules logging in the background."""
    try:
        # Get current event loop, create one if none exists
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Schedule the task without waiting for it
        if loop.is_running():
            asyncio.create_task(log_event(action=action, trace_info=trace_info, secure=secure,
                                          message=message, level=level, metadata=metadata
                                          ))
        else:
            # If no loop is running, just skip logging silently
            _log_error(f"Skipping log - no event loop running")
    except Exception as e:
        _log_error(f"Failed to schedule log task: {type(e).__name__}")

def log_event_sync(action : str, trace_info: str, message : str, secure: bool, level="info", metadata=None) -> None:
    """Enhanced synchronous wrapper that runs the logging operation and waits for completion."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(log_event(action=action, trace_info=trace_info, message=message, level=level, metadata=metadata, secure=secure))
        loop.close()
    except Exception as e:
        _log_error(f"Sync logging failed: {type(e).__name__}")

# Utility functions for different log levels with backward compatibility
class logger:
    def info(self, action : str, trace_info: str, message : str, secure: bool, metadata=None) -> None:
        """Log info level message"""
        log_event_async(action=action, trace_info=trace_info, message=message, secure=secure, level="info", metadata=metadata)

    def warning(self, action : str, trace_info: str, message : str, secure: bool, metadata=None) -> None:
        """Log warning level message"""
        log_event_async(action=action, trace_info=trace_info, message=message, secure=secure, level="warning", metadata=metadata)

    def error(self, action : str, trace_info: str, message : str, secure: bool, metadata=None) -> None:
        """Log error level message"""
        log_event_async(action=action, trace_info=trace_info, message=message, secure=secure, level="error", metadata=metadata)

    def critical(self, action : str, trace_info: str, message : str, secure: bool, metadata=None) -> None:
        """Log critical level message"""
        log_event_async(action=action, trace_info=trace_info, message=message, secure=secure, level="critical", metadata=metadata)

log = logger()