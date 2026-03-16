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


# Full path to our nmap wrapper that runs nmap via passwordless sudo.
# python-nmap tries each entry in nmap_search_path as a binary path.
_NMAP_WRAPPER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "nmap")
NMAP_SEARCH_PATH = (_NMAP_WRAPPER,) if os.path.isfile(_NMAP_WRAPPER) else ("nmap",)


def _can_use_raw_sockets() -> bool:
    """
    Returns True if nmap will run with root privileges — either because the
    process itself is root, or because the nmap-sudo wrapper is available
    (which runs nmap via passwordless sudo).
    """
    return os.geteuid() == 0 or os.path.isfile(_NMAP_WRAPPER)


def read_arp_cache() -> Dict[str, str]:
    """
    Read the OS ARP cache and return {ip: mac} for all complete entries.
    Readable without root. Populated automatically by any outbound network traffic
    to local hosts, so it fills in MACs that nmap misses when not running as root.
    """
    result: Dict[str, str] = {}
    try:
        with open("/proc/net/arp") as f:
            for line in list(f)[1:]:          # skip header row
                parts = line.split()
                if len(parts) >= 4:
                    ip, _hw_type, flags, mac = parts[0], parts[1], parts[2], parts[3]
                    # flags 0x2 = complete (ARP reply received), ignore incomplete/stale
                    if flags == "0x2" and mac != "00:00:00:00:00:00":
                        result[ip] = mac.upper()
    except Exception:
        pass
    return result


def resolve_hostname(ip: str) -> Optional[str]:
    """
    Resolve an IP to a hostname using the system resolver.
    Uses socket.gethostbyaddr() which queries the full resolver chain:
    /etc/hosts, local DNS, mDNS/Avahi, NetBIOS — not just PTR records.
    Returns None if resolution fails.
    """
    import socket
    try:
        hostname, _aliases, _addrs = socket.gethostbyaddr(ip)
        # Ignore if the resolver just echoed back the IP
        if hostname and hostname != ip:
            return hostname
    except (socket.herror, socket.gaierror, OSError):
        pass
    return None


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
    """
    Returns list of IPs that are up. Uses multiple probe types so hosts that
    silently drop ICMP (e.g. Windows firewall, some IoT devices) are still found:
      -PE  ICMP echo
      -PP  ICMP timestamp
      -PS  TCP SYN to common service ports
      -PA  TCP ACK to HTTP/HTTPS (catches hosts that only respond to ACK)
    ARP is used automatically by nmap for local subnets when running as root.
    """
    import nmap
    nm = nmap.PortScanner(nmap_search_path=NMAP_SEARCH_PATH)
    _register_scanner(job_id, nm)
    await _emit(job_id, "tier_start", {"tier": 1, "name": "Host Discovery", "target": cidr})
    loop = asyncio.get_event_loop()
    # TCP SYN/ACK probes require raw sockets (root); fall back gracefully when unavailable.
    if _can_use_raw_sockets():
        probe_args = "-sn -PE -PP -PS22,80,443,3389,8080,8443 -PA80,443 --min-rate 500"
    else:
        probe_args = "-sn -PE --min-rate 500"
    try:
        await loop.run_in_executor(
            None,
            lambda: nm.scan(hosts=cidr, arguments=probe_args)
        )
    finally:
        _deregister_scanner(job_id, nm)
    live_ips = [h for h in nm.all_hosts() if nm[h].state() == "up"]
    logger.info(f"[Job {job_id}] Tier 1: {len(live_ips)} live hosts in {cidr}")
    await _emit(job_id, "tier_done", {"tier": 1, "live_count": len(live_ips)})
    return live_ips


# ── Tier 2: TCP SYN/Connect Scan ─────────────────────────────────────────────

async def tier2_tcp_scan(
    ips: List[str], port_range: str, job_id: int, max_concurrency: int = 10
) -> Dict[str, Any]:
    import nmap
    if not ips:
        return {}
    raw = _can_use_raw_sockets()
    scan_type = "-sS" if raw else "-sT"
    os_flags = "-O --osscan-guess" if raw else ""
    args = f"{scan_type} {os_flags} -p {port_range} --open -T4 --min-rate 300 --max-retries 3 --host-timeout 10m".strip()
    await _emit(job_id, "tier_start", {"tier": 2, "name": "TCP Scan", "host_count": len(ips)})
    loop = asyncio.get_event_loop()
    results: Dict[str, Any] = {}
    done_count = 0
    sem = asyncio.Semaphore(max_concurrency)

    async def scan_one(ip: str):
        nonlocal done_count
        async with sem:
            nm = nmap.PortScanner(nmap_search_path=NMAP_SEARCH_PATH)
            _register_scanner(job_id, nm)
            try:
                await loop.run_in_executor(None, lambda: nm.scan(hosts=ip, arguments=args))
                if ip in nm.all_hosts():
                    results[ip] = _parse_nmap_host(nm[ip])
            except Exception as e:
                logger.warning(f"[Job {job_id}] TCP scan failed for {ip}: {e}")
            finally:
                _deregister_scanner(job_id, nm)
            done_count += 1
            await _emit(job_id, "host_progress", {"tier": 2, "done": done_count, "total": len(ips)})

    await asyncio.gather(*[scan_one(ip) for ip in ips])
    logger.info(f"[Job {job_id}] Tier 2: scanned {len(ips)} hosts, got results for {len(results)}")
    await _emit(job_id, "tier_done", {"tier": 2, "scanned": len(results)})
    return results


