from database.database_utils import get_db_connection
import aiomysql, asyncio, json
from datetime import datetime
from pathlib import Path
from typing import Callable

# Enhanced logger with better error handling and performance
def get_crypto_funcs(data: str, which: str) -> str | None:
    """Lazily import crypto helpers from utils.helpers to avoid circular imports."""
    if not which in ["hash", "encrypt"]:
        raise ValueError("Invalid which value. Must be 'hash' or 'encrypt'.")
    
    try:
        from utils.helpers import encrypt_sensitive_data, hash_sensitive_data
        if which == "hash":
            return hash_sensitive_data(data)
        elif which == "encrypt":
            return encrypt_sensitive_data(data)
        else:
            return None
    except Exception:
        print("Failed to import crypto helpers from utils.helpers.py")
        return None

async def log_event(action: str, trace_info: str, message: str, secure: bool, level: str= "info", metadata=None) -> None:
    """Enhanced logging function with better error handling and metadata support"""
    try:
        conn = await get_db_connection()
        if not conn:
            raise RuntimeError("Database connection unavailable for logging")

        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # Prepare metadata
            log_metadata = metadata or {}
            log_metadata.update({
                "timestamp": datetime.now().isoformat(),
                "level": level,
                "action": action,
                "trace_info": trace_info,
                "message": message
            })

            sql = "INSERT INTO logs (action, trace_info, message, level, metadata"
            params = [action, trace_info, message, level, json.dumps(log_metadata)]

            if secure:
                trace_info_hash = get_crypto_funcs(data=trace_info, which="hash")
                trace_info_encrypted = get_crypto_funcs(data=trace_info, which="encrypt")

                if not trace_info_hash or not trace_info_encrypted:
                    raise ValueError("Failed to generate secure trace info")

                sql += ", trace_info_hash, trace_info_secure) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                params.extend([trace_info_hash, trace_info_encrypted])
            else:
                sql += ") VALUES (%s, %s, %s, %s, %s)"

            await cursor.execute(sql, params)
            await conn.commit()
            
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

            await conn.commit()
            
            
    except Exception as e:
        # Fallback to file logging if database fails
        print(f"Database logging failed: {e}")
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
        print(f"File logging also failed: {e}")

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
            # If no loop is running, just print and skip logging
            print(f"[{level}] Skipping log: action: {action} - trace_info: {trace_info} - secure: {secure} - message: {message}")
    except Exception as e:
        print(f"Failed to schedule log task: {e}")

def log_event_sync(action : str, trace_info: str, message : str, secure: bool, level="info", metadata=None) -> None:
    """Enhanced synchronous wrapper that runs the logging operation and waits for completion."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(log_event(action=action, trace_info=trace_info, message=message, level=level, metadata=metadata, secure=secure))
        loop.close()
    except Exception as e:
        print(f"Sync logging failed: {e}")

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