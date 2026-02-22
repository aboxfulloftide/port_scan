# Task 14: Scan Worker — Core & Queue

## Status: COMPLETE ✅

**Completed:** 2026-02-22
**Files created:** `worker/__init__.py`, `worker/queue.py`, `worker/progress.py`, `worker/pipeline.py`, `worker/main.py`
**Deviations from plan:**
- `resolve_host` uses actual ORM field names: `current_ip`, `current_mac` (plan had `ip_address`, `mac_address`)
- `persist_ports` uses `service_name`/`service_ver` fields (plan had `service`)
- `PortBanner` FK is `host_port_id` (plan had `port_id`)
- `PortScreenshot.file_path` (plan had `filename`)
- `run_job` handles multiple subnet_ids (iterates over `job.subnet_ids` list)
- `ScanJob` uses `completed_at` and `error_message` (plan had `finished_at` and `error_msg`)
- Worker loop started in-process via `asynccontextmanager` lifespan in `api/main.py`
- nmap must be installed separately: `sudo apt install nmap`



**Depends on:** Task 04, Task 02  
**Complexity:** High  
**Description:** Implement the async scan worker process that consumes jobs from an in-memory queue, orchestrates the scan pipeline, and writes results to MySQL.

---

## Files to Create

- `worker/queue.py`
- `worker/main.py`
- `worker/pipeline.py`
- `worker/progress.py`

---

## `worker/queue.py`

```python
import asyncio

# Shared asyncio queue between API and worker (same process)
job_queue: asyncio.Queue = asyncio.Queue()
```

---

## `worker/progress.py`

```python
"""
Broadcast scan progress events to connected WebSocket clients.
"""
import asyncio
from typing import Dict, Set

# job_id -> set of asyncio.Queue (one per WS client)
_subscribers: Dict[int, Set[asyncio.Queue]] = {}

def subscribe(job_id: int) -> asyncio.Queue:
    q = asyncio.Queue(maxsize=256)
    _subscribers.setdefault(job_id, set()).add(q)
    return q

def unsubscribe(job_id: int, q: asyncio.Queue):
    if job_id in _subscribers:
        _subscribers[job_id].discard(q)
        if not _subscribers[job_id]:
            del _subscribers[job_id]

async def broadcast(job_id: int, event: dict):
    for q in list(_subscribers.get(job_id, [])):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass  # slow consumer — drop event
```

---

## `worker/pipeline.py`

