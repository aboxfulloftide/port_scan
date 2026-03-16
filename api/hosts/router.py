from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_, or_
from sqlalchemy.orm import selectinload
from typing import Optional
import logging
import os

from datetime import datetime, timedelta

from shared.db import get_db
from shared.models import (
    Host, HostPort, HostHistory, PortBanner, PortScreenshot,
    User, HostTrafficSnapshot, HostNetworkId, HostMergeLog,
    MergeSuggestionIgnore,
)
from api.auth.dependencies import get_current_user
from api.hosts.models import (
    HostSummaryOut, HostDetailOut, HostUpdate, PaginatedHosts,
    HostPortOut, HostHistoryOut, HostAliasSummary, HostNetworkIdOut,
    MergeSuggestion, MergeRequest, IgnoreRequest, IgnoredGroupOut,
)
from api.config import settings

router = APIRouter(prefix="/hosts", tags=["hosts"])
logger = logging.getLogger("api.hosts")


@router.get("", response_model=PaginatedHosts)
async def list_hosts(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    subnet_id: Optional[int] = Query(None),
    is_up: Optional[bool] = Query(None),
    is_new: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    show_aliases: bool = Query(False),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200)
):
    filters = []
    if not show_aliases:
        filters.append(Host.primary_host_id.is_(None))
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

    host_ids = [h.id for h in hosts]
    port_counts = {}
    bandwidth_map = {}
    if host_ids:
        pc_result = await db.execute(
            select(HostPort.host_id, func.count(HostPort.id))
            .where(HostPort.host_id.in_(host_ids), HostPort.state == "open")
            .group_by(HostPort.host_id)
        )
        port_counts = dict(pc_result.all())

        # Compute bandwidth over the last hour (relative to most recent snapshot)
        latest_ts = (await db.execute(
            select(func.max(HostTrafficSnapshot.scraped_at))
        )).scalar()
        if latest_ts:
            one_hour_before_latest = latest_ts - timedelta(hours=1)
            bw_result = await db.execute(
                select(
                    HostTrafficSnapshot.host_id,
                    (
                        (func.max(HostTrafficSnapshot.bytes_sent) - func.min(HostTrafficSnapshot.bytes_sent))
                        + (func.max(HostTrafficSnapshot.bytes_recv) - func.min(HostTrafficSnapshot.bytes_recv))
                    ).label("bw"),
                )
                .where(
                    HostTrafficSnapshot.host_id.in_(host_ids),
                    HostTrafficSnapshot.scraped_at >= one_hour_before_latest,
                )
                .group_by(HostTrafficSnapshot.host_id)
            )
            bandwidth_map = {row[0]: row[1] for row in bw_result.all()}

    # Compute alias counts
    alias_counts = {}
    if host_ids:
        ac_result = await db.execute(
            select(Host.primary_host_id, func.count(Host.id))
            .where(Host.primary_host_id.in_(host_ids))
            .group_by(Host.primary_host_id)
        )
        alias_counts = dict(ac_result.all())

    host_summaries = []
    for h in hosts:
        summary = HostSummaryOut.model_validate(h)
        summary.open_port_count = port_counts.get(h.id, 0)
        summary.bandwidth_1h = bandwidth_map.get(h.id, 0)
        summary.alias_count = alias_counts.get(h.id, 0)
        host_summaries.append(summary)

    # Sort by bandwidth descending, then hostname ascending
    host_summaries.sort(key=lambda s: (-s.bandwidth_1h, (s.hostname or "").lower()))

    return PaginatedHosts(total=total, page=page, per_page=per_page, hosts=host_summaries)


def _all_pairs(ids: list[int]) -> set[tuple[int, int]]:
    """Return all canonical (a<b) pairs from a list of IDs."""
    sorted_ids = sorted(ids)
    pairs = set()
    for i in range(len(sorted_ids)):
        for j in range(i + 1, len(sorted_ids)):
            pairs.add((sorted_ids[i], sorted_ids[j]))
    return pairs


