# Architecture Specification
## Internal Port & IP Scanner (NetScan)

**Version:** 1.0  
**Date:** 2026-02-18  
**Status:** Approved for Development

---

## 1. System Overview

NetScan is a self-hosted internal network scanning platform. It provides continuous visibility into hosts, open ports, services, and web interfaces across one or more internal IPv4 subnets. It is designed to run on a single Linux server and be accessed by multiple users on the LAN via a web browser.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        LAN Clients                          │
│                  (Browsers on the network)                  │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTPS (Nginx reverse proxy)
┌───────────────────────────▼─────────────────────────────────┐
│                        Nginx (existing)                      │
│         Static frontend assets + reverse proxy to API        │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP (localhost only)
┌───────────────────────────▼─────────────────────────────────┐
│                   FastAPI Backend (Python)                   │
│                   Runs as systemd service                    │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │  Auth Module │  │  Scan API    │  │   WoL API         │  │
│  │  (JWT/Users) │  │  (trigger,   │  │  (magic packet)   │  │
│  └─────────────┘  │   schedule,  │  └───────────────────┘  │
│                   │   profiles)  │                          │
│                   └──────────────┘                          │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                    Task Queue (APScheduler)                  │
│         Manages scheduled scans and WoL jobs                 │
└──────────┬────────────────────────────────────┬─────────────┘
           │                                    │
┌──────────▼──────────┐              ┌──────────▼──────────────┐
│   Scan Worker        │              │     WoL Worker           │
│   (Python process)   │              │   (wakeonlan lib)        │
│                      │              └─────────────────────────┘
│  ┌────────────────┐  │
│  │ 1. ICMP Sweep  │  │
│  │ 2. TCP SYN     │  │
│  │ 3. TCP Connect │  │
│  │ 4. UDP Scan    │  │
│  │ 5. Svc Finger  │  │
│  │ 6. Banner Grab │  │
│  │ 7. Screenshot  │  │
│  └────────────────┘  │
└──────────┬───────────┘
           │
┌──────────▼───────────┐
│     MySQL Database    │
│     (existing)        │
└──────────────────────┘
```

---

## 3. Component Breakdown

### 3.1 Nginx (Existing)
- Serves static frontend files from `/home/matheau/code/port_scan/static/`
- Reverse proxies `/api/` requests to FastAPI on `127.0.0.1:8000`
- Handles TLS termination (recommended: self-signed cert for LAN)
- No changes to existing Nginx config beyond adding a new server block

### 3.2 FastAPI Backend
- **Runtime:** Python 3.11+
- **Process manager:** systemd (`netscan-api.service`)
- **Port:** 8000 (localhost only, never exposed directly)
- **Responsibilities:**
  - User authentication and JWT issuance
  - CRUD for scan profiles, schedules, subnets
  - Triggering manual scans
  - Serving scan results, host data, screenshots
  - WoL magic packet dispatch
  - Serving screenshot images as static files or base64

### 3.3 Scan Worker
- **Runtime:** Python 3.11+, runs as a separate systemd service (`netscan-worker.service`)
- **Scan orchestration:** Executes tiered scan pipeline per host/subnet
- **nmap integration:** via `python-nmap` library
- **Screenshot engine:** Playwright with headless Chromium
- **Concurrency:** `asyncio` + `ThreadPoolExecutor` for parallel host scanning
- **Max concurrency:** Configurable, default 50 concurrent hosts
- **Results:** Written directly to MySQL on completion

### 3.4 Task Scheduler
- **Library:** APScheduler (Advanced Python Scheduler)
- **Runs inside:** the Scan Worker process
- **Responsibilities:**
  - Executing scheduled scan jobs (cron-style)
  - Executing scheduled WoL jobs per host
  - Loading schedules from MySQL on startup and on config change

### 3.5 MySQL Database (Existing)
- All NetScan tables created in a dedicated `netscan` schema/database
- Auth tables designed to be shared with future tools
- See `data_model.md` for full schema

### 3.6 Frontend
- **Stack:** Vanilla JS + HTML5 + CSS3 (no heavy framework dependency)
- **UI Library:** Bootstrap 5 (CDN) for clean responsive layout
- **Charts:** Chart.js for scan history trends
- **Served from:** Nginx static directory
- **Communicates with:** FastAPI via REST + JSON
- **Auth:** JWT stored in `httpOnly` cookie

---

## 4. Authentication Architecture

### 4.1 Design Goals
- Shared user table usable by other internal tools
- Stateless JWT tokens (no server-side session storage)
- Role-based access control (RBAC)

### 4.2 Flow
```
User → POST /api/auth/login (username + password)
     ← JWT access token (httpOnly cookie, 8hr expiry)
     ← JWT refresh token (httpOnly cookie, 7 day expiry)

All subsequent API calls → Bearer token validated by FastAPI middleware
```

### 4.3 Roles
| Role | Permissions |
|---|---|
| `admin` | Full access: users, config, scans, WoL, schedules |
| `operator` | Trigger scans, view all data, send WoL |
| `viewer` | Read-only: view scan results and host data |

---

## 5. Scan Pipeline Detail

Each scan job processes one or more subnets through the following ordered tiers. Each tier feeds results into the next. Tiers can be enabled/disabled per scan profile.

```
Tier 1: ICMP Ping Sweep          ~seconds    → Discover live hosts
Tier 2: TCP SYN Scan             ~seconds    → Fast port state (requires root)
         └─ fallback: TCP Connect ~minutes   → If not root
