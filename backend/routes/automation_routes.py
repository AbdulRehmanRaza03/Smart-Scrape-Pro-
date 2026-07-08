from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from typing import List, Optional
from datetime import datetime, timezone

from backend.models.database import get_db
from backend.models.models import (
    User, JobTemplate, Schedule, ScheduleRun, JobStatus,
    ScrapingEngine, ExportFormat, ScheduleInterval
)
from backend.auth.dependencies import get_current_active_user
from pydantic import BaseModel

router = APIRouter(prefix="/api/automation", tags=["Automation"])

# Schemas
class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    target_url: str
    engine: ScrapingEngine = ScrapingEngine.AUTO
    selectors: dict = {}
    headers: dict = {}
    cookies: dict = {}
    proxy_config: dict = {}
    pagination_config: dict = {}
    export_format: ExportFormat = ExportFormat.JSON

class ScheduleCreate(BaseModel):
    name: str
    template_id: str
    is_active: bool = True
    interval: ScheduleInterval
    cron_expression: Optional[str] = None
    retry_enabled: bool = False
    max_retries: int = 3
    retry_backoff_factor: float = 2.0


@router.post("/templates")
async def create_template(
    data: TemplateCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    template = JobTemplate(
        user_id=current_user.id,
        **data.dict()
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template

@router.get("/templates")
async def get_templates(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(JobTemplate).where(JobTemplate.user_id == current_user.id))
    return result.scalars().all()

@router.post("/schedules")
async def create_schedule(
    data: ScheduleCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify template exists
    tpl_res = await db.execute(select(JobTemplate).where(JobTemplate.id == data.template_id, JobTemplate.user_id == current_user.id))
    if not tpl_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Template not found")
        
    schedule = Schedule(
        user_id=current_user.id,
        **data.dict()
    )
    
    # Calculate initial next_run_at based on interval here ideally, for now set to now if active
    if schedule.is_active:
        schedule.next_run_at = datetime.now(timezone.utc)
        
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return schedule

@router.get("/schedules")
async def get_schedules(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Schedule).where(Schedule.user_id == current_user.id).order_by(desc(Schedule.created_at)))
    return result.scalars().all()

@router.get("/dashboard/analytics")
async def get_analytics(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    schedules = (await db.execute(select(Schedule).where(Schedule.user_id == current_user.id))).scalars().all()
    schedule_ids = [s.id for s in schedules]
    
    if not schedule_ids:
        return {"total_jobs": 0, "success_rate": 0, "failure_rate": 0, "avg_time": 0}
        
    runs = (await db.execute(select(ScheduleRun).where(ScheduleRun.schedule_id.in_(schedule_ids)))).scalars().all()
    
    total = len(runs)
    success = sum(1 for r in runs if r.status == "completed")
    failed = sum(1 for r in runs if r.status == "failed")
    
    durations = [r.duration_seconds for r in runs if r.duration_seconds is not None]
    avg_time = sum(durations) / len(durations) if durations else 0
    
    return {
        "total_jobs": total,
        "success_rate": (success / total * 100) if total else 0,
        "failure_rate": (failed / total * 100) if total else 0,
        "avg_time": round(avg_time, 2)
    }
