#!/usr/bin/env python3
"""
MySQL Connection Test for Madrasha App

This script tests the MySQL database connection and configuration.
It helps diagnose connection issues and verify database setup.
"""

import sys
import os
import asyncio
import aiomysql
from pathlib import Path

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import config

def test_config_loading():
    """Test if configuration is loaded correctly"""
    print("🔧 Testing Configuration Loading...")
    print("-" * 50)
    
    try:
        print(f"✅ Config loaded successfully")
        print(f"   MYSQL_HOST: {config.MYSQL_HOST}")
        print(f"   MYSQL_USER: {config.MYSQL_USER}")
        print(f"   MYSQL_DB: {config.MYSQL_DB}")
        print(f"   MYSQL_PASSWORD: {'*' * len(config.MYSQL_PASSWORD) if config.MYSQL_PASSWORD else 'None'}")
        return True
    except Exception as e:
        print(f"❌ Config loading failed: {e}")
        return False

def test_mysql_connection_sync():
    """Test MySQL connection using synchronous approach"""
    print("\n🔌 Testing MySQL Connection (Synchronous)...")
    print("-" * 50)
    
    try:
        import pymysql
        
        # Test connection
        connection = pymysql.connect(
            host=config.MYSQL_HOST,
            user=config.MYSQL_USER,
            password=config.MYSQL_PASSWORD or "",
            database=config.MYSQL_DB,
            charset='utf8mb4',
            connect_timeout=10
        )
        
        print("✅ MySQL connection successful!")
        
        # Test basic operations
        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone() or ("Unknown",)
            print(f"   MySQL Version: {version[0]}")
            
            cursor.execute("SHOW DATABASES")
            databases = cursor.fetchall()
            print(f"   Available databases: {[db[0] for db in databases]}")
            
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            print(f"   Tables in {config.MYSQL_DB}: {[table[0] for table in tables]}")
        
        connection.close()
        return True
        
    except Exception as e:
        print(f"❌ MySQL connection failed: {e}")
        return False

async def test_mysql_connection_async():
    """Test MySQL connection using asynchronous approach (like the app)"""
    print("\n🔌 Testing MySQL Connection (Asynchronous)...")
    print("-" * 50)
    
    try:
        # Test connection using aiomysql (same as the app)
        connection = await aiomysql.connect(
            host=config.MYSQL_HOST,
            user=config.MYSQL_USER,
            password=config.MYSQL_PASSWORD or "",
            db=config.MYSQL_DB,
            charset='utf8mb4',
            connect_timeout=10
        )
        
        print("✅ Async MySQL connection successful!")
        
        # Test basic operations
        async with connection.cursor() as cursor:
            await cursor.execute("SELECT VERSION()")
            version = await cursor.fetchone() or ("Unknown",)
            print(f"   MySQL Version: {version[0]}")
            
            await cursor.execute("SHOW DATABASES")
            databases = await cursor.fetchall()
            print(f"   Available databases: {[db[0] for db in databases]}")
            
            await cursor.execute("SHOW TABLES")
            tables = await cursor.fetchall()
            print(f"   Tables in {config.MYSQL_DB}: {[table[0] for table in tables]}")
        
        connection.close()
        return True
        
    except Exception as e:
        print(f"❌ Async MySQL connection failed: {e}")
        return False

def test_database_creation():
    """Test if database can be created if it doesn't exist"""
    print("\n🗄️ Testing Database Creation...")
    print("-" * 50)
    
    try:
        import pymysql
        
        # Connect without specifying database
        connection = pymysql.connect(
            host=config.MYSQL_HOST,
            user=config.MYSQL_USER,
            password=config.MYSQL_PASSWORD or "",
            charset='utf8mb4',
            connect_timeout=10
        )
        
        with connection.cursor() as cursor:
            # Try to create database if it doesn't exist
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{config.MYSQL_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            connection.commit()
            print(f"✅ Database '{config.MYSQL_DB}' created/verified successfully")
        
        connection.close()
        return True
        
    except Exception as e:
        print(f"❌ Database creation failed: {e}")
        return False

def test_sql_file_parsing():
    """Test if the SQL file can be parsed correctly"""
    print("\n📄 Testing SQL File Parsing...")
    print("-" * 50)
    
    try:
        project_root = Path(__file__).parent.parent.parent
        sql_file_path = project_root / "config" / "mysql" / "create_tables.sql"
        
        if not sql_file_path.exists():
            print(f"❌ SQL file not found: {sql_file_path}")
            return False
        
        with open(sql_file_path, 'r', encoding='utf-8') as file:
            sql_content = file.read()
        
        # Check for common syntax issues
        issues = []
        
        if "ENGINE=InnoDB" in sql_content:
            issues.append("Found 'ENGINE=InnoDB' without space")
        
        if "ENGINE = InnoDB" in sql_content:
            print("✅ SQL file uses correct 'ENGINE = InnoDB' syntax")
        
        # Count CREATE TABLE statements
        create_table_count = sql_content.count("CREATE TABLE")
        print(f"   Found {create_table_count} CREATE TABLE statements")
        
        if issues:
            print(f"❌ SQL file has issues: {', '.join(issues)}")
            return False
        else:
            print("✅ SQL file parsing successful")
            return True
            
    except Exception as e:
        print(f"❌ SQL file parsing failed: {e}")
        return False

def test_environment_variables():
    """Test if required environment variables are set"""
    print("\n🌍 Testing Environment Variables...")
    print("-" * 50)
    
    required_vars = [
        "MYSQL_HOST",
        "MYSQL_USER", 
        "MYSQL_PASSWORD",
        "MYSQL_DB"
    ]
    
    missing_vars = []
    
    for var in required_vars:
        value = get_env_var(var)
        if value:
            print(f"✅ {var}: {value}")
        else:
            print(f"❌ {var}: Not set")
            missing_vars.append(var)
    
    if missing_vars:
        print(f"\n⚠️ Missing environment variables: {', '.join(missing_vars)}")
        print("   Please check your .env file")
        return False
    else:
        print("\n✅ All required environment variables are set")
        return True

def main():
    """Run all tests"""
    print("🧪 MySQL Connection Diagnostic Tool")
    print("=" * 60)
    
    tests = [
        ("Environment Variables", test_environment_variables),
        ("Configuration Loading", test_config_loading),
        ("SQL File Parsing", test_sql_file_parsing),
        ("Database Creation", test_database_creation),
        ("MySQL Connection (Sync)", test_mysql_connection_sync),
        ("MySQL Connection (Async)", lambda: asyncio.run(test_mysql_connection_async())),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Results Summary")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Database connection should work.")
    else:
        print("⚠️ Some tests failed. Please check the issues above.")
        
        # Provide troubleshooting tips
        print("\n🔧 Troubleshooting Tips:")
        print("1. Ensure MySQL server is running")
        print("2. Check MySQL credentials in .env file")
        print("3. Verify database exists and user has permissions")
        print("4. Check firewall settings if connecting remotely")
        print("5. Try connecting with MySQL client to verify credentials")

if __name__ == "__main__":
    main()
