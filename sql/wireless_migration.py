#!/usr/bin/env python3
"""
Migration: add wireless AP support tables and columns.

- Adds `connection_type` ENUM column to `hosts` table (if not exists)
- Creates `wireless_aps` table (if not exists)
- Creates `host_wireless_clients` table (if not exists)

Safe to run multiple times.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from shared.db import engine, AsyncSessionLocal
from shared.models import WirelessAP, HostWirelessClient  # noqa: F401 — ensure metadata is loaded


async def add_connection_type_column() -> None:
    """Add connection_type ENUM column to hosts table if it doesn't already exist."""
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() "
            "AND table_name = 'hosts' "
            "AND column_name = 'connection_type'"
        ))
        exists = result.scalar()

        if exists:
            print("  hosts.connection_type column already exists — skipping.")
            return

        print("  Adding connection_type column to hosts table...")
        await conn.execute(text(
            "ALTER TABLE hosts "
            "ADD COLUMN connection_type ENUM('wired', 'wireless') NULL DEFAULT NULL"
        ))
        print("  Done.")


async def create_wireless_aps_table() -> None:
    """Create wireless_aps table if it doesn't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: WirelessAP.__table__.create(sync_conn, checkfirst=True)
        )
        print("  wireless_aps table ensured.")


async def create_host_wireless_clients_table() -> None:
    """Create host_wireless_clients table if it doesn't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: HostWirelessClient.__table__.create(sync_conn, checkfirst=True)
        )
        print("  host_wireless_clients table ensured.")


async def main() -> None:
    print("=== Wireless AP migration ===")

    print("[1/3] Checking hosts.connection_type column...")
    await add_connection_type_column()

    print("[2/3] Ensuring wireless_aps table...")
    await create_wireless_aps_table()

    print("[3/3] Ensuring host_wireless_clients table...")
    await create_host_wireless_clients_table()

    await engine.dispose()
    print("=== Migration complete ===")


if __name__ == "__main__":
    asyncio.run(main())
