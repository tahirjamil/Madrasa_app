"""
Comprehensive SQLAlchemy Testing Suite with Pytest
================================================

Advanced pytest-based testing for SQLAlchemy async operations with the Madrasha application models.
This test suite covers:
- Async SQLAlchemy engine and session management
- Model creation and relationships
- Database operations (CRUD) using ORM
- Transaction handling
- Connection pooling
- Error scenarios
- Performance testing
- Schema validation
- Multi-schema operations
"""

import pytest
import asyncio
import sys
from pathlib import Path
from typing import Dict, Any, AsyncGenerator, List
import time
from datetime import datetime, date
from decimal import Decimal

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine
from sqlalchemy import text, select, insert, update, delete, func
from sqlalchemy.exc import IntegrityError, ProgrammingError

from utils.mysql.database import (
    get_async_engine, get_async_session_factory, 
    close_async_engine, create_tables, drop_tables
)
from utils.mysql.models import (
    Base, GlobalTranslation, User, Transaction, Verification, Book,
    Interaction, Blocklist, AccountType, Translation, People, Payment,
    Routine, Exam, Event, Log, PasswordResetLog,
    TransactionType, Gender, AccountTypeEnum, VerificationStatus,
    Weekday, EventType, LogLevel
)
from config.config import config
from utils.helpers.improved_functions import get_env_var


class TestConfig:
    """Test configuration constants"""
    TEST_DB_SUFFIX = "_test_sqlalchemy"
    MAX_TEST_RECORDS = 100
    PERFORMANCE_THRESHOLD_MS = 2000
    TEST_TIMEOUT = 30


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Session-scoped async SQLAlchemy engine fixture"""
    # Override database name for testing
    original_db = config.MYSQL_DB
    config.MYSQL_DB = f"{original_db}{TestConfig.TEST_DB_SUFFIX}"
    
    engine = None
    try:
        engine = await get_async_engine()
        
        # Create test database if it doesn't exist
        async with engine.begin() as conn:
            await conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{config.MYSQL_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
        
        yield engine
        
    finally:
        # Cleanup: Drop test database
        if engine is not None:
            try:
                async with engine.begin() as conn:
                    await conn.execute(text(f"DROP DATABASE IF EXISTS `{config.MYSQL_DB}`"))
            except Exception:
                pass
            
            await close_async_engine()
        config.MYSQL_DB = original_db


@pytest.fixture(scope="session")
async def test_session_factory(test_engine):
    """Session-scoped async session factory"""
    return await get_async_session_factory()


@pytest.fixture
async def async_session(test_session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Function-scoped async session fixture"""
    async with test_session_factory() as session:
        yield session


@pytest.fixture(scope="session")
async def test_schemas_setup(test_engine):
    """Set up test database schemas"""
    async with test_engine.begin() as conn:
        # Create schemas
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS `global`"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS `annur`"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS `logs`"))
    
    yield
    
    # Cleanup schemas
    async with test_engine.begin() as conn:
        try:
            await conn.execute(text("DROP SCHEMA IF EXISTS `logs`"))
            await conn.execute(text("DROP SCHEMA IF EXISTS `annur`"))
            await conn.execute(text("DROP SCHEMA IF EXISTS `global`"))
        except Exception:
            pass


@pytest.fixture(scope="session")
async def test_tables_setup(test_engine, test_schemas_setup):
    """Set up test database tables"""
    # Create all tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield
    
    # Cleanup tables
    async with test_engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.drop_all)
        except Exception:
            pass


