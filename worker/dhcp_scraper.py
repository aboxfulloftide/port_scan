"""
DHCP hostname scraper — logs into a TP-Link router's web interface via
Playwright, calls the DHCP client API using the stok session token, and
extracts hostname → IP/MAC mappings.  Results are persisted to Host records.

Runs as a periodic background task (configurable interval via
DHCP_SCRAPE_INTERVAL_MIN env var).
"""
import asyncio
import ipaddress
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from api.config import settings
from shared.db import AsyncSessionLocal
from shared.models import Host, HostHistory, Subnet

logger = logging.getLogger("worker.dhcp_scraper")


class RouterLoginError(Exception):
    def __init__(self, code: str, message: str, data: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.data = data or {}


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
            stok = await _login_and_get_stok(page, router_url, settings.ROUTER_USERNAME, settings.ROUTER_PASSWORD)

            if not stok:
                logger.error("Login succeeded but no stok token received")
                return []

            logger.info("Router login successful, got stok token")

            # Step 3: Fetch DHCP client list using stok-authenticated API
            dhcp_url = f"{router_url}/cgi-bin/luci/;stok={stok}/admin/dhcps?form=client"
            result = await page.evaluate("""
                async (url) => {
                    const body = "data=" + encodeURIComponent(JSON.stringify({method: "get", params: {}}));
                    const res = await fetch(url, {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                            "X-Requested-With": "XMLHttpRequest",
                        },
                        body,
                        credentials: "include",
                    });
                    const text = await res.text();
                    return { ok: res.ok, status: res.status, text };
                }
            """, dhcp_url)

            if not result or not result.get("ok"):
                logger.warning(f"DHCP API request failed: HTTP {result.get('status') if result else 'unknown'}")
                return []

            data = json.loads(result.get("text") or "{}")
            err_code = str(data.get("error_code", ""))
            if err_code and err_code != "0":
                logger.warning(f"DHCP API returned error_code={err_code}")
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


# ── Login ────────────────────────────────────────────────────────────────────

async def _login_and_get_stok(page, router_url: str, username: str, password: str) -> Optional[str]:
    """
    Log into a TP-Link router using the JS widget encryption and return the stok token.
    The stok must be included in all subsequent API URL paths.
    """
    # Ensure we're on the login page
    try:
        if "/webpages/login.html" not in page.url:
            await page.goto(f"{router_url}/webpages/login.html", timeout=10000, wait_until="networkidle")
    except Exception:
        pass

    # Wait for TP-Link JS framework
    await page.wait_for_function("window.$ && $.su && $.su.url", timeout=8000)

    # Fill inputs, encrypt password, and read the encrypted value from .val()
    # IMPORTANT: After doEncrypt, the encrypted password is in .val(), NOT .getValue().
    # .getValue() still returns plaintext which causes error_code=700.
    creds = await page.evaluate(
        """
        ({ username, password }) => {
            try { $("#login-username").textbox("setValue", username); } catch (e) { $("#login-username").val(username); }
            try { $("#login-password").password("setValue", password); } catch (e) { $("#login-password").val(password); }

            try { $("#login-password").password("doEncrypt"); } catch (e) {}

            let enc = null;
            try { enc = $("#login-password").val(); } catch (e) {}
            if (!enc) { try { enc = $("input[name='password']").val(); } catch (e) {} }

            return { enc, url: $.su.url("/login?form=login") };
        }
        """,
        {"username": username, "password": password},
    )

    login_url = creds.get("url") if isinstance(creds, dict) else "/login?form=login"
    enc = creds.get("enc") if isinstance(creds, dict) else None
    if not enc:
        enc = password  # last resort — will likely fail with error 700

    # Send login request
    login_resp = await page.evaluate(
        """
        async ({ loginUrl, username, enc }) => {
            const body = "data=" + encodeURIComponent(JSON.stringify({
                method: "login",
                params: { username, password: enc },
            }));
            const res = await fetch(loginUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                },
                body,
                credentials: "include",
            });
            return { ok: res.ok, status: res.status, text: await res.text() };
        }
        """,
        {"loginUrl": login_url, "username": username, "enc": enc},
    )

    if not isinstance(login_resp, dict) or not login_resp.get("text"):
        raise RouterLoginError("no_response", "No response from router login")

    try:
        data = json.loads(login_resp["text"])
    except json.JSONDecodeError:
        raise RouterLoginError("bad_json", f"Non-JSON login response: {login_resp['text'][:200]}")

    err_code = str(data.get("error_code", ""))
    if err_code and err_code != "0":
        result_data = data.get("result") or {}
        raise RouterLoginError(err_code, f"Router login error_code={err_code}", result_data if isinstance(result_data, dict) else {})

    # Extract stok from the login response
    stok = None
    result_data = data.get("result")
    if isinstance(result_data, dict):
        stok = result_data.get("stok")

    return stok


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

async def update_hosts_from_dhcp(entries: list[dict]) -> dict:
    """
    Update existing Host records and create new ones from DHCP data.
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

            # Try to find existing host by IP
            result = await db.execute(select(Host).where(Host.current_ip == ip))
            host = result.scalar_one_or_none()

            # Fallback: try matching by MAC
            if not host and mac:
                result = await db.execute(select(Host).where(Host.current_mac == mac))
                host = result.scalar_one_or_none()

            if host:
                # Update existing host
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
