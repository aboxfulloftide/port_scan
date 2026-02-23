"""
Scan worker — runs as an asyncio background task in the same process as the API.
Consumes job IDs from job_queue and executes the scan pipeline.
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from sqlalchemy import select

from shared.db import AsyncSessionLocal
from shared.models import (
    ScanJob, Subnet, ScanProfile, Host, HostPort,
    PortBanner, PortScreenshot, HostHistory
)
from worker.queue import job_queue
from worker.pipeline import (
    tier1_ping_sweep, tier2_tcp_scan, tier3_udp_scan,
    tier4_fingerprint, tier5_screenshots, WEB_PORTS
)
from worker.progress import broadcast

logger = logging.getLogger("worker")

# Module-level registry so the cancel endpoint can look up and cancel running tasks
running_jobs: dict[int, asyncio.Task] = {}

SCREENSHOT_DIR = os.getenv(
    "SCREENSHOT_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "screenshots")
)


# ── Host Identity Resolution ──────────────────────────────────────────────────

async def resolve_host(db, ip: str, hostname: str | None, mac: str | None) -> tuple[Host, bool]:
    """
    Find or create a Host record. Returns (host, is_new).
    Primary identity: hostname (if available), then IP.
    Logs IP/MAC drift to host_history.
    """
    host = None
    is_new_host = False

    if hostname:
        result = await db.execute(select(Host).where(Host.hostname == hostname))
        host = result.scalar_one_or_none()

    if not host:
        result = await db.execute(select(Host).where(Host.current_ip == ip))
        host = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if not host:
        host = Host(
            hostname=hostname or None,
            current_ip=ip,
            current_mac=mac,
            is_up=True,
            is_new=True,
            first_seen=now,
            last_seen=now,
        )
        db.add(host)
        await db.flush()
        is_new_host = True
        logger.info(f"New host: {hostname or ip}")
    else:
        # Detect drift
        if host.current_ip != ip:
            db.add(HostHistory(
                host_id=host.id,
                event_type="ip_change",
                old_value=host.current_ip,
                new_value=ip,
            ))
            host.current_ip = ip

        if mac and host.current_mac != mac:
            db.add(HostHistory(
                host_id=host.id,
                event_type="mac_change",
                old_value=host.current_mac,
                new_value=mac,
            ))
            host.current_mac = mac

        if hostname and host.hostname != hostname:
            db.add(HostHistory(
                host_id=host.id,
                event_type="hostname_change",
                old_value=host.hostname,
                new_value=hostname,
            ))
            host.hostname = hostname

        if not host.is_up:
            db.add(HostHistory(
                host_id=host.id,
                event_type="status_change",
                old_value="down",
                new_value="up",
            ))

        host.is_up = True
        host.last_seen = now

    return host, is_new_host


# ── Port Persistence ──────────────────────────────────────────────────────────

async def persist_ports(db, host: Host, ports: list, job_id: int) -> tuple[int, int]:
    """
    Upsert port records. Returns (new_ports_count, total_open_count).
    """
    now = datetime.now(timezone.utc)
    new_ports = 0
    open_ports = 0

    for p in ports:
        if p["state"] != "open":
            continue
        open_ports += 1

        result = await db.execute(
            select(HostPort).where(
                HostPort.host_id == host.id,
                HostPort.port == p["port"],
                HostPort.protocol == p["protocol"],
            )
        )
        port_rec = result.scalar_one_or_none()

        if not port_rec:
            port_rec = HostPort(
                host_id=host.id,
                port=p["port"],
                protocol=p["protocol"],
                state=p["state"],
                service_name=p.get("service_name"),
                service_ver=p.get("service_ver"),
                is_new=True,
                first_seen=now,
                last_seen=now,
            )
            db.add(port_rec)
            await db.flush()
            new_ports += 1
        else:
            port_rec.state = p["state"]
            port_rec.service_name = p.get("service_name") or port_rec.service_name
            port_rec.service_ver = p.get("service_ver") or port_rec.service_ver
            port_rec.last_seen = now

        if p.get("banner"):
            db.add(PortBanner(
                host_port_id=port_rec.id,
                banner_text=p["banner"][:4096] if p["banner"] else None,
                captured_at=now,
            ))

    return new_ports, open_ports


# ── Main Job Runner ───────────────────────────────────────────────────────────

async def run_job(job_id: int):
    logger.info(f"Starting job {job_id}")

    async with AsyncSessionLocal() as db:
        job = await db.get(ScanJob, job_id)
        if not job:
            logger.error(f"Job {job_id} not found in DB")
            return

        # Guard: already running/done (e.g. duplicate queue entry)
        if job.status not in ("queued",):
            logger.warning(f"Job {job_id} has status '{job.status}', skipping")
            return

        profile = await db.get(ScanProfile, job.profile_id)
        if not profile:
            job.status = "failed"
            job.error_message = "Scan profile not found"
            await db.commit()
            return

        # Collect subnet CIDRs
        subnet_ids = job.subnet_ids if isinstance(job.subnet_ids, list) else []
        cidrs: list[str] = []
        for sid in subnet_ids:
            subnet = await db.get(Subnet, sid)
            if subnet:
                cidrs.append(subnet.cidr)

        if not cidrs:
            job.status = "failed"
            job.error_message = "No valid subnets found"
            await db.commit()
            return

        # Mark running
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    await broadcast(job_id, {"type": "job_start", "job_id": job_id, "subnets": cidrs})

    # Track totals across all subnets
    all_results: dict = {}
    all_live_ips: list[str] = []

    try:
        for cidr in cidrs:
            # Check for cancellation before each subnet
            async with AsyncSessionLocal() as db:
                job_check = await db.get(ScanJob, job_id)
                if job_check and job_check.status == "cancelled":
                    logger.info(f"Job {job_id} cancelled before subnet {cidr}")
                    return

            # Tier 1: Ping sweep
            live_ips = await tier1_ping_sweep(cidr, job_id)
            all_live_ips.extend(live_ips)

            if not live_ips:
                logger.info(f"[Job {job_id}] No live hosts in {cidr}")
                continue

            # Tier 2: TCP scan
            tcp_results = await tier2_tcp_scan(live_ips, profile.port_range, job_id)

            # Tier 3: UDP scan (optional)
            if profile.enable_udp:
                udp_results = await tier3_udp_scan(live_ips, profile.port_range, job_id)
                for ip, data in udp_results.items():
                    if ip in tcp_results:
                        tcp_results[ip]["ports"].extend(data["ports"])
                    else:
                        tcp_results[ip] = data

            all_results.update(tcp_results)

            # Update live host count in DB
            async with AsyncSessionLocal() as db:
                job_upd = await db.get(ScanJob, job_id)
                if job_upd:
                    job_upd.hosts_discovered = len(all_live_ips)
                    await db.commit()

        # Tier 4: Service fingerprinting
        if profile.enable_fingerprint and all_results:
            open_ports_map = {
                ip: [p["port"] for p in data["ports"] if p["state"] == "open"]
                for ip, data in all_results.items()
            }
            fp_results = await tier4_fingerprint(
                [ip for ip, ports in open_ports_map.items() if ports],
                open_ports_map,
                job_id
            )
            # Merge fingerprint data into results (richer service info)
            for ip, fp_data in fp_results.items():
                if ip in all_results:
                    # Replace ports with enriched version
                    all_results[ip]["ports"] = fp_data["ports"]
                    all_results[ip]["os_guess"] = fp_data.get("os_guess") or all_results[ip].get("os_guess")

        # Persist hosts and ports
        total_new_hosts = 0
        total_new_ports = 0
        total_hosts_up = 0
        web_targets = []

        async with AsyncSessionLocal() as db:
            for ip, data in all_results.items():
                host, is_new = await resolve_host(
                    db, ip, data.get("hostname"), data.get("mac")
                )
                host.os_guess = data.get("os_guess") or host.os_guess
                host.vendor = data.get("vendor") or host.vendor

                new_p, open_p = await persist_ports(db, host, data.get("ports", []), job_id)
                total_new_ports += new_p
                if is_new:
                    total_new_hosts += 1
                total_hosts_up += 1

                # Collect web targets for screenshots
                if profile.enable_screenshot:
                    for p in data.get("ports", []):
                        if p["state"] != "open":
                            continue
                        port_num = p["port"]
                        svc = (p.get("service_name") or "").lower()
                        is_web = port_num in WEB_PORTS or "http" in svc
                        if is_web:
                            protocol = "https" if (port_num in (443, 8443) or "https" in svc) else "http"
                            web_targets.append({"ip": ip, "port": port_num, "protocol": protocol})

            await db.commit()

        # Tier 5: Screenshots
        screenshot_map: dict = {}
        if profile.enable_screenshot and web_targets:
            screenshot_map = await tier5_screenshots(web_targets, job_id, SCREENSHOT_DIR)

            # Persist screenshot records
            async with AsyncSessionLocal() as db:
                for key, fname in screenshot_map.items():
                    ip, port_str = key.split(":")
                    result = await db.execute(
                        select(HostPort)
                        .join(Host, HostPort.host_id == Host.id)
                        .where(
                            Host.current_ip == ip,
                            HostPort.port == int(port_str),
                        )
                    )
                    port_rec = result.scalar_one_or_none()
                    if port_rec:
                        db.add(PortScreenshot(
                            host_port_id=port_rec.id,
                            file_path=fname,
                            url_captured=f"http://{ip}:{port_str}",
                            captured_at=datetime.now(timezone.utc),
                        ))
                await db.commit()

        # Finalize job
        async with AsyncSessionLocal() as db:
            job = await db.get(ScanJob, job_id)
            if job:
                # Recheck — may have been cancelled while scanning
                if job.status != "cancelled":
                    job.status = "completed"
                job.hosts_discovered = len(all_live_ips)
                job.hosts_up = total_hosts_up
                job.new_hosts_found = total_new_hosts
                job.new_ports_found = total_new_ports
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()

        logger.info(
            f"Job {job_id} done: {total_hosts_up} up, "
            f"{total_new_hosts} new hosts, {total_new_ports} new ports"
        )
        await broadcast(job_id, {
            "type": "job_done",
            "job_id": job_id,
            "status": "completed",
            "hosts_up": total_hosts_up,
            "new_hosts_found": total_new_hosts,
            "new_ports_found": total_new_ports,
        })

    except asyncio.CancelledError:
        async with AsyncSessionLocal() as db:
            job = await db.get(ScanJob, job_id)
            if job:
                job.status = "cancelled"
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()
        await broadcast(job_id, {"type": "job_done", "job_id": job_id, "status": "cancelled"})
        raise

    except Exception as e:
        logger.exception(f"Job {job_id} failed: {e}")
        async with AsyncSessionLocal() as db:
            job = await db.get(ScanJob, job_id)
            if job:
                job.status = "failed"
                job.error_message = str(e)[:1024]
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()
        await broadcast(job_id, {"type": "job_done", "job_id": job_id, "status": "failed", "error": str(e)})


# ── Worker Loop ───────────────────────────────────────────────────────────────

async def worker_loop():
    """
    Long-running asyncio task. Reads job IDs from job_queue and runs them.
    Multiple jobs can run concurrently (each as its own task).
    Send None to the queue to shut down.
    """
    logger.info("Scan worker started")

    while True:
        job_id = await job_queue.get()
        if job_id is None:  # shutdown signal
            logger.info("Scan worker shutting down")
            # Wait for in-flight jobs
            if running_jobs:
                await asyncio.gather(*running_jobs.values(), return_exceptions=True)
            break

        if job_id in running_jobs and not running_jobs[job_id].done():
            logger.warning(f"Job {job_id} already running, ignoring duplicate")
            continue

        task = asyncio.create_task(run_job(job_id), name=f"scan-job-{job_id}")
        running_jobs[job_id] = task
        task.add_done_callback(lambda t, jid=job_id: running_jobs.pop(jid, None))
