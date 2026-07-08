"""
SmartScrape Pro — Payment Routes
Stripe subscription management + Manual payment gateway (Easypaisa/JazzCash/Bank)
"""
from fastapi import (
    APIRouter, Depends, HTTPException, status,
    Request, UploadFile, File, Form
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional
import os
import shutil
import uuid

from backend.models.database import get_db
from backend.models.models import (
    User, Subscription, Payment, Notification,
    SubscriptionPlan, SubscriptionStatus, PaymentMethod, PaymentStatus
)
from backend.auth.dependencies import get_current_user, require_admin
from config.settings import settings, PLANS
from backend.payments.stripe_service import StripeService
from backend.utils.logger import logger

router = APIRouter(prefix="/payments", tags=["Payments"])
stripe_service = StripeService()

# ──────────────────────────────────────────
# SCHEMAS
# ──────────────────────────────────────────

class CreateStripeSessionRequest(BaseModel):
    plan: str  # basic | pro | business
    billing_period: int = 1  # months (future: annual)


class ManualPaymentRequest(BaseModel):
    plan: str
    method: str  # easypaisa | jazzcash | bank_transfer
    transaction_reference: str
    sender_account: Optional[str] = None
    amount: float


class AdminReviewRequest(BaseModel):
    payment_id: str
    action: str  # approve | reject
    notes: Optional[str] = None


# ──────────────────────────────────────────
# STRIPE ROUTES
# ──────────────────────────────────────────

@router.post("/stripe/create-checkout")
async def create_stripe_checkout(
    data: CreateStripeSessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe Checkout session for subscription."""

    if data.plan not in PLANS or data.plan == "free":
        raise HTTPException(status_code=400, detail="Invalid plan selected")

    plan_config = PLANS[data.plan]
    price_id = plan_config.get("stripe_price_id")
    if not price_id:
        raise HTTPException(
            status_code=500,
            detail="Stripe price ID not configured. Contact admin."
        )

    try:
        session = await stripe_service.create_checkout_session(
            user=current_user,
            plan=data.plan,
            price_id=price_id,
            db=db,
        )
        return {
            "checkout_url": session.url,
            "session_id": session.id,
        }
    except Exception as e:
        logger.error(f"Stripe checkout error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create payment session")


@router.post("/stripe/create-portal")
async def create_customer_portal(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create Stripe Customer Portal session for subscription management."""

    if not current_user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe subscription found")

    try:
        portal = await stripe_service.create_portal_session(current_user.stripe_customer_id)
        return {"portal_url": portal.url}
    except Exception as e:
        logger.error(f"Stripe portal error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create portal session")


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe webhook events."""

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = await stripe_service.verify_webhook(payload, sig_header)
    except ValueError as e:
        logger.warning(f"Invalid Stripe webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except Exception as e:
        logger.warning(f"Stripe webhook signature failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    await stripe_service.handle_webhook_event(event, db)
    return {"status": "ok"}


# ──────────────────────────────────────────
# MANUAL PAYMENT ROUTES (Easypaisa/JazzCash/Bank)
# ──────────────────────────────────────────

@router.post("/manual/submit")
async def submit_manual_payment(
    plan: str = Form(...),
    method: str = Form(...),
    transaction_reference: str = Form(...),
    sender_account: str = Form(None),
    amount: float = Form(...),
    payment_proof: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a manual payment with proof screenshot."""

    # Validate plan
    if plan not in PLANS or plan == "free":
        raise HTTPException(status_code=400, detail="Invalid plan")

    # Validate method
    valid_methods = ["easypaisa", "jazzcash", "bank_transfer"]
    if method not in valid_methods:
        raise HTTPException(status_code=400, detail="Invalid payment method")

    # Save payment proof file
    upload_dir = os.path.join(settings.UPLOAD_DIR, "payment_proofs")
    os.makedirs(upload_dir, exist_ok=True)

    file_ext = payment_proof.filename.split(".")[-1].lower()
    if file_ext not in ["jpg", "jpeg", "png", "pdf"]:
        raise HTTPException(status_code=400, detail="Only JPG, PNG, PDF files accepted")

    file_name = f"{current_user.id}_{uuid.uuid4()}.{file_ext}"
    file_path = os.path.join(upload_dir, file_name)

    with open(file_path, "wb") as f:
        shutil.copyfileobj(payment_proof.file, f)

    # Create payment record
    plan_config = PLANS[plan]
    payment = Payment(
        user_id=current_user.id,
        amount=amount,
        currency="USD",
        method=PaymentMethod(method),
        status=PaymentStatus.UNDER_REVIEW,
        plan=SubscriptionPlan(plan),
        billing_period_months=1,
        transaction_reference=transaction_reference,
        sender_account=sender_account,
        payment_proof_url=file_path,
        metadata={"plan_name": plan_config["name"]},
    )
    db.add(payment)

    # Notify admin
    admin_notif = Notification(
        user_id=(await _get_admin_id(db)),
        title="New Manual Payment Submitted",
        message=f"User {current_user.email} submitted {method} payment for {plan} plan (${amount}). Ref: {transaction_reference}",
        type="warning",
        action_url=f"/admin/payments/{payment.id}",
    )
    db.add(admin_notif)

    # Notify user
    user_notif = Notification(
        user_id=current_user.id,
        title="Payment Under Review",
        message=f"Your {method} payment of ${amount} for {plan_config['name']} plan is under review. We'll notify you within 24 hours.",
        type="info",
    )
    db.add(user_notif)

    await db.commit()

    return {
        "payment_id": payment.id,
        "status": "under_review",
        "message": "Payment proof submitted. Admin will review within 24 hours.",
    }


@router.get("/history")
async def get_payment_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's payment history."""

    result = await db.execute(
        select(Payment)
        .where(Payment.user_id == current_user.id)
        .order_by(desc(Payment.created_at))
        .limit(50)
    )
    payments = result.scalars().all()

    return [
        {
            "id": p.id,
            "amount": p.amount,
            "currency": p.currency,
            "method": p.method.value,
            "status": p.status.value,
            "plan": p.plan.value,
            "transaction_reference": p.transaction_reference,
            "created_at": p.created_at,
            "completed_at": p.completed_at,
        }
        for p in payments
    ]


@router.get("/subscription")
async def get_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's subscription details."""

    result = await db.execute(
        select(Subscription).where(Subscription.user_id == current_user.id)
    )
    sub = result.scalar_one_or_none()

    if not sub:
        return {"plan": "free", "status": "none"}

    plan_config = PLANS.get(sub.plan.value, {})

    return {
        "plan": sub.plan.value,
        "plan_name": plan_config.get("name", "Unknown"),
        "status": sub.status.value,
        "jobs_used_this_month": sub.jobs_used_this_month,
        "jobs_limit": sub.jobs_limit,
        "jobs_remaining": max(0, sub.jobs_limit - sub.jobs_used_this_month),
        "scheduling": plan_config.get("scheduling", False),
        "api_access": plan_config.get("api_access", False),
        "export_formats": plan_config.get("export_formats", ["csv"]),
        "concurrent_jobs": plan_config.get("concurrent_jobs", 1),
        "current_period_start": sub.current_period_start,
        "current_period_end": sub.current_period_end,
        "cancel_at_period_end": sub.cancel_at_period_end,
        "price_usd": plan_config.get("price_usd", 0),
    }


# ──────────────────────────────────────────
# ADMIN PAYMENT MANAGEMENT
# ──────────────────────────────────────────

@router.get("/admin/pending", dependencies=[Depends(require_admin)])
async def get_pending_payments(
    db: AsyncSession = Depends(get_db),
):
    """Admin: Get all pending/under-review manual payments."""

    result = await db.execute(
        select(Payment)
        .where(Payment.status.in_([PaymentStatus.PENDING, PaymentStatus.UNDER_REVIEW]))
        .order_by(desc(Payment.created_at))
    )
    payments = result.scalars().all()

    # Fetch user emails
    output = []
    for p in payments:
        user_result = await db.execute(select(User).where(User.id == p.user_id))
        user = user_result.scalar_one_or_none()
        output.append({
            "id": p.id,
            "user_email": user.email if user else "unknown",
            "user_id": p.user_id,
            "amount": p.amount,
            "currency": p.currency,
            "method": p.method.value,
            "status": p.status.value,
            "plan": p.plan.value,
            "transaction_reference": p.transaction_reference,
            "sender_account": p.sender_account,
            "payment_proof_url": p.payment_proof_url,
            "created_at": p.created_at,
        })

    return output


@router.post("/admin/review", dependencies=[Depends(require_admin)])
async def review_manual_payment(
    data: AdminReviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin: Approve or reject a manual payment."""

    result = await db.execute(select(Payment).where(Payment.id == data.payment_id))
    payment = result.scalar_one_or_none()

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if data.action == "approve":
        payment.status = PaymentStatus.COMPLETED
        payment.reviewed_by = current_user.id
        payment.reviewed_at = datetime.now(timezone.utc)
        payment.completed_at = datetime.now(timezone.utc)
        payment.admin_notes = data.notes

        # Activate subscription
        sub_result = await db.execute(
            select(Subscription).where(Subscription.user_id == payment.user_id)
        )
        sub = sub_result.scalar_one_or_none()

        plan_config = PLANS[payment.plan.value]
        if sub:
            sub.plan = payment.plan
            sub.status = SubscriptionStatus.ACTIVE
            sub.jobs_limit = plan_config["jobs_per_month"]
            sub.jobs_used_this_month = 0
            sub.current_period_start = datetime.now(timezone.utc)
        else:
            from datetime import timedelta
            sub = Subscription(
                user_id=payment.user_id,
                plan=payment.plan,
                status=SubscriptionStatus.ACTIVE,
                jobs_limit=plan_config["jobs_per_month"],
                jobs_used_this_month=0,
                current_period_start=datetime.now(timezone.utc),
                current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
            )
            db.add(sub)

        # Notify user
        notif = Notification(
            user_id=payment.user_id,
            title="Payment Approved! 🎉",
            message=f"Your {payment.method.value} payment has been approved. {plan_config['name']} plan is now active!",
            type="success",
        )
        db.add(notif)

    elif data.action == "reject":
        payment.status = PaymentStatus.FAILED
        payment.reviewed_by = current_user.id
        payment.reviewed_at = datetime.now(timezone.utc)
        payment.admin_notes = data.notes
        payment.failure_reason = data.notes or "Payment rejected by admin"

        notif = Notification(
            user_id=payment.user_id,
            title="Payment Rejected",
            message=f"Your {payment.method.value} payment was rejected. Reason: {data.notes or 'Invalid payment details'}. Contact support.",
            type="error",
        )
        db.add(notif)
    else:
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")

    await db.commit()
    return {"message": f"Payment {data.action}d successfully"}


@router.get("/admin/all", dependencies=[Depends(require_admin)])
async def get_all_payments(
    page: int = 1,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Admin: Get all payments with pagination."""

    offset = (page - 1) * limit
    result = await db.execute(
        select(Payment)
        .order_by(desc(Payment.created_at))
        .offset(offset)
        .limit(limit)
    )
    payments = result.scalars().all()

    return [
        {
            "id": p.id,
            "user_id": p.user_id,
            "amount": p.amount,
            "method": p.method.value,
            "status": p.status.value,
            "plan": p.plan.value,
            "created_at": p.created_at,
        }
        for p in payments
    ]


# ──────────────────────────────────────────
# PLAN INFO (public)
# ──────────────────────────────────────────

@router.get("/plans")
async def get_plans():
    """Get all available subscription plans."""
    return [
        {
            "id": plan_id,
            "name": plan["name"],
            "price_usd": plan["price_usd"],
            "jobs_per_month": plan["jobs_per_month"],
            "scheduling": plan["scheduling"],
            "api_access": plan["api_access"],
            "export_formats": plan["export_formats"],
            "concurrent_jobs": plan["concurrent_jobs"],
            "support": plan["support"],
        }
        for plan_id, plan in PLANS.items()
    ]


# ──────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────

async def _get_admin_id(db: AsyncSession) -> str:
    """Get the first admin user ID."""
    from backend.models.models import UserRole
    result = await db.execute(
        select(User).where(User.role == UserRole.ADMIN).limit(1)
    )
    admin = result.scalar_one_or_none()
    return admin.id if admin else "system"
