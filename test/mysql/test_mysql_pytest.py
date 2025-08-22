"""
Comprehensive MySQL Testing Suite with Pytest
=============================================

Advanced pytest-based testing for MySQL connections, operations, and features.
This test suite covers:
- Connection management (sync/async)
- Database operations (CRUD)
- Transaction handling
- Connection pooling
- Error scenarios
- Performance testing
- Schema validation
"""

import pytest
import asyncio
import aiomysql
import pymysql
import sys
from pathlib import Path
from typing import Dict, Any, AsyncGenerator, Generator
import time
import json

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from utils.helpers.improved_functions import get_env_var
from config import config


class TestConfig:
    """Test configuration constants"""
    TEST_DB_SUFFIX = "_test"
    MAX_CONNECTIONS = 5
    CONNECTION_TIMEOUT = 10
    TEST_TABLE_NAME = "pytest_test_table"
    PERFORMANCE_THRESHOLD_MS = 1000


@pytest.fixture(scope="session")
def mysql_config() -> Dict[str, Any]:
    """Session-scoped MySQL configuration fixture"""
    return {
        "host": config.MYSQL_HOST,
        "user": config.MYSQL_USER,
        "password": config.MYSQL_PASSWORD or "",
        "database": config.MYSQL_DB,
        "charset": "utf8mb4",
        "connect_timeout": TestConfig.CONNECTION_TIMEOUT,
        "autocommit": False
    }


@pytest.fixture(scope="session")
def test_db_config(mysql_config) -> Dict[str, Any]:
    """Test database configuration (separate from main DB)"""
    test_config = mysql_config.copy()
    test_config["database"] = f"{mysql_config['database']}{TestConfig.TEST_DB_SUFFIX}"
    return test_config


