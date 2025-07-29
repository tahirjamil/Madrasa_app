from database.database_utils import get_db_connection
import aiomysql
import asyncio

# Logger with auto-prune
async def log_event(action, phone, message):
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # Insert log
            await cursor.execute(
                "INSERT INTO logs (action, phone, message) VALUES (%s, %s, %s)",
                (action, phone, message)
            )

            # Count total rows
            await cursor.execute("SELECT COUNT(*) AS total FROM logs")
            result = await cursor.fetchone()
            total = result['total'] if result else 0

            # If more than 500, delete oldest
            if total > 500:
                # Deletes rows older than the newest 500, by log_id ASC
                await cursor.execute("""
                    DELETE FROM logs
                    WHERE log_id NOT IN (
                        SELECT log_id FROM (
                            SELECT log_id FROM logs
                            ORDER BY created_at DESC
                            LIMIT 500
                        ) AS keep_logs
                    )
                """)

            await conn.commit()
    except Exception as e:
        print(f"Logging failed: {e}")

# Non-blocking wrapper that can be called without await
def log_event_async(action, phone, message):
    """
    Non-blocking wrapper for log_event that schedules logging in the background.
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
            asyncio.create_task(log_event(action, phone, message))
        else:
            # If no loop is running, just print and skip logging
            print(f"Skipping log: {action} - {phone} - {message}")
    except Exception as e:
        print(f"Failed to schedule log task: {e}")

# Synchronous wrapper for cases where we want to ensure logging completes
def log_event_sync(action, phone, message):
    """
    Synchronous wrapper that runs the logging operation and waits for completion.
    Use sparingly as it will block the calling thread.
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(log_event(action, phone, message))
        loop.close()
    except Exception as e:
        print(f"Sync logging failed: {e}")
