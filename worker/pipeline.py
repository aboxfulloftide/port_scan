"""
Tiered scan pipeline:
  Tier 1 — ICMP ping sweep          (nmap -sn)
  Tier 2 — TCP SYN / Connect scan   (nmap -sS or -sT)
  Tier 3 — UDP scan                 (nmap -sU, optional per profile)
  Tier 4 — Service fingerprinting   (nmap -sV + banner script)
  Tier 5 — Web screenshots          (Playwright)
"""
import asyncio
import logging
import os
from typing import List, Dict, Any, Optional

logger = logging.getLogger("worker.pipeline")

# Registry of active nmap scanners keyed by job_id — used for hard cancellation
_active_scanners: dict[int, list] = {}


def _register_scanner(job_id: int, nm) -> None:
    _active_scanners.setdefault(job_id, []).append(nm)


def _deregister_scanner(job_id: int, nm) -> None:
    scanners = _active_scanners.get(job_id, [])
    if nm in scanners:
        scanners.remove(nm)
    if not scanners:
        _active_scanners.pop(job_id, None)


def kill_job_scanners(job_id: int) -> None:
    """Kill all active nmap subprocesses for a job. Safe to call at any time."""
    for nm in _active_scanners.pop(job_id, []):
        try:
            proc = getattr(nm, "_nm_proc", None)
            if proc and proc.poll() is None:
                proc.kill()
                logger.info(f"[Job {job_id}] Killed nmap process (pid {proc.pid})")
        except Exception as e:
            logger.warning(f"[Job {job_id}] Error killing nmap process: {e}")


async def _emit(job_id: int, event_type: str, data: dict):
    from worker.progress import broadcast
    await broadcast(job_id, {"type": event_type, **data})


def _parse_nmap_host(host_data) -> Dict[str, Any]:
    """Extract structured data from a python-nmap host result dict."""
    result: Dict[str, Any] = {
        "ip": host_data.get("addresses", {}).get("ipv4"),
        "mac": host_data.get("addresses", {}).get("mac"),
        "hostname": None,
        "vendor": host_data.get("vendor", {}).get(
            host_data.get("addresses", {}).get("mac", ""), None
        ),
        "ports": [],
        "os_guess": None,
    }
    hostnames = host_data.get("hostnames", [])
    if hostnames:
        result["hostname"] = hostnames[0].get("name") or None
    osmatch = host_data.get("osmatch", [])
    if osmatch:
        result["os_guess"] = osmatch[0].get("name")
    for proto in ("tcp", "udp"):
        for port_num, port_info in host_data.get(proto, {}).items():
            product = port_info.get("product", "")
            version = port_info.get("version", "")
            service_ver = f"{product} {version}".strip() or None
            result["ports"].append({
                "protocol": proto,
                "port": int(port_num),
                "state": port_info.get("state", "unknown"),
                "service_name": port_info.get("name"),
                "service_ver": service_ver,
                "banner": port_info.get("script", {}).get("banner"),
            })
    return result


# ── Tier 1: ICMP Ping Sweep ───────────────────────────────────────────────────

async def tier1_ping_sweep(cidr: str, job_id: int) -> List[str]:
    """Returns list of IPs that responded to ping."""
    import nmap
    nm = nmap.PortScanner()
    _register_scanner(job_id, nm)
    await _emit(job_id, "tier_start", {"tier": 1, "name": "ICMP Ping Sweep", "target": cidr})
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(
            None,
            lambda: nm.scan(hosts=cidr, arguments="-sn -PE --min-rate 500")
        )
    finally:
        _deregister_scanner(job_id, nm)
    live_ips = [h for h in nm.all_hosts() if nm[h].state() == "up"]
    logger.info(f"[Job {job_id}] Tier 1: {len(live_ips)} live hosts in {cidr}")
    await _emit(job_id, "tier_done", {"tier": 1, "live_count": len(live_ips)})
    return live_ips


# ── Tier 2: TCP SYN/Connect Scan ─────────────────────────────────────────────

async def tier2_tcp_scan(ips: List[str], port_range: str, job_id: int) -> Dict[str, Any]:
    import nmap
    if not ips:
        return {}
    nm = nmap.PortScanner()
    _register_scanner(job_id, nm)
    targets = " ".join(ips)
    import os
    scan_type = "-sS" if os.geteuid() == 0 else "-sT"
    args = f"{scan_type} -p {port_range} --open -T4 --min-rate 300"
    await _emit(job_id, "tier_start", {"tier": 2, "name": "TCP Scan", "host_count": len(ips)})
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, lambda: nm.scan(hosts=targets, arguments=args))
    finally:
        _deregister_scanner(job_id, nm)
    results = {h: _parse_nmap_host(nm[h]) for h in nm.all_hosts()}
    logger.info(f"[Job {job_id}] Tier 2: scanned {len(ips)} hosts, got results for {len(results)}")
    await _emit(job_id, "tier_done", {"tier": 2, "scanned": len(results)})
    return results


