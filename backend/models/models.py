"""
SmartScrape Pro — Database Models (SQLAlchemy 2.0)
Complete multi-tenant schema with full SaaS support
"""
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime,
    ForeignKey, Text, Enum, JSON, BigInteger, Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid
from datetime import datetime


Base = declarative_base()


def generate_uuid():
    return str(uuid.uuid4())


# ──────────────────────────────────────────
# ENUMS
# ──────────────────────────────────────────

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    STANDARD = "standard"
    PREMIUM = "premium"


class SubscriptionPlan(str, enum.Enum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    BUSINESS = "business"


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    CANCELLED = "cancelled"
    PAST_DUE = "past_due"
    TRIALING = "trialing"


class PaymentMethod(str, enum.Enum):
    STRIPE = "stripe"
    EASYPAISA = "easypaisa"
    JAZZCASH = "jazzcash"
    BANK_TRANSFER = "bank_transfer"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    UNDER_REVIEW = "under_review"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SCHEDULED = "scheduled"


class ScrapingEngine(str, enum.Enum):
    PLAYWRIGHT = "playwright"
    SELENIUM = "selenium"
    BEAUTIFULSOUP = "beautifulsoup"
    AUTO = "auto"


class ExportFormat(str, enum.Enum):
    CSV = "csv"
    JSON = "json"
    XLSX = "xlsx"
    XML = "xml"


# ──────────────────────────────────────────
# USER MODEL
# ──────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)

    # Role & status
    role = Column(Enum(UserRole), default=UserRole.STANDARD, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    is_banned = Column(Boolean, default=False, nullable=False)

    # Profile
    avatar_url = Column(String(500), nullable=True)
    phone = Column(String(20), nullable=True)
    company = Column(String(255), nullable=True)
    country = Column(String(100), nullable=True)
    timezone = Column(String(50), default="UTC")

    # API access
    api_key = Column(String(64), unique=True, nullable=True, index=True)
    api_key_created_at = Column(DateTime, nullable=True)

    # Stripe
    stripe_customer_id = Column(String(100), unique=True, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    last_login_at = Column(DateTime, nullable=True)

    # Relationships
    subscription = relationship("Subscription", back_populates="user", uselist=False)
    scraping_jobs = relationship("ScrapingJob", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")
    api_logs = relationship("APILog", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.email} [{self.role}]>"


# ──────────────────────────────────────────
# SUBSCRIPTION MODEL
# ──────────────────────────────────────────

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, unique=True)

    # Plan details
    plan = Column(Enum(SubscriptionPlan), default=SubscriptionPlan.FREE, nullable=False)
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE)

    # Stripe
    stripe_subscription_id = Column(String(100), unique=True, nullable=True)
    stripe_price_id = Column(String(100), nullable=True)

    # Billing
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, default=False)
    cancelled_at = Column(DateTime, nullable=True)
    trial_end = Column(DateTime, nullable=True)

    # Usage counters (reset monthly)
    jobs_used_this_month = Column(Integer, default=0)
    jobs_limit = Column(Integer, default=3)
    last_usage_reset = Column(DateTime, default=func.now())

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="subscription")

    def __repr__(self):
        return f"<Subscription {self.plan} [{self.status}] for user {self.user_id}>"


# ──────────────────────────────────────────
# PAYMENT MODEL
# ──────────────────────────────────────────

class Payment(Base):
    __tablename__ = "payments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)

    # Payment details
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="USD")
    method = Column(Enum(PaymentMethod), nullable=False)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING)

    # Plan
    plan = Column(Enum(SubscriptionPlan), nullable=False)
    billing_period_months = Column(Integer, default=1)

    # Stripe specific
    stripe_payment_intent_id = Column(String(100), nullable=True)
    stripe_invoice_id = Column(String(100), nullable=True)

    # Manual payment specific (Easypaisa, JazzCash, Bank)
    transaction_reference = Column(String(255), nullable=True)
    payment_proof_url = Column(String(500), nullable=True)  # uploaded screenshot
    sender_account = Column(String(100), nullable=True)
    admin_notes = Column(Text, nullable=True)
    reviewed_by = Column(String(36), nullable=True)  # admin user_id
    reviewed_at = Column(DateTime, nullable=True)

    # Metadata
    payment_metadata = Column(JSON, default={})
    failure_reason = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="payments")

    __table_args__ = (
        Index("idx_payments_user_status", "user_id", "status"),
        Index("idx_payments_method", "method"),
    )