@router.get("/merge-suggestions", response_model=list[MergeSuggestion])
async def merge_suggestions(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Find duplicate host candidates based on shared hostnames or MACs."""
    # Load all ignored pairs into a set for fast lookup
    ignored_result = await db.execute(
        select(MergeSuggestionIgnore.host_id_a, MergeSuggestionIgnore.host_id_b)
    )
    ignored_pairs: set[tuple[int, int]] = {(r[0], r[1]) for r in ignored_result.all()}

    suggestions: list[MergeSuggestion] = []

    # 1. Same hostname (non-null) appearing on multiple hosts
    dup_hostnames = await db.execute(
        select(Host.hostname, func.count(Host.id).label("cnt"))
        .where(Host.hostname.isnot(None), Host.primary_host_id.is_(None))
        .group_by(Host.hostname)
        .having(func.count(Host.id) > 1)
    )
    for hostname, cnt in dup_hostnames.all():
        result = await db.execute(
            select(Host).where(Host.hostname == hostname, Host.primary_host_id.is_(None))
        )
        hosts = result.scalars().all()
        host_ids = [h.id for h in hosts]

        # Skip if every pair in this group is ignored
        group_pairs = _all_pairs(host_ids)
        if group_pairs and group_pairs.issubset(ignored_pairs):
            continue

        pc_result = await db.execute(
            select(HostPort.host_id, func.count(HostPort.id))
            .where(HostPort.host_id.in_(host_ids), HostPort.state == "open")
            .group_by(HostPort.host_id)
        )
        port_counts = dict(pc_result.all())
        summaries = []
        for h in hosts:
            s = HostSummaryOut.model_validate(h)
            s.open_port_count = port_counts.get(h.id, 0)
            summaries.append(s)
        suggestions.append(MergeSuggestion(
            reason=f"Shared hostname: {hostname}",
            hosts=summaries,
        ))

    # 2. Shared MAC across host_network_ids for different primary hosts
    dup_macs = await db.execute(
        select(HostNetworkId.mac_address, func.count(func.distinct(HostNetworkId.host_id)).label("cnt"))
        .where(HostNetworkId.mac_address.isnot(None))
        .group_by(HostNetworkId.mac_address)
        .having(func.count(func.distinct(HostNetworkId.host_id)) > 1)
    )
    for mac, cnt in dup_macs.all():
        result = await db.execute(
            select(Host)
            .join(HostNetworkId, HostNetworkId.host_id == Host.id)
            .where(HostNetworkId.mac_address == mac, Host.primary_host_id.is_(None))
        )
        hosts = result.scalars().unique().all()
        if len(hosts) < 2:
            continue
        host_ids = [h.id for h in hosts]

        # Skip if every pair in this group is ignored
        group_pairs = _all_pairs(host_ids)
        if group_pairs and group_pairs.issubset(ignored_pairs):
            continue

        pc_result = await db.execute(
            select(HostPort.host_id, func.count(HostPort.id))
            .where(HostPort.host_id.in_(host_ids), HostPort.state == "open")
            .group_by(HostPort.host_id)
        )
        port_counts = dict(pc_result.all())
        summaries = []
        for h in hosts:
            s = HostSummaryOut.model_validate(h)
            s.open_port_count = port_counts.get(h.id, 0)
            summaries.append(s)
        suggestions.append(MergeSuggestion(
            reason=f"Shared MAC: {mac}",
            hosts=summaries,
        ))

    return suggestions


@router.post("/merge-suggestions/ignore")
async def ignore_suggestion(
    body: IgnoreRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dismiss a merge suggestion by storing all host pairs as ignored."""
    if len(body.host_ids) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 host IDs")

    pairs = _all_pairs(body.host_ids)
    inserted = 0
    now = datetime.utcnow()
    for a, b in pairs:
        existing = await db.execute(
            select(MergeSuggestionIgnore).where(
                MergeSuggestionIgnore.host_id_a == a,
                MergeSuggestionIgnore.host_id_b == b,
            )
        )
        if existing.scalar_one_or_none():
            continue
        db.add(MergeSuggestionIgnore(
            host_id_a=a, host_id_b=b,
            dismissed_by=current_user.id, dismissed_at=now,
        ))
        inserted += 1

    await db.commit()
    return {"ignored_pairs": inserted}


@router.get("/merge-suggestions/ignored", response_model=list[IgnoredGroupOut])
async def list_ignored_suggestions(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return ignored suggestion groups with host details."""
    result = await db.execute(
        select(MergeSuggestionIgnore).order_by(MergeSuggestionIgnore.dismissed_at.desc())
    )
    ignores = result.scalars().all()

    # Group pairs back into connected groups using union-find
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(x: int, y: int):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    dismissed_at_map: dict[int, datetime] = {}
    for ig in ignores:
        union(ig.host_id_a, ig.host_id_b)
        # Track latest dismissed_at per host
        for hid in (ig.host_id_a, ig.host_id_b):
            if hid not in dismissed_at_map or ig.dismissed_at > dismissed_at_map[hid]:
                dismissed_at_map[hid] = ig.dismissed_at

    # Build groups
    from collections import defaultdict
    groups: dict[int, set[int]] = defaultdict(set)
    all_host_ids = set()
    for ig in ignores:
        root = find(ig.host_id_a)
        groups[root].add(ig.host_id_a)
        groups[root].add(ig.host_id_b)
        all_host_ids.update((ig.host_id_a, ig.host_id_b))

    if not all_host_ids:
        return []

    # Fetch host details
    hosts_result = await db.execute(select(Host).where(Host.id.in_(all_host_ids)))
    hosts_by_id = {h.id: h for h in hosts_result.scalars().all()}

    # Fetch port counts
    pc_result = await db.execute(
        select(HostPort.host_id, func.count(HostPort.id))
        .where(HostPort.host_id.in_(list(all_host_ids)), HostPort.state == "open")
        .group_by(HostPort.host_id)
    )
    port_counts = dict(pc_result.all())

    output = []
    for root, member_ids in groups.items():
        sorted_ids = sorted(member_ids)
        summaries = []
        group_dismissed_at = None
        for hid in sorted_ids:
            host = hosts_by_id.get(hid)
            if not host:
                continue
            s = HostSummaryOut.model_validate(host)
            s.open_port_count = port_counts.get(hid, 0)
            summaries.append(s)
            dt = dismissed_at_map.get(hid)
            if dt and (group_dismissed_at is None or dt > group_dismissed_at):
                group_dismissed_at = dt

        if len(summaries) >= 2:
            output.append(IgnoredGroupOut(
                host_ids=sorted_ids,
                hosts=summaries,
                dismissed_at=group_dismissed_at or datetime.utcnow(),
            ))

    return output


@router.post("/merge-suggestions/unignore")
async def unignore_suggestion(
    body: IgnoreRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Restore a dismissed merge suggestion by removing ignored pairs."""
    if len(body.host_ids) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 host IDs")

    pairs = _all_pairs(body.host_ids)
    deleted = 0
    for a, b in pairs:
        result = await db.execute(
            select(MergeSuggestionIgnore).where(
                MergeSuggestionIgnore.host_id_a == a,
                MergeSuggestionIgnore.host_id_b == b,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            await db.delete(row)
            deleted += 1

    await db.commit()
    return {"restored_pairs": deleted}


@router.post("/merge")
async def merge_hosts(
    body: MergeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Merge alias hosts into a primary host."""
    primary = await db.get(Host, body.primary_host_id)
    if not primary:
        raise HTTPException(status_code=404, detail="Primary host not found")

    merged = []
    now = datetime.utcnow()

    for alias_id in body.alias_host_ids:
        if alias_id == body.primary_host_id:
            continue
        alias = await db.get(Host, alias_id)
        if not alias:
            continue

        # 1. Snapshot alias state
        snapshot = {
            "hostname": alias.hostname,
            "current_ip": alias.current_ip,
            "current_mac": alias.current_mac,
            "vendor": alias.vendor,
            "os_guess": alias.os_guess,
            "notes": alias.notes,
            "subnet_id": alias.subnet_id,
        }

        # 2. Set alias pointer
        alias.primary_host_id = primary.id

        # 3. Re-point ports (handle duplicate port/protocol conflicts)
        alias_ports_result = await db.execute(
            select(HostPort).where(HostPort.host_id == alias_id)
        )
        for ap in alias_ports_result.scalars().all():
            # Check if primary already has this port/protocol
            existing = await db.execute(
                select(HostPort).where(
                    HostPort.host_id == primary.id,
                    HostPort.port == ap.port,
                    HostPort.protocol == ap.protocol,
                )
            )
            existing_port = existing.scalar_one_or_none()
            if existing_port:
                # Update primary's port with latest info if alias is newer
                if ap.last_seen and (not existing_port.last_seen or ap.last_seen > existing_port.last_seen):
                    existing_port.last_seen = ap.last_seen
                    existing_port.state = ap.state
                    existing_port.service_name = ap.service_name or existing_port.service_name
                    existing_port.service_ver = ap.service_ver or existing_port.service_ver
                if ap.first_seen and (not existing_port.first_seen or ap.first_seen < existing_port.first_seen):
                    existing_port.first_seen = ap.first_seen
                # Delete the alias's duplicate port
                await db.delete(ap)
            else:
                ap.host_id = primary.id

        # 4. Re-point history
        await db.execute(
            update(HostHistory).where(HostHistory.host_id == alias_id).values(host_id=primary.id)
        )

        # 5. Re-point traffic snapshots
        await db.execute(
            update(HostTrafficSnapshot)
            .where(HostTrafficSnapshot.host_id == alias_id)
            .values(host_id=primary.id)
        )

        # 6. Copy network_ids (skip duplicates)
        nid_result = await db.execute(
            select(HostNetworkId).where(HostNetworkId.host_id == alias_id)
        )
        for nid in nid_result.scalars().all():
            existing = await db.execute(
                select(HostNetworkId).where(
                    HostNetworkId.host_id == primary.id,
                    HostNetworkId.ip_address == nid.ip_address,
                    HostNetworkId.mac_address == nid.mac_address,
                )
            )
            if existing.scalar_one_or_none():
                continue
            db.add(HostNetworkId(
                host_id=primary.id,
                ip_address=nid.ip_address,
                mac_address=nid.mac_address,
                source=nid.source,
                first_seen=nid.first_seen,
                last_seen=nid.last_seen,
            ))

        # 7. Merge timestamps
        if alias.first_seen and (not primary.first_seen or alias.first_seen < primary.first_seen):
            primary.first_seen = alias.first_seen
        if alias.last_seen and (not primary.last_seen or alias.last_seen > primary.last_seen):
            primary.last_seen = alias.last_seen

        # 8. Merge notes
        if alias.notes:
            primary.notes = ((primary.notes or "") + "\n" + alias.notes).strip()

        # 9. Log the merge
        db.add(HostMergeLog(
            primary_host_id=primary.id,
            alias_host_id=alias_id,
            action="merge",
            performed_by=current_user.id,
            performed_at=now,
            snapshot=snapshot,
        ))

        merged.append(alias_id)

    await db.commit()
    return {"merged": merged, "primary_host_id": primary.id}


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
            selectinload(Host.history),
            selectinload(Host.network_ids),
            selectinload(Host.aliases),
        )
        .where(Host.id == host_id)
    )
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")

    detail = HostDetailOut.model_validate(host)
    detail.network_ids = [HostNetworkIdOut.model_validate(n) for n in host.network_ids]
    detail.aliases = [HostAliasSummary.model_validate(a) for a in host.aliases]

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
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Host).where(Host.id == host_id))
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")

    updates = body.model_dump(exclude_none=True)
    # Allow clearing hostname by sending empty string
    if body.hostname is not None:
        updates["hostname"] = body.hostname or None
    if updates:
        now = datetime.utcnow()
        # Log hostname change in history
        if "hostname" in updates and updates["hostname"] != host.hostname:
            db.add(HostHistory(
                host_id=host_id,
                event_type="hostname_change",
                old_value=host.hostname,
                new_value=updates["hostname"],
                recorded_at=now,
            ))
        await db.execute(update(Host).where(Host.id == host_id).values(**updates))
        await db.commit()

    return await get_host(host_id, db, current_user)


@router.delete("/{host_id}/network-ids/{nid}")
async def remove_network_id(
    host_id: int,
    nid: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Remove a known identity (IP/MAC pair) from a host."""
    result = await db.execute(
        select(HostNetworkId).where(
            HostNetworkId.id == nid,
            HostNetworkId.host_id == host_id,
        )
    )
    network_id = result.scalar_one_or_none()
    if not network_id:
        raise HTTPException(status_code=404, detail="Network identity not found")

    await db.delete(network_id)

    # If this was the host's current IP, clear it to the next known identity or leave it
    host = await db.get(Host, host_id)
    if host and host.current_ip == network_id.ip_address:
        # Find another network identity to use, if any
        alt = await db.execute(
            select(HostNetworkId)
            .where(HostNetworkId.host_id == host_id, HostNetworkId.id != nid)
            .order_by(HostNetworkId.last_seen.desc())
            .limit(1)
        )
        alt_nid = alt.scalar_one_or_none()
        if alt_nid:
            host.current_ip = alt_nid.ip_address

    await db.commit()
    return {"removed": nid}


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

    full_path = os.path.join(settings.SCREENSHOT_DIR, screenshot.file_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Screenshot file not found on disk")

    return FileResponse(full_path, media_type="image/png")


@router.post("/{host_id}/unmerge")
async def unmerge_host(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Restore an alias host back to standalone."""
    alias = await db.get(Host, host_id)
    if not alias:
        raise HTTPException(status_code=404, detail="Host not found")
    if alias.primary_host_id is None:
        raise HTTPException(status_code=400, detail="Host is not an alias")

    # Find the most recent merge log to restore snapshot
    log_result = await db.execute(
        select(HostMergeLog)
        .where(
            HostMergeLog.alias_host_id == host_id,
            HostMergeLog.action == "merge",
        )
        .order_by(HostMergeLog.performed_at.desc())
        .limit(1)
    )
    merge_log = log_result.scalar_one_or_none()

    # Restore snapshot fields if available
    if merge_log and merge_log.snapshot:
        snap = merge_log.snapshot
        alias.hostname = snap.get("hostname", alias.hostname)
        alias.current_ip = snap.get("current_ip", alias.current_ip)
        alias.current_mac = snap.get("current_mac", alias.current_mac)
        alias.vendor = snap.get("vendor", alias.vendor)
        alias.os_guess = snap.get("os_guess", alias.os_guess)
        alias.notes = snap.get("notes", alias.notes)
        alias.subnet_id = snap.get("subnet_id", alias.subnet_id)

    primary_id = alias.primary_host_id
    alias.primary_host_id = None

    # Log the unmerge
    db.add(HostMergeLog(
        primary_host_id=primary_id,
        alias_host_id=host_id,
        action="unmerge",
        performed_by=current_user.id,
        performed_at=datetime.utcnow(),
    ))

    await db.commit()
    return {"unmerged": host_id, "former_primary_id": primary_id}


@router.post("/dhcp-sync")
async def trigger_dhcp_sync(
    _: User = Depends(get_current_user),
):
    """Manually trigger a DHCP hostname scrape from the router."""
    from worker.dhcp_scraper import scrape_dhcp_table, update_hosts_from_dhcp

    try:
        entries = await scrape_dhcp_table()
    except Exception as e:
        logger.exception("DHCP scrape failed")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "DHCP scrape failed", "detail": str(e)},
        )

    if not entries:
        return JSONResponse(
            content={
                "status": "no_data",
                "message": "No DHCP entries found. Check router credentials, page path, and Playwright installation.",
                "hosts_updated": 0,
            }
        )

    result = await update_hosts_from_dhcp(entries)
    return JSONResponse(
        content={
            "status": "ok",
            "entries_scraped": len(entries),
            "hosts_updated": result["updated"],
            "hosts_created": result["created"],
        }
    )
