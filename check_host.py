#!/usr/bin/env python3
"""Check if a host exists in the DB by IP (including network_ids history)."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.db import AsyncSessionLocal
from shared.models import Host, HostNetworkId
from sqlalchemy import select, or_


async def check(ip: str):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Host).where(Host.current_ip == ip)
        )
        hosts = result.scalars().all()

        if hosts:
            print(f"Hosts with current_ip={ip}:")
            for h in hosts:
                print(f"  id={h.id} hostname={h.hostname} is_up={h.is_up} primary_host_id={h.primary_host_id}")
        else:
            print(f"No host found with current_ip={ip}")

        result2 = await db.execute(
            select(HostNetworkId).where(HostNetworkId.ip_address == ip)
        )
        nids = result2.scalars().all()

        if nids:
            print(f"Network ID records for {ip}:")
            for n in nids:
                print(f"  host_id={n.host_id} mac={n.mac_address} source={n.source} last_seen={n.last_seen}")
        else:
            print(f"No network_id records for {ip}")


async def check_by_id(host_id: int):
    async with AsyncSessionLocal() as db:
        h = await db.get(Host, host_id)
        if h:
            print(f"Host {host_id}: current_ip={h.current_ip} hostname={h.hostname} is_up={h.is_up} primary_host_id={h.primary_host_id}")
            result = await db.execute(
                select(HostNetworkId).where(HostNetworkId.host_id == host_id)
            )
            for n in result.scalars().all():
                print(f"  network_id: ip={n.ip_address} mac={n.mac_address} last_seen={n.last_seen}")
        else:
            print(f"No host found with id={host_id}")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--id":
        asyncio.run(check_by_id(int(sys.argv[2])))
    else:
        ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.37"
        asyncio.run(check(ip))
