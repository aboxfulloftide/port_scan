from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from shared.db import get_db
from shared.models import Host, HostPort, Subnet, ScanJob, ScanProfile, User
from api.auth.dependencies import get_current_user
from api.dashboard.models import DashboardStats, SubnetSummary, RecentScan

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardStats)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    # Host counts
    total_hosts = (await db.execute(select(func.count()).select_from(Host))).scalar()
    hosts_up = (await db.execute(
        select(func.count()).select_from(Host).where(Host.is_up == True)
    )).scalar()
    hosts_down = total_hosts - hosts_up
    new_hosts = (await db.execute(
        select(func.count()).select_from(Host).where(Host.is_new == True)
    )).scalar()
    new_ports = (await db.execute(
        select(func.count()).select_from(HostPort).where(HostPort.is_new == True)
    )).scalar()

    # Subnet count
    total_subnets = (await db.execute(select(func.count()).select_from(Subnet))).scalar()

    # Active scans
    active_scans = (await db.execute(
        select(func.count()).select_from(ScanJob).where(ScanJob.status.in_(["queued", "running"]))
    )).scalar()

    # Per-subnet summary
    subnet_rows = (await db.execute(select(Subnet).order_by(Subnet.label))).scalars().all()
    subnets = []
    for s in subnet_rows:
        hc = (await db.execute(
            select(func.count()).select_from(Host).where(Host.subnet_id == s.id)
        )).scalar()
        uc = (await db.execute(
            select(func.count()).select_from(Host).where(Host.subnet_id == s.id, Host.is_up == True)
        )).scalar()
        subnets.append(SubnetSummary(
            id=s.id, cidr=s.cidr, label=s.label,
            host_count=hc, up_count=uc
        ))

    # Recent scans (last 10), enriched with profile name
    recent_rows = (await db.execute(
        select(ScanJob)
        .order_by(desc(ScanJob.created_at))
        .limit(10)
    )).scalars().all()

    recent_scans = []
    for job in recent_rows:
        profile = await db.get(ScanProfile, job.profile_id)
        recent_scans.append(RecentScan(
            id=job.id,
            profile_name=profile.name if profile else None,
            status=job.status,
            hosts_discovered=job.hosts_discovered,
            hosts_up=job.hosts_up,
            new_hosts_found=job.new_hosts_found,
            new_ports_found=job.new_ports_found,
            started_at=job.started_at,
            completed_at=job.completed_at,
        ))

    last_scan_at = next(
        (s.started_at for s in recent_scans if s.started_at is not None), None
    )

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