# ── Tier 3: UDP Scan (optional) ───────────────────────────────────────────────

async def tier3_udp_scan(
    ips: List[str], port_range: str, job_id: int, max_concurrency: int = 10
) -> Dict[str, Any]:
    import nmap
    if not ips:
        return {}
    await _emit(job_id, "tier_start", {"tier": 3, "name": "UDP Scan", "host_count": len(ips)})
    loop = asyncio.get_event_loop()
    results: Dict[str, Any] = {}
    done_count = 0
    sem = asyncio.Semaphore(max_concurrency)

    async def scan_one(ip: str):
        nonlocal done_count
        async with sem:
            nm = nmap.PortScanner(nmap_search_path=NMAP_SEARCH_PATH)
            _register_scanner(job_id, nm)
            try:
                await loop.run_in_executor(
                    None,
                    lambda: nm.scan(hosts=ip, arguments=f"-sU -p {port_range} --open -T3 --host-timeout 10m")
                )
                if ip in nm.all_hosts():
                    results[ip] = _parse_nmap_host(nm[ip])
            except Exception as e:
                logger.warning(f"[Job {job_id}] UDP scan failed for {ip}: {e}")
            finally:
                _deregister_scanner(job_id, nm)
            done_count += 1
            await _emit(job_id, "host_progress", {"tier": 3, "done": done_count, "total": len(ips)})

    await asyncio.gather(*[scan_one(ip) for ip in ips])
    logger.info(f"[Job {job_id}] Tier 3: UDP results for {len(results)} hosts")
    await _emit(job_id, "tier_done", {"tier": 3, "scanned": len(results)})
    return results


# ── Tier 4: Service Fingerprinting ───────────────────────────────────────────

async def tier4_fingerprint(
    ips: List[str],
    open_ports_map: Dict[str, List[int]],
    job_id: int,
    max_concurrency: int = 10,
) -> Dict[str, Any]:
    import nmap
    if not ips:
        return {}
    await _emit(job_id, "tier_start", {"tier": 4, "name": "Service Fingerprinting", "host_count": len(ips)})
    loop = asyncio.get_event_loop()
    results: Dict[str, Any] = {}
    done_count = 0
    sem = asyncio.Semaphore(max_concurrency)

    async def fingerprint_one(ip: str):
        nonlocal done_count
        ports = open_ports_map.get(ip, [])
        if not ports:
            return
        port_str = ",".join(str(p) for p in ports[:100])
        args = f"-sV --version-intensity 5 -p {port_str} --script=banner"
        async with sem:
            nm = nmap.PortScanner(nmap_search_path=NMAP_SEARCH_PATH)
            _register_scanner(job_id, nm)
            try:
                await loop.run_in_executor(None, lambda: nm.scan(hosts=ip, arguments=args))
                if ip in nm.all_hosts():
                    results[ip] = _parse_nmap_host(nm[ip])
            except Exception as e:
                logger.warning(f"[Job {job_id}] Fingerprint failed for {ip}: {e}")
            finally:
                _deregister_scanner(job_id, nm)
            done_count += 1
            await _emit(job_id, "host_progress", {"tier": 4, "done": done_count, "total": len(ips)})

    await asyncio.gather(*[fingerprint_one(ip) for ip in ips])
    logger.info(f"[Job {job_id}] Tier 4: fingerprinted {len(results)} hosts")
    await _emit(job_id, "tier_done", {"tier": 4, "fingerprinted": len(results)})
    return results


# ── Tier 5: Web Screenshots ───────────────────────────────────────────────────

WEB_PORTS = {80, 443, 8080, 8443, 8000, 8888, 3000}


async def tier5_screenshots(
    web_hosts: List[Dict],
    job_id: int,
    screenshot_dir: str,
    max_concurrency: int = 5,
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
    done_count = 0
    await _emit(job_id, "tier_start", {"tier": 5, "name": "Web Screenshots", "host_count": len(web_hosts)})

    async with async_playwright() as p:
        from api.config import settings
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,
        )
        sem = asyncio.Semaphore(max_concurrency)

        async def screenshot_one(entry: Dict):
            nonlocal done_count
            url = f"{entry['protocol']}://{entry['ip']}:{entry['port']}"
            fname = f"{entry['ip']}_{entry['port']}.png"
            fpath = os.path.join(screenshot_dir, fname)
            async with sem:
                try:
                    page = await context.new_page()
                    await page.goto(url, timeout=settings.SCREENSHOT_TIMEOUT_MS, wait_until="networkidle")
                    await page.screenshot(path=fpath, full_page=False)
                    await page.close()
                    results[f"{entry['ip']}:{entry['port']}"] = fname
                    logger.info(f"[Job {job_id}] Screenshot: {url}")
                except Exception as e:
                    logger.warning(f"[Job {job_id}] Screenshot failed for {url}: {e}")
                done_count += 1
                await _emit(job_id, "host_progress", {"tier": 5, "done": done_count, "total": len(web_hosts)})

        await asyncio.gather(*[screenshot_one(e) for e in web_hosts])
        await browser.close()

    await _emit(job_id, "tier_done", {"tier": 5, "screenshots": len(results)})
    return results
