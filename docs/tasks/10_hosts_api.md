# Task 10 — Hosts API

## Status: COMPLETE ✅

**Completed:** 2026-02-22
**Files created:** `api/hosts/__init__.py`, `api/hosts/models.py`, `api/hosts/router.py`



**Depends on:** Task 06  
**Complexity:** Medium  
**Run as:** netscan user

---

## Objective
Implement the `/api/hosts` endpoints: paginated host list with filters, full host detail with ports/banners/screenshots/history, patch for user-editable fields, acknowledge new flag, and screenshot serving.

---

## Files to Create

### `/home/matheau/code/port_scan/api/hosts/models.py`
```python
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class PortBannerOut(BaseModel):
    id: int
    banner_text: Optional[str]
    captured_at: datetime

    class Config:
        from_attributes = True


class PortScreenshotOut(BaseModel):
    id: int
    url_captured: Optional[str]
    captured_at: datetime
    screenshot_url: Optional[str] = None  # Populated by router

    class Config:
        from_attributes = True


class HostPortOut(BaseModel):
    id: int
    port: int
    protocol: str
    state: str
    service_name: Optional[str]
    service_ver: Optional[str]
    is_new: bool
    first_seen: datetime
    last_seen: Optional[datetime]
    banner: Optional[str] = None          # Latest banner text
    screenshot_url: Optional[str] = None  # URL to latest screenshot

    class Config:
        from_attributes = True


class HostHistoryOut(BaseModel):
    id: int
    event_type: str
    old_value: Optional[str]
    new_value: Optional[str]
    recorded_at: datetime

    class Config:
        from_attributes = True


class HostSummaryOut(BaseModel):
    id: int
    hostname: Optional[str]
    current_ip: str
    current_mac: Optional[str]
    vendor: Optional[str]
    os_guess: Optional[str]
    is_up: bool
    is_new: bool
    wol_enabled: bool
    first_seen: datetime
    last_seen: Optional[datetime]
    open_port_count: int = 0

    class Config:
        from_attributes = True


class HostDetailOut(BaseModel):
    id: int
    hostname: Optional[str]
    current_ip: str
    current_mac: Optional[str]
    vendor: Optional[str]
    os_guess: Optional[str]
    is_up: bool
    is_new: bool
    wol_enabled: bool
    notes: Optional[str]
    first_seen: datetime
    last_seen: Optional[datetime]
    ports: List[HostPortOut] = []
    history: List[HostHistoryOut] = []

    class Config:
        from_attributes = True


class HostUpdate(BaseModel):
    notes: Optional[str] = None
    wol_enabled: Optional[bool] = None
    is_new: Optional[bool] = None


class PaginatedHosts(BaseModel):
    total: int
    page: int
    per_page: int
    hosts: List[HostSummaryOut]
```

---