class TestSQLAlchemyEngine:
    """Test SQLAlchemy engine and connection management"""
    
    def test_environment_variables(self):
        """Test that all required environment variables are set"""
        required_vars = ["MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DB"]
        
        for var in required_vars:
            value = get_env_var(var)
            assert value is not None, f"Environment variable {var} is not set"
            assert len(value.strip()) > 0, f"Environment variable {var} is empty"
    
    @pytest.mark.asyncio
    async def test_engine_creation(self, test_engine):
        """Test async engine creation"""
        assert test_engine is not None, "Engine should be created"
        assert test_engine.url.database.endswith(TestConfig.TEST_DB_SUFFIX), "Should use test database"
    
    @pytest.mark.asyncio
    async def test_basic_connection(self, test_engine):
        """Test basic database connection"""
        async with test_engine.begin() as conn:
            result = await conn.execute(text("SELECT 1 as test"))
            row = result.fetchone()
            assert row[0] == 1, "Basic query should return 1"
    
    @pytest.mark.asyncio
    async def test_session_factory(self, test_session_factory, async_session):
        """Test async session factory"""
        assert test_session_factory is not None, "Session factory should be created"
        assert async_session is not None, "Session should be created from factory"
        
        # Test basic session operation
        result = await async_session.execute(text("SELECT 'session_test' as test"))
        row = result.fetchone()
        assert row[0] == "session_test", "Session should execute queries"
    
    @pytest.mark.asyncio
    async def test_multiple_sessions(self, test_session_factory):
        """Test creating multiple concurrent sessions"""
        sessions = []
        
        async def create_session_task(session_id: int) -> bool:
            async with test_session_factory() as session:
                result = await session.execute(text("SELECT :id as session_id"), {"id": session_id})
                row = result.fetchone()
                return row[0] == session_id
        
        # Create multiple concurrent sessions
        tasks = [create_session_task(i) for i in range(5)]
        results = await asyncio.gather(*tasks)
        
        assert all(results), "All sessions should work correctly"


