from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func

from shared.db import get_db
from shared.models import (
    User, Host, InterfaceTrafficSnapshot, HostTrafficSnapshot,
)
from api.auth.dependencies import get_current_user
from api.traffic.models import (
    InterfaceTrafficOut, HostTrafficOut,
    InterfaceHistoryPoint, HostTrafficHistoryPoint, TrafficSyncResult,
    DailyInterfaceTraffic,
)

router = APIRouter(prefix="/traffic", tags=["traffic"])


@router.get("/interfaces", response_model=list[InterfaceTrafficOut])
async def get_interface_stats(
    hours: int = Query(0, ge=0, description="If > 0, return snapshots from the last N hours"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Latest interface traffic stats (or historical if hours > 0)."""
    if hours > 0:
        since = datetime.utcnow() - timedelta(hours=hours)
        q = (
            select(InterfaceTrafficSnapshot)
            .where(InterfaceTrafficSnapshot.scraped_at >= since)
            .order_by(desc(InterfaceTrafficSnapshot.scraped_at))
        )
    else:
        # Get the latest scraped_at timestamp and return all rows with that timestamp
        latest_q = select(InterfaceTrafficSnapshot.scraped_at).order_by(
            desc(InterfaceTrafficSnapshot.scraped_at)
        ).limit(1)
        latest_ts = (await db.execute(latest_q)).scalar_one_or_none()
        if not latest_ts:
            return []
        q = select(InterfaceTrafficSnapshot).where(
            InterfaceTrafficSnapshot.scraped_at == latest_ts
        )

    rows = (await db.execute(q)).scalars().all()
    return rows


@router.get("/interfaces/history", response_model=list[InterfaceHistoryPoint])
async def get_interface_history(
    hours: int = Query(24, ge=1, le=17520),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Time-series interface traffic data for charts."""
    since = datetime.utcnow() - timedelta(hours=hours)
    q = (
        select(InterfaceTrafficSnapshot)
        .where(InterfaceTrafficSnapshot.scraped_at >= since)
        .order_by(InterfaceTrafficSnapshot.scraped_at)
    )
    rows = (await db.execute(q)).scalars().all()
    return rows


@router.get("/interfaces/daily", response_model=list[DailyInterfaceTraffic])
async def get_interface_daily(
    days: int = Query(365, ge=1, le=730),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Daily aggregated interface traffic (MAX - MIN per day)."""
    since = datetime.utcnow() - timedelta(days=days)
    day_col = func.date(InterfaceTrafficSnapshot.scraped_at).label("day")
    q = (
        select(
            InterfaceTrafficSnapshot.interface,
            day_col,
            (func.max(InterfaceTrafficSnapshot.bytes_sent) - func.min(InterfaceTrafficSnapshot.bytes_sent)).label("bytes_sent"),
            (func.max(InterfaceTrafficSnapshot.bytes_recv) - func.min(InterfaceTrafficSnapshot.bytes_recv)).label("bytes_recv"),
        )
        .where(InterfaceTrafficSnapshot.scraped_at >= since)
        .group_by(InterfaceTrafficSnapshot.interface, day_col)
        .order_by(day_col)
    )
    rows = (await db.execute(q)).all()
    return [
        DailyInterfaceTraffic(interface=r.interface, day=r.day, bytes_sent=r.bytes_sent, bytes_recv=r.bytes_recv)
        for r in rows
    ]


@router.get("/hosts", response_model=list[HostTrafficOut])
async def get_host_traffic(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Latest per-IP traffic snapshot for all hosts."""
    latest_q = select(HostTrafficSnapshot.scraped_at).order_by(
        desc(HostTrafficSnapshot.scraped_at)
    ).limit(1)
    latest_ts = (await db.execute(latest_q)).scalar_one_or_none()
    if not latest_ts:
        return []

    q = select(HostTrafficSnapshot).where(
        HostTrafficSnapshot.scraped_at == latest_ts
    )
    rows = (await db.execute(q)).scalars().all()

    # Enrich with hostnames
    results = []
    for row in rows:
        out = HostTrafficOut.model_validate(row)
        if row.host_id:
            host = await db.get(Host, row.host_id)
            if host:
                out.hostname = host.hostname
        results.append(out)

    return results


@router.get("/hosts/{host_id}/history", response_model=list[HostTrafficHistoryPoint])
async def get_host_traffic_history(
    host_id: int,
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Time-series traffic data for a specific host."""
    since = datetime.utcnow() - timedelta(hours=hours)
    q = (
        select(HostTrafficSnapshot)
        .where(
            HostTrafficSnapshot.host_id == host_id,
            HostTrafficSnapshot.scraped_at >= since,
        )
        .order_by(HostTrafficSnapshot.scraped_at)
    )
    rows = (await db.execute(q)).scalars().all()
    return rows


@router.post("/sync", response_model=TrafficSyncResult)
async def trigger_traffic_sync(
    background_tasks: BackgroundTasks,
    _: User = Depends(get_current_user),
):
    """Manually trigger a traffic stats scrape."""
    from worker.traffic_scraper import scrape_traffic_stats, persist_traffic_data

    result = await scrape_traffic_stats()
    counts = await persist_traffic_data(result["interface_stats"], result["ip_stats"])
    return TrafficSyncResult(**counts)
