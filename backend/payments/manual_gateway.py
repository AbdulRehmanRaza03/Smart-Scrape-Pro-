"""
SmartScrape Pro — Manual Payment Gateway
Easypaisa / JazzCash / Bank Transfer helper
Stores payment account config, generates instructions
"""
from config.settings import settings


# ── Payment Account Config ────────────────
# Update these in production via env vars or SystemConfig DB table

MANUAL_ACCOUNTS = {
    "easypaisa": {
        "name": "Easypaisa",
        "account_number": "0300-1234567",
        "account_title": "SmartScrape Pro (Pvt) Ltd",
        "instructions": [
            "Open Easypaisa app or dial *786#",
            "Select 'Send Money' → 'Mobile Account'",
            f"Enter number: 0300-1234567",
            "Enter amount as per your plan",
            "Screenshot the confirmation",
            "Submit reference ID + screenshot in payment form",
        ],
    },
    "jazzcash": {
        "name": "JazzCash",
        "account_number": "0301-1234567",
        "account_title": "SmartScrape Pro",
        "instructions": [
            "Open JazzCash app or dial *786#",
            "Select 'Send Money' → 'Mobile Wallet'",
            "Enter number: 0301-1234567",
            "Enter plan amount",
            "Note the transaction ID",
            "Submit TxID + screenshot in payment form",
        ],
    },
    "bank_transfer": {
        "name": "Bank Transfer",
        "bank_name": "HBL / Meezan Bank",
        "account_number": "0123456789012345",
        "iban": "PK36HABB0000000012345678",
        "account_title": "SmartScrape Technologies",
        "branch_code": "0034",
        "instructions": [
            "Transfer to: IBAN PK36HABB0000000012345678",
            "Bank: HBL (Habib Bank Limited)",
            "Account Title: SmartScrape Technologies",
            "Use your email as payment reference",
            "Send transaction screenshot via payment form",
            "Processing: 24-48 business hours",
        ],
    },
}

# PKR equivalent amounts (update as needed)
PLAN_PRICES_PKR = {
    "basic":    2_800,   # ~$10 USD
    "pro":      8_400,   # ~$30 USD
    "business": 28_000,  # ~$100 USD
}


def get_payment_instructions(method: str, plan: str) -> dict:
    """Return full payment instructions for given method and plan."""
    account = MANUAL_ACCOUNTS.get(method)
    if not account:
        return {"error": f"Unknown method: {method}"}

    pkr_amount = PLAN_PRICES_PKR.get(plan, 0)

    return {
        "method": method,
        "method_name": account["name"],
        "plan": plan,
        "amount_usd": {"basic": 10, "pro": 30, "business": 100}.get(plan, 0),
        "amount_pkr": pkr_amount,
        "account_info": {k: v for k, v in account.items() if k != "instructions"},
        "instructions": account["instructions"],
        "note": f"Send exactly PKR {pkr_amount:,} for {plan.title()} plan. Include your registered email in remarks.",
    }


def get_all_payment_info() -> dict:
    """Return all manual payment methods with instructions."""
    return {
        method: get_payment_instructions(method, "basic")
        for method in MANUAL_ACCOUNTS
    }


def verify_amount_reasonable(amount: float, plan: str) -> bool:
    """
    Basic sanity check: submitted amount should be close to expected PKR.
    Allows ±20% for currency fluctuation.
    """
    expected = PLAN_PRICES_PKR.get(plan, 0)
    if not expected:
        return False
    lower = expected * 0.8
    upper = expected * 1.3
    return lower <= amount <= upper