class TestModelOperations:
    """Test ORM model operations"""
    
    @pytest.mark.asyncio
    async def test_global_translation_crud(self, async_session, test_tables_setup):
        """Test CRUD operations on GlobalTranslation model"""
        # Create
        translation = GlobalTranslation(
            translation_text="test_key",
            bn_text="বাংলা পাঠ",
            ar_text="النص العربي",
            context="test_context",
            table_name="test_table"
        )
        
        async_session.add(translation)
        await async_session.commit()
        
        # Read
        stmt = select(GlobalTranslation).where(GlobalTranslation.translation_text == "test_key")
        result = await async_session.execute(stmt)
        retrieved = result.scalar_one()
        
        assert retrieved.translation_text == "test_key"
        assert retrieved.bn_text == "বাংলা পাঠ"
        assert retrieved.ar_text == "النص العربي"
        assert retrieved.context == "test_context"
        
        # Update
        retrieved.context = "updated_context"
        await async_session.commit()
        
        # Verify update
        await async_session.refresh(retrieved)
        assert retrieved.context == "updated_context"
        
        # Delete
        await async_session.delete(retrieved)
        await async_session.commit()
        
        # Verify deletion
        stmt = select(GlobalTranslation).where(GlobalTranslation.translation_text == "test_key")
        result = await async_session.execute(stmt)
        assert result.scalar_one_or_none() is None
    
    @pytest.mark.asyncio
    async def test_user_creation_with_relationships(self, async_session, test_tables_setup):
        """Test User model creation with related models"""
        # Create user
        user = User(
            fullname="John Doe",
            phone="01234567890",
            phone_hash="a" * 64,
            phone_encrypted="encrypted_phone",
            password_hash="hashed_password",
            email="john@example.com",
            email_hash="b" * 64,
            email_encrypted="encrypted_email",
            ip_address="192.168.1.1"
        )
        
        async_session.add(user)
        await async_session.flush()  # Get the user ID
        
        # Create account type
        account_type = AccountType(
            user_id=user.user_id,
            main_type=AccountTypeEnum.STUDENTS,
            student=True,
            teacher=False,
            staff=False,
            donor=False,
            badri_member=False,
            special_member=False
        )
        
        async_session.add(account_type)
        await async_session.commit()
        
        # Verify relationships
        stmt = select(User).where(User.user_id == user.user_id)
        result = await async_session.execute(stmt)
        retrieved_user = result.scalar_one()
        
        assert retrieved_user.fullname == "John Doe"
        assert retrieved_user.account_type is not None
        assert retrieved_user.account_type.main_type == AccountTypeEnum.STUDENTS
        assert retrieved_user.account_type.student is True
    
    @pytest.mark.asyncio
    async def test_transaction_operations(self, async_session, test_tables_setup):
        """Test Transaction model operations"""
        # First create a user
        user = User(
            fullname="Transaction User",
            phone="01987654321",
            phone_hash="c" * 64,
            phone_encrypted="encrypted_phone_trans",
            password_hash="hashed_password_trans",
            ip_address="192.168.1.2"
        )
        
        async_session.add(user)
        await async_session.flush()
        
        # Create transaction
        transaction = Transaction(
            user_id=user.user_id,
            type=TransactionType.FEES,
            month="January 2024",
            amount=Decimal("150.00"),
            date=datetime.now()
        )
        
        async_session.add(transaction)
        await async_session.commit()
        
        # Verify transaction
        stmt = select(Transaction).where(Transaction.user_id == user.user_id)
        result = await async_session.execute(stmt)
        retrieved_transaction = result.scalar_one()
        
        assert retrieved_transaction.type == TransactionType.FEES
        assert retrieved_transaction.amount == Decimal("150.00")
        assert retrieved_transaction.month == "January 2024"
        assert retrieved_transaction.user.fullname == "Transaction User"
    
    @pytest.mark.asyncio
    async def test_annur_models(self, async_session, test_tables_setup):
        """Test Annur schema models (Translation, People, etc.)"""
        # Create translation first
        translation = Translation(
            translation_text="student_name",
            bn_text="ছাত্র নাম",
            ar_text="اسم الطالب",
            context="people_names",
            table_name="peoples"
        )
        
        async_session.add(translation)
        await async_session.flush()
        
        # Create user for people relationship
        user = User(
            fullname="Annur Student",
            phone="01555666777",
            phone_hash="d" * 64,
            phone_encrypted="encrypted_phone_annur",
            password_hash="hashed_password_annur",
            ip_address="192.168.1.3"
        )
        
        async_session.add(user)
        await async_session.flush()
        
        # Create people record
        people = People(
            user_id=user.user_id,
            serial=1001,
            student_id=2024001,
            name="student_name",  # References translation
            date_of_birth=date(2000, 1, 15),
            birth_certificate_encrypted="encrypted_birth_cert",
            national_id_encrypted="encrypted_nid",
            blood_group="A+",
            gender=Gender.MALE,
            present_address_hash="e" * 64,
            address_hash="f" * 64,
            permanent_address_hash="g" * 64,
            phone="01555666777",
            available=True,
            acc_type=AccountTypeEnum.STUDENTS,
            status=VerificationStatus.VERIFIED
        )
        
        async_session.add(people)
        await async_session.commit()
        
        # Verify relationships
        stmt = select(People).where(People.student_id == 2024001)
        result = await async_session.execute(stmt)
        retrieved_people = result.scalar_one()
        
        assert retrieved_people.serial == 1001
        assert retrieved_people.gender == Gender.MALE
        assert retrieved_people.acc_type == AccountTypeEnum.STUDENTS
        assert retrieved_people.status == VerificationStatus.VERIFIED
        assert retrieved_people.user.fullname == "Annur Student"
    
    @pytest.mark.asyncio
    async def test_routine_and_exam_models(self, async_session, test_tables_setup):
        """Test Routine and Exam models"""
        # Create translations for subjects and books
        subject_translation = Translation(
            translation_text="mathematics",
            bn_text="গণিত",
            ar_text="الرياضيات",
            context="subjects",
            table_name="routines"
        )
        
        teacher_translation = Translation(
            translation_text="ustaz_ahmed",
            bn_text="উস্তাজ আহমেদ",
            ar_text="الأستاذ أحمد",
            context="teacher_names",
            table_name="routines"
        )
        
        book_translation = Translation(
            translation_text="algebra_book",
            bn_text="বীজগণিত বই",
            ar_text="كتاب الجبر",
            context="books",
            table_name="exams"
        )
        
        async_session.add_all([subject_translation, teacher_translation, book_translation])
        await async_session.flush()
        
        # Create routine
        routine = Routine(
            gender=Gender.MALE,
            class_group="science",
            class_level="grade_10",
            weekday=Weekday.MONDAY,
            subject="mathematics",
            name="ustaz_ahmed",
            serial=1
        )
        
        # Create exam
        exam = Exam(
            book="algebra_book",
            class_name="grade_10",
            gender=Gender.MALE,
            start_time=datetime(2024, 6, 15, 9, 0),
            end_time=datetime(2024, 6, 15, 11, 0),
            exam_date=date(2024, 6, 15),
            weekday=Weekday.SATURDAY
        )
        
        async_session.add_all([routine, exam])
        await async_session.commit()
        
        # Verify routine
        stmt = select(Routine).where(Routine.class_level == "grade_10")
        result = await async_session.execute(stmt)
        retrieved_routine = result.scalar_one()
        
        assert retrieved_routine.gender == Gender.MALE
        assert retrieved_routine.weekday == Weekday.MONDAY
        assert retrieved_routine.serial == 1
        
        # Verify exam
        stmt = select(Exam).where(Exam.class_name == "grade_10")
        result = await async_session.execute(stmt)
        retrieved_exam = result.scalar_one()
        
        assert retrieved_exam.gender == Gender.MALE
        assert retrieved_exam.weekday == Weekday.SATURDAY
        assert retrieved_exam.exam_date == date(2024, 6, 15)


