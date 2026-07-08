"""
SmartScrape Pro — Admin Routes
Full admin panel: users, subscriptions, analytics, system management
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, update
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta

from backend.models.database import get_db
from backend.models.models import (
    User, Subscription, Payment, ScrapingJob, APILog,
    Notification, UserRole, SubscriptionPlan, SubscriptionStatus, JobStatus,
    PaymentStatus
)
from backend.auth.dependencies import get_current_user, require_admin
from config.settings import PLANS

router = APIRouter(prefix="/admin", tags=["Admin"])


# ──────────────────────────────────────────
# DASHBOARD STATS
# ──────────────────────────────────────────

@router.get("/stats", dependencies=[Depends(require_admin)])
async def get_admin_stats(db: AsyncSession = Depends(get_db)):
    """Admin dashboard — key metrics overview."""

    # Total users
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar()

    # Active subscriptions by plan
    subs_result = await db.execute(
        select(Subscription.plan, func.count().label("count"))
        .where(Subscription.status == SubscriptionStatus.ACTIVE)
        .group_by(Subscription.plan)
    )
    subs_by_plan = {row.plan.value: row.count for row in subs_result}

    # Revenue this month
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0)
    revenue_result = await db.execute(
        select(func.sum(Payment.amount))
        .where(
            Payment.status == PaymentStatus.COMPLETED,
            Payment.completed_at >= month_start
        )
    )
    monthly_revenue = revenue_result.scalar() or 0.0

    # Total revenue
    total_revenue = (await db.execute(
        select(func.sum(Payment.amount)).where(Payment.status == PaymentStatus.COMPLETED)
    )).scalar() or 0.0

    # Jobs this month
    jobs_this_month = (await db.execute(
        select(func.count()).select_from(ScrapingJob).where(
            ScrapingJob.created_at >= month_start
        )
    )).scalar()

    # Jobs by status
    jobs_status_result = await db.execute(
        select(ScrapingJob.status, func.count().label("count")).group_by(ScrapingJob.status)
    )
    jobs_by_status = {row.status.value: row.count for row in jobs_status_result}

    # Pending manual payments
    pending_payments = (await db.execute(
        select(func.count()).select_from(Payment).where(
            Payment.status.in_([PaymentStatus.PENDING, PaymentStatus.UNDER_REVIEW])
        )
    )).scalar()

    # New users this week
    week_start = datetime.now(timezone.utc) - timedelta(days=7)
    new_users_week = (await db.execute(
        select(func.count()).select_from(User).where(User.created_at >= week_start)
    )).scalar()

    return {
        "users": {
            "total": total_users,
            "new_this_week": new_users_week,
        },
        "subscriptions": {
            "by_plan": subs_by_plan,
            "total_paid": sum(v for k, v in subs_by_plan.items() if k != "free"),
        },
        "revenue": {
            "this_month": round(monthly_revenue, 2),
            "total": round(total_revenue, 2),
        },
        "jobs": {
            "this_month": jobs_this_month,
            "by_status": jobs_by_status,
        },
        "pending_payments": pending_payments,
    }


# ──────────────────────────────────────────
# USER MANAGEMENT
# ──────────────────────────────────────────

@router.get("/users", dependencies=[Depends(require_admin)])
async def list_users(
    page: int = 1,
    limit: int = 50,
    search: Optional[str] = None,
    plan: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all users with subscription info."""

    query = select(User).order_by(desc(User.created_at))

    if search:
        query = query.where(
            (User.email.ilike(f"%{search}%")) | (User.username.ilike(f"%{search}%"))
        )

    offset = (page - 1) * limit
    result = await db.execute(query.offset(offset).limit(limit))
    users = result.scalars().all()

    total = (await db.execute(select(func.count()).select_from(User))).scalar()

    output = []
    for user in users:
        sub_result = await db.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        )
        sub = sub_result.scalar_one_or_none()
        output.append({
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role.value,
            "is_active": user.is_active,
            "is_banned": user.is_banned,
            "country": user.country,
            "created_at": user.created_at,
            "last_login_at": user.last_login_at,
            "plan": sub.plan.value if sub else "free",
            "subscription_status": sub.status.value if sub else "none",
            "jobs_used": sub.jobs_used_this_month if sub else 0,
        })

    return {"total": total, "page": page, "users": output}


