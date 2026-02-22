from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from croniter import croniter

from shared.db import get_db
from shared.models import Schedule, ScanProfile, Subnet, User
from api.auth.dependencies import get_current_user, require_operator, require_admin
from api.schedules.models import ScheduleCreate, ScheduleUpdate, ScheduleOut

router = APIRouter(prefix="/schedules", tags=["schedules"])


def compute_next_run(cron_expr: str) -> datetime:
    return croniter(cron_expr, datetime.utcnow()).get_next(datetime)


async def enrich_schedule(schedule: Schedule, db: AsyncSession) -> ScheduleOut:
    out = ScheduleOut.model_validate(schedule)
    out.subnet_ids = schedule.subnet_ids if isinstance(schedule.subnet_ids, list) else []
    profile = await db.get(ScanProfile, schedule.profile_id)
    out.profile_name = profile.name if profile else None
    return out


@router.get("", response_model=list[ScheduleOut])
async def list_schedules(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    result = await db.execute(select(Schedule).order_by(Schedule.name))
    schedules = result.scalars().all()
    return [await enrich_schedule(s, db) for s in schedules]


@router.post("", response_model=ScheduleOut, status_code=201)
async def create_schedule(
    body: ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator)
):
    if not await db.get(ScanProfile, body.profile_id):
        raise HTTPException(status_code=404, detail="Scan profile not found")

    for sid in body.subnet_ids:
        if not await db.get(Subnet, sid):
            raise HTTPException(status_code=404, detail=f"Subnet {sid} not found")

    next_run = compute_next_run(body.cron_expression)
    schedule = Schedule(
        name=body.name,
        profile_id=body.profile_id,
        subnet_ids=body.subnet_ids,
        cron_expression=body.cron_expression,
        next_run_at=next_run,
        created_by=current_user.id
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return await enrich_schedule(schedule, db)


@router.patch("/{schedule_id}", response_model=ScheduleOut)
async def update_schedule(
    schedule_id: int,
    body: ScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator)
):
    result = await db.execute(select(Schedule).where(Schedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    updates = body.model_dump(exclude_none=True)

    if "cron_expression" in updates:
        updates["next_run_at"] = compute_next_run(updates["cron_expression"])

    if "profile_id" in updates:
        if not await db.get(ScanProfile, updates["profile_id"]):
            raise HTTPException(status_code=404, detail="Scan profile not found")

    if updates:
        await db.execute(update(Schedule).where(Schedule.id == schedule_id).values(**updates))
        await db.commit()
        await db.refresh(schedule)

    return await enrich_schedule(schedule, db)


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    result = await db.execute(select(Schedule).where(Schedule.id == schedule_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Schedule not found")

    await db.execute(delete(Schedule).where(Schedule.id == schedule_id))
    await db.commit()