class TestTransactionHandling:
    """Test SQLAlchemy transaction handling"""
    
    @pytest.mark.asyncio
    async def test_transaction_commit(self, async_session, test_tables_setup):
        """Test successful transaction commit"""
        translation = GlobalTranslation(
            translation_text="commit_test",
            bn_text="কমিট টেস্ট",
            context="test",
            table_name="test"
        )
        
        async_session.add(translation)
        await async_session.commit()
        
        # Verify data is committed
        stmt = select(GlobalTranslation).where(GlobalTranslation.translation_text == "commit_test")
        result = await async_session.execute(stmt)
        retrieved = result.scalar_one_or_none()
        
        assert retrieved is not None, "Data should be committed"
        assert retrieved.bn_text == "কমিট টেস্ট"
    
    @pytest.mark.asyncio
    async def test_transaction_rollback(self, async_session, test_tables_setup):
        """Test transaction rollback"""
        # Create initial data
        translation = GlobalTranslation(
            translation_text="rollback_test",
            bn_text="রোলব্যাক টেস্ট",
            context="test",
            table_name="test"
        )
        
        async_session.add(translation)
        await async_session.commit()
        
        # Start new transaction and modify
        stmt = select(GlobalTranslation).where(GlobalTranslation.translation_text == "rollback_test")
        result = await async_session.execute(stmt)
        retrieved = result.scalar_one()
        
        retrieved.bn_text = "পরিবর্তিত টেক্সট"
        
        # Rollback transaction
        await async_session.rollback()
        
        # Verify rollback - should still have original value
        await async_session.refresh(retrieved)
        assert retrieved.bn_text == "রোলব্যাক টেস্ট", "Should have original value after rollback"
    
    @pytest.mark.asyncio
    async def test_nested_transaction(self, test_session_factory, test_tables_setup):
        """Test nested transaction with savepoints"""
        async with test_session_factory() as session:
            # Outer transaction
            translation1 = GlobalTranslation(
                translation_text="outer_transaction",
                bn_text="বাইরের লেনদেন",
                context="test",
                table_name="test"
            )
            
            session.add(translation1)
            
            # Nested transaction (savepoint)
            async with session.begin_nested():
                translation2 = GlobalTranslation(
                    translation_text="inner_transaction",
                    bn_text="ভিতরের লেনদেন",
                    context="test",
                    table_name="test"
                )
                
                session.add(translation2)
                # This will rollback only the nested transaction
                await session.rollback()
            
            await session.commit()
            
            # Verify only outer transaction was committed
            stmt = select(GlobalTranslation).where(GlobalTranslation.translation_text == "outer_transaction")
            result = await session.execute(stmt)
            outer = result.scalar_one_or_none()
            
            stmt = select(GlobalTranslation).where(GlobalTranslation.translation_text == "inner_transaction")
            result = await session.execute(stmt)
            inner = result.scalar_one_or_none()
            
            assert outer is not None, "Outer transaction should be committed"
            assert inner is None, "Inner transaction should be rolled back"


