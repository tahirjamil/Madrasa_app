import aiomysql
import os
from config import Config

# Centralized Async DB Connection
def get_db_config():
    # Ensure all required config values are present and not None
    if not all([
        Config.MYSQL_HOST,
        Config.MYSQL_USER,
        Config.MYSQL_PASSWORD is not None,  # Password can be empty string but not None
        Config.MYSQL_DB
    ]):
        raise ValueError("Database configuration is incomplete. Please check your config settings.")
    return dict(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD or "",
        db=Config.MYSQL_DB,
        autocommit=False,
        charset='utf8mb4',
        connect_timeout=60
    )

async def connect_to_db():
    try:
        config = get_db_config()
        return await aiomysql.connect(**config)
    except Exception as e:
        print(f"Database connection failed: {e}")
        return None

async def get_db_connection():
    """
    Get the database connection from the app context.
    This should be used in route handlers to access the single connection.
    """
    from quart import current_app
    if not hasattr(current_app, 'db') or current_app.db is None:
        raise RuntimeError("Database connection not available")
    return current_app.db

# Table Creation
async def create_tables():
    conn = None
    try:
        conn = await connect_to_db()
        if conn is None:
            print("Database connection failed during table creation")
            return

        # Get the path to the create_tables.sql file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sql_file_path = os.path.join(current_dir, 'commands', 'create_tables.sql')
        
        # Read the SQL file
        try:
            with open(sql_file_path, 'r', encoding='utf-8') as file:
                sql_content = file.read()
        except FileNotFoundError:
            print(f"SQL file not found at: {sql_file_path}")
            return
        except Exception as e:
            print(f"Error reading SQL file: {e}")
            return

        # Suppress MySQL warnings
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SET sql_notes = 0")
            await conn.commit()

        # Split the SQL content into individual statements
        # Remove comments and split by semicolon
        sql_statements = []
        lines = sql_content.split('\n')
        current_statement = ""
        
        for line in lines:
            # Skip comment lines and empty lines
            stripped_line = line.strip()
            if stripped_line.startswith('--') or stripped_line == '':
                continue
            
            current_statement += line + '\n'
            
            # If line ends with semicolon, we have a complete statement
            if stripped_line.endswith(';'):
                sql_statements.append(current_statement.strip())
                current_statement = ""

        # Execute each SQL statement
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            for statement in sql_statements:
                if statement.strip():  # Skip empty statements
                    try:
                        await cursor.execute(statement)
                        print(f"Executed SQL statement: {statement[:50]}...")
                    except Exception as e:
                        print(f"Error executing SQL statement: {e}")
                        print(f"Statement: {statement}")
                        continue

        # Re-enable MySQL warnings
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SET sql_notes = 1")
            await conn.commit()
            
        print("Database tables created successfully from create_tables.sql")

    except Exception as e:
        if conn:
            await conn.rollback()
        print(f"Database table creation failed: {e}")
        raise
    finally:
        if conn:
            try:
                if not conn.closed:
                    conn.close()
            except Exception as e:
                print(f"Error closing database connection: {e}")