"""
SmartScrape Pro — Auth Dependencies
FastAPI dependency injection for authentication & authorization
"""
from fastapi import Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models.database import get_db
from backend.models.models import User, UserRole
from backend.auth.security import decode_token


# ──────────────────────────────────────────
# SECURITY SCHEMES
# ──────────────────────────────────────────

bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# ──────────────────────────────────────────
# GET CURRENT USER
# ──────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    api_key: str = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate the current user from JWT or API key."""

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user = None

    # ── Try JWT Bearer token
    if credentials:
        payload = decode_token(credentials.credentials)
        if payload and payload.get("type") == "access":
            user_id = payload.get("sub")
            if user_id:
                result = await db.execute(
                    select(User).where(User.id == user_id)
                )
                user = result.scalar_one_or_none()

    # ── Try API Key (for Business plan)
    if not user and api_key:
        result = await db.execute(
            select(User).where(User.api_key == api_key)
        )
        user = result.scalar_one_or_none()

    if not user:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated"
        )

    if user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is banned. Contact support."
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    return current_user


# ──────────────────────────────────────────
# ROLE-BASED ACCESS CONTROL
# ──────────────────────────────────────────

def require_role(*roles: UserRole):
    """Factory: creates a dependency that requires one of the given roles."""
    async def _check_role(
        current_user: User = Depends(get_current_user)
    ) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {[r.value for r in roles]}"
            )
        return current_user
    return _check_role


# Shorthand role dependencies
require_admin = require_role(UserRole.ADMIN)
require_premium = require_role(UserRole.ADMIN, UserRole.PREMIUM)
require_any_user = require_role(UserRole.ADMIN, UserRole.PREMIUM, UserRole.STANDARD)


# ──────────────────────────────────────────
# SUBSCRIPTION CHECKS
# ──────────────────────────────────────────

async def require_active_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Ensure user has an active subscription with jobs remaining."""
    from backend.models.models import Subscription, SubscriptionStatus

    result = await db.execute(
        select(Subscription).where(Subscription.user_id == current_user.id)
    )
    sub = result.scalar_one_or_none()

    if not sub or sub.status not in [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Active subscription required. Please upgrade your plan."
        )

    if sub.jobs_used_this_month >= sub.jobs_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Monthly job limit reached ({sub.jobs_limit} jobs). Upgrade to get more."
        )

    return current_user


async def require_scheduling_feature(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Require Pro or Business plan for scheduling."""
    from backend.models.models import Subscription, SubscriptionPlan
    from config.settings import PLANS

    result = await db.execute(
        select(Subscription).where(Subscription.user_id == current_user.id)
    )
    sub = result.scalar_one_or_none()

    if not sub:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Subscription required"
        )

    plan_config = PLANS.get(sub.plan.value, {})
    if not plan_config.get("scheduling", False):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Job scheduling requires Pro or Business plan. Please upgrade."
        )

    return current_user