### `/home/matheau/code/port_scan/api/hosts/router.py`
```python
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_, or_
from sqlalchemy.orm import selectinload
from typing import Optional
import os

from shared.db import get_db
from shared.models import Host, HostPort, HostHistory, PortBanner, PortScreenshot, User
from auth.dependencies import get_current_user
from hosts.models import (
    HostSummaryOut, HostDetailOut, HostUpdate, PaginatedHosts,
    HostPortOut, HostHistoryOut
)

router = APIRouter(prefix="/hosts", tags=["hosts"])
SCREENSHOT_DIR = os.getenv("SCREENSHOT_DIR", "/home/matheau/code/port_scan/screenshots")


@router.get("", response_model=PaginatedHosts)
async def list_hosts(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    subnet_id: Optional[int] = Query(None),
    is_up: Optional[bool] = Query(None),
    is_new: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200)
):
    filters = []
    if subnet_id is not None:
        filters.append(Host.subnet_id == subnet_id)
    if is_up is not None:
        filters.append(Host.is_up == is_up)
    if is_new is not None:
        filters.append(Host.is_new == is_new)
    if search:
        term = f"%{search}%"
        filters.append(or_(
            Host.hostname.ilike(term),
            Host.current_ip.ilike(term),
            Host.current_mac.ilike(term)
        ))

    count_q = select(func.count(Host.id))
    if filters:
        count_q = count_q.where(and_(*filters))
    total = (await db.execute(count_q)).scalar()

    q = select(Host)
    if filters:
        q = q.where(and_(*filters))
    q = q.order_by(Host.hostname.asc(), Host.current_ip.asc())
    q = q.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(q)
    hosts = result.scalars().all()

    # Get open port counts
    host_ids = [h.id for h in hosts]
    port_counts = {}
    if host_ids:
        pc_result = await db.execute(
            select(HostPort.host_id, func.count(HostPort.id))
            .where(HostPort.host_id.in_(host_ids), HostPort.state == "open")
            .group_by(HostPort.host_id)
        )
        port_counts = dict(pc_result.all())

    host_summaries = []
    for h in hosts:
        summary = HostSummaryOut.model_validate(h)
        summary.open_port_count = port_counts.get(h.id, 0)
        host_summaries.append(summary)

    return PaginatedHosts(total=total, page=page, per_page=per_page, hosts=host_summaries)


@router.get("/{host_id}", response_model=HostDetailOut)
async def get_host(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Host)
        .options(
            selectinload(Host.ports).selectinload(HostPort.banners),
            selectinload(Host.ports).selectinload(HostPort.screenshots),
            selectinload(Host.history)
        )
        .where(Host.id == host_id)
    )
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")

    detail = HostDetailOut.model_validate(host)

    # Enrich ports with latest banner and screenshot URL
    for port_model, port_out in zip(host.ports, detail.ports):
        if port_model.banners:
            latest_banner = sorted(port_model.banners, key=lambda b: b.captured_at, reverse=True)[0]
            port_out.banner = latest_banner.banner_text
        if port_model.screenshots:
            latest_ss = sorted(port_model.screenshots, key=lambda s: s.captured_at, reverse=True)[0]
            port_out.screenshot_url = f"/api/hosts/{host_id}/ports/{port_model.id}/screenshot"

    return detail


@router.patch("/{host_id}", response_model=HostDetailOut)
async def update_host(
    host_id: int,
    body: HostUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    result = await db.execute(select(Host).where(Host.id == host_id))
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")

    updates = body.model_dump(exclude_none=True)
    if updates:
        await db.execute(update(Host).where(Host.id == host_id).values(**updates))
        await db.commit()

    return await get_host(host_id, db, _)


@router.post("/{host_id}/acknowledge")
async def acknowledge_host(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    result = await db.execute(select(Host).where(Host.id == host_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Host not found")

    await db.execute(update(Host).where(Host.id == host_id).values(is_new=False))
    await db.execute(
        update(HostPort).where(HostPort.host_id == host_id).values(is_new=False)
    )
    await db.commit()
    return {"acknowledged": True}


@router.get("/{host_id}/ports/{port_id}/screenshot")
async def get_screenshot(
    host_id: int,
    port_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    result = await db.execute(
        select(PortScreenshot)
        .where(PortScreenshot.host_port_id == port_id)
        .order_by(PortScreenshot.captured_at.desc())
        .limit(1)
    )
    screenshot = result.scalar_one_or_none()
    if not screenshot:
        raise HTTPException(status_code=404, detail="No screenshot available")

    full_path = os.path.join(SCREENSHOT_DIR, screenshot.file_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Screenshot file not found on disk")

    return FileResponse(full_path, media_type="image/png")
```

---

## Acceptance Criteria
- [ ] `GET /api/hosts` returns paginated results with `total`, `page`, `per_page`
- [ ] Filtering by `subnet_id`, `is_up`, `is_new`, and `search` all work correctly
- [ ] `GET /api/hosts/{id}` returns full detail including ports, banners, history
- [ ] `GET /api/hosts/{id}` includes `screenshot_url` for ports that have screenshots
- [ ] `PATCH /api/hosts/{id}` only updates `notes`, `wol_enabled`, `is_new`
- [ ] `POST /api/hosts/{id}/acknowledge` clears `is_new` on host and all its ports
- [ ] `GET /api/hosts/{id}/ports/{port_id}/screenshot` returns PNG file
- [ ] `GET /api/hosts/{id}/ports/{port_id}/screenshot` returns `404` if no screenshot