class TestErrorHandling:
    """Test error scenarios and edge cases"""
    
    @pytest.mark.asyncio
    async def test_integrity_constraint_violation(self, async_session, test_tables_setup):
        """Test handling of integrity constraint violations"""
        # Create user with unique phone
        user1 = User(
            fullname="User One",
            phone="01111111111",
            phone_hash="unique1" + "a" * 57,
            phone_encrypted="encrypted_phone_1",
            password_hash="hashed_password_1",
            ip_address="192.168.1.10"
        )
        
        async_session.add(user1)
        await async_session.commit()
        
        # Try to create another user with same phone (should violate unique constraint)
        user2 = User(
            fullname="User Two",
            phone="01111111111",  # Same phone
            phone_hash="unique1" + "a" * 57,  # Same hash
            phone_encrypted="encrypted_phone_2",
            password_hash="hashed_password_2",
            ip_address="192.168.1.11"
        )
        
        async_session.add(user2)
        
        with pytest.raises(IntegrityError):
            await async_session.commit()
    
    @pytest.mark.asyncio
    async def test_foreign_key_constraint_violation(self, async_session, test_tables_setup):
        """Test foreign key constraint violations"""
        # Try to create transaction with non-existent user_id
        transaction = Transaction(
            user_id=99999,  # Non-existent user
            type=TransactionType.FEES,
            amount=Decimal("100.00"),
            date=datetime.now()
        )
        
        async_session.add(transaction)
        
        with pytest.raises(IntegrityError):
            await async_session.commit()
    
    @pytest.mark.asyncio
    async def test_invalid_enum_value(self, async_session, test_tables_setup):
        """Test handling of invalid enum values"""
        # This would typically be caught by Pydantic validation,
        # but let's test the database constraint
        with pytest.raises((ValueError, IntegrityError)):
            user = User(
                fullname="Enum Test User",
                phone="01222222222",
                phone_hash="enum_test" + "a" * 55,
                phone_encrypted="encrypted_phone_enum",
                password_hash="hashed_password_enum",
                ip_address="192.168.1.20"
            )
            
            async_session.add(user)
            await async_session.flush()
            
            # Create account type with invalid enum (this would be caught by SQLAlchemy)
            account_type = AccountType(
                user_id=user.user_id,
                main_type="invalid_type",  # Invalid enum value
                student=False,
                teacher=False,
                staff=False,
                donor=False,
                badri_member=False,
                special_member=False
            )
            
            async_session.add(account_type)
            await async_session.commit()


