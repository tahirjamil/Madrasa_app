from database.database_utils import get_db_connection
import aiomysql
import asyncio

# Logger with auto-prune
async def log_event(action, phone, message):
    conn = await get_db_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # Insert log
            await cursor.execute(
                "INSERT INTO logs (action, phone, message) VALUES (%s, %s, %s)",
                (action, phone, message)
            )

            # Count total rows
            await cursor.execute("SELECT COUNT(*) AS total FROM logs")
            total = await cursor.fetchone()['total']

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
        print("Logging failed:", e)

# Non-blocking wrapper that can be called without await
def log_event_async(action, phone, message):
    """
    Non-blocking wrapper for log_event that schedules logging in the background.
    Can be called without await to avoid blocking the main flow.
    """
    try:
        asyncio.create_task(log_event(action, phone, message))
    except Exception as e:
        print(f"Failed to schedule log task: {e}")