@router.get("/users/{user_id}", dependencies=[Depends(require_admin)])
async def get_user_detail(user_id: str, db: AsyncSession = Depends(get_db)):
    """Get detailed user information."""

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    sub_result = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    sub = sub_result.scalar_one_or_none()

    payment_result = await db.execute(
        select(Payment).where(Payment.user_id == user_id).order_by(desc(Payment.created_at)).limit(10)
    )
    payments = payment_result.scalars().all()

    job_result = await db.execute(
        select(ScrapingJob).where(ScrapingJob.user_id == user_id).order_by(desc(ScrapingJob.created_at)).limit(10)
    )
    jobs = job_result.scalars().all()

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role.value,
            "is_active": user.is_active,
            "is_banned": user.is_banned,
            "country": user.country,
            "company": user.company,
            "created_at": user.created_at,
            "last_login_at": user.last_login_at,
            "stripe_customer_id": user.stripe_customer_id,
        },
        "subscription": {
            "plan": sub.plan.value if sub else "free",
            "status": sub.status.value if sub else "none",
            "jobs_used": sub.jobs_used_this_month if sub else 0,
            "jobs_limit": sub.jobs_limit if sub else 0,
            "current_period_end": sub.current_period_end if sub else None,
        } if sub else None,
        "payments": [{"id": p.id, "amount": p.amount, "method": p.method.value, "status": p.status.value, "created_at": p.created_at} for p in payments],
        "recent_jobs": [{"id": j.id, "name": j.name, "status": j.status.value, "created_at": j.created_at} for j in jobs],
    }


