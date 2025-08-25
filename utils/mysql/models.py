# """
# SQLAlchemy Models for Madrasha Application (Async)
# =================================================

# This module contains all SQLAlchemy model definitions for the Madrasha application
# with full async support using SQLAlchemy 2.0+ and async session management.

# Author: AI Assistant
# Date: 2024
# """

# from datetime import datetime, date
# from decimal import Decimal
# from typing import Optional, List, Dict, Any, TYPE_CHECKING
# from enum import Enum as PyEnum

# from sqlalchemy import (
#     Integer, String, Boolean, DateTime, Date, Text, 
#     ForeignKey, UniqueConstraint, Index, CheckConstraint, JSON,
#     Enum as SQLEnum, CHAR, DECIMAL, func, text
# )
# from sqlalchemy.orm import (
#     DeclarativeBase, Mapped, mapped_column, relationship,
#     declared_attr
# )
# from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncEngine, AsyncSession


# # =============================================================================
# # BASE CLASS
# # =============================================================================

# MADRASA_NAME = "annur"

# class Base(AsyncAttrs, DeclarativeBase):
#     """Base class for all models with async support"""
    
#     def __init_subclass__(cls, **kwargs):
#         super().__init_subclass__(**kwargs)
#         # if subclass already defines __tablename__, keep it
#         if "__tablename__" in cls.__dict__:
#             return
#         name = cls.__name__.lower()
#         cls.__tablename__ = name if name.endswith("s") else name + "s"


# # =============================================================================
# # ENUM DEFINITIONS
# # =============================================================================

# class TransactionType(PyEnum):
#     """Transaction types enumeration"""
#     FEES = "fees"
#     DONATIONS = "donations"
#     OTHERS = "others"


# class Gender(PyEnum):
#     """Gender enumeration"""
#     MALE = "male"
#     FEMALE = "female"
#     OTHERS = "others"


# class ThreatLevel(PyEnum):
#     """Threat level enumeration"""
#     LOW = "low"
#     MEDIUM = "medium"
#     HIGH = "high"
#     NONE = "none"


# class AccountTypeEnum(PyEnum):
#     """Account type enumeration"""
#     ADMINS = "admins"
#     STUDENTS = "students"
#     TEACHERS = "teachers"
#     STAFFS = "staffs"
#     OTHERS = "others"
#     BADRI_MEMBERS = "badri_members"
#     DONORS = "donors"


# class VerificationStatus(PyEnum):
#     """Verification status enumeration"""
#     VERIFIED = "verified"
#     PENDING = "pending"
#     REJECTED = "rejected"


# class Weekday(PyEnum):
#     """Weekday enumeration"""
#     SATURDAY = "saturday"
#     SUNDAY = "sunday"
#     MONDAY = "monday"
#     TUESDAY = "tuesday"
#     WEDNESDAY = "wednesday"
#     THURSDAY = "thursday"
#     FRIDAY = "friday"


# class EventType(PyEnum):
#     """Event type enumeration"""
#     EVENT = "event"
#     FUNCTION = "function"


# class LogLevel(PyEnum):
#     """Log level enumeration"""
#     INFO = "info"
#     WARNING = "warning"
#     ERROR = "error"
#     CRITICAL = "critical"


# # =============================================================================
# # BASE MODEL CLASS
# # =============================================================================

# class TimestampMixin:
#     """Mixin to add created_at and updated_at timestamps"""
#     created_at: Mapped[datetime] = mapped_column(
#         DateTime(timezone=True), 
#         server_default=func.current_timestamp(),
#         nullable=False
#     )
#     updated_at: Mapped[datetime] = mapped_column(
#         DateTime(timezone=True), 
#         server_default=func.current_timestamp(),
#         server_onupdate=func.current_timestamp(),
#         nullable=False
#     )


# # =============================================================================
# # GLOBAL DATABASE MODELS
# # =============================================================================

# class GlobalTranslation(Base, TimestampMixin):
#     """Global translations table"""
#     __tablename__ = "global_translations"
#     __table_args__ = {"schema": "global"}