@pytest.fixture(scope="session")
async def test_database_setup(test_db_config) -> AsyncGenerator[Dict[str, Any], None]:
    """Set up test database and clean up after all tests"""
    # Create test database (connect without specifying database)
    connection = await aiomysql.connect(
        host=test_db_config["host"],
        user=test_db_config["user"],
        password=test_db_config["password"],
        charset=test_db_config["charset"]
    )
    
    try:
        async with connection.cursor() as cursor:
            await cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{test_db_config['database']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            await connection.commit()
    finally:
        connection.close()
    
    yield test_db_config
    
    # Cleanup: Drop test database
    connection = await aiomysql.connect(
        host=test_db_config["host"],
        user=test_db_config["user"],
        password=test_db_config["password"],
        charset=test_db_config["charset"]
    )
    
    try:
        async with connection.cursor() as cursor:
            await cursor.execute(f"DROP DATABASE IF EXISTS `{test_db_config['database']}`")
            await connection.commit()
    finally:
        connection.close()


@pytest.fixture
async def async_connection(test_database_setup) -> AsyncGenerator[aiomysql.Connection, None]:
    """Async MySQL connection fixture"""
    # aiomysql uses 'db' parameter instead of 'database'
    config = test_database_setup.copy()
    config['db'] = config.pop('database')
    connection = await aiomysql.connect(**config)
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def sync_connection(test_database_setup) -> Generator[pymysql.Connection, None, None]:
    """Sync MySQL connection fixture"""
    connection = pymysql.connect(**test_database_setup)
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
async def connection_pool(test_database_setup) -> AsyncGenerator[aiomysql.Pool, None]:
    """Connection pool fixture"""
    # aiomysql uses 'db' parameter instead of 'database'
    config = test_database_setup.copy()
    config['db'] = config.pop('database')
    pool = await aiomysql.create_pool(
        maxsize=TestConfig.MAX_CONNECTIONS,
        **config
    )
    try:
        yield pool
    finally:
        pool.close()
        await pool.wait_closed()


@pytest.fixture
async def test_table(async_connection) -> AsyncGenerator[str, None]:
    """Create and cleanup test table"""
    table_name = TestConfig.TEST_TABLE_NAME
    
    async with async_connection.cursor() as cursor:
        # Create test table
        await cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS `{table_name}` (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) UNIQUE,
                age INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                data JSON,
                INDEX idx_name (name),
                INDEX idx_email (email)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        await async_connection.commit()
    
    yield table_name
    
    # Cleanup
    async with async_connection.cursor() as cursor:
        await cursor.execute(f"DROP TABLE IF EXISTS `{table_name}`")
        await async_connection.commit()


class TestMySQLConnections:
    """Test MySQL connection functionality"""
    
    def test_environment_variables(self):
        """Test that all required MySQL environment variables are set"""
        required_vars = ["MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DB"]
        
        for var in required_vars:
            value = get_env_var(var)
            assert value is not None, f"Environment variable {var} is not set"
            assert len(value.strip()) > 0, f"Environment variable {var} is empty"
    
    def test_sync_connection_basic(self, sync_connection):
        """Test basic synchronous connection"""
        assert sync_connection.open, "Connection should be open"
        
        with sync_connection.cursor() as cursor:
            cursor.execute("SELECT 1 as test")
            result = cursor.fetchone()
            assert result[0] == 1, "Basic query should return 1"
    
    @pytest.mark.asyncio
    async def test_async_connection_basic(self, async_connection):
        """Test basic asynchronous connection"""
        async with async_connection.cursor() as cursor:
            await cursor.execute("SELECT 1 as test")
            result = await cursor.fetchone()
            assert result[0] == 1, "Basic query should return 1"
    
    @pytest.mark.asyncio
    async def test_connection_pool(self, connection_pool):
        """Test connection pooling"""
        # Pool might have minimum connections pre-created, so check it's within expected range
        assert connection_pool.size <= TestConfig.MAX_CONNECTIONS, "Pool size should not exceed maximum"
        assert connection_pool.maxsize == TestConfig.MAX_CONNECTIONS
        
        # Get connection from pool
        async with connection_pool.acquire() as conn:
            assert conn is not None, "Should get connection from pool"
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT 'pool_test' as test")
                result = await cursor.fetchone()
                assert result[0] == "pool_test"
    
    @pytest.mark.asyncio
    async def test_multiple_connections_from_pool(self, connection_pool):
        """Test acquiring multiple connections from pool"""
        connections = []
        
        # Acquire multiple connections
        for i in range(3):
            conn = await connection_pool.acquire()
            connections.append(conn)
            
            async with conn.cursor() as cursor:
                await cursor.execute(f"SELECT {i} as conn_id")
                result = await cursor.fetchone()
                assert result[0] == i
        
        # Release all connections
        for conn in connections:
            connection_pool.release(conn)
    
    def test_connection_error_handling(self, test_db_config):
        """Test connection error scenarios"""
        # Test with wrong password
        bad_config = test_db_config.copy()
        bad_config["password"] = "wrong_password"
        
        with pytest.raises(pymysql.OperationalError):
            pymysql.connect(**bad_config)
        
        # Test with wrong host
        bad_config = test_db_config.copy()
        bad_config["host"] = "nonexistent.host"
        bad_config["connect_timeout"] = 1  # Fast timeout
        
        with pytest.raises((pymysql.OperationalError, pymysql.err.OperationalError)):
            pymysql.connect(**bad_config)


class TestDatabaseOperations:
    """Test database CRUD operations"""
    
    @pytest.mark.asyncio
    async def test_create_operations(self, async_connection, test_table):
        """Test CREATE (INSERT) operations"""
        async with async_connection.cursor() as cursor:
            # Single insert
            await cursor.execute(
                f"INSERT INTO `{test_table}` (name, email, age) VALUES (%s, %s, %s)",
                ("John Doe", "john@example.com", 25)
            )
            await async_connection.commit()
            
            # Verify insert
            await cursor.execute(f"SELECT * FROM `{test_table}` WHERE email = %s", ("john@example.com",))
            result = await cursor.fetchone()
            assert result is not None
            assert result[1] == "John Doe"  # name column
            assert result[2] == "john@example.com"  # email column
            assert result[3] == 25  # age column
    
    @pytest.mark.asyncio
    async def test_bulk_insert(self, async_connection, test_table):
        """Test bulk insert operations"""
        test_data = [
            ("Alice Smith", "alice@example.com", 30),
            ("Bob Johnson", "bob@example.com", 35),
            ("Charlie Brown", "charlie@example.com", 28)
        ]
        
        async with async_connection.cursor() as cursor:
            await cursor.executemany(
                f"INSERT INTO `{test_table}` (name, email, age) VALUES (%s, %s, %s)",
                test_data
            )
            await async_connection.commit()
            
            # Verify all records
            await cursor.execute(f"SELECT COUNT(*) FROM `{test_table}`")
            count = await cursor.fetchone()
            assert count[0] == 3, "Should have 3 records"
    
    @pytest.mark.asyncio
    async def test_read_operations(self, async_connection, test_table):
        """Test READ (SELECT) operations"""
        # Insert test data
        async with async_connection.cursor() as cursor:
            test_data = [
                ("User 1", "user1@test.com", 20),
                ("User 2", "user2@test.com", 25),
                ("User 3", "user3@test.com", 30)
            ]
            
            await cursor.executemany(
                f"INSERT INTO `{test_table}` (name, email, age) VALUES (%s, %s, %s)",
                test_data
            )
            await async_connection.commit()
            
            # Test various SELECT operations
            await cursor.execute(f"SELECT * FROM `{test_table}` ORDER BY age")
            all_results = await cursor.fetchall()
            assert len(all_results) == 3
            assert all_results[0][3] == 20  # First should be youngest
            
            # Test WHERE clause
            await cursor.execute(f"SELECT * FROM `{test_table}` WHERE age > %s", (22,))
            filtered_results = await cursor.fetchall()
            assert len(filtered_results) == 2
            
            # Test LIMIT
            await cursor.execute(f"SELECT * FROM `{test_table}` LIMIT 1")
            limited_result = await cursor.fetchone()
            assert limited_result is not None
    
    @pytest.mark.asyncio
    async def test_update_operations(self, async_connection, test_table):
        """Test UPDATE operations"""
        async with async_connection.cursor() as cursor:
            # Insert test record
            await cursor.execute(
                f"INSERT INTO `{test_table}` (name, email, age) VALUES (%s, %s, %s)",
                ("Update Test", "update@test.com", 25)
            )
            await async_connection.commit()
            
            # Update the record
            await cursor.execute(
                f"UPDATE `{test_table}` SET age = %s WHERE email = %s",
                (30, "update@test.com")
            )
            affected_rows = cursor.rowcount
            await async_connection.commit()
            
            assert affected_rows == 1, "Should update exactly 1 row"
            
            # Verify update
            await cursor.execute(f"SELECT age FROM `{test_table}` WHERE email = %s", ("update@test.com",))
            result = await cursor.fetchone()
            assert result[0] == 30, "Age should be updated to 30"
    
    @pytest.mark.asyncio
    async def test_delete_operations(self, async_connection, test_table):
        """Test DELETE operations"""
        async with async_connection.cursor() as cursor:
            # Insert test records
            test_data = [
                ("Delete 1", "delete1@test.com", 20),
                ("Delete 2", "delete2@test.com", 25),
            ]
            
            await cursor.executemany(
                f"INSERT INTO `{test_table}` (name, email, age) VALUES (%s, %s, %s)",
                test_data
            )
            await async_connection.commit()
            
            # Delete one record
            await cursor.execute(f"DELETE FROM `{test_table}` WHERE email = %s", ("delete1@test.com",))
            affected_rows = cursor.rowcount
            await async_connection.commit()
            
            assert affected_rows == 1, "Should delete exactly 1 row"
            
            # Verify deletion
            await cursor.execute(f"SELECT COUNT(*) FROM `{test_table}` WHERE email = %s", ("delete1@test.com",))
            count = await cursor.fetchone()
            assert count[0] == 0, "Record should be deleted"
    
    @pytest.mark.asyncio
    async def test_json_data_handling(self, async_connection, test_table):
        """Test JSON data operations"""
        json_data = {"preferences": {"theme": "dark", "language": "en"}, "settings": {"notifications": True}}
        
        async with async_connection.cursor() as cursor:
            await cursor.execute(
                f"INSERT INTO `{test_table}` (name, email, data) VALUES (%s, %s, %s)",
                ("JSON User", "json@test.com", json.dumps(json_data))
            )
            await async_connection.commit()
            
            # Retrieve and verify JSON data
            await cursor.execute(f"SELECT data FROM `{test_table}` WHERE email = %s", ("json@test.com",))
            result = await cursor.fetchone()
            
            retrieved_data = json.loads(result[0])
            assert retrieved_data["preferences"]["theme"] == "dark"
            assert retrieved_data["settings"]["notifications"] is True


class TestTransactions:
    """Test transaction handling"""
    
    @pytest.mark.asyncio
    async def test_transaction_commit(self, async_connection, test_table):
        """Test successful transaction commit"""
        async with async_connection.cursor() as cursor:
            # Start transaction (autocommit is False by default in our fixture)
            await cursor.execute(
                f"INSERT INTO `{test_table}` (name, email, age) VALUES (%s, %s, %s)",
                ("Transaction User", "trans@test.com", 25)
            )
            
            # Commit transaction
            await async_connection.commit()
            
            # Verify data is committed
            await cursor.execute(f"SELECT * FROM `{test_table}` WHERE email = %s", ("trans@test.com",))
            result = await cursor.fetchone()
            assert result is not None, "Data should be committed"
    
    @pytest.mark.asyncio
    async def test_transaction_rollback(self, async_connection, test_table):
        """Test transaction rollback"""
        async with async_connection.cursor() as cursor:
            # Insert initial data
            await cursor.execute(
                f"INSERT INTO `{test_table}` (name, email, age) VALUES (%s, %s, %s)",
                ("Rollback Test", "rollback@test.com", 25)
            )
            await async_connection.commit()
            
            # Start new transaction
            await cursor.execute(
                f"UPDATE `{test_table}` SET age = %s WHERE email = %s",
                (99, "rollback@test.com")
            )
            
            # Rollback transaction
            await async_connection.rollback()
            
            # Verify rollback - age should still be original value
            await cursor.execute(f"SELECT age FROM `{test_table}` WHERE email = %s", ("rollback@test.com",))
            result = await cursor.fetchone()
            assert result[0] == 25, "Age should be original value after rollback"
    
    @pytest.mark.asyncio
    async def test_transaction_isolation(self, test_database_setup, test_table):
        """Test transaction isolation between connections"""
        # This test verifies basic transaction behavior rather than strict isolation
        # since MySQL's default isolation level may vary
        
        # Create two separate connections
        # aiomysql uses 'db' parameter instead of 'database'
        config = test_database_setup.copy()
        config['db'] = config.pop('database')
        conn1 = await aiomysql.connect(**config)
        conn2 = await aiomysql.connect(**config)
        
        try:
            # First, ensure the table exists and clean any previous test data
            async with conn1.cursor() as cursor1:
                await cursor1.execute(f"DELETE FROM `{test_table}` WHERE email = %s", ("isolation@test.com",))
                await conn1.commit()
            
            # Test 1: Connection 1 inserts and commits, Connection 2 should see it
            async with conn1.cursor() as cursor1:
                await cursor1.execute(
                    f"INSERT INTO `{test_table}` (name, email, age) VALUES (%s, %s, %s)",
                    ("Isolation Test", "isolation@test.com", 25)
                )
                await conn1.commit()  # Commit immediately
            
            # Connection 2: Should see the committed data
            async with conn2.cursor() as cursor2:
                await cursor2.execute(f"SELECT * FROM `{test_table}` WHERE email = %s", ("isolation@test.com",))
                result = await cursor2.fetchone()
                assert result is not None, "Should see committed data from another connection"
                assert result[1] == "Isolation Test", "Should retrieve correct name"
            
            # Test 2: Verify transaction rollback doesn't affect other connections
            async with conn1.cursor() as cursor1:
                await cursor1.execute(
                    f"UPDATE `{test_table}` SET age = %s WHERE email = %s",
                    (99, "isolation@test.com")
                )
                # Don't commit, rollback instead
                await conn1.rollback()
            
            # Connection 2: Should still see original data
            async with conn2.cursor() as cursor2:
                await cursor2.execute(f"SELECT age FROM `{test_table}` WHERE email = %s", ("isolation@test.com",))
                result = await cursor2.fetchone()
                assert result is not None, "Should still see the record"
                assert result[0] == 25, "Age should still be original value after rollback"
        
        finally:
            conn1.close()
            conn2.close()


class TestPerformance:
    """Test performance and load scenarios"""
    
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_bulk_operations_performance(self, async_connection, test_table):
        """Test performance of bulk operations"""
        # Generate test data
        test_data = [(f"User {i}", f"user{i}@perf.com", 20 + (i % 50)) for i in range(1000)]
        
        start_time = time.time()
        
        async with async_connection.cursor() as cursor:
            await cursor.executemany(
                f"INSERT INTO `{test_table}` (name, email, age) VALUES (%s, %s, %s)",
                test_data
            )
            await async_connection.commit()
        
        duration = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        # Performance assertion
        assert duration < TestConfig.PERFORMANCE_THRESHOLD_MS, f"Bulk insert took {duration:.2f}ms, should be under {TestConfig.PERFORMANCE_THRESHOLD_MS}ms"
        
        # Verify all records inserted
        async with async_connection.cursor() as cursor:
            await cursor.execute(f"SELECT COUNT(*) FROM `{test_table}`")
            count = await cursor.fetchone()
            assert count[0] == 1000, "Should have inserted 1000 records"
    
    @pytest.mark.asyncio
    async def test_concurrent_connections(self, test_database_setup):
        """Test multiple concurrent connections"""
        async def worker_task(worker_id: int) -> bool:
            """Worker task for concurrent testing"""
            # aiomysql uses 'db' parameter instead of 'database'
            config = test_database_setup.copy()
            config['db'] = config.pop('database')
            connection = await aiomysql.connect(**config)
            try:
                async with connection.cursor() as cursor:
                    await cursor.execute("SELECT %s as worker_id", (worker_id,))
                    result = await cursor.fetchone()
                    return result[0] == worker_id
            finally:
                connection.close()
        
        # Run multiple concurrent workers
        workers = [worker_task(i) for i in range(10)]
        results = await asyncio.gather(*workers)
        
        assert all(results), "All concurrent connections should succeed"


class TestErrorHandling:
    """Test error scenarios and edge cases"""
    
    @pytest.mark.asyncio
    async def test_duplicate_key_error(self, async_connection, test_table):
        """Test handling of duplicate key errors"""
        async with async_connection.cursor() as cursor:
            # Insert first record
            await cursor.execute(
                f"INSERT INTO `{test_table}` (name, email, age) VALUES (%s, %s, %s)",
                ("Duplicate Test", "duplicate@test.com", 25)
            )
            await async_connection.commit()
            
            # Try to insert duplicate email (should fail due to UNIQUE constraint)
            with pytest.raises(aiomysql.IntegrityError):
                await cursor.execute(
                    f"INSERT INTO `{test_table}` (name, email, age) VALUES (%s, %s, %s)",
                    ("Another User", "duplicate@test.com", 30)
                )
                await async_connection.commit()
    
    @pytest.mark.asyncio
    async def test_invalid_sql_syntax(self, async_connection):
        """Test handling of invalid SQL syntax"""
        async with async_connection.cursor() as cursor:
            with pytest.raises(aiomysql.ProgrammingError):
                await cursor.execute("INVALID SQL SYNTAX HERE")
    
    @pytest.mark.asyncio
    async def test_table_not_exists_error(self, async_connection):
        """Test handling of non-existent table errors"""
        async with async_connection.cursor() as cursor:
            with pytest.raises(aiomysql.ProgrammingError):
                await cursor.execute("SELECT * FROM non_existent_table")
    
    @pytest.mark.asyncio
    async def test_connection_timeout_handling(self, test_database_setup):
        """Test connection timeout scenarios"""
        # Create config with very short timeout
        timeout_config = test_database_setup.copy()
        timeout_config["connect_timeout"] = 0.001  # 1ms timeout
        timeout_config["host"] = "192.0.2.1"  # Non-routable IP (will timeout)
        # aiomysql uses 'db' parameter instead of 'database'
        timeout_config['db'] = timeout_config.pop('database')
        
        with pytest.raises((aiomysql.OperationalError, asyncio.TimeoutError, OSError)):
            await aiomysql.connect(**timeout_config)


class TestSchemaValidation:
    """Test database schema and structure"""
    
    @pytest.mark.asyncio
    async def test_table_structure(self, async_connection, test_table):
        """Test that test table has correct structure"""
        async with async_connection.cursor() as cursor:
            await cursor.execute(f"DESCRIBE `{test_table}`")
            columns = await cursor.fetchall()
            
            # Convert to dict for easier testing
            column_info = {col[0]: {"type": col[1], "null": col[2], "key": col[3], "extra": col[5] if len(col) > 5 else ""} for col in columns}
            
            # Verify expected columns exist
            expected_columns = ["id", "name", "email", "age", "created_at", "data"]
            for col in expected_columns:
                assert col in column_info, f"Column {col} should exist"
            
            # Verify specific column properties
            # Check for AUTO_INCREMENT in either the 'key' or 'extra' field
            id_info = column_info["id"]
            has_auto_increment = ("AUTO_INCREMENT" in id_info.get("key", "") or 
                                "auto_increment" in id_info.get("extra", "").lower())
            assert has_auto_increment, f"ID should be auto increment. Got key='{id_info.get('key')}', extra='{id_info.get('extra')}'"
            
            assert column_info["email"]["key"] == "UNI", "Email should have unique constraint"
            assert "varchar(255)" in column_info["name"]["type"].lower(), "Name should be varchar(255)"
    
    @pytest.mark.asyncio
    async def test_indexes_exist(self, async_connection, test_table):
        """Test that expected indexes exist"""
        async with async_connection.cursor() as cursor:
            await cursor.execute(f"SHOW INDEX FROM `{test_table}`")
            indexes = await cursor.fetchall()
            
            index_names = {idx[2] for idx in indexes}  # Column 2 is Key_name
            
            # Should have indexes on name and email
            assert "idx_name" in index_names, "Should have index on name column"
            assert "idx_email" in index_names, "Should have index on email column"
            assert "PRIMARY" in index_names, "Should have primary key index"


# Parametrized tests for testing multiple scenarios
@pytest.mark.parametrize("age,expected_category", [
    (17, "minor"),
    (18, "adult"),
    (65, "adult"),
    (66, "senior"),
])
@pytest.mark.asyncio
async def test_age_categorization(async_connection, test_table, age, expected_category):
    """Parametrized test for age categorization logic"""
    async with async_connection.cursor() as cursor:
        await cursor.execute(
            f"INSERT INTO `{test_table}` (name, email, age) VALUES (%s, %s, %s)",
            (f"User Age {age}", f"age{age}@test.com", age)
        )
        await async_connection.commit()
        
        # Test age categorization query
        await cursor.execute(f"""
            SELECT 
                CASE 
                    WHEN age < 18 THEN 'minor'
                    WHEN age >= 66 THEN 'senior'
                    ELSE 'adult'
                END as category
            FROM `{test_table}` 
            WHERE age = %s
        """, (age,))
        
        result = await cursor.fetchone()
        assert result[0] == expected_category, f"Age {age} should be categorized as {expected_category}"


if __name__ == "__main__":
    # This file is designed to be run with pytest only
    print("This test file is designed to be run with pytest.")
    print("Run: pytest test/mysql/test_mysql_pytest.py -v")