class TestPerformance:
    """Test performance scenarios"""
    
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_bulk_insert_performance(self, async_session, test_tables_setup):
        """Test bulk insert operations performance"""
        start_time = time.time()
        
        # Create bulk translations
        translations = []
        for i in range(TestConfig.MAX_TEST_RECORDS):
            translation = GlobalTranslation(
                translation_text=f"bulk_test_{i}",
                bn_text=f"বাল্ক টেস্ট {i}",
                ar_text=f"اختبار مجمع {i}",
                context="bulk_test",
                table_name="test"
            )
            translations.append(translation)
        
        async_session.add_all(translations)
        await async_session.commit()
        
        duration = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        # Performance assertion
        assert duration < TestConfig.PERFORMANCE_THRESHOLD_MS, f"Bulk insert took {duration:.2f}ms, should be under {TestConfig.PERFORMANCE_THRESHOLD_MS}ms"
        
        # Verify all records inserted
        stmt = select(func.count(GlobalTranslation.translation_text)).where(GlobalTranslation.context == "bulk_test")
        result = await async_session.execute(stmt)
        count = result.scalar()
        
        assert count == TestConfig.MAX_TEST_RECORDS, f"Should have inserted {TestConfig.MAX_TEST_RECORDS} records"
    
    @pytest.mark.asyncio
    async def test_complex_query_performance(self, async_session, test_tables_setup):
        """Test performance of complex queries with joins"""
        # Create test data
        user = User(
            fullname="Query Test User",
            phone="01333333333",
            phone_hash="query_test" + "a" * 55,
            phone_encrypted="encrypted_phone_query",
            password_hash="hashed_password_query",
            ip_address="192.168.1.30"
        )
        
        async_session.add(user)
        await async_session.flush()
        
        # Create multiple transactions
        transactions = []
        for i in range(50):
            transaction = Transaction(
                user_id=user.user_id,
                type=TransactionType.FEES if i % 2 == 0 else TransactionType.DONATIONS,
                amount=Decimal(f"{100 + i}.00"),
                date=datetime.now(),
                month=f"Month {i % 12 + 1}"
            )
            transactions.append(transaction)
        
        async_session.add_all(transactions)
        await async_session.commit()
        
        start_time = time.time()
        
        # Complex query with aggregations and joins
        stmt = (
            select(
                User.fullname,
                func.count(Transaction.transaction_id).label('transaction_count'),
                func.sum(Transaction.amount).label('total_amount'),
                func.avg(Transaction.amount).label('avg_amount')
            )
            .join(Transaction, User.user_id == Transaction.user_id)
            .where(User.user_id == user.user_id)
            .group_by(User.user_id, User.fullname)
        )
        
        result = await async_session.execute(stmt)
        row = result.fetchone()
        
        duration = (time.time() - start_time) * 1000
        
        # Verify query results
        assert row.fullname == "Query Test User"
        assert row.transaction_count == 50
        assert row.total_amount > Decimal("5000.00")
        
        # Performance check (should be very fast for this small dataset)
        assert duration < 1000, f"Complex query took {duration:.2f}ms, should be under 1000ms"