#     translation_text: Mapped[str] = mapped_column(String(255), primary_key=True)
#     bn_text: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
#     ar_text: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
#     context: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
#     table_name: Mapped[str] = mapped_column(String(20), index=True, nullable=False)

#     # Relationships
#     books: Mapped[List["Book"]] = relationship("Book", back_populates="translation")


# class User(Base, TimestampMixin):
#     """Users table"""
#     __tablename__ = "users"
#     __table_args__ = (
#         UniqueConstraint("fullname", "phone", name="unique_user"),
#         Index("idx_users_phone_fullname", "phone", "fullname"),
#         {"schema": "global"}
#     )

#     user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
#     fullname: Mapped[str] = mapped_column(String(50), nullable=False)
#     phone: Mapped[str] = mapped_column(String(20), nullable=False)
#     phone_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
#     phone_encrypted: Mapped[str] = mapped_column(String(255), nullable=False)
#     password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
#     email: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
#     email_hash: Mapped[Optional[str]] = mapped_column(CHAR(64), nullable=True)
#     email_encrypted: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
#     ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
#     deactivated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
#     scheduled_deletion_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

#     # Relationships
#     transactions: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
#     interactions: Mapped[List["Interaction"]] = relationship("Interaction", back_populates="user", cascade="all, delete-orphan")
#     account_type: Mapped["AccountType"] = relationship("AccountType", back_populates="user", uselist=False, cascade="all, delete-orphan")
#     peoples: Mapped[List["People"]] = relationship("People", back_populates="user")
#     payments: Mapped[List["Payment"]] = relationship("Payment", back_populates="user")


# class Transaction(Base, TimestampMixin):
#     """Transactions table"""
#     __tablename__ = "transactions"
#     __table_args__ = (
#         Index("idx_transactions_updated_at", "updated_at"),
#         CheckConstraint("amount > 0.0", name="check_amount_positive"),
#         {"schema": "global"}
#     )

#     transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
#     user_id: Mapped[int] = mapped_column(Integer, ForeignKey("global.users.user_id", ondelete="CASCADE", onupdate="CASCADE"), index=True, nullable=False)
#     type: Mapped[str] = mapped_column(SQLEnum(TransactionType), index=True, nullable=False)
#     month: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
#     amount: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
#     date: Mapped[datetime] = mapped_column(DateTime, nullable=False)

#     # Relationships
#     user: Mapped["User"] = relationship("User", back_populates="transactions")


# class Verification(Base):
#     """Verifications table"""
#     __tablename__ = "verifications"
#     __table_args__ = (
#         CheckConstraint("code >= 1000 AND code <= 999999", name="check_code_range"),
#         {"schema": "global"}
#     )

#     verification_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
#     created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False)
#     phone: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
#     phone_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
#     phone_encrypted: Mapped[str] = mapped_column(String(255), nullable=False)
#     code: Mapped[int] = mapped_column(Integer, nullable=False)
#     ip_address: Mapped[Optional[str]] = mapped_column(String(45), index=True, nullable=True)


# class Book(Base, TimestampMixin):
#     """Books table"""
#     __tablename__ = "books"
#     __table_args__ = {"schema": "global"}

#     book_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
#     name: Mapped[str] = mapped_column(String(255), ForeignKey("global.global_translations.translation_text", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False)
#     class_name: Mapped[Optional[str]] = mapped_column("_class", String(50), index=True, nullable=True)

#     # Relationships
#     translation: Mapped["GlobalTranslation"] = relationship("GlobalTranslation", back_populates="books")


# class Interaction(Base, TimestampMixin):
#     """Interactions table"""
#     __tablename__ = "interactions"
#     __table_args__ = (
#         UniqueConstraint("user_id", "device_id", name="uniq_user_device"),
#         {"schema": "global"}
#     )

