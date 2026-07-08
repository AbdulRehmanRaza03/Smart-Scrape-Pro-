"""
SmartScrape Pro — Server Launcher
Supports: dev, production, celery worker, celery beat
"""
import argparse
import subprocess
import sys
import os


def run_dev():
    """Run FastAPI in development mode with hot reload."""
    print("🚀 Starting SmartScrape Pro [DEV MODE]")
    os.system("uvicorn main:app --host 0.0.0.0 --port 8000 --reload --log-level debug")


def run_prod():
    """Run FastAPI in production with multiple workers."""
    print("🚀 Starting SmartScrape Pro [PRODUCTION MODE]")
    workers = os.cpu_count() * 2 + 1
    os.system(
        f"uvicorn main:app --host 0.0.0.0 --port 8000 "
        f"--workers {workers} --log-level info "
        f"--access-log --proxy-headers"
    )


def run_celery_worker():
    """Start Celery worker for background scraping jobs."""
    print("⚙️  Starting Celery Worker...")
    os.system(
        "celery -A backend.scheduler.tasks.celery_app worker "
        "--loglevel=info --queues=scraping,notifications "
        "--concurrency=4"
    )


def run_celery_beat():
    """Start Celery Beat scheduler for periodic tasks."""
    print("⏰ Starting Celery Beat Scheduler...")
    os.system(
        "celery -A backend.scheduler.tasks.celery_app beat "
        "--loglevel=info"
    )


def run_setup():
    """Install dependencies and set up environment."""
    print("📦 Installing dependencies...")
    os.system(f"{sys.executable} -m pip install -r requirements.txt")
    print("🎭 Installing Playwright browsers...")
    os.system("playwright install chromium")
    print("📁 Creating required directories...")
    for d in ["database", "logs", "exports", "exports/uploads"]:
        os.makedirs(d, exist_ok=True)
    if not os.path.exists("config/.env"):
        import shutil
        shutil.copy("config/.env.example", "config/.env")
        print("📝 Created config/.env from example — please update your credentials!")
    print("✅ Setup complete! Run: python run.py --mode dev")


def main():
    parser = argparse.ArgumentParser(description="SmartScrape Pro Server Launcher")
    parser.add_argument(
        "--mode",
        choices=["dev", "prod", "worker", "beat", "setup"],
        default="dev",
        help="Run mode: dev | prod | worker | beat | setup"
    )
    args = parser.parse_args()

    modes = {
        "dev": run_dev,
        "prod": run_prod,
        "worker": run_celery_worker,
        "beat": run_celery_beat,
        "setup": run_setup,
    }
    modes[args.mode]()


if __name__ == "__main__":
    main()
