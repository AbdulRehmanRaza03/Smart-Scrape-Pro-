#!/usr/bin/env python3
"""Create a test regular user"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from backend.models.database import engine, AsyncSessionLocal
from backend.models.models import Base, User, UserRole, Subscription, SubscriptionPlan, SubscriptionStatus
from backend.auth.security import hash_password
from sqlalchemy import select


async def create_test_user():
    """Create a test regular user"""
    
    async with AsyncSessionLocal() as session:
        # Check if user exists
        result = await session.execute(
            select(User).where(User.email == "test@smartscrapepro.com")
        )
        user = result.scalar_one_or_none()
        
        if user:
            print("✅ Test user already exists")
            print(f"   📧 Email: test@smartscrapepro.com")
            print(f"   🔑 Password: TestPass123!")
            return
        
        # Create test user
        print("👤 Creating test user...")
        user = User(
            email="test@smartscrapepro.com",
            username="testuser",
            hashed_password=hash_password("TestPass123!"),
            full_name="Test User",
            role=UserRole.STANDARD,
            is_active=True,
            is_verified=True,
            is_banned=False,
        )
        session.add(user)
        await session.flush()
        
        # Create free subscription
        subscription = Subscription(
            user_id=user.id,
            plan=SubscriptionPlan.FREE,
            status=SubscriptionStatus.ACTIVE,
            jobs_used_this_month=0,
            jobs_limit=3,
        )
        session.add(subscription)
        await session.commit()
        
        print("✅ Test user created successfully!")
        print(f"   📧 Email: test@smartscrapepro.com")
        print(f"   🔑 Password: TestPass123!")
        print(f"   📋 Plan: FREE (3 jobs/month)")


if __name__ == "__main__":
    print("🚀 Creating test user...")
    asyncio.run(create_test_user())
    print("✨ Done!")