#     interaction_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
#     user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("global.users.user_id", ondelete="CASCADE", onupdate="CASCADE"), index=True, nullable=True)
#     device_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
#     device_brand: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
#     ip_address: Mapped[str] = mapped_column(String(45), index=True, nullable=False)
#     open_times: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
#     os_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
#     app_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

#     # Relationships
#     user: Mapped[Optional["User"]] = relationship("User", back_populates="interactions")


# class Blocklist(Base, TimestampMixin):
#     """Blocklist table"""
#     __tablename__ = "blocklist"
#     __table_args__ = {"schema": "global"}

#     block_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
#     trace_info: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
#     additional_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
#     threat_level: Mapped[str] = mapped_column(SQLEnum(ThreatLevel), nullable=False, index=True, server_default=text("'high'"))


# class AccountType(Base, TimestampMixin):
#     """Account types table"""
#     __tablename__ = "acc_types"
#     __table_args__ = {"schema": "global"}

#     user_id: Mapped[int] = mapped_column(Integer, ForeignKey("global.users.user_id", ondelete="CASCADE", onupdate="CASCADE"), primary_key=True)
#     main_type: Mapped[str] = mapped_column(SQLEnum(AccountTypeEnum), ForeignKey(f"{MADRASA_NAME}.peoples.acc_type", ondelete="CASCADE", onupdate="CASCADE"), nullable=False)
#     teacher: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True, server_default=text("0"))
#     student: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True, server_default=text("0"))
#     staff: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True, server_default=text("0"))
#     donor: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True, server_default=text("0"))
#     badri_member: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True, server_default=text("0"))
#     special_member: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True, server_default=text("0"))

#     # Relationships
#     user: Mapped["User"] = relationship("User", back_populates="account_type")
#     acc_type: Mapped["People"] = relationship("People", back_populates="account_types")

# # =============================================================================
# # MADRASA DATABASE MODELS
# # =============================================================================

# class Translation(Base, TimestampMixin):
#     """Translations table for Madrasa database"""
#     __tablename__ = "translations"
#     __table_args__ = {"schema": f"{MADRASA_NAME}"}

#     translation_text: Mapped[str] = mapped_column(String(255), primary_key=True)
#     bn_text: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
#     ar_text: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
#     context: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
#     table_name: Mapped[str] = mapped_column(String(20), index=True, nullable=False)

#     # Relationships
#     peoples_by_name: Mapped[List["People"]] = relationship("People", foreign_keys="People.name", back_populates="name_translation")
#     peoples_by_address: Mapped[List["People"]] = relationship("People", foreign_keys="People.address", back_populates="address_translation")
#     peoples_by_father: Mapped[List["People"]] = relationship("People", foreign_keys="People.father_name", back_populates="father_translation")
#     peoples_by_mother: Mapped[List["People"]] = relationship("People", foreign_keys="People.mother_name", back_populates="mother_translation")
#     routines_by_subject: Mapped[List["Routine"]] = relationship("Routine", foreign_keys="Routine.subject", back_populates="subject_translation")
#     routines_by_name: Mapped[List["Routine"]] = relationship("Routine", foreign_keys="Routine.name", back_populates="name_translation")
#     exams_by_book: Mapped[List["Exam"]] = relationship("Exam", foreign_keys="Exam.book", back_populates="book_translation")
#     events_by_title: Mapped[List["Event"]] = relationship("Event", foreign_keys="Event.title", back_populates="title_translation")


# class People(Base, TimestampMixin):
#     """Peoples table"""
#     __tablename__ = "peoples"
#     __table_args__ = (
#         UniqueConstraint("name", "phone", name="unique_people"),
#         Index("idx_peoples_name_phone", "name", "phone"),
#         CheckConstraint("serial >= 0", name="check_serial_positive"),
#         CheckConstraint("student_id >= 0", name="check_student_id_positive"),
#         {"schema": f"{MADRASA_NAME}"}
#     )

