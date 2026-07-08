"""
SmartScrape Pro — Main FastAPI Application
Production-ready SaaS platform entry point
"""
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import time
import os

from config.settings import settings
from backend.utils.logger import logger, setup_logging
from backend.models.database import init_db


# ──────────────────────────────────────────
# LIFESPAN
# ──────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    setup_logging()
    logger.info("🚀 SmartScrape Pro starting up...")

    # Create required directories
    for d in ["./exports", "./exports/uploads", "./logs", "./database"]:
        os.makedirs(d, exist_ok=True)

    logger.info("📦 Using SQLite database (dev mode)")
    logger.success("✅ SmartScrape Pro is ready!")
    yield

    logger.info("👋 SmartScrape Pro shutting down...")


# ──────────────────────────────────────────
# APP INSTANCE
# ──────────────────────────────────────────

app = FastAPI(
    title="SmartScrape Pro API",
    description="""
## SmartScrape Pro — Enterprise Web Scraping SaaS

A multi-tenant SaaS platform for automated web scraping with:
- **Multi-user authentication** with JWT
- **Role-based access control** (Admin, Standard, Premium)
- **Subscription billing** via Stripe + Manual payments (Easypaisa, JazzCash, Bank)
- **Background job execution** via Celery
- **Playwright/Selenium scraping engine** with anti-bot handling
- **Per-user data isolation**
- **Admin dashboard** with full user management

### Plans
| Plan | Price | Jobs/Month | Scheduling | API Access |
|------|-------|------------|------------|------------|
| Free | $0 | 3 | ❌ | ❌ |
| Basic | $10 | 10 | ❌ | ❌ |
| Pro | $30 | 100 | ✅ | ❌ |
| Business | $100 | Unlimited | ✅ | ✅ |
    """,
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


# ──────────────────────────────────────────
# MIDDLEWARE
# ──────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8000",
        "https://app.smartscrapepro.com",
        "https://smartscrapepro.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request timing middleware
@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
    response.headers["X-Powered-By"] = "SmartScrape Pro"
    return response


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = (time.time() - start) * 1000

    if request.url.path not in ["/health", "/api/docs", "/api/redoc"]:
        logger.info(
            f"{request.method} {request.url.path} → {response.status_code} ({duration:.0f}ms)"
        )
    return response


# ──────────────────────────────────────────
# RATE LIMITING
# ──────────────────────────────────────────

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded

    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    logger.info("⚡ Rate limiting enabled")
except ImportError:
    logger.warning("slowapi not installed — rate limiting disabled")


# ──────────────────────────────────────────
# ROUTES
# ──────────────────────────────────────────

from backend.routes.auth_routes import router as auth_router
from backend.routes.payment_routes import router as payment_router
from backend.routes.job_routes import router as job_router
from backend.routes.admin_routes import router as admin_router
from backend.routes.notification_routes import router as notif_router
from backend.routes.automation_routes import router as automation_router
from backend.utils.middleware import APILoggingMiddleware, SecurityHeadersMiddleware

app.add_middleware(APILoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(payment_router, prefix="/api/v1")
app.include_router(job_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(automation_router, prefix="/api/v1")
app.include_router(notif_router, prefix="/api/v1")


# ──────────────────────────────────────────
# FRONTEND ROUTES (HTML Templates)
# ──────────────────────────────────────────

@app.get("/auth/login", tags=["Frontend"])
async def login_page():
    """Serve login page."""
    if os.path.exists("./frontend/templates/auth/login.html"):
        return FileResponse("./frontend/templates/auth/login.html", media_type="text/html")
    return HTMLResponse("<h1>Login Page</h1>")

@app.get("/auth/signup", tags=["Frontend"])
async def signup_page():
    """Serve signup page."""
    if os.path.exists("./frontend/templates/auth/login.html"):
        return FileResponse("./frontend/templates/auth/login.html", media_type="text/html")
    return HTMLResponse("<h1>Signup Page</h1>")

@app.get("/dashboard", tags=["Frontend"])
async def dashboard_page():
    """Serve user dashboard."""
    if os.path.exists("./frontend/templates/user/dashboard.html"):
        return FileResponse("./frontend/templates/user/dashboard.html", media_type="text/html")
    return HTMLResponse("<h1>Dashboard</h1>")

@app.get("/admin", tags=["Frontend"])
async def admin_page():
    """Serve admin dashboard."""
    if os.path.exists("./frontend/templates/admin/admin.html"):
        return FileResponse("./frontend/templates/admin/admin.html", media_type="text/html")
    return HTMLResponse("<h1>Admin Dashboard</h1>")


# ──────────────────────────────────────────
# STATIC FILES (if frontend exists)
# ──────────────────────────────────────────

if os.path.exists("./frontend/static"):
    app.mount("/static", StaticFiles(directory="./frontend/static"), name="static")


# ──────────────────────────────────────────
# HEALTH & ROOT
# ──────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint for load balancers."""
    return {
        "status": "healthy",
        "app": "SmartScrape Pro",
        "version": "1.0.0",
        "env": settings.APP_ENV,
    }


@app.get("/", tags=["System"])
async def root():
    """API root — returns platform info."""
    return {
        "platform": "SmartScrape Pro",
        "version": "1.0.0",
        "description": "Enterprise Web Scraping SaaS Platform",
        "docs": "/api/docs",
        "status": "operational",
        "plans": {
            "free": "$0/month — 3 jobs",
            "basic": "$10/month — 10 jobs",
            "pro": "$30/month — 100 jobs + scheduling",
            "business": "$100/month — unlimited + API",
        }
    }


# ──────────────────────────────────────────
# GLOBAL EXCEPTION HANDLER
# ──────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "Something went wrong. Our team has been notified.",
        }
    )