class UpdateUserRequest(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    is_banned: Optional[bool] = None
    plan: Optional[str] = None


@router.put("/users/{user_id}", dependencies=[Depends(require_admin)])
async def update_user(
    user_id: str,
    data: UpdateUserRequest,
    db: AsyncSession = Depends(get_db),
):
    """Admin: Update user role, status, or plan."""

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if data.role is not None:
        try:
            user.role = UserRole(data.role)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid role: {data.role}")

    if data.is_active is not None:
        user.is_active = data.is_active

    if data.is_banned is not None:
        user.is_banned = data.is_banned

    # Update subscription plan
    if data.plan is not None:
        if data.plan not in PLANS:
            raise HTTPException(status_code=400, detail="Invalid plan")

        sub_result = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
        sub = sub_result.scalar_one_or_none()
        plan_config = PLANS[data.plan]

        if sub:
            sub.plan = SubscriptionPlan(data.plan)
            sub.status = SubscriptionStatus.ACTIVE
            sub.jobs_limit = plan_config["jobs_per_month"]
        else:
            sub = Subscription(
                user_id=user_id,
                plan=SubscriptionPlan(data.plan),
                status=SubscriptionStatus.ACTIVE,
                jobs_limit=plan_config["jobs_per_month"],
            )
            db.add(sub)

    await db.commit()
    return {"message": "User updated successfully"}


@router.delete("/users/{user_id}", dependencies=[Depends(require_admin)])
async def delete_user(user_id: str, db: AsyncSession = Depends(get_db)):
    """Admin: Delete a user account."""

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role == UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Cannot delete admin accounts")

    await db.delete(user)
    await db.commit()
    return {"message": "User deleted"}


# ──────────────────────────────────────────
# ALL JOBS (ADMIN VIEW)
# ──────────────────────────────────────────

@router.get("/jobs", dependencies=[Depends(require_admin)])
async def list_all_jobs(
    page: int = 1,
    limit: int = 50,
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Admin: View all scraping jobs across all users."""

    query = select(ScrapingJob).order_by(desc(ScrapingJob.created_at))

    if status_filter:
        try:
            query = query.where(ScrapingJob.status == JobStatus(status_filter))
        except ValueError:
            pass

    offset = (page - 1) * limit
    result = await db.execute(query.offset(offset).limit(limit))
    jobs = result.scalars().all()

    total = (await db.execute(select(func.count()).select_from(ScrapingJob))).scalar()

    return {
        "total": total,
        "jobs": [
            {
                "id": j.id,
                "user_id": j.user_id,
                "name": j.name,
                "target_url": j.target_url,
                "status": j.status.value,
                "engine": j.engine.value,
                "records_scraped": j.records_scraped,
                "duration_seconds": j.duration_seconds,
                "created_at": j.created_at,
            }
            for j in jobs
        ]
    }


# ──────────────────────────────────────────
# SYSTEM ANALYTICS
# ──────────────────────────────────────────

@router.get("/analytics/revenue", dependencies=[Depends(require_admin)])
async def revenue_analytics(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """Revenue analytics over time."""

    since = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(Payment)
        .where(
            Payment.status == PaymentStatus.COMPLETED,
            Payment.completed_at >= since
        )
        .order_by(Payment.completed_at)
    )
    payments = result.scalars().all()

    # Group by day
    daily = {}
    for p in payments:
        day = p.completed_at.strftime("%Y-%m-%d")
        daily[day] = daily.get(day, 0) + p.amount

    by_method = {}
    for p in payments:
        method = p.method.value
        by_method[method] = by_method.get(method, 0) + p.amount

    by_plan = {}
    for p in payments:
        plan = p.plan.value
        by_plan[plan] = by_plan.get(plan, 0) + p.amount

    return {
        "period_days": days,
        "total_revenue": round(sum(daily.values()), 2),
        "daily_revenue": daily,
        "by_method": {k: round(v, 2) for k, v in by_method.items()},
        "by_plan": {k: round(v, 2) for k, v in by_plan.items()},
        "transaction_count": len(payments),
    }


@router.get("/analytics/users", dependencies=[Depends(require_admin)])
async def user_analytics(db: AsyncSession = Depends(get_db)):
    """User growth and activity analytics."""

    # Signups by month
    result = await db.execute(
        select(
            func.strftime("%Y-%m", User.created_at).label("month"),
            func.count().label("count")
        ).group_by("month").order_by("month")
    )
    signups_by_month = {row.month: row.count for row in result}

    # Users by country
    country_result = await db.execute(
        select(User.country, func.count().label("count"))
        .where(User.country.isnot(None))
        .group_by(User.country)
        .order_by(desc("count"))
        .limit(10)
    )
    by_country = {row.country: row.count for row in country_result}

    # Active vs inactive
    active = (await db.execute(select(func.count()).select_from(User).where(User.is_active == True))).scalar()
    inactive = (await db.execute(select(func.count()).select_from(User).where(User.is_active == False))).scalar()

    return {
        "signups_by_month": signups_by_month,
        "by_country": by_country,
        "active_users": active,
        "inactive_users": inactive,
    }


# ──────────────────────────────────────────
# NOTIFICATIONS (ADMIN BROADCAST)
# ──────────────────────────────────────────

class BroadcastRequest(BaseModel):
    title: str
    message: str
    type: str = "info"
    target: str = "all"  # all | plan:basic | plan:pro | plan:business


@router.post("/broadcast", dependencies=[Depends(require_admin)])
async def broadcast_notification(
    data: BroadcastRequest,
    db: AsyncSession = Depends(get_db),
):
    """Broadcast notification to users."""

    if data.target == "all":
        users_result = await db.execute(select(User).where(User.is_active == True))
    elif data.target.startswith("plan:"):
        plan = data.target.split(":")[1]
        subs_result = await db.execute(
            select(Subscription.user_id).where(Subscription.plan == SubscriptionPlan(plan))
        )
        user_ids = [row.user_id for row in subs_result]
        users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
    else:
        raise HTTPException(status_code=400, detail="Invalid target")

    users = users_result.scalars().all()

    for user in users:
        notif = Notification(
            user_id=user.id,
            title=data.title,
            message=data.message,
            type=data.type,
        )
        db.add(notif)

    await db.commit()
    return {"message": f"Notification sent to {len(users)} users"}