# ──────────────────────────────────────────
# MANUAL PAYMENT CONFIG (PaymentMethods)
# ──────────────────────────────────────────
class PaymentMethodConfig(Base):
    __tablename__ = "payment_methods"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False) # e.g., JazzCash, EasyPaisa, Bank Transfer
    provider = Column(String(50), nullable=False) 
    account_title = Column(String(255), nullable=False)
    account_number = Column(String(100), nullable=False)
    instructions = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


# ──────────────────────────────────────────
# PAYMENT REQUESTS
# ──────────────────────────────────────────
class PaymentRequest(Base):
    __tablename__ = "payment_requests"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    method_id = Column(String(36), ForeignKey("payment_methods.id"), nullable=False)
    
    requested_plan = Column(String(50), nullable=False)
    amount = Column(Float, nullable=False)
    
    transaction_id = Column(String(255), nullable=False)
    proof_image_path = Column(String(500), nullable=False)
    sender_details = Column(String(255), nullable=True)
    
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    rejection_reason = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(String(36), ForeignKey("users.id"), nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    method = relationship("PaymentMethodConfig")


# ──────────────────────────────────────────
# PAYMENT LOGS
# ──────────────────────────────────────────
class PaymentLog(Base):
    __tablename__ = "payment_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    request_id = Column(String(36), ForeignKey("payment_requests.id"), nullable=False)
    admin_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    
    action = Column(String(50), nullable=False) # e.g., "created", "approved", "rejected"
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=func.now())

    request = relationship("PaymentRequest")
    admin = relationship("User", foreign_keys=[admin_id])


# ──────────────────────────────────────────
# SCRAPING JOB MODEL
# ──────────────────────────────────────────

class ScrapingJob(Base):
    __tablename__ = "scraping_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)

    # Job config
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    target_url = Column(Text, nullable=False)
    engine = Column(Enum(ScrapingEngine), default=ScrapingEngine.AUTO)

    # Scraping configuration (JSON)
    selectors = Column(JSON, default={})
    # Example: {"title": "h1", "price": ".price", "description": "#desc"}
    headers = Column(JSON, default={})
    cookies = Column(JSON, default={})
    proxy_config = Column(JSON, default={})
    pagination_config = Column(JSON, default={})
    # {"type": "url", "pattern": "?page={}", "max_pages": 10}

    # Job status
    status = Column(Enum(JobStatus), default=JobStatus.PENDING)
    priority = Column(Integer, default=5)  # 1-10

    # Scheduling
    is_scheduled = Column(Boolean, default=False)
    cron_expression = Column(String(100), nullable=True)  # "0 9 * * 1" = every Monday 9am
    next_run_at = Column(DateTime, nullable=True)
    last_run_at = Column(DateTime, nullable=True)

    # Celery
    celery_task_id = Column(String(100), nullable=True)

    # Results
    records_scraped = Column(Integer, default=0)
    pages_scraped = Column(Integer, default=0)
    duration_seconds = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    result_file_path = Column(String(500), nullable=True)
    export_format = Column(Enum(ExportFormat), default=ExportFormat.JSON)

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="scraping_jobs")
    logs = relationship("JobLog", back_populates="job", cascade="all, delete-orphan")
    results = relationship("ScrapingResult", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_jobs_user_status", "user_id", "status"),
        Index("idx_jobs_scheduled", "is_scheduled", "next_run_at"),
    )


# ──────────────────────────────────────────
# JOB LOG MODEL
# ──────────────────────────────────────────

class JobLog(Base):
    __tablename__ = "job_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    job_id = Column(String(36), ForeignKey("scraping_jobs.id"), nullable=False)

    level = Column(String(20), default="INFO")  # INFO, WARNING, ERROR, DEBUG
    message = Column(Text, nullable=False)
    details = Column(JSON, default={})

    created_at = Column(DateTime, default=func.now())

    # Relationships
    job = relationship("ScrapingJob", back_populates="logs")

    __table_args__ = (
        Index("idx_joblogs_job_id", "job_id"),
    )