#     people_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
#     user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("global.users.user_id", ondelete="SET NULL", onupdate="CASCADE"), index=True, nullable=True)
#     serial: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
#     student_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
#     name: Mapped[str] = mapped_column(String(255), ForeignKey(f"{MADRASA_NAME}.translations.translation_text", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False)
#     date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
#     birth_certificate: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
#     birth_certificate_encrypted: Mapped[str] = mapped_column(String(255), nullable=False)
#     national_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
#     national_id_encrypted: Mapped[str] = mapped_column(String(255), nullable=False)
#     blood_group: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
#     gender: Mapped[str] = mapped_column(SQLEnum(Gender), index=True, nullable=False)
#     title1: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
#     title2: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
#     source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
#     present_address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
#     present_address_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
#     address: Mapped[Optional[str]] = mapped_column(String(255), ForeignKey(f"{MADRASA_NAME}.translations.translation_text", ondelete="SET NULL", onupdate="CASCADE"), nullable=True)
#     address_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
#     permanent_address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
#     permanent_address_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
#     father_or_spouse: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
#     father_name: Mapped[Optional[str]] = mapped_column(String(255), ForeignKey(f"{MADRASA_NAME}.translations.translation_text", ondelete="SET NULL", onupdate="CASCADE"), nullable=True)
#     mother_name: Mapped[Optional[str]] = mapped_column(String(255), ForeignKey(f"{MADRASA_NAME}.translations.translation_text", ondelete="SET NULL", onupdate="CASCADE"), nullable=True)
#     class_name: Mapped[Optional[str]] = mapped_column(String(100), index=True, nullable=True)
#     phone: Mapped[str] = mapped_column(String(20), nullable=False)
#     guardian_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
#     available: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("1"))
#     degree: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
#     image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
#     acc_type: Mapped[str] = mapped_column(SQLEnum(AccountTypeEnum), index=True, nullable=False)
#     status: Mapped[str] = mapped_column(SQLEnum(VerificationStatus), index=True, nullable=False, server_default=text("'pending'"))

#     # Relationships
#     user: Mapped[Optional["User"]] = relationship("User", back_populates="peoples")
#     account_types: Mapped[List["AccountType"]] = relationship("AccountType", back_populates="acc_type")
#     name_translation: Mapped["Translation"] = relationship("Translation", foreign_keys="People.name", back_populates="peoples_by_name")
#     address_translation: Mapped[Optional["Translation"]] = relationship("Translation", foreign_keys="People.address", back_populates="peoples_by_address")
#     father_translation: Mapped[Optional["Translation"]] = relationship("Translation", foreign_keys="People.father_name", back_populates="peoples_by_father")
#     mother_translation: Mapped[Optional["Translation"]] = relationship("Translation", foreign_keys="People.mother_name", back_populates="peoples_by_mother")


# class Payment(Base, TimestampMixin):
#     """Payments table"""
#     __tablename__ = "payments"
#     __table_args__ = (
#         CheckConstraint("reduced_fee >= 0.0", name="check_reduced_fee_positive"),
#         CheckConstraint("due_months >= 0", name="check_due_months_positive"),
#         CheckConstraint("tax >= 0.0", name="check_tax_positive"),
#         {"schema": f"{MADRASA_NAME}"}
#     )

#     payment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
#     user_id: Mapped[int] = mapped_column(Integer, ForeignKey("global.users.user_id", ondelete="CASCADE", onupdate="CASCADE"), index=True, nullable=False)
#     food: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("1"))
#     special_food: Mapped[bool] = mapped_column(Boolean, index=True, nullable=False, server_default=text("0"))
#     reduced_fee: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), index=True, nullable=False, server_default=text("0.0"))
#     due_months: Mapped[int] = mapped_column(Integer, index=True, nullable=False, server_default=text("0"))
#     tax: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False, server_default=text("0.0"))

#     # Relationships
#     user: Mapped[Optional["User"]] = relationship("User", back_populates="payments")


