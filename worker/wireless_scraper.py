"""
Wireless AP client scraper.

Supports two brands:
  - tplink_deco  : TP-Link Deco BE63 (2.0) — browser-based login via Playwright
  - netgear      : Netgear WAX206 AX3200 — browser-based login, Attached Devices page

Results are persisted to HostWirelessClient and used to update Host.connection_type.
Runs as a periodic background task driven by each AP's scrape_interval_min.
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, and_

from shared.db import AsyncSessionLocal
from shared.models import Host, HostNetworkId, HostWirelessClient, WirelessAP

logger = logging.getLogger("worker.wireless_scraper")

# ── Helpers ───────────────────────────────────────────────────────────────────

_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}$")


def _normalise_mac(mac: str) -> str:
    return mac.replace("-", ":").upper()


def _is_valid_mac(mac: Optional[str]) -> bool:
    return bool(mac and _MAC_RE.match(mac))


# ── TP-Link Deco BE63 scraper ─────────────────────────────────────────────────

async def scrape_deco(ap: WirelessAP) -> list[dict]:
    """
    Log into a TP-Link Deco BE63 web UI by driving the SPA via Playwright.

    The Deco uses a hybrid AES+RSA encryption scheme (tpEncrypt.js) that is
    complex to replicate.  Instead, we let the SPA's own JS handle login:
    fill the password field, click LOG IN, intercept the login response for
    the stok, then use the SPA's encryptor to query the client list.

    Returns a list of dicts: {mac, ip, hostname, ssid, band, signal_dbm}
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright not installed — cannot scrape Deco AP")
        return []

    password = ap.password_enc  # already decrypted by caller
    if not password:
        logger.warning(f"AP {ap.name!r}: no password configured, skipping")
        return []

    from urllib.parse import urlparse
    parsed = urlparse(ap.url.rstrip("/"))
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--ignore-certificate-errors"],
        )
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        try:
            logger.info(f"Deco [{ap.name}]: connecting to {base_url}")

            # ── Step 1: Load the SPA, wait for login page to render ────────
            login_ready = asyncio.Event()

            async def _on_response(response):
                if "form=keys" in response.url:
                    try:
                        body = await response.json()
                        if body.get("error_code") == 0:
                            login_ready.set()
                    except Exception:
                        pass

            page.on("response", _on_response)
            await page.goto(
                f"{base_url}/webpages/index.html",
                timeout=20000,
                wait_until="domcontentloaded",
            )

            try:
                await asyncio.wait_for(login_ready.wait(), timeout=15.0)
            except asyncio.TimeoutError:
                logger.error(f"Deco [{ap.name}]: timed out waiting for login page")
                return []

            # Give the SPA a moment to render the login form
            await asyncio.sleep(1)

            logger.info(f"Deco [{ap.name}]: login page ready, filling password")

            # ── Step 2: Fill password and click LOG IN ─────────────────────
            pwd_input = page.locator("input.password-hidden")
            if await pwd_input.count() == 0:
                logger.error(f"Deco [{ap.name}]: password input not found")
                return []

            await pwd_input.fill(password)

            # Click the LOG IN button (use title selector — many a.button-button exist)
            login_btn = page.locator("a.button-button[title='LOG IN']")
            if await login_btn.count() == 0:
                logger.error(f"Deco [{ap.name}]: LOG IN button not found")
                return []

            await login_btn.click()

            # Wait for the SPA to navigate past login (hash → #networkMap)
            try:
                await page.wait_for_function(
                    "() => window.location.hash && !window.location.hash.includes('login')",
                    timeout=15000,
                )
            except Exception:
                # Check if we're on an error dialog or still on login
                current_hash = await page.evaluate("() => window.location.hash")
                logger.error(f"Deco [{ap.name}]: login may have failed, hash={current_hash}")
                return []

            logger.info(f"Deco [{ap.name}]: login successful, navigated to post-login SPA")

            # ── Step 3: Read client list from SPA's data store ─────────────
            # The SPA handles all AES encryption/decryption internally.
            # We read the already-parsed data from its stores.
            return await _deco_fetch_clients_via_page(page, base_url, "", ap.name)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"Deco [{ap.name}]: {exc}", exc_info=True)
            return []
        finally:
            await browser.close()


