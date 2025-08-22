import os
import asyncio
import aiomysql
from typing import Optional, Any, Dict
from contextlib import asynccontextmanager
from utils.helpers.improved_functions import get_project_root

from utils.helpers.logger import log

# Type alias for database configuration
AiomysqlConnectConfig = Dict[str, Any]


# Centralized Async DB Connection
def get_db_config() -> AiomysqlConnectConfig:
    # Import config here to avoid circular imports
    from config import config
    
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
            raise ValueError(f"Invalid MySQL port: {port}. Must be between 1 and 65535.")
    
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

# Global connection pool
_db_pool: Optional[Any] = None
_pool_lock = asyncio.Lock()

async def get_db_pool() -> Any:
    """Get or create the database connection pool (thread-safe)"""
    global _db_pool
    
    if _db_pool is None:
        async with _pool_lock:
            if _db_pool is None:  # Double-check pattern
                _db_pool = await create_db_pool()
    
    return _db_pool

async def create_db_pool() -> Any:
    """Create a new database connection pool"""
    from config import config
    if aiomysql is None:  # pragma: no cover
        raise RuntimeError("aiomysql is not installed. Please add 'aiomysql' to requirements.txt")

    try:
        SQL_config: Dict[str, Any] = get_db_config()
        
        # Create connection pool with optimal settings
        pool = await aiomysql.create_pool(
            **SQL_config,
            minsize=config.MYSQL_MIN_CONNECTIONS,  # Minimum connections in pool
            maxsize=config.MYSQL_MAX_CONNECTIONS,  # Maximum connections in pool
            pool_recycle=3600,  # Recycle connections after 1 hour
            echo=False,  # Don't echo SQL queries
        )
        
        log.info(action="db_pool_created", trace_info="system", message="Database connection pool created successfully", secure=False)
        return pool
        
    except Exception as e:
        log.critical(action="db_pool_creation_failed", trace_info="system", message=f"Failed to create database pool: {type(e).__name__}", secure=False)
        raise RuntimeError(f"Database pool creation failed. Please check your database configuration.")

async def close_db_pool():
    """Close the database connection pool"""
    global _db_pool
    
    if _db_pool is not None:
        _db_pool.close()
        await _db_pool.wait_closed()
        _db_pool = None
        log.info(action="db_pool_closed", trace_info="system", message="Database connection pool closed", secure=False)

@asynccontextmanager
async def get_traced_db_cursor():
    """Get a database connection from the pool (context manager)"""
    pool = await get_db_pool()
    conn = None
    try:
        from utils.otel.otel_utils import TracedCursorWrapper
        conn = await pool.acquire()
        async with conn.cursor(aiomysql.DictCursor) as _cursor:
            traced_cursor = TracedCursorWrapper(_cursor)
            yield traced_cursor
    finally:
        if conn:
            pool.release(conn)


# Table Creation
async def create_tables():
    # Import config here to avoid circular imports
    from config import config
    
    # Get the path to the create_tables.sql file
    config_dir = os.path.join(get_project_root(), 'config')
    sql_file_path = os.path.join(config_dir, 'mysql', 'create_tables.sql')
    
    # Read the SQL file
    try:
        with open(sql_file_path, 'r', encoding='utf-8') as file:
            sql_content = file.read()
    except FileNotFoundError:
        log.error(action="sql_file_not_found", trace_info="system", message=f"SQL file not found at: {sql_file_path}", secure=False)
        raise FileNotFoundError(f"SQL file not found at: {sql_file_path}")
    except Exception as e:
        log.error(action="sql_file_read_error", trace_info="system", message=f"Error reading SQL file: {type(e).__name__}", secure=False)
        raise

    try:
        async with get_traced_db_cursor() as conn:
            if conn is None:
                log.error(action="db_connection_failed", trace_info="system", message="Database connection failed during table creation", secure=False)
                raise RuntimeError("Database connection failed during table creation")

            # Suppress MySQL warnings
            if aiomysql is not None:
                async with conn.cursor(aiomysql.DictCursor) as _cursor:
                    from utils.otel.otel_utils import TracedCursorWrapper
                    cursor = TracedCursorWrapper(_cursor)
                    await cursor.execute("SET sql_notes = 0")
                    

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
            if aiomysql is not None:
                async with conn.cursor(aiomysql.DictCursor) as _cursor:
                    from utils.otel.otel_utils import TracedCursorWrapper
                    cursor = TracedCursorWrapper(_cursor)
                    for statement in sql_statements:
                        if statement.strip():  # Skip empty statements
                            try:
                                await cursor.execute(statement)
                            except Exception as e:
                                # Log error but don't expose SQL statement details
                                log.error(action="sql_statement_error", trace_info="system", message=f"Error executing SQL statement: {type(e).__name__}", secure=False)
                                # Continue with other statements
                                continue

            # Re-enable MySQL warnings
            if aiomysql is not None:
                async with conn.cursor(aiomysql.DictCursor) as _cursor:
                    from utils.otel.otel_utils import TracedCursorWrapper
                    cursor = TracedCursorWrapper(_cursor)
                    await cursor.execute("SET sql_notes = 1")
                    
                
        log.info(action="tables_created", trace_info="system", message="Database tables created successfully from create_tables.sql", secure=False)

    except Exception as e:
        log.error(action="table_creation_failed", trace_info="system", message=f"Database table creation failed: {type(e).__name__}", secure=False)
        raise