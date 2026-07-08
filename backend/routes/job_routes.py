"""
SmartScrape Pro — Scraping Job Routes
Create, manage, execute, and export scraping jobs
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from pydantic import BaseModel, HttpUrl
from typing import Optional, Any
from datetime import datetime, timezone
import os

from backend.models.database import get_db
from backend.models.models import (
    User, ScrapingJob, JobLog, ScrapingResult,
    Subscription, JobStatus, ScrapingEngine, ExportFormat
)
from backend.auth.dependencies import (
    get_current_user, require_active_subscription, require_scheduling_feature
)
from config.settings import settings

router = APIRouter(prefix="/jobs", tags=["Scraping Jobs"])


# ──────────────────────────────────────────
# SCHEMAS
# ──────────────────────────────────────────

class CreateJobRequest(BaseModel):
    name: str
    description: Optional[str] = None
    target_url: str
    engine: str = "auto"  # auto | playwright | beautifulsoup
    selectors: Optional[dict] = {}
    headers: Optional[dict] = {}
    cookies: Optional[list] = []
    proxy_config: Optional[dict] = {}
    pagination_config: Optional[dict] = {}
    export_format: str = "json"  # json | csv | xlsx
    is_scheduled: bool = False
    cron_expression: Optional[str] = None


class UpdateJobRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    selectors: Optional[dict] = None
    export_format: Optional[str] = None
    is_scheduled: Optional[bool] = None
    cron_expression: Optional[str] = None


# ──────────────────────────────────────────
# CREATE JOB
# ──────────────────────────────────────────

@router.post("/", status_code=201)
async def create_job(
    data: CreateJobRequest,
    current_user: User = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db),
):
    """Create a new scraping job."""

    # Validate engine
    valid_engines = ["auto", "playwright", "beautifulsoup", "selenium"]
    if data.engine not in valid_engines:
        raise HTTPException(status_code=400, detail=f"Invalid engine. Choose from: {valid_engines}")

    # Validate export format
    valid_formats = ["json", "csv", "xlsx", "xml"]
    if data.export_format not in valid_formats:
        raise HTTPException(status_code=400, detail=f"Invalid format. Choose from: {valid_formats}")

    # Check scheduling permission
    if data.is_scheduled and data.cron_expression:
        sub_result = await db.execute(
            select(Subscription).where(Subscription.user_id == current_user.id)
        )
        sub = sub_result.scalar_one_or_none()
        from config.settings import PLANS
        plan_config = PLANS.get(sub.plan.value if sub else "free", {})
        if not plan_config.get("scheduling", False):
            raise HTTPException(
                status_code=402,
                detail="Scheduling requires Pro or Business plan"
            )

    # Map engine string to enum
    engine_map = {
        "auto": ScrapingEngine.AUTO,
        "playwright": ScrapingEngine.PLAYWRIGHT,
        "beautifulsoup": ScrapingEngine.BEAUTIFULSOUP,
        "selenium": ScrapingEngine.SELENIUM,
    }

    format_map = {
        "json": ExportFormat.JSON,
        "csv": ExportFormat.CSV,
        "xlsx": ExportFormat.XLSX,
        "xml": ExportFormat.XML,
    }

    job = ScrapingJob(
        user_id=current_user.id,
        name=data.name,
        description=data.description,
        target_url=data.target_url,
        engine=engine_map.get(data.engine, ScrapingEngine.AUTO),
        selectors=data.selectors,
        headers=data.headers,
        cookies=data.cookies,
        proxy_config=data.proxy_config,
        pagination_config=data.pagination_config,
        export_format=format_map.get(data.export_format, ExportFormat.JSON),
        is_scheduled=data.is_scheduled,
        cron_expression=data.cron_expression,
        status=JobStatus.PENDING,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return {
        "id": job.id,
        "name": job.name,
        "status": job.status.value,
        "created_at": job.created_at,
        "message": "Job created. Use POST /jobs/{id}/run to execute."
    }


# ──────────────────────────────────────────
# LIST JOBS
# ──────────────────────────────────────────

@router.get("/")
async def list_jobs(
    page: int = 1,
    limit: int = 20,
    status_filter: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all scraping jobs for the current user."""

    query = select(ScrapingJob).where(ScrapingJob.user_id == current_user.id)

    if status_filter:
        try:
            query = query.where(ScrapingJob.status == JobStatus(status_filter))
        except ValueError:
            pass

    query = query.order_by(desc(ScrapingJob.created_at))

    # Count total
    count_result = await db.execute(
        select(func.count()).select_from(ScrapingJob).where(ScrapingJob.user_id == current_user.id)
    )
    total = count_result.scalar()

    # Paginate
    offset = (page - 1) * limit
    result = await db.execute(query.offset(offset).limit(limit))
    jobs = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
        "jobs": [
            {
                "id": j.id,
                "name": j.name,
                "target_url": j.target_url,
                "status": j.status.value,
                "engine": j.engine.value,
                "records_scraped": j.records_scraped,
                "duration_seconds": j.duration_seconds,
                "is_scheduled": j.is_scheduled,
                "cron_expression": j.cron_expression,
                "last_run_at": j.last_run_at,
                "next_run_at": j.next_run_at,
                "created_at": j.created_at,
                "has_results": j.records_scraped > 0,
            }
            for j in jobs
        ]
    }