async def _deco_fetch_clients_via_page(page, base_url: str, stok: str, ap_name: str) -> list[dict]:
    """
    After SPA login, wait for the client_list API call to complete, then read
    client data from the SPA's connectedClientsStore (already decrypted/parsed).
    """
    # Wait for the client_list API call to arrive (the SPA fetches it
    # automatically after navigating to the network map).
    client_list_done = asyncio.Event()

    async def _on_resp(response):
        if "form=client_list" in response.url:
            client_list_done.set()

    page.on("response", _on_resp)

    try:
        await asyncio.wait_for(client_list_done.wait(), timeout=15.0)
    except asyncio.TimeoutError:
        logger.debug(f"Deco [{ap_name}]: client_list API call not seen, trying store anyway")

    # Small delay for SPA to decrypt + populate the store
    await asyncio.sleep(1)

    # Read from the SPA's connectedClientsStore
    clients = await page.evaluate("""
        () => {
            try {
                const store = $.su.storeManager.get("connectedClientsStore");
                if (store) {
                    const data = store.getData();
                    if (data && data.length > 0) {
                        return {ok: true, clients: data, method: "store.getData"};
                    }
                }
            } catch(e) {}
            return {ok: false, clients: [], method: "none"};
        }
    """)

    if clients["ok"] and clients["clients"]:
        logger.info(f"Deco [{ap_name}]: got {len(clients['clients'])} clients via {clients['method']}")
        entries = [_parse_deco_spa_client(c) for c in clients["clients"] if c]
        # Filter out wired clients and entries with no MAC
        entries = [e for e in entries if e.get("mac") and e.get("band") != "wired"]
        logger.info(f"Deco [{ap_name}]: {len(entries)} wireless clients after filtering wired")
        return entries

    logger.warning(f"Deco [{ap_name}]: could not fetch clients ({clients['method']})")
    return []


def _parse_deco_spa_client(item: dict) -> dict:
    """Parse a client record from the SPA's connectedClientsStore format.

    Device names are base64-encoded by the Deco firmware.
    connectionType values: "band2_4", "band5", "band6", "wired".
    """
    mac = item.get("mac") or ""
    mac = _normalise_mac(mac)
    if not _is_valid_mac(mac):
        return {}

    # Decode base64 device name
    hostname = None
    raw_name = item.get("deviceName") or item.get("name")
    if raw_name:
        try:
            import base64
            hostname = base64.b64decode(raw_name).decode("utf-8", errors="replace")
        except Exception:
            hostname = raw_name
    if hostname in ("", "--", "N/A", "unknown"):
        hostname = None

    band = item.get("connectionType") or item.get("connection_type") or None

    return {
        "mac": mac,
        "ip": item.get("ip") or None,
        "hostname": hostname,
        "ssid": None,
        "band": str(band) if band else None,
        "signal_dbm": None,
    }


# ── Netgear WAX206 scraper ────────────────────────────────────────────────────