class TestSchemaValidation:
    """Test database schema and model validation"""
    
    @pytest.mark.asyncio
    async def test_model_table_creation(self, test_engine, test_schemas_setup):
        """Test that all model tables are created correctly"""
        async with test_engine.begin() as conn:
            # Check if tables exist in correct schemas
            global_tables = await conn.execute(text("SHOW TABLES FROM `global`"))
            global_table_names = {row[0] for row in global_tables.fetchall()}
            
            expected_global_tables = {
                'global_translations', 'users', 'transactions', 'verifications',
                'books', 'interactions', 'blocklist', 'acc_types'
            }
            
            for table in expected_global_tables:
                assert table in global_table_names, f"Table {table} should exist in global schema"
            
            # Check annur schema tables
            annur_tables = await conn.execute(text("SHOW TABLES FROM `annur`"))
            annur_table_names = {row[0] for row in annur_tables.fetchall()}
            
            expected_annur_tables = {
                'translations', 'peoples', 'payments', 'routines', 'exams', 'events'
            }
            
            for table in expected_annur_tables:
                assert table in annur_table_names, f"Table {table} should exist in annur schema"
    
    @pytest.mark.asyncio
    async def test_model_constraints(self, async_session, test_tables_setup):
        """Test model constraints and validations"""
        # Test check constraints
        user = User(
            fullname="Constraint Test",
            phone="01444444444",
            phone_hash="constraint" + "a" * 54,
            phone_encrypted="encrypted_phone_constraint",
            password_hash="hashed_password_constraint",
            ip_address="192.168.1.40"
        )
        
        async_session.add(user)
        await async_session.flush()
        
        # Test negative amount constraint (should fail)
        with pytest.raises(IntegrityError):
            transaction = Transaction(
                user_id=user.user_id,
                type=TransactionType.FEES,
                amount=Decimal("-100.00"),  # Negative amount should fail
                date=datetime.now()
            )
            
            async_session.add(transaction)
            await async_session.commit()
    
    @pytest.mark.asyncio
    async def test_model_relationships_loading(self, async_session, test_tables_setup):
        """Test that model relationships load correctly"""
        # Create user with related data
        user = User(
            fullname="Relationship Test",
            phone="01555555555",
            phone_hash="relation" + "a" * 55,
            phone_encrypted="encrypted_phone_relation",
            password_hash="hashed_password_relation",
            ip_address="192.168.1.50"
        )
        
        async_session.add(user)
        await async_session.flush()
        
        # Create account type
        account_type = AccountType(
            user_id=user.user_id,
            main_type=AccountTypeEnum.TEACHERS,
            teacher=True,
            student=False,
            staff=False,
            donor=False,
            badri_member=False,
            special_member=False
        )
        
        # Create transactions
        transaction1 = Transaction(
            user_id=user.user_id,
            type=TransactionType.FEES,
            amount=Decimal("200.00"),
            date=datetime.now()
        )
        
        transaction2 = Transaction(
            user_id=user.user_id,
            type=TransactionType.DONATIONS,
            amount=Decimal("50.00"),
            date=datetime.now()
        )
        
        async_session.add_all([account_type, transaction1, transaction2])
        await async_session.commit()
        
        # Test relationship loading
        stmt = select(User).where(User.user_id == user.user_id)
        result = await async_session.execute(stmt)
        loaded_user = result.scalar_one()
        
        # Load relationships
        await async_session.refresh(loaded_user, ['account_type', 'transactions'])
        
        assert loaded_user.account_type is not None
        assert loaded_user.account_type.teacher is True
        assert len(loaded_user.transactions) == 2
        assert sum(t.amount for t in loaded_user.transactions) == Decimal("250.00")


# Parametrized tests
@pytest.mark.parametrize("transaction_type,expected_category", [
    (TransactionType.FEES, "educational"),
    (TransactionType.DONATIONS, "charitable"),
    (TransactionType.OTHERS, "miscellaneous"),
])
@pytest.mark.asyncio
async def test_transaction_categorization(async_session, test_tables_setup, transaction_type, expected_category):
    """Parametrized test for transaction categorization"""
    # Create user
    user = User(
        fullname="Param Test User",
        phone=f"015{hash(transaction_type.value) % 10000000:07d}",
        phone_hash=f"param{transaction_type.value}" + "a" * (64 - len(f"param{transaction_type.value}")),
        phone_encrypted=f"encrypted_phone_param_{transaction_type.value}",
        password_hash=f"hashed_password_param_{transaction_type.value}",
        ip_address="192.168.1.60"
    )
    
    async_session.add(user)
    await async_session.flush()
    
    # Create transaction
    transaction = Transaction(
        user_id=user.user_id,
        type=transaction_type,
        amount=Decimal("100.00"),
        date=datetime.now()
    )
    
    async_session.add(transaction)
    await async_session.commit()
    
    # Test categorization logic
    stmt = select(
        Transaction.type,
        text("""
            CASE 
                WHEN type = 'fees' THEN 'educational'
                WHEN type = 'donations' THEN 'charitable'
                ELSE 'miscellaneous'
            END as category
        """)
    ).where(Transaction.user_id == user.user_id)
    
    result = await async_session.execute(stmt)
    row = result.fetchone()
    
    assert row.category == expected_category, f"Transaction type {transaction_type.value} should be categorized as {expected_category}"


if __name__ == "__main__":
    # This file is designed to be run with pytest only
    print("This test file is designed to be run with pytest.")
    print("Run: pytest test/mysql/test_sqlalchemy.py -v")
    print("For slow tests: pytest test/mysql/test_sqlalchemy.py -v -m slow")
