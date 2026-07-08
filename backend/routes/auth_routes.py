"""
SmartScrape Pro — Authentication Routes
POST /auth/signup, /auth/login, /auth/refresh, /auth/me, etc.
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr, validator
from datetime import datetime, timezone
import secrets
import re

from backend.models.database import get_db
from backend.models.models import User, Subscription, UserRole, SubscriptionPlan, SubscriptionStatus
from backend.auth.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token, generate_api_key
)
from backend.auth.dependencies import get_current_user
from config.settings import PLANS

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ──────────────────────────────────────────
# SCHEMAS
# ──────────────────────────────────────────

class SignupRequest(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: str | None = None
    company: str | None = None
    country: str | None = None

    @validator("username")
    def validate_username(cls, v):
        if not re.match(r"^[a-zA-Z0-9_]{3,30}$", v):
            raise ValueError("Username must be 3-30 chars, alphanumeric and underscores only")
        return v.lower()

    @validator("password")
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    role: str
    plan: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @validator("new_password")
    def validate_new_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UpdateProfileRequest(BaseModel):
    full_name: str | None = None
    company: str | None = None
    country: str | None = None
    phone: str | None = None
    timezone: str | None = None


# ──────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────

def get_user_plan(subscription) -> str:
    if not subscription:
        return "free"
    return subscription.plan.value


# ──────────────────────────────────────────
# ROUTES
# ──────────────────────────────────────────

@router.post("/signup", response_model=TokenResponse, status_code=201)
async def signup(
    data: SignupRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user account with free plan."""

    # Check email uniqueness
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered"
        )

    # Check username uniqueness
    result = await db.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken"
        )

    # Create user
    user = User(
        email=data.email,
        username=data.username,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        company=data.company,
        country=data.country,
        role=UserRole.STANDARD,
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    await db.flush()  # get the ID

    # Create free subscription
    free_plan = PLANS["free"]
    subscription = Subscription(
        user_id=user.id,
        plan=SubscriptionPlan.FREE,
        status=SubscriptionStatus.ACTIVE,
        jobs_used_this_month=0,
        jobs_limit=free_plan["jobs_per_month"],
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(user)

    # Generate tokens
    token_data = {"sub": user.id, "email": user.email, "role": user.role.value}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=user.id,
        email=user.email,
        role=user.role.value,
        plan="free",
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user and return JWT tokens."""

    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

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

    # Update last login
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    # Fetch subscription
    sub_result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    sub = sub_result.scalar_one_or_none()

    token_data = {"sub": user.id, "email": user.email, "role": user.role.value}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=user.id,
        email=user.email,
        role=user.role.value,
        plan=get_user_plan(sub),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Exchange refresh token for a new access token."""

    payload = decode_token(data.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    sub_result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    sub = sub_result.scalar_one_or_none()

    token_data = {"sub": user.id, "email": user.email, "role": user.role.value}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
        user_id=user.id,
        email=user.email,
        role=user.role.value,
        plan=get_user_plan(sub),
    )


@router.get("/me")
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current authenticated user profile."""

    sub_result = await db.execute(
        select(Subscription).where(Subscription.user_id == current_user.id)
    )
    sub = sub_result.scalar_one_or_none()

    return {
        "id": current_user.id,
        "email": current_user.email,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "role": current_user.role.value,
        "is_verified": current_user.is_verified,
        "company": current_user.company,
        "country": current_user.country,
        "phone": current_user.phone,
        "timezone": current_user.timezone,
        "avatar_url": current_user.avatar_url,
        "created_at": current_user.created_at,
        "last_login_at": current_user.last_login_at,
        "subscription": {
            "plan": sub.plan.value if sub else "free",
            "status": sub.status.value if sub else "inactive",
            "jobs_used_this_month": sub.jobs_used_this_month if sub else 0,
            "jobs_limit": sub.jobs_limit if sub else 3,
            "current_period_end": sub.current_period_end if sub else None,
        } if sub else None,
        "has_api_key": bool(current_user.api_key),
    }


@router.put("/me")
async def update_profile(
    data: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user profile."""

    if data.full_name is not None:
        current_user.full_name = data.full_name
    if data.company is not None:
        current_user.company = data.company
    if data.country is not None:
        current_user.country = data.country
    if data.phone is not None:
        current_user.phone = data.phone
    if data.timezone is not None:
        current_user.timezone = data.timezone

    await db.commit()
    return {"message": "Profile updated successfully"}


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change user password."""

    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    current_user.hashed_password = hash_password(data.new_password)
    await db.commit()
    return {"message": "Password changed successfully"}


@router.post("/generate-api-key")
async def generate_user_api_key(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate or rotate API key (Business plan only)."""
    from backend.models.models import Subscription, SubscriptionPlan

    sub_result = await db.execute(
        select(Subscription).where(Subscription.user_id == current_user.id)
    )
    sub = sub_result.scalar_one_or_none()

    if not sub or sub.plan not in [SubscriptionPlan.BUSINESS]:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="API key access requires Business plan"
            )

    new_key = generate_api_key()
    current_user.api_key = new_key
    current_user.api_key_created_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "api_key": new_key,
        "created_at": current_user.api_key_created_at,
        "message": "API key generated. Store it safely — it won't be shown again."
    }