```python
"""
Tiered scan pipeline:
  Tier 1 — ICMP ping sweep
  Tier 2 — TCP SYN / Connect scan (nmap)
  Tier 3 — UDP scan (nmap, optional per profile)
  Tier 4 — Service fingerprinting + banner grab (nmap -sV)
  Tier 5 — Web screenshot (Playwright)
"""
import asyncio
import logging
import nmap
from typing import List, Dict, Any
from shared.db import AsyncSessionLocal
from shared.models import (
    Host, HostPort, PortBanner, ScanJob, Subnet, ScanProfile
)
from worker.progress import broadcast
from sqlalchemy import select

logger = logging.getLogger("worker.pipeline")

# ── Helpers ───────────────────────────────────────────────────────────────────

async def _emit(job_id: int, event_type: str, data: dict):
    await broadcast(job_id, {"type": event_type, **data})

def _parse_nmap_host(host_data) -> Dict[str, Any]:
    """Extract structured data from python-nmap host result."""
    result = {
        "ip": host_data.get("addresses", {}).get("ipv4"),
        "mac": host_data.get("addresses", {}).get("mac"),
        "hostname": None,
        "ports": [],
        "os_guess": None,
    }
    hostnames = host_data.get("hostnames", [])
    if hostnames:
        result["hostname"] = hostnames[0].get("name")
    osmatch = host_data.get("osmatch", [])
    if osmatch:
        result["os_guess"] = osmatch[0].get("name")
    for proto in ("tcp", "udp"):
        for port_num, port_info in host_data.get(proto, {}).items():
            result["ports"].append({
                "protocol": proto,
                "port": port_num,
                "state": port_info.get("state"),
                "service": port_info.get("name"),
                "product": port_info.get("product"),
                "version": port_info.get("version"),
                "banner": port_info.get("script", {}).get("banner"),
            })
    return result

# ── Tier 1: ICMP Ping Sweep ───────────────────────────────────────────────────

async def tier1_ping_sweep(cidr: str, job_id: int) -> List[str]:
    """Returns list of IPs that responded to ping."""
    nm = nmap.PortScanner()
    await _emit(job_id, "tier_start", {"tier": 1, "name": "ICMP Ping Sweep", "target": cidr})
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: nm.scan(hosts=cidr, arguments="-sn -PE --min-rate 500"))
    live_ips = [h for h in nm.all_hosts() if nm[h].state() == "up"]
    await _emit(job_id, "tier_done", {"tier": 1, "live_count": len(live_ips)})
    return live_ips

# ── Tier 2: TCP SYN Scan ──────────────────────────────────────────────────────

async def tier2_tcp_scan(ips: List[str], port_range: str, job_id: int) -> Dict[str, Any]:
    nm = nmap.PortScanner()
    targets = " ".join(ips)
    args = f"-sS -p {port_range} --open -T4 --min-rate 300"
    await _emit(job_id, "tier_start", {"tier": 2, "name": "TCP SYN Scan", "host_count": len(ips)})
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: nm.scan(hosts=targets, arguments=args))
    results = {h: _parse_nmap_host(nm[h]) for h in nm.all_hosts()}
    await _emit(job_id, "tier_done", {"tier": 2, "scanned": len(results)})
    return results

# ── Tier 3: UDP Scan (optional) ───────────────────────────────────────────────

async def tier3_udp_scan(ips: List[str], port_range: str, job_id: int) -> Dict[str, Any]:
    nm = nmap.PortScanner()
    targets = " ".join(ips)
    args = f"-sU -p {port_range} --open -T3"
    await _emit(job_id, "tier_start", {"tier": 3, "name": "UDP Scan", "host_count": len(ips)})
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: nm.scan(hosts=targets, arguments=args))
    results = {h: _parse_nmap_host(nm[h]) for h in nm.all_hosts()}
    await _emit(job_id, "tier_done", {"tier": 3, "scanned": len(results)})
    return results

# ── Tier 4: Service Fingerprinting ───────────────────────────────────────────

async def tier4_fingerprint(ips: List[str], open_ports: Dict[str, List[int]], job_id: int) -> Dict[str, Any]:
    nm = nmap.PortScanner()
    await _emit(job_id, "tier_start", {"tier": 4, "name": "Service Fingerprinting"})
    results = {}
    loop = asyncio.get_event_loop()
    for ip in ips:
        ports = open_ports.get(ip, [])
        if not ports:
            continue
        port_str = ",".join(str(p) for p in ports)
        args = f"-sV --version-intensity 5 -p {port_str} --script=banner"
        await loop.run_in_executor(None, lambda: nm.scan(hosts=ip, arguments=args))
        if ip in nm.all_hosts():
            results[ip] = _parse_nmap_host(nm[ip])
    await _emit(job_id, "tier_done", {"tier": 4, "fingerprinted": len(results)})
    return results

# ── Tier 5: Web Screenshots ───────────────────────────────────────────────────

async def tier5_screenshots(web_hosts: List[Dict], job_id: int, screenshot_dir: str) -> Dict[str, str]:
    """web_hosts: list of {ip, port, protocol (http/https)}"""
    from playwright.async_api import async_playwright
    import os
    results = {}
    await _emit(job_id, "tier_start", {"tier": 5, "name": "Web Screenshots", "count": len(web_hosts)})
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        for entry in web_hosts:
            url = f"{entry['protocol']}://{entry['ip']}:{entry['port']}"
            fname = f"{entry['ip']}_{entry['port']}.png"
            fpath = os.path.join(screenshot_dir, fname)
            try:
                page = await browser.new_page()
                await page.goto(url, timeout=8000, wait_until="domcontentloaded")
                await page.screenshot(path=fpath, full_page=False)
                await page.close()
                results[f"{entry['ip']}:{entry['port']}"] = fname
            except Exception as e:
                logger.warning(f"Screenshot failed for {url}: {e}")
        await browser.close()
    await _emit(job_id, "tier_done", {"tier": 5, "screenshots": len(results)})
    return results
```

---

## `worker/main.py`

