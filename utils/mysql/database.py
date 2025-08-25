# """SQLAlchemy Database Utilities for Madrasha Application"""

# import asyncio
# from typing import Optional, Any, Dict, List

# from sqlalchemy.ext.asyncio import (
#     create_async_engine, AsyncSession, AsyncEngine, 
#     async_sessionmaker
# )

# from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

# from utils.mysql.models import (
#     GlobalTranslation, User, Transaction, Verification, Book, 
#     Interaction, Blocklist, AccountType,
#     Translation, People, Payment, Routine, Exam, Event,
#     Log, PasswordResetLog
# )

# # =============================================================================
# # CONFIGURATION
# # =============================================================================

# def get_sqlalchemy_config() -> Dict[str, Any]:
#     """Get SQLAlchemy engine configuration"""
#     from config import config
    
#     return {
#         "echo": False,  # Don't echo SQL queries
#         "pool_size": int(config.MYSQL_MIN_CONNECTIONS or 5),
#         "max_overflow": (config.MYSQL_MAX_CONNECTIONS or 10) - (config.MYSQL_MIN_CONNECTIONS or 5),
#         "pool_recycle": 3600,  # Recycle connections after 1 hour
#         "pool_pre_ping": True,  # Verify connections before use
#         "connect_args": {
#             "connect_timeout": getattr(config, "MYSQL_TIMEOUT", 60),
#             "auth_plugin": "caching_sha2_password",
#         }
#     }


# # =============================================================================
# # GLOBAL ENGINE AND SESSION MANAGEMENT
# # =============================================================================

# _async_engine: Optional[AsyncEngine] = None
# _async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None
# _engine_lock = asyncio.Lock()


# async def get_async_engine() -> AsyncEngine:
#     """Get or create the async SQLAlchemy engine (thread-safe)"""
#     global _async_engine
    
#     if _async_engine is None:
#         async with _engine_lock:
#             if _async_engine is None:  # Double-check pattern
#                 _async_engine = await create_async_engine_instance()
    
#     return _async_engine


# async def create_async_engine_instance() -> AsyncEngine:
#     """Create a new async SQLAlchemy engine"""
#     from config import config
#     from utils.helpers.logger import log
#     try:
#         url = config.get_sqlalchemy_url()
#         engine_config = get_sqlalchemy_config()

#         # Make sure no sync-only poolclass sneaks in
#         engine_config.pop("poolclass", None)
        
#         engine = create_async_engine(url, **engine_config)

#         if config.OTEL_ENABLED:
#             # Instrument the underlying sync engine for OpenTelemetry
#             try:
#                 SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine, service="madrasha-db")
#             except Exception:
#                 # avoid crashing on repeated instrumentation or missing OTEL setup
#                 raise RuntimeError("OTEL SQLAlchemy instrumentation failed or already applied")
        
#         log.info(
#             action="sqlalchemy_engine_created", 
#             message="SQLAlchemy async engine created successfully", 
#         )
#         return engine
        
#     except Exception as e:
#         log.critical(
#             action="sqlalchemy_engine_creation_failed", 
#             message=f"Failed to create SQLAlchemy engine: {type(e).__name__}", 
#         )
#         raise RuntimeError(f"SQLAlchemy engine creation failed. Please check your database configuration.")


# async def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
#     """Get or create the async session factory"""
#     global _async_session_factory
    
#     if _async_session_factory is None:
#         engine = await get_async_engine()
#         _async_session_factory = async_sessionmaker(
#             engine,
#             class_=AsyncSession,
#             expire_on_commit=False,
#             autoflush=False,
#             autocommit=False
#         )
    
#     return _async_session_factory


# async def close_async_engine():
#     """Close the async SQLAlchemy engine"""
#     from utils.helpers.logger import log
#     global _async_engine, _async_session_factory
    
#     if _async_engine is not None:
#         await _async_engine.dispose()
#         _async_engine = None
#         _async_session_factory = None
#         log.info(
#             action="sqlalchemy_engine_closed", 
#             trace_info="system", 
#             message="SQLAlchemy async engine closed", 
#             secure=False
#         )


# # =============================================================================
# # ASYNC UTILITY FUNCTIONS
# # =============================================================================

# def get_all_models() -> List[type]:
#     """Get all model classes"""
#     return [
#         # Global models
#         GlobalTranslation, User, Transaction, Verification, Book, 
#         Interaction, Blocklist, AccountType,
#         # Annur models
#         Translation, People, Payment, Routine, Exam, Event,
#         # Logs models
#         Log, PasswordResetLog
#     ]


# def get_models_by_schema(schema: str) -> List[type]:
#     """Get models by database schema"""
#     schema_models = {
#         "global": [GlobalTranslation, User, Transaction, Verification, Book, Interaction, Blocklist, AccountType],
#         "annur": [Translation, People, Payment, Routine, Exam, Event],
#         "logs": [Log, PasswordResetLog]
#     }
#     return schema_models.get(schema, [])


# # =============================================================================
# # ASYNC DATABASE OPERATIONS
# # =============================================================================

# async def create_tables(async_engine: AsyncEngine, schema: str | None = None) -> None:
#     if schema:
#         models = get_models_by_schema(schema)
#     else:
#         models = get_all_models()
#     async with async_engine.begin() as conn:
#         for model in models:
#             await conn.run_sync(model.__table__.create)


# async def drop_tables(async_engine: AsyncEngine, schema: str | None = None) -> None:
#     if schema:
#         models = get_models_by_schema(schema)
#     else:
#         models = get_all_models()
#     async with async_engine.begin() as conn:
#         for model in reversed(models):
#             await conn.run_sync(model.__table__.drop)