async def scrape_netgear(ap: WirelessAP) -> list[dict]:
    """
    Log into a Netgear WAX206 admin UI and scrape the Attached Devices page.
    Only rows where the "Connection Type" column contains "Wireless" are returned.

    The WAX206 uses a frameset (index.htm → formframe iframe).  Login is via a
    "Local Device Password" form, then the Attached Devices page is triggered
    by calling click_action('attached') which loads QOS_list_device.htm into
    formframe.

    Returns a list of dicts: {mac, ip, hostname, ssid, band, signal_dbm}
    where band = the full connection type string (e.g. "5GHz Wireless1").
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright not installed — cannot scrape Netgear AP")
        return []

    password = ap.password_enc  # already decrypted by caller
    if not password:
        logger.warning(f"AP {ap.name!r}: no password configured, skipping")
        return []

    url = ap.url.rstrip("/")
    entries: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--ignore-certificate-errors"],
        )
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        try:
            logger.info(f"Netgear [{ap.name}]: connecting to {url}")

            # ── Step 1: Login ──────────────────────────────────────────────
            await page.goto(url, timeout=15000, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # Fill the "Local Device Password" form
            pwd_field = page.locator("#localPasswd")
            if await pwd_field.count() == 0:
                logger.error(f"Netgear [{ap.name}]: #localPasswd not found on login page")
                return entries

            await pwd_field.fill(password)
            await page.locator("#apply").click()
            await asyncio.sleep(3)

            # Handle multi-login page ("You are logged in from another device")
            if "multi_login" in page.url:
                logger.info(f"Netgear [{ap.name}]: multi-login page, clicking Yes")
                yes_btn = page.locator("input[value='Yes']")
                if await yes_btn.count() > 0:
                    await yes_btn.first.click()
                else:
                    await page.get_by_text("Yes").click()
                await asyncio.sleep(4)

            # Verify we landed on the post-login page
            if "index.htm" not in page.url and "basic_home" not in page.url:
                logger.error(f"Netgear [{ap.name}]: login may have failed, url={page.url}")
                return entries

            logger.info(f"Netgear [{ap.name}]: login successful")

            # ── Step 2: Navigate to Attached Devices ───────────────────────
            # The sidebar nav uses click_action('attached') which loads
            # QOS_list_device.htm into the formframe iframe.
            await page.evaluate("click_action('attached')")
            await asyncio.sleep(4)

            # ── Step 3: Extract device data from formframe ─────────────────
            formframe = None
            for frame in page.frames:
                if frame.name == "formframe":
                    formframe = frame
                    break

            if not formframe:
                logger.error(f"Netgear [{ap.name}]: formframe not found")
                return entries

            logger.info(f"Netgear [{ap.name}]: formframe loaded {formframe.url}")

            entries = await _netgear_extract_devices(formframe, ap.name)
            logger.info(f"Netgear [{ap.name}]: found {len(entries)} wireless clients")

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"Netgear [{ap.name}]: unexpected error: {exc}", exc_info=True)
        finally:
            await browser.close()

    return entries


async def _netgear_extract_devices(frame, ap_name: str) -> list[dict]:
    """
    Extract wireless device data from the Netgear Attached Devices table
    (QOS_list_device.htm) loaded in formframe.

    Uses frame.evaluate to parse the table via JS, avoiding issues with
    nested sub-tables in the Device Name column.
    """
    devices = await frame.evaluate("""
        () => {
            // Find #device_table or the largest table
            let table = document.getElementById("device_table");
            if (!table) {
                let maxRows = 0;
                for (const t of document.querySelectorAll("table")) {
                    const rows = t.querySelectorAll(":scope > tbody > tr, :scope > tr");
                    if (rows.length > maxRows) { maxRows = rows.length; table = t; }
                }
            }
            if (!table) return [];

            const rows = table.querySelectorAll(":scope > tbody > tr, :scope > tr");
            const results = [];

            for (let i = 0; i < rows.length; i++) {
                const cells = rows[i].querySelectorAll(":scope > td");
                if (cells.length < 5) continue;

                // MAC address is always the last cell
                const mac = cells[cells.length - 1].textContent.trim();
                if (!/^([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}$/.test(mac)) continue;

                // IP address is second-to-last
                const ip = cells[cells.length - 2].textContent.trim();

                // Connection Type is at index 2 (after checkbox and #)
                const connType = cells[2].textContent.trim();
                if (!connType.toLowerCase().includes("wireless")) continue;

                // Device name: the cell with a nested table (between connType and IP)
                // It's the cell that contains a sub-table. Take the last text from it.
                let hostname = "";
                for (let c = 3; c < cells.length - 2; c++) {
                    const nested = cells[c].querySelectorAll("td");
                    if (nested.length > 0) {
                        hostname = nested[nested.length - 1].textContent.trim();
                        break;
                    }
                    const text = cells[c].textContent.trim();
                    if (text.length > 0) {
                        hostname = text;
                        break;
                    }
                }

                results.push({mac, ip, hostname, band: connType});
            }

            return results;
        }
    """)

    entries: list[dict] = []
    for d in devices:
        mac = _normalise_mac(d.get("mac", ""))
        if not _is_valid_mac(mac):
            continue

        ip = d.get("ip", "")
        if ip and not re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip):
            ip = None

        hostname = d.get("hostname", "")
        if hostname in ("", "---", "--", "N/A", "unknown"):
            hostname = None

        entries.append({
            "mac": mac,
            "ip": ip or None,
            "hostname": hostname,
            "ssid": None,
            "band": d.get("band") or None,
            "signal_dbm": None,
        })

    return entries


# ── Combined scrape ───────────────────────────────────────────────────────────

async def scrape_all_aps() -> list[dict]:
    """
    Load all enabled WirelessAPs from the database, scrape each one,
    decrypt passwords before passing to individual scrapers, and return
    a combined list of client dicts with ap_id injected.
    """
    from shared.crypto import decrypt

    all_entries: list[dict] = []

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WirelessAP).where(WirelessAP.enabled == True)
        )
        aps = list(result.scalars().all())

    for ap in aps:
        # Decrypt password in-memory (don't mutate the ORM object's field)
        plaintext_password: Optional[str] = None
        if ap.password_enc:
            try:
                plaintext_password = decrypt(ap.password_enc)
            except Exception as exc:
                logger.error(f"AP {ap.name!r}: failed to decrypt password: {exc}")
                continue

        # Build a lightweight proxy so scrapers get the plaintext password
        # via ap.password_enc (we temporarily shadow it without touching the DB)
        class _APProxy:
            pass

        proxy = _APProxy()
        for attr in ("id", "name", "brand", "url", "username", "enabled",
                     "notes", "scrape_interval_min"):
            setattr(proxy, attr, getattr(ap, attr))
        proxy.password_enc = plaintext_password  # type: ignore[attr-defined]

        try:
            if ap.brand == "tplink_deco":
                entries = await scrape_deco(proxy)  # type: ignore[arg-type]
            elif ap.brand == "netgear":
                entries = await scrape_netgear(proxy)  # type: ignore[arg-type]
            else:
                logger.warning(f"AP {ap.name!r}: unknown brand {ap.brand!r}, skipping")
                continue
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"AP {ap.name!r}: scrape failed: {exc}", exc_info=True)
            continue

        for entry in entries:
            entry["ap_id"] = ap.id

        all_entries.extend(entries)
        logger.info(f"AP {ap.name!r} ({ap.brand}): scraped {len(entries)} wireless clients")

    return all_entries


# ── Persistence ───────────────────────────────────────────────────────────────

async def persist_wireless_data(entries: list[dict]) -> None:
    """
    Upsert HostWirelessClient rows, link to Host records by MAC, update
    Host.connection_type, and clear connection_type for hosts that have
    dropped off the wireless scan.
    """
    now = datetime.utcnow()
    seen_host_ids: set[int] = set()
    seen_ap_ids: set[int] = set()

    async with AsyncSessionLocal() as db:
        for entry in entries:
            mac = entry.get("mac")
            ap_id = entry.get("ap_id")
            if not mac or not ap_id:
                continue

            seen_ap_ids.add(ap_id)

            # ── Look up matching Host ─────────────────────────────────────
            host_id: Optional[int] = None

            # 1. Match via Host.current_mac
            result = await db.execute(
                select(Host).where(Host.current_mac == mac)
            )
            host = result.scalar_one_or_none()

            # 2. Match via HostNetworkId.mac_address
            if not host:
                result = await db.execute(
                    select(Host)
                    .join(HostNetworkId, HostNetworkId.host_id == Host.id)
                    .where(HostNetworkId.mac_address == mac)
                )
                host = result.scalars().first()

            if host:
                # Follow alias pointer
                if host.primary_host_id is not None:
                    primary = await db.get(Host, host.primary_host_id)
                    if primary:
                        host = primary
                host_id = host.id
                seen_host_ids.add(host_id)
                # Update connection type
                if host.connection_type != "wireless":
                    host.connection_type = "wireless"

            # ── Upsert HostWirelessClient ─────────────────────────────────
            result = await db.execute(
                select(HostWirelessClient).where(
                    and_(
                        HostWirelessClient.ap_id == ap_id,
                        HostWirelessClient.mac_address == mac,
                    )
                )
            )
            client = result.scalar_one_or_none()

            if client:
                client.host_id = host_id
                client.ip_address = entry.get("ip") or client.ip_address
                client.hostname = entry.get("hostname") or client.hostname
                client.ssid = entry.get("ssid") or client.ssid
                client.band = entry.get("band") or client.band
                sig = entry.get("signal_dbm")
                if sig is not None:
                    client.signal_dbm = sig
                client.last_seen = now
            else:
                db.add(HostWirelessClient(
                    ap_id=ap_id,
                    host_id=host_id,
                    mac_address=mac,
                    ip_address=entry.get("ip"),
                    hostname=entry.get("hostname"),
                    ssid=entry.get("ssid"),
                    band=entry.get("band"),
                    signal_dbm=entry.get("signal_dbm"),
                    last_seen=now,
                ))

        # ── Update last_scraped on each AP we processed ───────────────────
        for ap_id in seen_ap_ids:
            ap = await db.get(WirelessAP, ap_id)
            if ap:
                ap.last_scraped = now

        # ── Clear connection_type for recently-disconnected wireless hosts ─
        # Any host that was wireless but was NOT seen in this scan, and whose
        # last_seen is older than 5 minutes, reverts to None (or could be wired).
        cutoff = now - timedelta(minutes=5)
        if seen_ap_ids:
            # Only consider hosts associated with APs we actually ran
            result = await db.execute(
                select(Host).where(
                    and_(
                        Host.connection_type == "wireless",
                        Host.last_seen <= cutoff,
                    )
                )
            )
            stale_hosts = result.scalars().all()
            for host in stale_hosts:
                if host.id not in seen_host_ids:
                    host.connection_type = None

        await db.commit()

    logger.info(
        f"Wireless persist: {len(entries)} entries, "
        f"{len(seen_host_ids)} hosts matched, "
        f"{len(seen_ap_ids)} APs updated"
    )


# ── Periodic background task ──────────────────────────────────────────────────

async def wireless_scrape_loop() -> None:
    """
    Periodic background task.  Runs immediately on startup, then repeats
    on the minimum scrape_interval_min across all enabled APs
    (falls back to WIRELESS_SCRAPE_INTERVAL_MIN from settings).
    """
    from api.config import settings

    # Determine the polling interval
    async def _get_min_interval() -> int:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(WirelessAP).where(WirelessAP.enabled == True)
                )
                aps = result.scalars().all()
                if not aps:
                    return settings.WIRELESS_SCRAPE_INTERVAL_MIN
                return min(ap.scrape_interval_min for ap in aps)
        except Exception:
            return settings.WIRELESS_SCRAPE_INTERVAL_MIN

    interval_min = await _get_min_interval()
    logger.info(f"Wireless scraper started — interval {interval_min} min")

    # Run immediately on startup
    try:
        entries = await scrape_all_aps()
        await persist_wireless_data(entries)
    except asyncio.CancelledError:
        logger.info("Wireless scraper shutting down (initial run)")
        raise
    except Exception as exc:
        logger.error(f"Wireless scrape (initial) failed: {exc}", exc_info=True)

    while True:
        interval_min = await _get_min_interval()
        try:
            await asyncio.sleep(interval_min * 60)
        except asyncio.CancelledError:
            logger.info("Wireless scraper shutting down")
            raise

        try:
            entries = await scrape_all_aps()
            await persist_wireless_data(entries)
        except asyncio.CancelledError:
            logger.info("Wireless scraper shutting down")
            raise
        except Exception as exc:
            logger.error(f"Wireless scrape failed: {exc}", exc_info=True)
