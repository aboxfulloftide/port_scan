# Task 13: Wake-on-LAN API

## Status: COMPLETE (partial) ✅

**Completed:** 2026-02-22
**Files created:** `api/wol/__init__.py`, `api/wol/router.py`
**Deviations from plan:**
- Located at `api/wol/` not `wol/` (matches project layout)
- No APScheduler WoL scheduler implemented — manual send and log only
- `POST /api/wol/send` and `GET /api/wol/log` endpoints working
- WoL schedule CRUD (`wol_schedules` table) not yet implemented



**Depends on:** Task 04, Task 06, Task 12  
**Complexity:** Medium  
**Description:** Implement manual WoL trigger, WoL scheduling, and WoL log endpoints.

---

## Files to Create

- `wol/models.py`
- `wol/router.py`
- `wol/scheduler.py`

---

## `wol/models.py`

```python
from pydantic import BaseModel, validator
from typing import Optional
from datetime import datetime
from croniter import croniter

class WolSendRequest(BaseModel):
    host_id: int
    broadcast: Optional[str] = "255.255.255.255"
    port: Optional[int] = 9

class WolScheduleCreate(BaseModel):
    host_id: int
    cron_expr: str
    broadcast: Optional[str] = "255.255.255.255"
    port: Optional[int] = 9
    enabled: bool = True

    @validator("cron_expr")
    def valid_cron(cls, v):
        if not croniter.is_valid(v):
            raise ValueError("Invalid cron expression")
        return v

class WolScheduleOut(BaseModel):
    id: int
    host_id: int
    hostname: Optional[str]
    cron_expr: str
    broadcast: str
    port: int
    enabled: bool
    created_at: datetime

    class Config:
        orm_mode = True

class WolLogOut(BaseModel):
    id: int
    host_id: int
    hostname: Optional[str]
    triggered_by: str   # "manual" | "schedule"
    mac_used: str
    success: bool
    error_msg: Optional[str]
    created_at: datetime

    class Config:
        orm_mode = True
```

---

## `wol/router.py`

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from shared.db import get_db
from shared.models import Host, WolSchedule, WolLog
from auth.dependencies import require_operator, require_admin
from .models import WolSendRequest, WolScheduleCreate, WolScheduleOut, WolLogOut
from .scheduler import add_wol_job, remove_wol_job
import wakeonlan, logging

router = APIRouter(prefix="/api/wol", tags=["wol"])
logger = logging.getLogger("wol")

# ── Manual Send ──────────────────────────────────────────────────────────────

@router.post("/send", status_code=200)
async def send_wol(
    body: WolSendRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_operator)
):
    host = await db.get(Host, body.host_id)
    if not host:
        raise HTTPException(404, "Host not found")
    if not host.mac_address:
        raise HTTPException(400, "Host has no MAC address stored")
    if not host.wol_enabled:
        raise HTTPException(400, "WoL is not enabled for this host")

    success = True
    error_msg = None
    try:
        wakeonlan.send_magic_packet(host.mac_address, ip_address=body.broadcast, port=body.port)
        logger.info(f"WoL sent to {host.hostname} ({host.mac_address})")
    except Exception as e:
        success = False
        error_msg = str(e)
        logger.error(f"WoL failed for {host.hostname}: {e}")

    log = WolLog(
        host_id=host.id,
        triggered_by="manual",
        mac_used=host.mac_address,
        success=success,
        error_msg=error_msg,
    )
    db.add(log)
    await db.commit()

    if not success:
        raise HTTPException(500, f"WoL packet failed: {error_msg}")
    return {"status": "sent", "mac": host.mac_address}

# ── WoL Schedules ─────────────────────────────────────────────────────────────

@router.get("/schedules", response_model=list[WolScheduleOut])
async def list_wol_schedules(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_operator)
):
    result = await db.execute(select(WolSchedule))
    return result.scalars().all()

