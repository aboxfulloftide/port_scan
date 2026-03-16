#!/usr/bin/env python3
"""
Migration: deduplicate hosts by MAC (keep newest), then add unique index on current_mac.
Safe to run multiple times — skips dedup if already clean, skips index if already exists.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, func, text, update
from shared.db import AsyncSessionLocal, engine
from shared.models import Host, HostPort, HostHistory, HostNetworkId, HostTrafficSnapshot


async def merge_into(db, winner: Host, loser: Host):
    """Move all child records from loser to winner, then delete loser."""
    print(f"  Merging host {loser.id} (ip={loser.current_ip} last_seen={loser.last_seen}) "
          f"-> host {winner.id} (ip={winner.current_ip} last_seen={winner.last_seen})")

    # Ports: move non-conflicting, update existing if loser is newer
    loser_ports = (await db.execute(select(HostPort).where(HostPort.host_id == loser.id))).scalars().all()
    for lp in loser_ports:
        existing = (await db.execute(
            select(HostPort).where(
                HostPort.host_id == winner.id,
                HostPort.port == lp.port,
                HostPort.protocol == lp.protocol,
            )
        )).scalar_one_or_none()
        if existing:
            if lp.last_seen and (not existing.last_seen or lp.last_seen > existing.last_seen):
                existing.state = lp.state
                existing.service_name = lp.service_name or existing.service_name
                existing.service_ver = lp.service_ver or existing.service_ver
                existing.last_seen = lp.last_seen
            await db.delete(lp)
        else:
            lp.host_id = winner.id

    # Network IDs: move non-duplicates
    loser_nids = (await db.execute(select(HostNetworkId).where(HostNetworkId.host_id == loser.id))).scalars().all()
    for nid in loser_nids:
        existing = (await db.execute(
            select(HostNetworkId).where(
                HostNetworkId.host_id == winner.id,
                HostNetworkId.ip_address == nid.ip_address,
                HostNetworkId.mac_address == nid.mac_address,
            )
        )).scalar_one_or_none()
        if existing:
            await db.delete(nid)
        else:
            nid.host_id = winner.id

    # History
    await db.execute(
        update(HostHistory).where(HostHistory.host_id == loser.id).values(host_id=winner.id)
        .execution_options(synchronize_session=False)
    )

    # Traffic snapshots
    await db.execute(
        update(HostTrafficSnapshot).where(HostTrafficSnapshot.host_id == loser.id).values(host_id=winner.id)
        .execution_options(synchronize_session=False)
    )

    # Merge timestamps
    if loser.first_seen and (not winner.first_seen or loser.first_seen < winner.first_seen):
        winner.first_seen = loser.first_seen
    if loser.notes:
        winner.notes = ((winner.notes or "") + "\n" + loser.notes).strip()

    await db.flush()
    await db.delete(loser)


async def deduplicate():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Host.current_mac, func.count(Host.id).label("cnt"))
            .where(Host.current_mac.isnot(None), Host.primary_host_id.is_(None))
            .group_by(Host.current_mac)
            .having(func.count(Host.id) > 1)
        )
        dup_macs = result.all()

        if not dup_macs:
            print("No duplicate MACs found — nothing to merge.")
            return

        for mac, cnt in dup_macs:
            print(f"MAC {mac}: {cnt} duplicates")
            hosts_result = await db.execute(
                select(Host)
                .where(Host.current_mac == mac, Host.primary_host_id.is_(None))
                .order_by(Host.last_seen.is_(None).asc(), Host.last_seen.desc())
            )
            hosts = hosts_result.scalars().all()
            winner = hosts[0]
            for loser in hosts[1:]:
                await merge_into(db, winner, loser)

        await db.commit()
        print("Deduplication complete.")


async def clear_alias_macs():
    """Aliases don't need current_mac — it causes unique constraint conflicts."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Host).where(Host.primary_host_id.isnot(None), Host.current_mac.isnot(None))
        )
        aliases = result.scalars().all()
        if aliases:
            print(f"Clearing current_mac on {len(aliases)} alias host(s)...")
            for a in aliases:
                a.current_mac = None
            await db.commit()


async def add_unique_index():
    async with engine.begin() as conn:
        # Check if index already exists
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() "
            "AND table_name = 'hosts' "
            "AND index_name = 'uq_hosts_current_mac'"
        ))
        exists = result.scalar()
        if exists:
            print("Unique index on current_mac already exists — skipping.")
            return

        print("Adding unique index on hosts.current_mac ...")
        # NULL values are excluded from unique enforcement in MySQL, so
        # hosts with no MAC can coexist without violating the constraint.
        await conn.execute(text(
            "ALTER TABLE hosts ADD UNIQUE INDEX uq_hosts_current_mac (current_mac)"
        ))
        print("Index added.")


async def main():
    await deduplicate()
    await clear_alias_macs()
    await add_unique_index()


if __name__ == "__main__":
    asyncio.run(main())