Tier 3: UDP Scan                 ~minutes    → DNS, SNMP, DHCP, TFTP etc.
Tier 4: Service Fingerprinting   ~minutes    → nmap -sV on open ports
Tier 5: Banner Grabbing          ~seconds    → Raw socket per open port
Tier 6: Web Screenshot           ~seconds    → Playwright on HTTP/HTTPS ports
```

**Parallelism strategy:**
- Tier 1 & 2: Run across all hosts in parallel (batch of N)
- Tiers 3-6: Run per-host after that host is confirmed up
- Screenshot: Only triggered on ports 80, 443, 8080, 8443, and any port returning HTTP banner

**ICMP-silent host handling:**
After the ping sweep, the worker queries the database for all known hosts in the target subnet(s) that did not respond to ICMP. These hosts are added to the TCP/UDP/fingerprint scan targets automatically, so hosts that block ping still get fully scanned.

**DHCP hostname enrichment:**
After scan results are persisted, the worker scrapes the router's DHCP client table (via Playwright) and updates host records with DHCP-assigned hostnames and MAC addresses. Unmatched DHCP entries create new host records with auto-assigned subnets.

---

## 6. Host Identity Resolution

Since IP and MAC can change, hostname is the canonical identity:

```
Incoming scan result
        │
        ▼
Does a host with this hostname exist in DB?
   YES → Update IP, MAC, last_seen. Log drift if IP/MAC changed.
   NO  →
        Does a host with this IP exist (no hostname)?
           YES → Update record, assign hostname
           NO  → Create new host record. Flag as NEW.
```

**Hostname resolution order:**
1. nmap reverse DNS lookup
2. NetBIOS/mDNS name (via nmap scripts)
3. PTR record query
4. DHCP client table from router (post-scan enrichment)
5. Fallback: use IP as identifier

---

## 7. Wake-on-LAN Architecture

- Magic packet sent via Python `wakeonlan` library
- Requires stored MAC address for the target host
- Broadcast to subnet broadcast address (e.g., `192.168.1.255`)
- **Manual WoL:** API endpoint `POST /api/hosts/{id}/wol` → immediate dispatch
- **Scheduled WoL:** Stored in `wol_schedules` table, loaded by APScheduler
- WoL events logged to `wol_log` table with timestamp and triggered_by

---

## 8. Directory Structure

```
/home/matheau/code/port_scan/
├── api/                        # FastAPI backend
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── auth/
│   │   ├── router.py
│   │   ├── models.py
│   │   └── utils.py
│   ├── hosts/
│   │   ├── router.py
│   │   └── models.py
│   ├── scans/
│   │   ├── router.py
│   │   └── models.py
│   ├── profiles/
│   │   ├── router.py
│   │   └── models.py
│   ├── schedules/
│   │   ├── router.py
│   │   └── models.py
│   └── wol/
│       ├── router.py
│       └── utils.py
├── worker/                     # Scan worker process
│   ├── main.py
│   ├── scheduler.py
│   ├── pipeline/
│   │   ├── icmp.py
│   │   ├── tcp_syn.py
│   │   ├── udp.py
│   │   ├── fingerprint.py
│   │   ├── banner.py
│   │   └── screenshot.py
│   └── identity.py             # Host identity resolution logic
├── shared/                     # Shared DB models, config
│   ├── db.py
│   └── models.py
├── screenshots/                # Stored screenshot images
├── logs/
├── requirements.txt
└── .env

/home/matheau/code/port_scan/static/               # Frontend (served by Nginx)
├── index.html
├── assets/
│   ├── css/
│   ├── js/
│   └── img/
└── pages/
    ├── hosts.html
    ├── scan.html
    ├── profiles.html
    ├── schedules.html
    ├── users.html
    └── settings.html
```

---

## 9. Systemd Services

### `netscan-api.service`
```ini
[Unit]
Description=NetScan API Service
After=network.target mysql.service

[Service]
User=netscan
WorkingDirectory=/home/matheau/code/port_scan/api
ExecStart=/home/matheau/code/port_scan/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

### `netscan-worker.service`
```ini
[Unit]
Description=NetScan Scan Worker
After=network.target mysql.service netscan-api.service

[Service]
User=root
WorkingDirectory=/home/matheau/code/port_scan/worker
ExecStart=/home/matheau/code/port_scan/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

> **Note:** Worker runs as root to enable TCP SYN (raw socket) scanning. This is scoped and isolated from the API process.

---

## 10. Security Considerations

| Concern | Mitigation |
|---|---|
| Raw socket scanning requires root | Worker isolated as separate process from API |
| JWT secret exposure | Stored in `.env`, not in code |
| Screenshot storage | Stored locally, served via authenticated API endpoint |
| Network exposure | API only on localhost; Nginx handles external access |
| SQL injection | SQLAlchemy ORM with parameterized queries |
| Brute force login | Rate limiting via `slowapi` on auth endpoints |
