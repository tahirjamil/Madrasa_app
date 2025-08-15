import asyncio
import aiomysql, os
from typing import Any, cast, TypedDict, Optional
from quart import current_app
from config import config, MadrasaApp

class AiomysqlConnectConfig(TypedDict, total=False):
    host: str
    unix_socket: str
    user: str
    password: str
    db: str
    port: int
    autocommit: bool
    charset: str
    connect_timeout: int


# Centralized Async DB Connection
def get_db_config() -> AiomysqlConnectConfig:
    # Basic presence checks
    if not all([
        config.MYSQL_HOST,
        config.MYSQL_USER,
        config.MYSQL_PASSWORD is not None,
        config.MYSQL_DB
    ]):
        raise ValueError("Database configuration is incomplete. Please check your config settings.")

    # Cast/normalize primitive values to explicit typed locals
    host: str = str(config.MYSQL_HOST)
    user: str = str(config.MYSQL_USER)
    password: str = str(config.MYSQL_PASSWORD)
    db: str = str(config.MYSQL_DB)

    # Port (int)
    port: int = 3306
    if hasattr(config, "MYSQL_PORT") and config.MYSQL_PORT is not None:
        try:
            port = int(config.MYSQL_PORT)
        except Exception:
            raise ValueError(f"MYSQL_PORT must be an integer, got: {config.MYSQL_PORT}")
        if port <= 0 or port > 65535:
            port = 3306  # Default MySQL port
            print(f"Invalid MySQL port: {port}. Must be between 1 and 65535.")

    # Timeout (int)
    try:
        timeout: int = int(config.MYSQL_TIMEOUT) if hasattr(config, "MYSQL_TIMEOUT") and config.MYSQL_TIMEOUT is not None else 60
    except Exception:
        timeout = 60

    autocommit: bool = True
    charset: str = "utf8mb4"

    # Build unix-socket config
    if hasattr(config, "MYSQL_UNIX_SOCKET") and config.MYSQL_UNIX_SOCKET:
        unix_socket: str = str(config.MYSQL_UNIX_SOCKET)
        unix_cfg: AiomysqlConnectConfig = {
            "unix_socket": unix_socket,
            "user": user,
            "password": password,
            "db": db,
            "autocommit": autocommit,
            "charset": charset,
            "connect_timeout": timeout,
        }
        return unix_cfg

    # Build TCP config
    tcp_cfg: AiomysqlConnectConfig = {
        "host": host,
        "user": user,
        "password": password,
        "db": db,
        "port": port,
        "autocommit": autocommit,
        "charset": charset,
        "connect_timeout": timeout,
    }
    return tcp_cfg

async def connect_to_db() -> Optional[aiomysql.Connection]:
    if aiomysql is None:  # pragma: no cover
        raise RuntimeError("aiomysql is not installed. Please add 'aiomysql' to requirements.txt")

    try:
        SQL_config: AiomysqlConnectConfig = get_db_config()
        return await aiomysql.connect(**SQL_config)
    except Exception as e:
        # Prefer raising in production, but printing is okay for dev
        print(f"Database connection failed: {e}")
        return None

async def get_db():
    """Get the database connection from the app context."""
    app = cast(MadrasaApp, current_app)
    if not hasattr(app, 'db') or app.db is None:
        raise RuntimeError("Database connection not available")
    return app.db

async def get_db_connection(max_retries: int = 3) -> Any:
    """Get database connection with retry logic"""
    for attempt in range(max_retries):
        try:
            conn = await get_db()
            return conn
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            else:
                await asyncio.sleep(0.1 * (attempt + 1))  # Exponential backoff
    
    raise Exception("Database connection failed")

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
        async with conn.cursor(aiomysql.DictCursor) as _cursor:
            from observability.db_tracing import TracedCursorWrapper
            cursor = TracedCursorWrapper(_cursor)
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
        async with conn.cursor(aiomysql.DictCursor) as _cursor:
            from observability.db_tracing import TracedCursorWrapper
            cursor = TracedCursorWrapper(_cursor)
            for statement in sql_statements:
                if statement.strip():  # Skip empty statements
                    try:
                        await cursor.execute(statement)
                    except Exception as e:
                        print(f"Error executing SQL statement: {e}")
                        print(f"Statement: {statement}")
                        continue

        # Re-enable MySQL warnings
        async with conn.cursor(aiomysql.DictCursor) as _cursor:
            from observability.db_tracing import TracedCursorWrapper
            cursor = TracedCursorWrapper(_cursor)
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