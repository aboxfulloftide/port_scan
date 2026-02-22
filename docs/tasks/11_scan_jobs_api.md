# Task 11 — Scan Jobs API

## Status: COMPLETE ✅

**Completed:** 2026-02-22
**Files created:** `api/scans/__init__.py`, `api/scans/models.py`, `api/scans/router.py`
**Deviations/fixes:**
- `ScanJobDetailOut.triggered_by` typed as `Optional[Union[str, int]]` (int FK from ORM, enriched to username string) — was `Optional[str]` which caused 500
- Worker enqueuing added to `trigger_scan`: `await job_queue.put(job.id)`
- WebSocket path is `/api/scans/ws/{job_id}` (polls DB every 2s, no pub/sub in this endpoint)



**Depends on:** Task 06  
**Complexity:** Medium  
**Run as:** netscan user

---

## Objective
Implement `/api/scans` endpoints: list scan history, trigger a manual scan, get live job status, cancel a job. Also implement the WebSocket endpoint for live scan progress streaming.

---

## Files to Create

### `/home/matheau/code/port_scan/api/scans/models.py`
```python
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ScanTriggerRequest(BaseModel):
    profile_id: int
    subnet_ids: List[int]


class ScanJobSummaryOut(BaseModel):
    id: int
    profile_id: int
    profile_name: Optional[str] = None
    status: str
    hosts_discovered: Optional[int]
    hosts_up: Optional[int]
    new_hosts_found: Optional[int]
    new_ports_found: Optional[int]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    triggered_by: Optional[str] = None   # username or "scheduler"
    created_at: datetime

    class Config:
        from_attributes = True


class ScanJobDetailOut(ScanJobSummaryOut):
    subnet_ids: List[int]
    progress_percent: Optional[int] = None
    current_tier: Optional[str] = None
    error_message: Optional[str] = None


class PaginatedScans(BaseModel):
    total: int
    scans: List[ScanJobSummaryOut]
```

---

### `/home/matheau/code/port_scan/api/scans/router.py`
```python
import json
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from typing import Optional

from shared.db import get_db, AsyncSessionLocal
from shared.models import ScanJob, ScanProfile, Subnet, User
from auth.dependencies import get_current_user, require_operator
from auth.utils import decode_access_token
from scans.models import ScanTriggerRequest, ScanJobSummaryOut, ScanJobDetailOut, PaginatedScans

router = APIRouter(prefix="/scans", tags=["scans"])

# In-memory progress store: {job_id: {progress_percent, current_tier, ...}}
# Worker process updates this via DB; API reads from DB for WS
PROGRESS_POLL_INTERVAL = 2  # seconds


@router.get("", response_model=PaginatedScans)
async def list_scans(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100)
):
    q = select(ScanJob)
    if status:
        q = q.where(ScanJob.status == status)
    q = q.order_by(ScanJob.created_at.desc())

    total = (await db.execute(select(func.count(ScanJob.id)))).scalar()
    q = q.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(q)
    jobs = result.scalars().all()

    # Enrich with profile name and triggered_by username
    summaries = []
    for job in jobs:
        s = ScanJobSummaryOut.model_validate(job)
        profile = await db.get(ScanProfile, job.profile_id)
        s.profile_name = profile.name if profile else None
        if job.triggered_by:
            user = await db.get(User, job.triggered_by)
            s.triggered_by = user.username if user else str(job.triggered_by)
        else:
            s.triggered_by = "scheduler"
        summaries.append(s)

    return PaginatedScans(total=total, scans=summaries)


@router.post("", status_code=202)
async def trigger_scan(
    body: ScanTriggerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator)
):
    # Validate profile exists
    profile = await db.get(ScanProfile, body.profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Scan profile not found")

    # Validate all subnet IDs exist
    for sid in body.subnet_ids:
        subnet = await db.get(Subnet, sid)
        if not subnet:
            raise HTTPException(status_code=404, detail=f"Subnet {sid} not found")

    # Check for already running scan
    running = await db.execute(
        select(ScanJob).where(ScanJob.status.in_(["queued", "running"]))
    )
    if running.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A scan is already queued or running")

    job = ScanJob(
        profile_id=body.profile_id,
        subnet_ids=body.subnet_ids,
        status="queued",
        triggered_by=current_user.id
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return {"job_id": job.id, "status": "queued", "message": "Scan job queued successfully"}


@router.get("/{job_id}", response_model=ScanJobDetailOut)
async def get_scan(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    job = await db.get(ScanJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scan job not found")

    detail = ScanJobDetailOut.model_validate(job)
    detail.subnet_ids = job.subnet_ids if isinstance(job.subnet_ids, list) else []
    profile = await db.get(ScanProfile, job.profile_id)
    detail.profile_name = profile.name if profile else None
    return detail


@router.post("/{job_id}/cancel")
async def cancel_scan(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator)
):
    job = await db.get(ScanJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scan job not found")
    if job.status not in ("queued", "running"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel a job with status '{job.status}'")

    await db.execute(
        update(ScanJob).where(ScanJob.id == job_id).values(status="cancelled")
    )
    await db.commit()
    return {"status": "cancelled"}


@router.websocket("/ws/{job_id}")
async def scan_progress_ws(websocket: WebSocket, job_id: int):
    """
    WebSocket endpoint for live scan progress.
    Auth via access_token cookie.
    """
    token = websocket.cookies.get("access_token")
    if not token or not decode_access_token(token):
        await websocket.close(code=4001)
        return

    await websocket.accept()
    try:
        while True:
            async with AsyncSessionLocal() as db:
                job = await db.get(ScanJob, job_id)
                if not job:
                    await websocket.send_json({"type": "error", "message": "Job not found"})
                    break

                if job.status in ("completed", "failed", "cancelled"):
                    await websocket.send_json({
                        "type": "completed" if job.status == "completed" else job.status,
                        "job_id": job_id,
                        "summary": {
                            "hosts_discovered": job.hosts_discovered,
                            "hosts_up": job.hosts_up,
                            "new_hosts_found": job.new_hosts_found,
                            "new_ports_found": job.new_ports_found,
                            "status": job.status
                        }
                    })
                    break

                await websocket.send_json({
                    "type": "progress",
                    "job_id": job_id,
                    "status": job.status,
                    "hosts_up": job.hosts_up or 0,
                    "new_hosts_found": job.new_hosts_found or 0,
                    "new_ports_found": job.new_ports_found or 0
                })

            await asyncio.sleep(PROGRESS_POLL_INTERVAL)

    except WebSocketDisconnect:
        pass
```

---

## Acceptance Criteria
- [ ] `GET /api/scans` returns paginated scan history with profile name and triggered_by
- [ ] `POST /api/scans` returns `202` and creates a `queued` job
- [ ] `POST /api/scans` returns `409` if a scan is already running or queued
- [ ] `POST /api/scans` returns `404` for invalid profile or subnet IDs
- [ ] `GET /api/scans/{id}` returns full job detail
- [ ] `POST /api/scans/{id}/cancel` sets status to `cancelled`
- [ ] `POST /api/scans/{id}/cancel` returns `400` for already completed jobs
- [ ] WebSocket `/api/scans/ws/{id}` rejects unauthenticated connections with code `4001`
- [ ] WebSocket sends progress updates every 2 seconds until job completes
