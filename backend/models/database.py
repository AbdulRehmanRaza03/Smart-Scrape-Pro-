"""
SmartScrape Pro — Database Engine & Session Management
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from backend.utils.logger import logger
import os

from config.settings import settings
from backend.models.models import Base


# ──────────────────────────────────────────
# ENGINE SETUP
# ──────────────────────────────────────────

def get_engine():
    """Create SQLAlchemy async engine based on environment."""
    db_url = settings.DATABASE_URL

    if "sqlite" in db_url:
        # SQLite — dev mode (no connection pool needed)
        engine = create_async_engine(
            db_url,
            echo=settings.DEBUG,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        logger.info("📦 Using SQLite database (dev mode)")
    else:
        # PostgreSQL — production
        engine = create_async_engine(
            db_url,
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        logger.info("🐘 Using PostgreSQL database (production mode)")

    return engine


engine = get_engine()

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ──────────────────────────────────────────
# DEPENDENCY (FastAPI)
# ──────────────────────────────────────────

async def get_db() -> AsyncSession:
    """FastAPI dependency — yields DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ──────────────────────────────────────────
# INIT DATABASE
# ──────────────────────────────────────────

async def init_db():
    """Create all tables and seed default admin."""
    # Ensure DB directory exists
    os.makedirs("./database", exist_ok=True)
    os.makedirs("./exports/uploads", exist_ok=True)
    os.makedirs("./logs", exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database tables created/verified")

    # Seed admin user
    await seed_admin()


async def seed_admin():
    """Create default admin user if not exists."""
    from backend.models.models import User, Subscription, UserRole, SubscriptionPlan, SubscriptionStatus
    from backend.auth.security import hash_password
    from sqlalchemy import select
    import secrets

    async with AsyncSessionLocal() as db:
        # Check if admin exists
        result = await db.execute(
            select(User).where(User.email == settings.ADMIN_EMAIL)
        )
        existing = result.scalar_one_or_none()

        if existing:
            logger.info(f"Admin user already exists: {settings.ADMIN_EMAIL}")
            return

        # Create admin
        admin = User(
            email=settings.ADMIN_EMAIL,
            username="admin",
            hashed_password=hash_password(settings.ADMIN_PASSWORD),
            full_name="System Administrator",
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True,
            api_key=secrets.token_urlsafe(32),
        )
        db.add(admin)
        await db.flush()

        # Give admin a business subscription
        sub = Subscription(
            user_id=admin.id,
            plan=SubscriptionPlan.BUSINESS,
            status=SubscriptionStatus.ACTIVE,
            jobs_used_this_month=0,
            jobs_limit=999999,
        )
        db.add(sub)
        await db.commit()

        logger.success(f"🔐 Admin user created: {settings.ADMIN_EMAIL}")
