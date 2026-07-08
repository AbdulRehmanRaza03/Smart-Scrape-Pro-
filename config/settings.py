"""
SmartScrape Pro — Application Configuration
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional
import os


class Settings(BaseSettings):
    # App
    APP_NAME: str = "SmartScrape Pro"
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = "dev-secret-change-in-production"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./database/smartscrape.db"

    # JWT
    JWT_SECRET_KEY: str = "jwt-secret-change-this"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Stripe
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_BASIC_PRICE_ID: str = ""
    STRIPE_PRO_PRICE_ID: str = ""
    STRIPE_BUSINESS_PRICE_ID: str = ""

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # Admin defaults
    ADMIN_EMAIL: str = "admin@smartscrapepro.com"
    ADMIN_PASSWORD: str = "AdminPass123!"

    # File Upload
    UPLOAD_DIR: str = "./exports/uploads"
    MAX_UPLOAD_SIZE_MB: int = 10

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # Scraping
    SCRAPE_TIMEOUT_SECONDS: int = 30
    MAX_CONCURRENT_JOBS: int = 5

    # Plan limits
    BASIC_JOBS_PER_MONTH: int = 10
    PRO_JOBS_PER_MONTH: int = 100
    BUSINESS_JOBS_PER_MONTH: int = 999999

    class Config:
        env_file = "config/.env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

# Plan configuration
PLANS = {
    "free": {
        "name": "Free",
        "price_usd": 0,
        "jobs_per_month": 3,
        "scheduling": False,
        "api_access": False,
        "export_formats": ["csv"],
        "concurrent_jobs": 1,
        "support": "community",
    },
    "basic": {
        "name": "Basic",
        "price_usd": 10,
        "jobs_per_month": settings.BASIC_JOBS_PER_MONTH,
        "scheduling": False,
        "api_access": False,
        "export_formats": ["csv", "json"],
        "concurrent_jobs": 2,
        "support": "email",
        "stripe_price_id": settings.STRIPE_BASIC_PRICE_ID,
    },
    "pro": {
        "name": "Pro",
        "price_usd": 30,
        "jobs_per_month": settings.PRO_JOBS_PER_MONTH,
        "scheduling": True,
        "api_access": False,
        "export_formats": ["csv", "json", "xlsx"],
        "concurrent_jobs": 5,
        "support": "priority",
        "stripe_price_id": settings.STRIPE_PRO_PRICE_ID,
    },
    "business": {
        "name": "Business",
        "price_usd": 100,
        "jobs_per_month": settings.BUSINESS_JOBS_PER_MONTH,
        "scheduling": True,
        "api_access": True,
        "export_formats": ["csv", "json", "xlsx", "xml"],
        "concurrent_jobs": 20,
        "support": "dedicated",
        "stripe_price_id": settings.STRIPE_BUSINESS_PRICE_ID,
    },
}
