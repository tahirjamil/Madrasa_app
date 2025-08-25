#!/usr/bin/env python3
"""
SQLAlchemy Connection Test for Madrasha App

This script tests the SQLAlchemy database connection and model operations.
It helps diagnose SQLAlchemy issues and verify ORM setup.
"""

import sys
import os
import asyncio
from pathlib import Path

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Load environment variables
from dotenv import load_dotenv
PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from config.config import config
from utils.mysql.database import get_async_engine, get_async_session_factory, close_async_engine
from utils.mysql.models import Base, Translation, People, AccountType, TransactionType
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def test_environment_variables():
    """Test if required environment variables are set"""
    print("🌍 Testing Environment Variables...")
    print("-" * 50)
    
    required_vars = [
        ("MYSQL_HOST", config.MYSQL_HOST),
        ("MYSQL_USER", config.MYSQL_USER), 
        ("MYSQL_PASSWORD", config.MYSQL_PASSWORD),
        ("MYSQL_DB", config.MYSQL_DB),
        ("MYSQL_PORT", config.MYSQL_PORT)
    ]
    
    missing_vars = []
    
    for var_name, value in required_vars:
        if value:
            display_value = "*" * len(str(value)) if "PASSWORD" in var_name else str(value)
            print(f"✅ {var_name}: {display_value}")
        else:
            print(f"❌ {var_name}: Not set")
            missing_vars.append(var_name)
    
    if missing_vars:
        print(f"\n⚠️ Missing environment variables: {', '.join(missing_vars)}")
        return False
    else:
        print("\n✅ All required environment variables are set")
        return True


def test_sqlalchemy_url_generation():
    """Test SQLAlchemy URL generation"""
    print("\n🔗 Testing SQLAlchemy URL Generation...")
    print("-" * 50)
    
    try:
        url = config.get_sqlalchemy_url()
        print(f"✅ SQLAlchemy URL generated successfully")
        # Mask password in output
        safe_url = url.replace(f":{config.MYSQL_PASSWORD}@", ":***@") if config.MYSQL_PASSWORD else url
        print(f"   URL: {safe_url}")
        
        # Check URL components
        if "mysql+aiomysql://" in url:
            print("✅ Using correct aiomysql driver")
        else:
            print("❌ URL doesn't use aiomysql driver")
            return False
            
        if f"/{config.MYSQL_DB}" in url:
            print(f"✅ Database '{config.MYSQL_DB}' included in URL")
        else:
            print(f"❌ Database '{config.MYSQL_DB}' not found in URL")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ SQLAlchemy URL generation failed: {e}")
        return False


async def test_async_engine_creation():
    """Test async SQLAlchemy engine creation"""
    print("\n⚙️ Testing Async Engine Creation...")
    print("-" * 50)
    
    try:
        # Test direct engine creation (bypassing singleton for testing)
        from utils.mysql.database import get_sqlalchemy_config
        
        url = config.get_sqlalchemy_url()
        engine_config = get_sqlalchemy_config()
        engine_config["pool_pre_ping"] = False  # Disable for simple test
        
        engine = create_async_engine(url, **engine_config)
        print("✅ Async engine created successfully")
        print(f"   Engine URL: {str(engine.url).replace(f':{config.MYSQL_PASSWORD}@', ':***@')}")
        print(f"   Pool size: {engine.pool.size() if hasattr(engine.pool, 'size') else 'N/A'}") # type: ignore
        
        await engine.dispose()
        return True
        
    except Exception as e:
        print(f"❌ Async engine creation failed: {e}")
        return False


async def test_database_connection():
    """Test basic database connection"""
    print("\n🔌 Testing Database Connection...")
    print("-" * 50)
    
    engine = None
    try:
        # Create engine for testing
        from utils.mysql.database import get_sqlalchemy_config
        
        url = config.get_sqlalchemy_url()
        engine_config = get_sqlalchemy_config()
        engine_config["pool_pre_ping"] = False
        engine = create_async_engine(url, **engine_config)
        
        # Test basic connection
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1 as test"))
            test_value = result.scalar()
            
            if test_value == 1:
                print("✅ Database connection successful")
            else:
                print(f"❌ Unexpected result: {test_value}")
                return False
                
            # Test database info
            result = await conn.execute(text("SELECT VERSION()"))
            version = result.scalar()
            print(f"   MySQL Version: {version}")
            
            result = await conn.execute(text("SELECT DATABASE()"))
            current_db = result.scalar()
            print(f"   Current Database: {current_db}")
            
        return True
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False
    finally:
        if engine:
            await engine.dispose()


async def test_model_imports():
    """Test SQLAlchemy model imports"""
    print("\n📦 Testing Model Imports...")
    print("-" * 50)
    
    try:
        # Test importing key models
        models_to_test = [
            ("Base", Base),
            ("Translation", Translation),
            ("People", People),
            ("AccountType", AccountType),
            ("TransactionType", TransactionType)
        ]
        
        for model_name, model_class in models_to_test:
            print(f"✅ {model_name}: {model_class.__name__}")
            
            # Check if it has a table name
            if hasattr(model_class, '__tablename__'):
                print(f"   Table: {model_class.__tablename__}")
            
            # Check if it has a schema
            if hasattr(model_class, '__table_args__') and model_class.__table_args__:
                if isinstance(model_class.__table_args__, dict) and 'schema' in model_class.__table_args__:
                    print(f"   Schema: {model_class.__table_args__['schema']}")
        
        print("✅ All model imports successful")
        return True
        
    except Exception as e:
        print(f"❌ Model imports failed: {e}")
        return False