```python
"""
Scan worker — runs in the same process as the API (via asyncio task).
Consumes job IDs from job_queue and executes the scan pipeline.
"""
import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy import select
from shared.db import AsyncSessionLocal
from shared.models import ScanJob, Subnet, ScanProfile, Host, HostPort, PortBanner, PortScreenshot, HostHistory
from worker.queue import job_queue
from worker.pipeline import (
    tier1_ping_sweep, tier2_tcp_scan, tier3_udp_scan,
    tier4_fingerprint, tier5_screenshots
)
from worker.progress import broadcast
from config import settings

logger = logging.getLogger("worker")

# ── Host Identity Resolution ──────────────────────────────────────────────────

async def resolve_host(db, ip: str, hostname: str, mac: str) -> Host:
    """
    Find or create a host record.
    Primary identity: hostname (if available), fallback to IP.
    Detect IP/MAC drift and log to host_history.
    """
    host = None
    if hostname:
        result = await db.execute(select(Host).where(Host.hostname == hostname))
        host = result.scalar_one_or_none()
    if not host:
        result = await db.execute(select(Host).where(Host.ip_address == ip))
        host = result.scalar_one_or_none()

    if not host:
        host = Host(
            hostname=hostname,
            ip_address=ip,
            mac_address=mac,
            is_new=True,
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
        )
        db.add(host)
        await db.flush()
        logger.info(f"New host discovered: {hostname or ip}")
    else:
        changes = {}
        if host.ip_address != ip:
            changes["ip_address"] = {"old": host.ip_address, "new": ip}
            host.ip_address = ip
        if mac and host.mac_address != mac:
            changes["mac_address"] = {"old": host.mac_address, "new": mac}
            host.mac_address = mac
        if changes:
            hist = HostHistory(host_id=host.id, changes=str(changes))
            db.add(hist)
        host.last_seen = datetime.now(timezone.utc)
        host.status = "up"
    return host

# ── Port Persistence ──────────────────────────────────────────────────────────

async def persist_ports(db, host: Host, ports: list, job_id: int):
    for p in ports:
        result = await db.execute(
            select(HostPort).where(
                HostPort.host_id == host.id,
                HostPort.port == p["port"],
                HostPort.protocol == p["protocol"]
            )
        )
        port_rec = result.scalar_one_or_none()
        if not port_rec:
            port_rec = HostPort(
                host_id=host.id,
                port=p["port"],
                protocol=p["protocol"],
                state=p["state"],
                service=p["service"],
                is_new=True,
            )
            db.add(port_rec)
            await db.flush()
        else:
            port_rec.state = p["state"]
            port_rec.service = p["service"]
            port_rec.last_seen = datetime.now(timezone.utc)

        if p.get("banner"):
            banner = PortBanner(
                port_id=port_rec.id,
                raw_banner=p["banner"],
                product=p.get("product"),
                version=p.get("version"),
                scan_job_id=job_id,
            )
            db.add(banner)

# ── Main Worker Loop ──────────────────────────────────────────────────────────

async def run_job(job_id: int):
    async with AsyncSessionLocal() as db:
        job = await db.get(ScanJob, job_id)
        if not job:
            return
        subnet = await db.get(Subnet, job.subnet_id)
        profile = await db.get(ScanProfile, job.profile_id)

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

        await broadcast(job_id, {"type": "job_start", "job_id": job_id, "subnet": subnet.cidr})

        try:
            # Tier 1
            live_ips = await tier1_ping_sweep(subnet.cidr, job_id)

            # Tier 2
            tcp_results = await tier2_tcp_scan(live_ips, profile.port_range, job_id)

            # Tier 3 (optional)
            udp_results = {}
            if profile.enable_udp:
                udp_results = await tier3_udp_scan(live_ips, profile.port_range, job_id)

            # Merge TCP + UDP
            all_results = {**tcp_results}
            for ip, data in udp_results.items():
                if ip in all_results:
                    all_results[ip]["ports"].extend(data["ports"])
                else:
                    all_results[ip] = data

            # Tier 4
            open_ports_map = {
                ip: [p["port"] for p in data["ports"] if p["state"] == "open"]
                for ip, data in all_results.items()
            }
            fp_results = await tier4_fingerprint(list(all_results.keys()), open_ports_map, job_id)
            for ip, data in fp_results.items():
                if ip in all_results:
                    all_results[ip].update(data)

            # Persist hosts and ports
            web_hosts = []
            for ip, data in all_results.items():
                host = await resolve_host(db, ip, data.get("hostname"), data.get("mac"))
                host.os_guess = data.get("os_guess")
                await persist_ports(db, host, data.get("ports", []), job_id)
                for p in data.get("ports", []):
                    if p["service"] in ("http", "https", "http-alt") and p["state"] == "open":
                        web_hosts.append({"ip": ip, "port": p["port"], "protocol": p["service"].replace("-alt", "")})

            await db.commit()

            # Tier 5
            if profile.enable_screenshots and web_hosts:
                screenshots = await tier5_screenshots(web_hosts, job_id, settings.SCREENSHOT_DIR)
                async with AsyncSessionLocal() as db2:
                    for key, fname in screenshots.items():
                        ip, port = key.split(":")
                        result = await db2.execute(
                            select(HostPort).join(Host).where(
                                Host.ip_address == ip,
                                HostPort.port == int(port)
                            )
                        )
                        port_rec = result.scalar_one_or_none()
                        if port_rec:
                            ss = PortScreenshot(port_id=port_rec.id, filename=fname, scan_job_id=job_id)
                            db2.add(ss)
                    await db2.commit()

            job.status = "completed"
            job.hosts_found = len(all_results)
        except asyncio.CancelledError:
            job.status = "cancelled"
            raise
        except Exception as e:
            job.status = "failed"
            job.error_msg = str(e)
            logger.exception(f"Job {job_id} failed: {e}")
        finally:
            job.finished_at = datetime.now(timezone.utc)
            await db.commit()
            await broadcast(job_id, {"type": "job_done", "job_id": job_id, "status": job.status})

async def worker_loop():
    logger.info("Scan worker started")
    running_jobs: dict[int, asyncio.Task] = {}
    while True:
        job_id = await job_queue.get()
        if job_id is None:  # shutdown signal
            break
        task = asyncio.create_task(run_job(job_id))
        running_jobs[job_id] = task
        task.add_done_callback(lambda t, jid=job_id: running_jobs.pop(jid, None))
```

---

## Startup Integration

In `api/main.py` lifespan:
```python
from worker.main import worker_loop
import asyncio

_worker_task = None

async def startup():
    global _worker_task
    _worker_task = asyncio.create_task(worker_loop())

async def shutdown():
    from worker.queue import job_queue
    await job_queue.put(None)  # signal worker to stop
    if _worker_task:
        await _worker_task
```
