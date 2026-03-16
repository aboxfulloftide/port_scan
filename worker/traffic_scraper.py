"""
Traffic statistics scraper — logs into a TP-Link router's web interface via
Playwright, calls the traffic API endpoints using the stok session token, and
extracts interface-level and per-IP bandwidth data.  Results are persisted as
historical snapshots for trend charts.

Runs as a periodic background task (configurable interval via
TRAFFIC_SCRAPE_INTERVAL_MIN env var).
"""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, delete

from api.config import settings
from shared.db import AsyncSessionLocal
from shared.models import Host, InterfaceTrafficSnapshot, HostTrafficSnapshot
from worker.router_auth import RouterLoginError, login_and_get_stok, make_router_api_call

logger = logging.getLogger("worker.traffic_scraper")


async def scrape_traffic_stats() -> dict:
    """
    Log into the TP-Link router and scrape traffic statistics.
    Returns dict with 'interface_stats' and 'ip_stats' lists.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright not installed — cannot scrape traffic stats")
        return {"interface_stats": [], "ip_stats": []}

    if not settings.ROUTER_URL or not settings.ROUTER_PASSWORD:
        logger.warning("ROUTER_URL or ROUTER_PASSWORD not configured — skipping traffic scrape")
        return {"interface_stats": [], "ip_stats": []}

    router_url = settings.ROUTER_URL.rstrip("/")
    interface_stats = []
    ip_stats = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=["--no-sandbox", "--disable-dev-shm-usage", "--ignore-certificate-errors"]
        )
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        try:
            logger.info(f"Connecting to router at {router_url} for traffic stats")
            await page.goto(router_url, timeout=15000, wait_until="networkidle")

            stok = await login_and_get_stok(page, router_url, settings.ROUTER_USERNAME, settings.ROUTER_PASSWORD)
            if not stok:
                logger.error("Login succeeded but no stok token received")
                return {"interface_stats": [], "ip_stats": []}

            logger.info("Router login successful for traffic scrape")

            # Try multiple known TP-Link API paths for interface statistics
            IFACE_CANDIDATES = [
                ("ifstat", "list"),
            ]
            iface_data = {}
            for path, form in IFACE_CANDIDATES:
                iface_data = await make_router_api_call(page, stok, router_url, path, form, quiet=True)
                if iface_data:
                    logger.info(f"Interface stats found at {path}?form={form}")
                    break
            else:
                logger.warning("No working interface stats endpoint found on router")

            if iface_data:
                iface_result = iface_data.get("result") or iface_data.get("data") or {}
                if isinstance(iface_result, dict):
                    # Could be keyed by interface name, or a nested structure
                    for key, val in iface_result.items():
                        if isinstance(val, dict) and any(k in val for k in ("tx_bytes", "rx_bytes", "tx_pkts")):
                            interface_stats.append(_parse_interface_stats(key, val))
                        elif isinstance(val, list):
                            for item in val:
                                if isinstance(item, dict):
                                    name = item.get("name") or item.get("interface") or key
                                    interface_stats.append(_parse_interface_stats(name, item))
                elif isinstance(iface_result, list):
                    for item in iface_result:
                        if isinstance(item, dict):
                            name = item.get("name") or item.get("interface") or "unknown"
                            interface_stats.append(_parse_interface_stats(name, item))

            # Try multiple known TP-Link API paths for per-IP traffic
            CLIENT_CANDIDATES = [
                ("ipstats", "list"),
            ]
            client_data = {}
            for path, form in CLIENT_CANDIDATES:
                client_data = await make_router_api_call(page, stok, router_url, path, form, quiet=True)
                if client_data:
                    logger.info(f"Client traffic found at {path}?form={form}")
                    break
            else:
                logger.warning("No working client traffic endpoint found on router")

            if client_data:
                client_list = client_data.get("result") or client_data.get("data") or []
                if isinstance(client_list, list):
                    # Deduplicate — router returns many duplicate rows per IP
                    seen_ips = {}
                    for item in client_list:
                        if isinstance(item, dict):
                            entry = _parse_ip_stats(item)
                            if entry:
                                seen_ips[entry["ip_address"]] = entry
                    ip_stats = list(seen_ips.values())

            logger.info(f"Scraped {len(interface_stats)} interfaces, {len(ip_stats)} IP entries")

        except RouterLoginError as e:
            logger.error(f"Router login failed (code {e.code}): {e}")
            raise
        except Exception as e:
            logger.error(f"Traffic scrape failed: {e}")
        finally:
            await browser.close()

    return {"interface_stats": interface_stats, "ip_stats": ip_stats}


def _parse_interface_stats(name: str, data: dict) -> dict:
    return {
        "interface": name,
        "bytes_sent": int(data.get("tx_bytes") or 0),
        "bytes_recv": int(data.get("rx_bytes") or 0),
        "packets_sent": int(data.get("tx_pkts") or data.get("tx_packets") or 0),
        "packets_recv": int(data.get("rx_pkts") or data.get("rx_packets") or 0),
    }


def _parse_ip_stats(data: dict) -> dict | None:
    ip = data.get("addr") or data.get("ip") or data.get("ipaddr")
    if not ip:
        return None
    return {
        "ip_address": ip,
        "bytes_sent": int(data.get("tx_bytes") or 0),
        "bytes_recv": int(data.get("rx_bytes") or 0),
        "packets_sent": int(data.get("tx_pkts") or data.get("tx_packets") or 0),
        "packets_recv": int(data.get("rx_pkts") or data.get("rx_packets") or 0),
    }


async def persist_traffic_data(interface_stats: list[dict], ip_stats: list[dict]) -> dict:
    """
    Store traffic snapshots in the database.
    Returns counts: {"interfaces": int, "hosts": int}
    """
    now = datetime.utcnow()
    iface_count = 0
    host_count = 0

    async with AsyncSessionLocal() as db:
        # Insert interface snapshots
        for stat in interface_stats:
            db.add(InterfaceTrafficSnapshot(
                interface=stat["interface"],
                bytes_sent=stat["bytes_sent"],
                bytes_recv=stat["bytes_recv"],
                packets_sent=stat["packets_sent"],
                packets_recv=stat["packets_recv"],
                scraped_at=now,
            ))
            iface_count += 1

        # Insert per-IP snapshots, resolving host_id by current_ip
        for stat in ip_stats:
            ip = stat["ip_address"]
            result = await db.execute(select(Host.id).where(Host.current_ip == ip))
            host_id = result.scalars().first()

            db.add(HostTrafficSnapshot(
                ip_address=ip,
                host_id=host_id,
                bytes_sent=stat["bytes_sent"],
                bytes_recv=stat["bytes_recv"],
                packets_sent=stat["packets_sent"],
                packets_recv=stat["packets_recv"],
                scraped_at=now,
            ))
            host_count += 1

        await db.commit()

    logger.info(f"Traffic persist: {iface_count} interface snapshots, {host_count} host snapshots")
    return {"interfaces": iface_count, "hosts": host_count}


async def traffic_scrape_loop():
    """
    Periodic background task that scrapes router traffic statistics
    and stores historical snapshots.
    """
    interval = settings.TRAFFIC_SCRAPE_INTERVAL_MIN * 60

    if not settings.ROUTER_URL or not settings.ROUTER_PASSWORD:
        logger.info("Traffic scraper disabled (ROUTER_URL/ROUTER_PASSWORD not set)")
        return

    logger.info(
        f"Traffic scraper started — scraping {settings.ROUTER_URL} "
        f"every {settings.TRAFFIC_SCRAPE_INTERVAL_MIN} min"
    )

    # Wait before first scrape to avoid colliding with DHCP scraper login
    await asyncio.sleep(30)

    # Run once after initial delay
    try:
        result = await scrape_traffic_stats()
        await persist_traffic_data(result["interface_stats"], result["ip_stats"])
    except Exception as e:
        logger.error(f"Initial traffic scrape failed: {e}")

    # Then loop on interval
    while True:
        await asyncio.sleep(interval)
        try:
            result = await scrape_traffic_stats()
            await persist_traffic_data(result["interface_stats"], result["ip_stats"])
        except asyncio.CancelledError:
            logger.info("Traffic scraper shutting down")
            raise
        except Exception as e:
            logger.error(f"Traffic scrape failed: {e}")


async def traffic_cleanup_loop():
    """
    Periodic background task that deletes old traffic snapshots.
    Runs every hour.
    """
    logger.info(
        f"Traffic cleanup started — interface retention: {settings.INTERFACE_TRAFFIC_RETENTION_DAYS}d, "
        f"host retention: {settings.HOST_TRAFFIC_RETENTION_DAYS}d"
    )

    while True:
        await asyncio.sleep(3600)  # every hour
        try:
            async with AsyncSessionLocal() as db:
                iface_cutoff = datetime.utcnow() - timedelta(days=settings.INTERFACE_TRAFFIC_RETENTION_DAYS)
                result = await db.execute(
                    delete(InterfaceTrafficSnapshot).where(
                        InterfaceTrafficSnapshot.scraped_at < iface_cutoff
                    )
                )
                iface_deleted = result.rowcount

                host_cutoff = datetime.utcnow() - timedelta(days=settings.HOST_TRAFFIC_RETENTION_DAYS)
                result = await db.execute(
                    delete(HostTrafficSnapshot).where(
                        HostTrafficSnapshot.scraped_at < host_cutoff
                    )
                )
                host_deleted = result.rowcount

                await db.commit()

            if iface_deleted or host_deleted:
                logger.info(f"Traffic cleanup: deleted {iface_deleted} interface rows, {host_deleted} host rows")
        except asyncio.CancelledError:
            logger.info("Traffic cleanup shutting down")
            raise
        except Exception as e:
            logger.error(f"Traffic cleanup failed: {e}")