async def test_session_factory():
    """Test async session factory creation"""
    print("\n🏭 Testing Session Factory...")
    print("-" * 50)
    
    engine = None
    try:
        # Create engine and session factory
        from utils.mysql.database import get_sqlalchemy_config
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
        
        url = config.get_sqlalchemy_url()
        engine_config = get_sqlalchemy_config()
        engine_config["pool_pre_ping"] = False
        engine = create_async_engine(url, **engine_config)
        
        # Create session factory
        session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False
        )
        
        print("✅ Session factory created successfully")
        
        # Test session creation
        async with session_factory() as session:
            result = await session.execute(text("SELECT 'session_test' as test"))
            test_value = result.scalar()
            
            if test_value == "session_test":
                print("✅ Session operations working")
            else:
                print(f"❌ Unexpected session result: {test_value}")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Session factory test failed: {e}")
        return False
    finally:
        if engine:
            await engine.dispose()


async def test_basic_model_operations():
    """Test basic model operations without complex relationships"""
    print("\n🔧 Testing Basic Model Operations...")
    print("-" * 50)
    
    engine = None
    try:
        # Create engine and session
        from utils.mysql.database import get_sqlalchemy_config
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
        
        url = config.get_sqlalchemy_url()
        engine_config = get_sqlalchemy_config()
        engine_config["pool_pre_ping"] = False
        engine = create_async_engine(url, **engine_config)
        
        session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        async with session_factory() as session:
            # Test simple query on Translation model (if table exists)
            try:
                result = await session.execute(text("SHOW TABLES LIKE 'translations'"))
                table_exists = result.fetchone() is not None
                
                if table_exists:
                    print("✅ Found 'translations' table")
                    
                    # Try to count records
                    result = await session.execute(text("SELECT COUNT(*) FROM global.translations"))
                    count = result.scalar()
                    print(f"   Translation records: {count}")
                else:
                    print("⚠️ 'translations' table not found (may need to be created)")
                    
            except Exception as e:
                print(f"⚠️ Table check failed: {e}")
        
        print("✅ Basic model operations test completed")
        return True
        
    except Exception as e:
        print(f"❌ Basic model operations failed: {e}")
        return False
    finally:
        if engine:
            await engine.dispose()


def test_singleton_engine():
    """Test the singleton engine pattern"""
    print("\n🔄 Testing Singleton Engine Pattern...")
    print("-" * 50)
    
    try:
        # This tests the actual singleton used by the app
        async def _test_singleton():
            engine1 = await get_async_engine()
            engine2 = await get_async_engine()
            
            if engine1 is engine2:
                print("✅ Singleton pattern working correctly")
                return True
            else:
                print("❌ Singleton pattern not working - different engines returned")
                return False
        
        result = asyncio.run(_test_singleton())
        return result
        
    except Exception as e:
        print(f"❌ Singleton engine test failed: {e}")
        return False


async def run_async_tests():
    """Run all async tests"""
    async_tests = [
        ("Async Engine Creation", test_async_engine_creation),
        ("Database Connection", test_database_connection),
        ("Model Imports", test_model_imports),
        ("Session Factory", test_session_factory),
        ("Basic Model Operations", test_basic_model_operations),
    ]
    
    results = []
    
    for test_name, test_func in async_tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    return results


def main():
    """Run all tests"""
    print("🧪 SQLAlchemy Connection Diagnostic Tool")
    print("=" * 60)
    
    # Sync tests
    sync_tests = [
        ("Environment Variables", test_environment_variables),
        ("SQLAlchemy URL Generation", test_sqlalchemy_url_generation),
        ("Singleton Engine Pattern", test_singleton_engine),
    ]
    
    all_results = []
    
    # Run sync tests
    for test_name, test_func in sync_tests:
        try:
            result = test_func()
            all_results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            all_results.append((test_name, False))
    
    # Run async tests
    try:
        async_results = asyncio.run(run_async_tests())
        all_results.extend(async_results)
    except Exception as e:
        print(f"❌ Async tests failed with exception: {e}")
        all_results.append(("Async Tests", False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Results Summary")
    print("=" * 60)
    
    passed = 0
    total = len(all_results)
    
    for test_name, result in all_results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! SQLAlchemy setup is working correctly.")
    else:
        print("⚠️ Some tests failed. Please check the issues above.")
        
        # Provide troubleshooting tips
        print("\n🔧 Troubleshooting Tips:")
        print("1. Ensure MySQL server is running")
        print("2. Check MySQL credentials in .env file")
        print("3. Verify database exists and user has permissions")
        print("4. Run 'python test/mysql/test_mysql_connection.py' first")
        print("5. Check that database tables are created")
        print("6. Consider running with aiomysql==0.1.1 if issues persist")


if __name__ == "__main__":
    main()
