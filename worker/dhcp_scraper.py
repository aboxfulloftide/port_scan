"""
DHCP hostname scraper — logs into a TP-Link router's web interface via
Playwright, calls the DHCP client API using the stok session token, and
extracts hostname → IP/MAC mappings.  Results are persisted to Host records.

Runs as a periodic background task (configurable interval via
DHCP_SCRAPE_INTERVAL_MIN env var).
"""
import asyncio
import ipaddress
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from api.config import settings
from shared.db import AsyncSessionLocal
from shared.models import Host, HostHistory, HostNetworkId, Subnet
from worker.router_auth import RouterLoginError, login_and_get_stok, make_router_api_call

logger = logging.getLogger("worker.dhcp_scraper")


async def scrape_dhcp_table() -> list[dict]:
    """
    Log into the TP-Link router and scrape the DHCP client table.
    Returns list of dicts: [{"hostname": str, "mac": str, "ip": str, "lease": str}, ...]
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright not installed — cannot scrape DHCP table")
        return []

    if not settings.ROUTER_URL or not settings.ROUTER_PASSWORD:
        logger.warning("ROUTER_URL or ROUTER_PASSWORD not configured — skipping DHCP scrape")
        return []

    router_url = settings.ROUTER_URL.rstrip("/")
    entries: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=["--no-sandbox", "--disable-dev-shm-usage", "--ignore-certificate-errors"]
        )
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        try:
            # Step 1: Navigate to the router login page
            logger.info(f"Connecting to router at {router_url}")
            await page.goto(router_url, timeout=15000, wait_until="networkidle")

            # Step 2: Log in and obtain stok session token
            stok = await login_and_get_stok(page, router_url, settings.ROUTER_USERNAME, settings.ROUTER_PASSWORD)

            if not stok:
                logger.error("Login succeeded but no stok token received")
                return []

            logger.info("Router login successful, got stok token")

            # Step 3: Fetch DHCP client list using stok-authenticated API
            data = await make_router_api_call(page, stok, router_url, "dhcps", "client")
            if not data:
                logger.warning("DHCP API request failed or returned error")
                return []

            dhcp_list = data.get("result")
            if not isinstance(dhcp_list, list):
                logger.warning(f"DHCP API result is not a list: {type(dhcp_list)}")
                return []

            for item in dhcp_list:
                if not isinstance(item, dict):
                    continue
                entry = _parse_dhcp_dict(item)
                if entry:
                    entries.append(entry)

            logger.info(f"Scraped {len(entries)} DHCP entries from router")

        except RouterLoginError as e:
            logger.error(f"Router login failed (code {e.code}): {e}")
            raise
        except Exception as e:
            logger.error(f"DHCP scrape failed: {e}")
        finally:
            await browser.close()

    return entries


# ── Parsing ──────────────────────────────────────────────────────────────────

def _parse_dhcp_dict(data: dict) -> Optional[dict]:
    """Parse a dict-style DHCP entry from the TP-Link API response.
    Expected keys: name, macaddr, ipaddr, leasetime, interface
    """
    hostname = data.get("name") or data.get("hostname") or data.get("clientName")
    ip = data.get("ipaddr") or data.get("ip") or data.get("ipAddress")
    mac = data.get("macaddr") or data.get("mac") or data.get("macAddress")
    lease = data.get("leasetime") or data.get("lease")

    if not ip:
        return None

    if mac:
        mac = mac.replace("-", ":").upper()

    return {"hostname": hostname, "mac": mac, "ip": ip, "lease": lease}


# ── Persistence ──────────────────────────────────────────────────────────────

async def _record_network_id_dhcp(db, host: Host, ip: str, mac: str | None):
    """Upsert a row in host_network_ids for DHCP-discovered identity."""
    now = datetime.utcnow()
    result = await db.execute(
        select(HostNetworkId).where(
            HostNetworkId.host_id == host.id,
            HostNetworkId.ip_address == ip,
            HostNetworkId.mac_address == mac,
        )
    )
    nid = result.scalar_one_or_none()
    if nid:
        nid.last_seen = now
    else:
        db.add(HostNetworkId(
            host_id=host.id,
            ip_address=ip,
            mac_address=mac,
            source="dhcp",
            first_seen=now,
            last_seen=now,
        ))


async def update_hosts_from_dhcp(entries: list[dict]) -> dict:
    """
    Update existing Host records and create new ones from DHCP data.
    Lookup is by current_ip only — IP is the sole identity key.
    Returns dict: {"updated": int, "created": int}
    """
    if not entries:
        return {"updated": 0, "created": 0}

    updated = 0
    created = 0

    async with AsyncSessionLocal() as db:
        # Load subnets once for assigning new hosts to the right subnet
        subnet_result = await db.execute(select(Subnet).where(Subnet.is_active == True))
        subnets = subnet_result.scalars().all()
        subnet_networks = []
        for s in subnets:
            try:
                subnet_networks.append((s.id, ipaddress.ip_network(s.cidr, strict=False)))
            except ValueError:
                pass

        now = datetime.utcnow()

        for entry in entries:
            ip = entry.get("ip")
            hostname = entry.get("hostname")
            mac = entry.get("mac")

            if not ip:
                continue

            # Skip generic/empty hostnames
            is_valid_hostname = hostname and hostname not in ("*", "--", "N/A", "unknown", "")

            result = await db.execute(select(Host).where(Host.current_ip == ip))
            host = result.scalar_one_or_none()

            # If no match by IP, check by MAC — the device may have gotten a new IP
            if not host and mac:
                result = await db.execute(select(Host).where(Host.current_mac == mac))
                host = result.scalar_one_or_none()
                if host:
                    # Record the IP change
                    old_ip = host.current_ip
                    host.current_ip = ip
                    db.add(HostHistory(
                        host_id=host.id,
                        event_type="ip_change",
                        old_value=old_ip,
                        new_value=ip,
                    ))

            if host:
                changed = False

                if is_valid_hostname and host.hostname != hostname:
                    if host.hostname:
                        db.add(HostHistory(
                            host_id=host.id,
                            event_type="hostname_change",
                            old_value=host.hostname,
                            new_value=hostname,
                        ))
                    host.hostname = hostname
                    changed = True

                if mac and host.current_mac != mac:
                    if host.current_mac:
                        db.add(HostHistory(
                            host_id=host.id,
                            event_type="mac_change",
                            old_value=host.current_mac,
                            new_value=mac,
                        ))
                    host.current_mac = mac
                    changed = True

                await _record_network_id_dhcp(db, host, ip, mac)

                if changed:
                    updated += 1
            else:
                # Create new host from DHCP entry
                subnet_id = None
                try:
                    addr = ipaddress.ip_address(ip)
                    for sid, net in subnet_networks:
                        if addr in net:
                            subnet_id = sid
                            break
                except ValueError:
                    pass

                new_host = Host(
                    hostname=hostname if is_valid_hostname else None,
                    current_ip=ip,
                    current_mac=mac,
                    subnet_id=subnet_id,
                    is_up=True,
                    is_new=True,
                    first_seen=now,
                    last_seen=now,
                )
                db.add(new_host)
                await db.flush()
                await _record_network_id_dhcp(db, new_host, ip, mac)
                created += 1

        await db.commit()

    logger.info(f"DHCP sync: updated {updated}, created {created} hosts")
    return {"updated": updated, "created": created}


# ── Periodic Task ────────────────────────────────────────────────────────────

async def dhcp_scrape_loop():
    """
    Periodic background task that scrapes the router DHCP table
    and updates host records.
    """
    interval = settings.DHCP_SCRAPE_INTERVAL_MIN * 60

    if not settings.ROUTER_URL or not settings.ROUTER_PASSWORD:
        logger.info("DHCP scraper disabled (ROUTER_URL/ROUTER_PASSWORD not set)")
        return

    logger.info(
        f"DHCP scraper started — scraping {settings.ROUTER_URL} "
        f"every {settings.DHCP_SCRAPE_INTERVAL_MIN} min"
    )

    # Run once immediately on startup
    try:
        entries = await scrape_dhcp_table()
        await update_hosts_from_dhcp(entries)
    except Exception as e:
        logger.error(f"Initial DHCP scrape failed: {e}")

    # Then loop on interval
    while True:
        await asyncio.sleep(interval)
        try:
            entries = await scrape_dhcp_table()
            await update_hosts_from_dhcp(entries)
        except asyncio.CancelledError:
            logger.info("DHCP scraper shutting down")
            raise
        except Exception as e:
            logger.error(f"DHCP scrape failed: {e}")