# ──────────────────────────────────────────
# GET SINGLE JOB
# ──────────────────────────────────────────

@router.get("/{job_id}")
async def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed info about a specific job."""

    result = await db.execute(
        select(ScrapingJob).where(
            ScrapingJob.id == job_id,
            ScrapingJob.user_id == current_user.id  # TENANT ISOLATION
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get recent logs
    logs_result = await db.execute(
        select(JobLog)
        .where(JobLog.job_id == job_id)
        .order_by(desc(JobLog.created_at))
        .limit(50)
    )
    logs = logs_result.scalars().all()

    return {
        "id": job.id,
        "name": job.name,
        "description": job.description,
        "target_url": job.target_url,
        "engine": job.engine.value,
        "selectors": job.selectors,
        "export_format": job.export_format.value,
        "status": job.status.value,
        "records_scraped": job.records_scraped,
        "pages_scraped": job.pages_scraped,
        "duration_seconds": job.duration_seconds,
        "error_message": job.error_message,
        "is_scheduled": job.is_scheduled,
        "cron_expression": job.cron_expression,
        "last_run_at": job.last_run_at,
        "next_run_at": job.next_run_at,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "has_download": bool(job.result_file_path),
        "logs": [
            {
                "level": l.level,
                "message": l.message,
                "created_at": l.created_at,
            }
            for l in logs
        ]
    }


# ──────────────────────────────────────────
# RUN JOB
# ──────────────────────────────────────────

@router.post("/{job_id}/run")
async def run_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db),
):
    """Queue a scraping job for execution."""

    result = await db.execute(
        select(ScrapingJob).where(
            ScrapingJob.id == job_id,
            ScrapingJob.user_id == current_user.id
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == JobStatus.RUNNING:
        raise HTTPException(status_code=409, detail="Job is already running")

    # Queue via Celery if available, else run in background
    try:
        from backend.scheduler.tasks import run_scraping_job as celery_task
        task = celery_task.delay(job_id)
        job.status = JobStatus.QUEUED
        job.celery_task_id = task.id
        await db.commit()
        return {
            "job_id": job_id,
            "celery_task_id": task.id,
            "status": "queued",
            "message": "Job queued for execution via Celery"
        }
    except Exception:
        # Celery not available — run in background thread
        background_tasks.add_task(_run_job_background, job_id)
        job.status = JobStatus.QUEUED
        await db.commit()
        return {
            "job_id": job_id,
            "status": "queued",
            "message": "Job queued for execution (background mode)"
        }


async def _run_job_background(job_id: str):
    """Run job in FastAPI background task (no Celery)."""
    from backend.scheduler.tasks import _execute_scraping_job
    try:
        await _execute_scraping_job(job_id, "background")
    except Exception as e:
        logger_local = __import__("loguru").logger
        logger_local.error(f"Background job {job_id} failed: {e}")


# ──────────────────────────────────────────
# UPDATE JOB
# ──────────────────────────────────────────

@router.put("/{job_id}")
async def update_job(
    job_id: str,
    data: UpdateJobRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a scraping job configuration."""

    result = await db.execute(
        select(ScrapingJob).where(
            ScrapingJob.id == job_id,
            ScrapingJob.user_id == current_user.id
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == JobStatus.RUNNING:
        raise HTTPException(status_code=409, detail="Cannot update a running job")

    if data.name is not None:
        job.name = data.name
    if data.description is not None:
        job.description = data.description
    if data.selectors is not None:
        job.selectors = data.selectors
    if data.is_scheduled is not None:
        job.is_scheduled = data.is_scheduled
    if data.cron_expression is not None:
        job.cron_expression = data.cron_expression

    await db.commit()
    return {"message": "Job updated successfully"}


# ──────────────────────────────────────────
# DELETE JOB
# ──────────────────────────────────────────

@router.delete("/{job_id}")
async def delete_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a scraping job and its data."""

    result = await db.execute(
        select(ScrapingJob).where(
            ScrapingJob.id == job_id,
            ScrapingJob.user_id == current_user.id
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    await db.delete(job)
    await db.commit()
    return {"message": "Job deleted successfully"}


# ──────────────────────────────────────────
# GET RESULTS
# ──────────────────────────────────────────

@router.get("/{job_id}/results")
async def get_results(
    job_id: str,
    page: int = 1,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get scraped results for a job."""

    # Verify ownership
    job_result = await db.execute(
        select(ScrapingJob).where(
            ScrapingJob.id == job_id,
            ScrapingJob.user_id == current_user.id
        )
    )
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    offset = (page - 1) * limit
    result = await db.execute(
        select(ScrapingResult)
        .where(ScrapingResult.job_id == job_id)
        .offset(offset)
        .limit(limit)
    )
    results = result.scalars().all()

    count_result = await db.execute(
        select(func.count()).select_from(ScrapingResult).where(ScrapingResult.job_id == job_id)
    )
    total = count_result.scalar()

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "results": [{"id": r.id, "data": r.data, "source_url": r.source_url, "created_at": r.created_at} for r in results]
    }


# ──────────────────────────────────────────
# DOWNLOAD EXPORT
# ──────────────────────────────────────────

@router.get("/{job_id}/download")
async def download_results(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download scraped results as file."""

    result = await db.execute(
        select(ScrapingJob).where(
            ScrapingJob.id == job_id,
            ScrapingJob.user_id == current_user.id
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.result_file_path or not os.path.exists(job.result_file_path):
        raise HTTPException(status_code=404, detail="Result file not found. Run the job first.")

    filename = os.path.basename(job.result_file_path)
    return FileResponse(
        path=job.result_file_path,
        filename=filename,
        media_type="application/octet-stream"
    )


# ──────────────────────────────────────────
# CANCEL JOB
# ──────────────────────────────────────────

@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a running or queued job."""

    result = await db.execute(
        select(ScrapingJob).where(
            ScrapingJob.id == job_id,
            ScrapingJob.user_id == current_user.id
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in [JobStatus.RUNNING, JobStatus.QUEUED, JobStatus.PENDING]:
        raise HTTPException(status_code=409, detail=f"Job is {job.status.value}, cannot cancel")

    # Revoke Celery task if possible
    if job.celery_task_id:
        try:
            from backend.scheduler.tasks import celery_app
            celery_app.control.revoke(job.celery_task_id, terminate=True)
        except Exception:
            pass

    job.status = JobStatus.CANCELLED
    await db.commit()
    return {"message": "Job cancelled"}
