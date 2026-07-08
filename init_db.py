#!/usr/bin/env python3
"""Initialize database with admin user"""
import asyncio
import sys
import os

# Add project to path
sys.path.insert(0, os.path.dirname(__file__))

from backend.models.database import engine, AsyncSessionLocal, init_db as init_db_tables
from backend.models.models import Base, User, UserRole, Subscription, SubscriptionPlan, SubscriptionStatus
from backend.auth.security import hash_password
from sqlalchemy import select


async def init_db():
    """Initialize database and create admin user"""
    
    # Create tables
    print("📦 Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database tables created")
    
    # Create session
    async with AsyncSessionLocal() as session:
        # Check if admin exists
        result = await session.execute(
            select(User).where(User.email == "admin@smartscrapepro.com")
        )
        admin = result.scalar_one_or_none()
        
        if admin:
            print("✅ Admin user already exists")
            return
        
        # Create admin
        print("👤 Creating admin user...")
        admin = User(
            email="admin@smartscrapepro.com",
            username="admin",
            hashed_password=hash_password("AdminPass123!"),
            full_name="Admin User",
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True,
            is_banned=False,
        )
        session.add(admin)
        await session.flush()
        
        # Create admin subscription
        subscription = Subscription(
            user_id=admin.id,
            plan=SubscriptionPlan.BUSINESS,
            status=SubscriptionStatus.ACTIVE,
            jobs_used_this_month=0,
            jobs_limit=999999,
        )
        session.add(subscription)
        await session.commit()
        
        print("✅ Admin user created successfully!")
        print(f"   📧 Email: admin@smartscrapepro.com")
        print(f"   🔑 Password: AdminPass123!")


if __name__ == "__main__":
    print("🚀 Initializing SmartScrape Pro database...")
    asyncio.run(init_db())
    print("✨ Database initialization complete!")
