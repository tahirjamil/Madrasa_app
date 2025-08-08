from database.database_utils import get_db_connection
import aiomysql
import asyncio
import json
from datetime import datetime
from pathlib import Path

# Enhanced logger with better error handling and performance
async def log_event(action : str, trace_info, trace_info_hash, trace_info_encrypted, message : str, level="info", metadata=None):
    """
    Enhanced logging function with better error handling and metadata support
    
    """
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # Prepare metadata
            log_metadata = metadata or {}
            log_metadata.update({
                "timestamp": datetime.now().isoformat(),
                "level": level,
                "action": action,
                "trace_info": trace_info,
                "trace_info_hash": trace_info_hash,
                "trace_info_encrypted": trace_info_encrypted,
                "message": message
            })
            
            # Insert log with enhanced data
            await cursor.execute(
                "INSERT INTO logs (action, trace_info, trace_info_hash, trace_info_encrypted, message, level, metadata) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (action, trace_info, trace_info_hash, trace_info_encrypted, message, level, json.dumps(log_metadata))
            )

            # Enhanced auto-prune with better performance
            await cursor.execute("SELECT COUNT(*) AS total FROM logs")
            result = await cursor.fetchone()
            total = result['total'] if result else 0

            # If more than 1000, delete oldest (increased from 500)
            if total > 1000:
                # More efficient deletion using LIMIT
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
        await _log_to_file(action, trace_info, trace_info_hash, trace_info_encrypted, message, level, metadata, error=True)

async def _log_to_file(action : str, trace_info, trace_info_hash, trace_info_encrypted, message : str, level, metadata=None, error=False):
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
            "trace_info_hash": trace_info_hash,
            "trace_info_encrypted": trace_info_encrypted,
            "message": message,
            "metadata": metadata or {},
            "source": "file_backup" if error else "database"
        }
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
            
    except Exception as e:
        print(f"File logging also failed: {e}")

def log_event_async(action : str, trace_info, trace_info_hash, trace_info_encrypted, message : str, level="info", metadata=None):
    """
    Enhanced non-blocking wrapper for log_event that schedules logging in the background.
    Can be called without await to avoid blocking the main flow.
    
    """
    try:
        # Get current event loop, create one if none exists
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Schedule the task without waiting for it
        if loop.is_running():
            asyncio.create_task(log_event(action, trace_info, trace_info_hash, trace_info_encrypted, message, level, metadata))
        else:
            # If no loop is running, just print and skip logging
            print(f"[{level}] Skipping log: {action} - {trace_info} - {trace_info_hash} - {trace_info_encrypted} - {message}")
    except Exception as e:
        print(f"Failed to schedule log task: {e}")

def log_event_sync(action : str, trace_info, trace_info_hash, trace_info_encrypted, message : str, level="info", metadata=None):
    """
    Enhanced synchronous wrapper that runs the logging operation and waits for completion.
    Use sparingly as it will block the calling thread.

    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(log_event(action, trace_info, trace_info_hash, trace_info_encrypted, message, level, metadata))
        loop.close()
    except Exception as e:
        print(f"Sync logging failed: {e}")

# Utility functions for different log levels with backward compatibility
class logger:
    def info(self, action : str, trace_info, message : str, trace_info_hash = None, trace_info_encrypted = None, metadata=None):
        """Log info level message"""
        log_event_async(action=action, trace_info=trace_info, trace_info_hash=trace_info_hash, trace_info_encrypted=trace_info_encrypted, message=message, level="info", metadata=metadata)

    def warning(self, action : str, trace_info, message : str, trace_info_hash = None, trace_info_encrypted = None, metadata=None):
        """Log warning level message"""
        log_event_async(action=action, trace_info=trace_info, trace_info_hash=trace_info_hash, trace_info_encrypted=trace_info_encrypted, message=message, level="warning", metadata=metadata)

    def error(self, action : str, trace_info, message : str, trace_info_hash = None, trace_info_encrypted = None, metadata=None):
        """Log error level message"""
        log_event_async(action=action, trace_info=trace_info, trace_info_hash=trace_info_hash, trace_info_encrypted=trace_info_encrypted, message=message, level="error", metadata=metadata)

    def critical(self, action : str, trace_info, message : str, trace_info_hash = None, trace_info_encrypted = None, metadata=None):
        """Log critical level message"""
        log_event_async(action=action, trace_info=trace_info, trace_info_hash=trace_info_hash, trace_info_encrypted=trace_info_encrypted, message=message, level="critical", metadata=metadata)

log = logger()