@router.post("/schedules", response_model=WolScheduleOut, status_code=201)
async def create_wol_schedule(
    body: WolScheduleCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_operator)
):
    host = await db.get(Host, body.host_id)
    if not host or not host.mac_address:
        raise HTTPException(400, "Host not found or has no MAC address")
    sched = WolSchedule(**body.dict())
    db.add(sched)
    await db.commit()
    await db.refresh(sched)
    if sched.enabled:
        add_wol_job(sched, host.mac_address)
    return sched

@router.delete("/schedules/{schedule_id}", status_code=204)
async def delete_wol_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin)
):
    sched = await db.get(WolSchedule, schedule_id)
    if not sched:
        raise HTTPException(404, "WoL schedule not found")
    remove_wol_job(sched.id)
    await db.delete(sched)
    await db.commit()

@router.post("/schedules/{schedule_id}/toggle", response_model=WolScheduleOut)
async def toggle_wol_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_operator)
):
    sched = await db.get(WolSchedule, schedule_id)
    if not sched:
        raise HTTPException(404, "WoL schedule not found")
    host = await db.get(Host, sched.host_id)
    sched.enabled = not sched.enabled
    await db.commit()
    await db.refresh(sched)
    if sched.enabled:
        add_wol_job(sched, host.mac_address)
    else:
        remove_wol_job(sched.id)
    return sched

# ── WoL Log ───────────────────────────────────────────────────────────────────

@router.get("/log", response_model=list[WolLogOut])
async def get_wol_log(
    host_id: int = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_operator)
):
    q = select(WolLog).order_by(desc(WolLog.created_at)).limit(limit)
    if host_id:
        q = q.where(WolLog.host_id == host_id)
    result = await db.execute(q)
    return result.scalars().all()
```

---

## `wol/scheduler.py`

```python
from apscheduler.triggers.cron import CronTrigger
from schedules.scheduler import scheduler   # reuse the same APScheduler instance
from shared.db import AsyncSessionLocal
from shared.models import WolSchedule, Host, WolLog
import wakeonlan, logging

logger = logging.getLogger("wol.scheduler")

async def _fire_wol(schedule_id: int):
    async with AsyncSessionLocal() as db:
        sched = await db.get(WolSchedule, schedule_id)
        if not sched or not sched.enabled:
            return
        host = await db.get(Host, sched.host_id)
        if not host or not host.mac_address:
            return
        success = True
        error_msg = None
        try:
            wakeonlan.send_magic_packet(
                host.mac_address,
                ip_address=sched.broadcast,
                port=sched.port
            )
        except Exception as e:
            success = False
            error_msg = str(e)
            logger.error(f"Scheduled WoL failed for host {host.id}: {e}")

        log = WolLog(
            host_id=host.id,
            triggered_by="schedule",
            mac_used=host.mac_address,
            success=success,
            error_msg=error_msg,
        )
        db.add(log)
        await db.commit()

def add_wol_job(sched: WolSchedule, mac: str):
    parts = sched.cron_expr.split()
    trigger = CronTrigger(
        minute=parts[0], hour=parts[1],
        day=parts[2], month=parts[3], day_of_week=parts[4],
        timezone="UTC"
    )
    scheduler.add_job(
        _fire_wol,
        trigger=trigger,
        args=[sched.id],
        id=f"wol_sched_{sched.id}",
        replace_existing=True
    )

def remove_wol_job(schedule_id: int):
    job_id = f"wol_sched_{schedule_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

def load_all_wol_schedules(schedules: list, hosts: dict):
    """Called at startup. hosts = {host_id: mac_address}"""
    for sched in schedules:
        if sched.enabled and sched.host_id in hosts:
            add_wol_job(sched, hosts[sched.host_id])
```

---

## Startup Integration

Add to `api/main.py` lifespan startup:
```python
from wol.scheduler import load_all_wol_schedules
from shared.models import WolSchedule, Host
from sqlalchemy import select

async with AsyncSessionLocal() as db:
    wol_scheds = (await db.execute(select(WolSchedule).where(WolSchedule.enabled == True))).scalars().all()
    hosts_result = (await db.execute(select(Host.id, Host.mac_address))).all()
    host_mac_map = {h.id: h.mac_address for h in hosts_result if h.mac_address}
    load_all_wol_schedules(wol_scheds, host_mac_map)
```
