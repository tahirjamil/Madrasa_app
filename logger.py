from database import connect_to_db

# Logger with auto-prune
def log_event(action, phone, message):
    conn = connect_to_db()
    try:
        with conn.cursor() as cursor:
            # Insert log
            cursor.execute(
                "INSERT INTO logs (action, phone, message) VALUES (%s, %s, %s)",
                (action, phone, message)
            )

            # Count total rows
            cursor.execute("SELECT COUNT(*) AS total FROM logs")
            total = cursor.fetchone()['total']

            # If more than 500, delete oldest
            if total > 500:
                # Deletes rows older than the newest 500, by log_id ASC
                cursor.execute("""
                    DELETE FROM logs
                    WHERE log_id NOT IN (
                        SELECT log_id FROM (
                            SELECT log_id FROM logs
                            ORDER BY created_at DESC
                            LIMIT 500
                        ) AS keep_logs
                    )
                """)

            conn.commit()
    except Exception as e:
        print("Logging failed:", e)