# class Routine(Base, TimestampMixin):
#     """Routines table"""
#     __tablename__ = "routines"
#     __table_args__ = (
#         UniqueConstraint("class_group", "class_level", "weekday", "serial", name="unique_routine"),
#         CheckConstraint("serial >= 0", name="check_serial_positive"),
#         {"schema": f"{MADRASA_NAME}"}
#     )

#     routine_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
#     gender: Mapped[str] = mapped_column(SQLEnum(Gender), nullable=False)
#     class_group: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
#     class_level: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
#     weekday: Mapped[str] = mapped_column(SQLEnum(Weekday), index=True, nullable=False)
#     subject: Mapped[str] = mapped_column(String(255), ForeignKey(f"{MADRASA_NAME}.translations.translation_text", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False)
#     name: Mapped[str] = mapped_column(String(255), ForeignKey(f"{MADRASA_NAME}.translations.translation_text", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False)
#     serial: Mapped[int] = mapped_column(Integer, nullable=False)

#     # Relationships
#     subject_translation: Mapped["Translation"] = relationship("Translation", foreign_keys="Routine.subject", back_populates="routines_by_subject")
#     name_translation: Mapped["Translation"] = relationship("Translation", foreign_keys="Routine.name", back_populates="routines_by_name")


# class Exam(Base, TimestampMixin):
#     """Exams table"""
#     __tablename__ = "exams"
#     __table_args__ = {"schema": f"{MADRASA_NAME}"}

#     exam_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
#     book: Mapped[Optional[str]] = mapped_column(String(255), ForeignKey(f"{MADRASA_NAME}.translations.translation_text", ondelete="SET NULL", onupdate="CASCADE"), nullable=True)
#     class_name: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
#     gender: Mapped[str] = mapped_column(SQLEnum(Gender), index=True, nullable=False)
#     start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
#     end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
#     sec_start_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
#     sec_end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
#     exam_date: Mapped[date] = mapped_column(Date, nullable=False)
#     weekday: Mapped[str] = mapped_column(SQLEnum(Weekday), index=True, nullable=False)

#     # Relationships
#     book_translation: Mapped[Optional["Translation"]] = relationship("Translation", foreign_keys="Exam.book", back_populates="exams_by_book")


# class Event(Base, TimestampMixin):
#     """Events table"""
#     __tablename__ = "events"
#     __table_args__ = {"schema": f"{MADRASA_NAME}"}

#     event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
#     type: Mapped[str] = mapped_column(SQLEnum(EventType), index=True, nullable=False)
#     title: Mapped[str] = mapped_column(String(255), ForeignKey(f"{MADRASA_NAME}.translations.translation_text", ondelete="RESTRICT", onupdate="CASCADE"), index=True, nullable=False)
#     time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
#     event_date: Mapped[date] = mapped_column(Date, nullable=False)
#     function_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

#     # Relationships
#     title_translation: Mapped["Translation"] = relationship("Translation", foreign_keys="Event.title", back_populates="events_by_title")


# # =============================================================================
# # LOGS DATABASE MODELS
# # =============================================================================

# class Log(Base):
#     """Logs table"""
#     __tablename__ = "logs"
#     __table_args__ = {"schema": "logs"}

#     log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
#     created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, server_default=func.current_timestamp(), nullable=False)
#     action: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
#     trace_info: Mapped[str] = mapped_column(String(255), index=True, nullable=False, server_default=text("'system'"))
#     trace_info_hash: Mapped[Optional[str]] = mapped_column(CHAR(64), nullable=True)
#     trace_info_encrypted: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
#     level: Mapped[str] = mapped_column(SQLEnum(LogLevel), nullable=False, server_default=text("'info'"))
#     message: Mapped[str] = mapped_column(Text, nullable=False)
#     meta_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)


# class PasswordResetLog(Base):
#     """Password reset logs table"""
#     __tablename__ = "password_reset_logs"
#     __table_args__ = {"schema": "logs"}

#     password_reset_log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
#     created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False)
#     user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
#     ip_address: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
#     reset_method: Mapped[str] = mapped_column(String(255), index=True, nullable=False)