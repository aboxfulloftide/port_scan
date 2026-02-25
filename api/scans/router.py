import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from typing import Optional

from shared.db import get_db, AsyncSessionLocal
from shared.models import ScanJob, ScanProfile, Subnet, User
from api.auth.dependencies import get_current_user, require_operator
from api.auth.utils import decode_access_token
from api.scans.models import ScanTriggerRequest, ScanJobSummaryOut, ScanJobDetailOut, PaginatedScans

router = APIRouter(prefix="/scans", tags=["scans"])

PROGRESS_POLL_INTERVAL = 2


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
    profile = await db.get(ScanProfile, body.profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Scan profile not found")

    for sid in body.subnet_ids:
        subnet = await db.get(Subnet, sid)
        if not subnet:
            raise HTTPException(status_code=404, detail=f"Subnet {sid} not found")

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

    # Enqueue for the worker
    from worker.queue import job_queue
    await job_queue.put(job.id)

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
    if job.triggered_by:
        user = await db.get(User, job.triggered_by)
        detail.triggered_by = user.username if user else str(job.triggered_by)
    else:
        detail.triggered_by = "scheduler"
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

    # Kill active nmap subprocesses first so threads don't linger
    from worker.pipeline import kill_job_scanners
    kill_job_scanners(job_id)

    # Cancel the asyncio task if it's running
    from worker.main import running_jobs
    task = running_jobs.get(job_id)
    if task and not task.done():
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=3.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    # If job was still queued (not yet picked up), update DB directly
    await db.refresh(job)
    if job.status != "cancelled":
        await db.execute(
            update(ScanJob).where(ScanJob.id == job_id).values(status="cancelled")
        )
        await db.commit()

    return {"status": "cancelled"}


@router.websocket("/ws/{job_id}")
async def scan_progress_ws(websocket: WebSocket, job_id: int):
    token = websocket.cookies.get("access_token")
    if not token or not decode_access_token(token):
        await websocket.close(code=4001)
        return

    await websocket.accept()

    from worker.progress import subscribe, unsubscribe
    q = subscribe(job_id)
    try:
        # Send current job state immediately on connect
        async with AsyncSessionLocal() as db:
            job = await db.get(ScanJob, job_id)
            if not job:
                await websocket.send_json({"type": "error", "message": "Job not found"})
                return
            # If already done, send terminal event and exit
            if job.status in ("completed", "failed", "cancelled"):
                await websocket.send_json({
                    "type": job.status,
                    "job_id": job_id,
                    "hosts_up": job.hosts_up or 0,
                    "new_hosts_found": job.new_hosts_found or 0,
                    "new_ports_found": job.new_ports_found or 0,
                    "status": job.status,
                })
                await websocket.close()
                return
            # Send initial progress snapshot
            await websocket.send_json({
                "type": "progress",
                "job_id": job_id,
                "status": job.status,
                "hosts_up": job.hosts_up or 0,
                "new_hosts_found": job.new_hosts_found or 0,
                "new_ports_found": job.new_ports_found or 0,
            })

        # Stream live events from the broadcast queue
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=PROGRESS_POLL_INTERVAL)
            except asyncio.TimeoutError:
                # Heartbeat: re-check DB to pick up stats updates
                try:
                    async with AsyncSessionLocal() as db:
                        job = await db.get(ScanJob, job_id)
                    if job:
                        await websocket.send_json({
                            "type": "progress",
                            "job_id": job_id,
                            "status": job.status,
                            "hosts_up": job.hosts_up or 0,
                            "new_hosts_found": job.new_hosts_found or 0,
                            "new_ports_found": job.new_ports_found or 0,
                        })
                except Exception:
                    pass
                continue

            await websocket.send_json(event)
            # Stop streaming once a terminal event is sent
            if event.get("type") in ("completed", "failed", "cancelled", "job_done"):
                await websocket.close()
                break

    except WebSocketDisconnect:
        pass
    finally:
        unsubscribe(job_id, q)