# ──────────────────────────────────────────
# SCRAPING RESULT MODEL
# ──────────────────────────────────────────

class ScrapingResult(Base):
    __tablename__ = "scraping_results"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    job_id = Column(String(36), ForeignKey("scraping_jobs.id"), nullable=False)

    # The actual scraped data (JSON)
    data = Column(JSON, nullable=False, default={})
    source_url = Column(Text, nullable=True)
    page_number = Column(Integer, default=1)

    created_at = Column(DateTime, default=func.now())

    # Relationships
    job = relationship("ScrapingJob", back_populates="results")

    __table_args__ = (
        Index("idx_results_job_id", "job_id"),
    )


# ──────────────────────────────────────────
# API LOG MODEL
# ──────────────────────────────────────────

class APILog(Base):
    __tablename__ = "api_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    method = Column(String(10), nullable=False)
    endpoint = Column(String(255), nullable=False)
    status_code = Column(Integer, nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    response_time_ms = Column(Float, nullable=True)
    request_body_size = Column(Integer, default=0)

    created_at = Column(DateTime, default=func.now())

    # Relationships
    user = relationship("User", back_populates="api_logs")

    __table_args__ = (
        Index("idx_apilogs_user_id", "user_id"),
        Index("idx_apilogs_created_at", "created_at"),
    )


# ──────────────────────────────────────────
# NOTIFICATION MODEL
# ──────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)

    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(50), default="info")  # info, success, warning, error
    is_read = Column(Boolean, default=False)
    action_url = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=func.now())

    # Relationships
    user = relationship("User", back_populates="notifications")

    __table_args__ = (
        Index("idx_notif_user_unread", "user_id", "is_read"),
    )


# ──────────────────────────────────────────
# SYSTEM CONFIG MODEL (admin settings)
# ──────────────────────────────────────────

class SystemConfig(Base):
    __tablename__ = "system_config"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    updated_by = Column(String(36), nullable=True)


# ──────────────────────────────────────────
# JOB TEMPLATE MODEL
# ──────────────────────────────────────────

class JobTemplate(Base):
    __tablename__ = "job_templates"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    target_url = Column(Text, nullable=False)
    engine = Column(Enum(ScrapingEngine), default=ScrapingEngine.AUTO)
    
    selectors = Column(JSON, default={})
    headers = Column(JSON, default={})
    cookies = Column(JSON, default={})
    proxy_config = Column(JSON, default={})
    pagination_config = Column(JSON, default={})
    
    export_format = Column(Enum(ExportFormat), default=ExportFormat.JSON)
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    user = relationship("User")


# ──────────────────────────────────────────
# SCHEDULE MODEL
# ──────────────────────────────────────────

class ScheduleInterval(str, enum.Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"

class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    template_id = Column(String(36), ForeignKey("job_templates.id"), nullable=False)

    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    
    interval = Column(Enum(ScheduleInterval), default=ScheduleInterval.DAILY)
    cron_expression = Column(String(100), nullable=True) # Used if interval is CUSTOM
    
    # Retry mechanism
    retry_enabled = Column(Boolean, default=False)
    max_retries = Column(Integer, default=3)
    retry_backoff_factor = Column(Float, default=2.0)
    
    next_run_at = Column(DateTime, nullable=True)
    last_run_at = Column(DateTime, nullable=True)
    
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    user = relationship("User")
    template = relationship("JobTemplate")
    runs = relationship("ScheduleRun", back_populates="schedule", cascade="all, delete-orphan")


# ──────────────────────────────────────────
# SCHEDULE RUN (HISTORY) MODEL
# ──────────────────────────────────────────

class ScheduleRun(Base):
    __tablename__ = "schedule_runs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    schedule_id = Column(String(36), ForeignKey("schedules.id"), nullable=False)
    job_id = Column(String(36), ForeignKey("scraping_jobs.id"), nullable=True) # Linked to the actual ScrapingJob execution

    status = Column(String(50), default="running") # running, completed, failed, retrying
    error_message = Column(Text, nullable=True)
    
    duration_seconds = Column(Float, nullable=True)
    records_extracted = Column(Integer, default=0)

    started_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime, nullable=True)

    schedule = relationship("Schedule", back_populates="runs")
    job = relationship("ScrapingJob")
