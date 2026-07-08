"""
SmartScrape Pro — Shared Utility Helpers
"""
import re
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from urllib.parse import urlparse


# ── URL Validation ────────────────────────

def is_valid_url(url: str) -> bool:
    """Check URL is valid http/https."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def sanitize_url(url: str) -> str:
    """Strip whitespace and ensure scheme."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


# ── Cron Helpers ─────────────────────────

CRON_PRESETS = {
    "every_hour":    "0 * * * *",
    "every_day_9am": "0 9 * * *",
    "every_monday":  "0 9 * * 1",
    "every_week":    "0 9 * * 0",
    "every_month":   "0 9 1 * *",
}


def validate_cron(expr: str) -> bool:
    """Basic 5-field cron expression validation."""
    parts = expr.strip().split()
    if len(parts) != 5:
        return False
    ranges = [(0,59),(0,23),(1,31),(1,12),(0,7)]
    for part, (lo, hi) in zip(parts, ranges):
        if part == "*":
            continue
        try:
            val = int(part)
            if not (lo <= val <= hi):
                return False
        except ValueError:
            if not re.match(r"^\*/\d+$", part):
                return False
    return True


def next_cron_run(cron_expr: str) -> Optional[datetime]:
    """Get approximate next run datetime for a cron expression."""
    try:
        from croniter import croniter
        itr = croniter(cron_expr, datetime.now(timezone.utc))
        return itr.get_next(datetime)
    except ImportError:
        # croniter not installed — return estimate
        return datetime.now(timezone.utc) + timedelta(hours=1)
    except Exception:
        return None


# ── Data Processing ───────────────────────

def flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    """Flatten nested dict: {'a': {'b': 1}} → {'a.b': 1}"""
    items = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep))
        else:
            items[new_key] = v
    return items


def truncate(text: str, max_len: int = 200) -> str:
    """Truncate string with ellipsis."""
    if not text:
        return ""
    return text[:max_len] + "…" if len(text) > max_len else text


def clean_text(text: str) -> str:
    """Strip excess whitespace from scraped text."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


# ── File Helpers ──────────────────────────

ALLOWED_PROOF_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
ALLOWED_EXPORT_EXTENSIONS = {".json", ".csv", ".xlsx", ".xml"}


def safe_filename(name: str, ext: str) -> str:
    """Generate a safe filename."""
    name = re.sub(r"[^\w\-]", "_", name)[:50]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    rand = secrets.token_hex(4)
    return f"{name}_{ts}_{rand}{ext}"


def file_size_mb(path: str) -> float:
    """Get file size in MB."""
    import os
    try:
        return os.path.getsize(path) / (1024 * 1024)
    except Exception:
        return 0.0


# ── Security ──────────────────────────────

def mask_email(email: str) -> str:
    """Mask email: ab***@gmail.com"""
    try:
        local, domain = email.split("@")
        return local[:2] + "***@" + domain
    except Exception:
        return "***"


def hash_ip(ip: str) -> str:
    """Hash IP for privacy-safe logging."""
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


# ── Pagination ────────────────────────────

def paginate(items: list, page: int, limit: int) -> dict:
    """Simple list paginator."""
    total = len(items)
    offset = (page - 1) * limit
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": max(1, (total + limit - 1) // limit),
        "items": items[offset:offset + limit],
    }


# ── Response Builders ─────────────────────

def ok(data: Any = None, message: str = "Success") -> dict:
    return {"status": "ok", "message": message, "data": data}


def err(message: str, code: str = "ERROR") -> dict:
    return {"status": "error", "code": code, "message": message}
