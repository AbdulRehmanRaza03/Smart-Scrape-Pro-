"""
SmartScrape Pro — Stripe Payment Service
Handles Stripe API calls: checkout sessions, webhooks, customer portal
"""
from typing import Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config.settings import settings, PLANS
from backend.utils.logger import logger


class StripeService:
    """
    Stripe integration service.
    All methods are async-compatible via httpx or stripe's sync library run in executor.
    """

    def __init__(self):
        self._stripe = None

    def _get_stripe(self):
        """Lazy-load stripe to avoid import errors if key not set."""
        if self._stripe is None:
            import stripe
            stripe.api_key = settings.STRIPE_SECRET_KEY
            self._stripe = stripe
        return self._stripe

    async def create_or_get_customer(self, user, db: AsyncSession) -> str:
        """Create or retrieve Stripe customer ID for a user."""
        stripe = self._get_stripe()

        if user.stripe_customer_id:
            return user.stripe_customer_id

        # Create new customer
        customer = stripe.Customer.create(
            email=user.email,
            name=user.full_name or user.username,
            metadata={
                "user_id": user.id,
                "username": user.username,
            }
        )

        user.stripe_customer_id = customer.id
        await db.commit()

        logger.info(f"Created Stripe customer {customer.id} for user {user.email}")
        return customer.id

    async def create_checkout_session(self, user, plan: str, price_id: str, db: AsyncSession):
        """Create a Stripe Checkout session."""
        stripe = self._get_stripe()

        customer_id = await self.create_or_get_customer(user, db)
        plan_config = PLANS[plan]

        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{
                "price": price_id,
                "quantity": 1,
            }],
            mode="subscription",
            success_url=f"{settings.APP_NAME}://payment/success?session_id={{CHECKOUT_SESSION_ID}}&plan={plan}",
            cancel_url=f"{settings.APP_NAME}://payment/cancelled",
            metadata={
                "user_id": user.id,
                "plan": plan,
            },
            subscription_data={
                "metadata": {
                    "user_id": user.id,
                    "plan": plan,
                }
            },
            allow_promotion_codes=True,
        )

        return session

    async def create_portal_session(self, customer_id: str):
        """Create a Stripe Customer Portal session."""
        stripe = self._get_stripe()

        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url="https://app.smartscrapepro.com/dashboard",
        )
        return session

    async def verify_webhook(self, payload: bytes, sig_header: str):
        """Verify and decode a Stripe webhook event."""
        stripe = self._get_stripe()

        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            settings.STRIPE_WEBHOOK_SECRET
        )
        return event

    async def handle_webhook_event(self, event: dict, db: AsyncSession):
        """Route webhook events to appropriate handlers."""
        event_type = event["type"]

        logger.info(f"Handling Stripe webhook: {event_type}")

        handlers = {
            "checkout.session.completed": self._handle_checkout_completed,
            "customer.subscription.updated": self._handle_subscription_updated,
            "customer.subscription.deleted": self._handle_subscription_deleted,
            "invoice.payment_failed": self._handle_payment_failed,
            "invoice.payment_succeeded": self._handle_payment_succeeded,
        }

        handler = handlers.get(event_type)
        if handler:
            try:
                await handler(event["data"]["object"], db)
            except Exception as e:
                logger.error(f"Error handling Stripe event {event_type}: {e}")
        else:
            logger.debug(f"Unhandled Stripe event type: {event_type}")

    async def _handle_checkout_completed(self, session: dict, db: AsyncSession):
        """Handle successful checkout — activate subscription."""
        from backend.models.models import User, Subscription, Payment, SubscriptionPlan, SubscriptionStatus, PaymentMethod, PaymentStatus

        user_id = session.get("metadata", {}).get("user_id")
        plan = session.get("metadata", {}).get("plan")

        if not user_id or not plan:
            logger.warning("Checkout completed but missing metadata")
            return

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            logger.error(f"User {user_id} not found for checkout completion")
            return

        # Update/create subscription
        sub_result = await db.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        )
        sub = sub_result.scalar_one_or_none()
        plan_config = PLANS[plan]

        if sub:
            sub.plan = SubscriptionPlan(plan)
            sub.status = SubscriptionStatus.ACTIVE
            sub.jobs_limit = plan_config["jobs_per_month"]
            sub.stripe_subscription_id = session.get("subscription")
            sub.current_period_start = datetime.now(timezone.utc)
            sub.current_period_end = datetime.now(timezone.utc) + timedelta(days=30)
        else:
            sub = Subscription(
                user_id=user_id,
                plan=SubscriptionPlan(plan),
                status=SubscriptionStatus.ACTIVE,
                jobs_limit=plan_config["jobs_per_month"],
                jobs_used_this_month=0,
                stripe_subscription_id=session.get("subscription"),
                current_period_start=datetime.now(timezone.utc),
                current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
            )
            db.add(sub)

        # Record payment
        amount = session.get("amount_total", 0) / 100  # Stripe amounts in cents
        payment = Payment(
            user_id=user_id,
            amount=amount,
            currency=session.get("currency", "usd").upper(),
            method=PaymentMethod.STRIPE,
            status=PaymentStatus.COMPLETED,
            plan=SubscriptionPlan(plan),
            stripe_payment_intent_id=session.get("payment_intent"),
            completed_at=datetime.now(timezone.utc),
        )
        db.add(payment)

        # Add role upgrade if premium plan
        if plan in ["pro", "business"]:
            from backend.models.models import UserRole
            user.role = UserRole.PREMIUM

        await db.commit()
        logger.success(f"Subscription activated for user {user_id}: {plan}")

    async def _handle_subscription_updated(self, subscription: dict, db: AsyncSession):
        """Handle subscription update (upgrade/downgrade/cancel)."""
        from backend.models.models import Subscription, SubscriptionStatus

        stripe_sub_id = subscription.get("id")
        result = await db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
        )
        sub = result.scalar_one_or_none()

        if not sub:
            return

        stripe_status = subscription.get("status")
        status_map = {
            "active": SubscriptionStatus.ACTIVE,
            "canceled": SubscriptionStatus.CANCELLED,
            "past_due": SubscriptionStatus.PAST_DUE,
            "trialing": SubscriptionStatus.TRIALING,
        }

        if stripe_status in status_map:
            sub.status = status_map[stripe_status]

        sub.cancel_at_period_end = subscription.get("cancel_at_period_end", False)

        if subscription.get("cancel_at_period_end"):
            from datetime import datetime
            sub.cancelled_at = datetime.now(timezone.utc)

        await db.commit()
        logger.info(f"Subscription {stripe_sub_id} updated to {stripe_status}")

    async def _handle_subscription_deleted(self, subscription: dict, db: AsyncSession):
        """Handle subscription cancellation — downgrade to free."""
        from backend.models.models import Subscription, SubscriptionStatus, SubscriptionPlan
        from config.settings import PLANS

        stripe_sub_id = subscription.get("id")
        result = await db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
        )
        sub = result.scalar_one_or_none()

        if sub:
            sub.plan = SubscriptionPlan.FREE
            sub.status = SubscriptionStatus.CANCELLED
            sub.jobs_limit = PLANS["free"]["jobs_per_month"]
            await db.commit()
            logger.info(f"Subscription {stripe_sub_id} cancelled — downgraded to free")

    async def _handle_payment_failed(self, invoice: dict, db: AsyncSession):
        """Handle failed payment."""
        from backend.models.models import Subscription, SubscriptionStatus

        customer_id = invoice.get("customer")
        # Mark subscription as past_due
        result = await db.execute(
            select(Subscription)
            .join(Subscription.user)
        )
        # This is a simplified version — in production would look up by stripe customer id
        logger.warning(f"Payment failed for Stripe customer {customer_id}")

    async def _handle_payment_succeeded(self, invoice: dict, db: AsyncSession):
        """Handle successful recurring payment."""
        customer_id = invoice.get("customer")
        amount = invoice.get("amount_paid", 0) / 100
        logger.info(f"Payment succeeded: ${amount} for customer {customer_id}")

    async def cancel_subscription(self, stripe_subscription_id: str, at_period_end: bool = True):
        """Cancel a Stripe subscription."""
        stripe = self._get_stripe()
        stripe.Subscription.modify(
            stripe_subscription_id,
            cancel_at_period_end=at_period_end,
        )