# ── Tier 3: UDP Scan (optional) ───────────────────────────────────────────────

async def tier3_udp_scan(ips: List[str], port_range: str, job_id: int) -> Dict[str, Any]:
    import nmap
    if not ips:
        return {}
    nm = nmap.PortScanner()
    _register_scanner(job_id, nm)
    targets = " ".join(ips)
    args = f"-sU -p {port_range} --open -T3"
    await _emit(job_id, "tier_start", {"tier": 3, "name": "UDP Scan", "host_count": len(ips)})
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, lambda: nm.scan(hosts=targets, arguments=args))
    finally:
        _deregister_scanner(job_id, nm)
    results = {h: _parse_nmap_host(nm[h]) for h in nm.all_hosts()}
    logger.info(f"[Job {job_id}] Tier 3: UDP results for {len(results)} hosts")
    await _emit(job_id, "tier_done", {"tier": 3, "scanned": len(results)})
    return results


# ── Tier 4: Service Fingerprinting ───────────────────────────────────────────

async def tier4_fingerprint(
    ips: List[str],
    open_ports_map: Dict[str, List[int]],
    job_id: int
) -> Dict[str, Any]:
    import nmap
    if not ips:
        return {}
    nm = nmap.PortScanner()
    await _emit(job_id, "tier_start", {"tier": 4, "name": "Service Fingerprinting"})
    results: Dict[str, Any] = {}
    loop = asyncio.get_event_loop()
    for ip in ips:
        ports = open_ports_map.get(ip, [])
        if not ports:
            continue
        port_str = ",".join(str(p) for p in ports[:100])  # cap at 100 ports
        args = f"-sV --version-intensity 5 -p {port_str} --script=banner"
        _register_scanner(job_id, nm)
        try:
            await loop.run_in_executor(None, lambda: nm.scan(hosts=ip, arguments=args))
            if ip in nm.all_hosts():
                results[ip] = _parse_nmap_host(nm[ip])
        except Exception as e:
            logger.warning(f"[Job {job_id}] Fingerprint failed for {ip}: {e}")
        finally:
            _deregister_scanner(job_id, nm)
    logger.info(f"[Job {job_id}] Tier 4: fingerprinted {len(results)} hosts")
    await _emit(job_id, "tier_done", {"tier": 4, "fingerprinted": len(results)})
    return results


# ── Tier 5: Web Screenshots ───────────────────────────────────────────────────

WEB_PORTS = {80, 443, 8080, 8443, 8000, 8888, 3000}


async def tier5_screenshots(
    web_hosts: List[Dict],
    job_id: int,
    screenshot_dir: str
) -> Dict[str, str]:
    """
    web_hosts: list of {"ip": str, "port": int, "protocol": "http"/"https"}
    Returns dict of "ip:port" -> "filename.png"
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning(f"[Job {job_id}] Playwright not installed — skipping screenshots")
        return {}

    os.makedirs(screenshot_dir, exist_ok=True)
    results: Dict[str, str] = {}
    await _emit(job_id, "tier_start", {"tier": 5, "name": "Web Screenshots", "count": len(web_hosts)})

    async with async_playwright() as p:
        from api.config import settings
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,
        )
        for entry in web_hosts:
            url = f"{entry['protocol']}://{entry['ip']}:{entry['port']}"
            fname = f"{entry['ip']}_{entry['port']}.png"
            fpath = os.path.join(screenshot_dir, fname)
            try:
                page = await context.new_page()
                await page.goto(url, timeout=settings.SCREENSHOT_TIMEOUT_MS, wait_until="networkidle")
                await page.screenshot(path=fpath, full_page=False)
                await page.close()
                results[f"{entry['ip']}:{entry['port']}"] = fname
                logger.info(f"[Job {job_id}] Screenshot: {url}")
            except Exception as e:
                logger.warning(f"[Job {job_id}] Screenshot failed for {url}: {e}")
        await browser.close()

    await _emit(job_id, "tier_done", {"tier": 5, "screenshots": len(results)})
    return results
