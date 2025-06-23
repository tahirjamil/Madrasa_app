from database import connect_to_db

# Logger
def log_event(action, phone, message):
    conn = connect_to_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO logs (action, phone, message) VALUES (%s, %s, %s)",
                (action, phone, message)
            )
            conn.commit()
    except Exception as e:
        print("Logging failed:", e)
