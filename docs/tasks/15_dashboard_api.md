# Task 15: Dashboard API

**Depends on:** Task 04, Task 06, Task 10  
**Complexity:** Low  
**Description:** Implement the `/api/dashboard` endpoint that returns aggregated summary statistics for the UI home page.

---

## Files to Create

- `dashboard/router.py`
- `dashboard/models.py`

---

## `dashboard/models.py`

```python
from pydantic import BaseModel
from typing import List
from datetime import datetime

class SubnetSummary(BaseModel):
    id: int
    cidr: str
    label: str
    host_count: int
    up_count: int

class RecentScan(BaseModel):
    id: int
    subnet_cidr: str
    profile_name: str
    status: str
    hosts_found: int
    started_at: datetime
    finished_at: datetime | None

class DashboardStats(BaseModel):
    total_hosts: int
    hosts_up: int
    hosts_down: int
    new_hosts: int           # hosts with is_new=True
    new_ports: int           # ports with is_new=True
    total_subnets: int
    active_scans: int
    subnets: List[SubnetSummary]
    recent_scans: List[RecentScan]
    last_scan_at: datetime | None
```

---

## `dashboard/router.py`

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from shared.db import get_db
from shared.models import Host, HostPort, Subnet, ScanJob, ScanProfile
from auth.dependencies import require_operator
from .models import DashboardStats, SubnetSummary, RecentScan

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("/", response_model=DashboardStats)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_operator)
):
    # Host counts
    total_hosts = (await db.execute(select(func.count()).select_from(Host))).scalar()
    hosts_up = (await db.execute(select(func.count()).select_from(Host).where(Host.status == "up"))).scalar()
    hosts_down = total_hosts - hosts_up
    new_hosts = (await db.execute(select(func.count()).select_from(Host).where(Host.is_new == True))).scalar()
    new_ports = (await db.execute(select(func.count()).select_from(HostPort).where(HostPort.is_new == True))).scalar()

    # Subnet count
    total_subnets = (await db.execute(select(func.count()).select_from(Subnet))).scalar()

    # Active scans
    active_scans = (await db.execute(
        select(func.count()).select_from(ScanJob).where(ScanJob.status.in_(["queued", "running"]))
    )).scalar()

    # Per-subnet summary
    subnet_rows = (await db.execute(select(Subnet))).scalars().all()
    subnets = []
    for s in subnet_rows:
        hc = (await db.execute(select(func.count()).select_from(Host).where(Host.subnet_id == s.id))).scalar()
        uc = (await db.execute(
            select(func.count()).select_from(Host).where(Host.subnet_id == s.id, Host.status == "up")
        )).scalar()
        subnets.append(SubnetSummary(
            id=s.id, cidr=s.cidr, label=s.label or s.cidr,
            host_count=hc, up_count=uc
        ))

    # Recent scans (last 10)
    recent_rows = (await db.execute(
        select(ScanJob, Subnet.cidr.label("subnet_cidr"), ScanProfile.name.label("profile_name"))
        .join(Subnet, ScanJob.subnet_id == Subnet.id)
        .join(ScanProfile, ScanJob.profile_id == ScanProfile.id)
        .order_by(desc(ScanJob.started_at))
        .limit(10)
    )).all()
    recent_scans = [
        RecentScan(
            id=job.id,
            subnet_cidr=cidr,
            profile_name=pname,
            status=job.status,
            hosts_found=job.hosts_found or 0,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )
        for job, cidr, pname in recent_rows
    ]

    # Last scan time
    last_scan_at = recent_scans[0].started_at if recent_scans else None

    return DashboardStats(
        total_hosts=total_hosts,
        hosts_up=hosts_up,
        hosts_down=hosts_down,
        new_hosts=new_hosts,
        new_ports=new_ports,
        total_subnets=total_subnets,
        active_scans=active_scans,
        subnets=subnets,
        recent_scans=recent_scans,
        last_scan_at=last_scan_at,
    )
```

---

## Register Router

In `api/main.py`:
```python
from dashboard.router import router as dashboard_router
app.include_router(dashboard_router)
```
