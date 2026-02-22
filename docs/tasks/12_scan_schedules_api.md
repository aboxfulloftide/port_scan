# Task 12 — Scan Schedules CRUD API

## Status: COMPLETE ✅

**Completed:** 2026-02-22
**Files created:** `api/schedules/__init__.py`, `api/schedules/models.py`, `api/schedules/router.py`



**Depends on:** Task 06  
**Complexity:** Medium  
**Run as:** netscan user

---

## Objective
Implement `/api/schedules` endpoints for managing automated scan schedules. Includes cron expression validation and next-run-time calculation.

---

## Files to Create

### `/home/matheau/code/port_scan/api/schedules/models.py`
```python
from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime
from croniter import croniter


class ScheduleCreate(BaseModel):
    name: str
    profile_id: int
    subnet_ids: List[int]
    cron_expression: str

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v):
        if not croniter.is_valid(v):
            raise ValueError(f"Invalid cron expression: '{v}'")
        return v

    @field_validator("subnet_ids")
    @classmethod
    def validate_subnets(cls, v):
        if not v:
            raise ValueError("At least one subnet_id is required")
        return v


class ScheduleUpdate(BaseModel):
    name: Optional[str] = None
    profile_id: Optional[int] = None
    subnet_ids: Optional[List[int]] = None
    cron_expression: Optional[str] = None
    is_active: Optional[bool] = None


class ScheduleOut(BaseModel):
    id: int
    name: str
    profile_id: int
    profile_name: Optional[str] = None
    subnet_ids: List[int]
    cron_expression: str
    is_active: bool
    created_at: datetime
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]

    class Config:
        from_attributes = True
```

---

### `/home/matheau/code/port_scan/api/schedules/router.py`
```python
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from croniter import croniter

from shared.db import get_db
from shared.models import Schedule, ScanProfile, Subnet, User
from auth.dependencies import get_current_user, require_operator, require_admin
from schedules.models import ScheduleCreate, ScheduleUpdate, ScheduleOut

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
    # Validate profile
    if not await db.get(ScanProfile, body.profile_id):
        raise HTTPException(status_code=404, detail="Scan profile not found")

    # Validate subnets
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
```

---

## Additional Dependency
Add `croniter` to `requirements.txt`:
```
croniter==1.4.1
```

---

## Acceptance Criteria
- [ ] `GET /api/schedules` returns all schedules with `profile_name` enriched
- [ ] `POST /api/schedules` validates cron expression (e.g. `not-a-cron` returns `422`)
- [ ] `POST /api/schedules` computes and stores `next_run_at`
- [ ] `POST /api/schedules` returns `404` for invalid profile or subnet IDs
- [ ] `PATCH /api/schedules/{id}` recalculates `next_run_at` when cron changes
- [ ] `PATCH /api/schedules/{id}` can toggle `is_active` without changing other fields
- [ ] `DELETE /api/schedules/{id}` requires admin role
- [ ] Valid cron `"0 2 * * *"` is accepted
- [ ] Invalid cron `"99 99 99 99 99"` returns `422`
