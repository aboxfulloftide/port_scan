# NetScan — AI Agent Project Overview

> This file is the canonical entry point for any AI coding assistant working on this project.
> Read this first before touching any code or documentation.

---

## What Is NetScan?

NetScan is a **self-hosted internal network scanner** with a web dashboard. It discovers hosts on private IPv4 subnets, fingerprints services, grabs banners, captures web screenshots, tracks host identity over time (handling DHCP drift), and can wake hosts via Wake-on-LAN — all controllable from a browser.

---

## Tech Stack at a Glance

| Layer | Technology |
|---|---|
| Web Server | Nginx (serves SPA + reverse proxies API) |
| Backend API | Python 3.11+, FastAPI, APScheduler |
| Scan Engine | Python asyncio worker, Nmap, Playwright |
| Database | MySQL (existing host instance) |
| Frontend | React 18, Vite, TailwindCSS, React Query, Recharts |
| Auth | JWT (access + refresh tokens, httpOnly cookies), RBAC |
| WoL | Python `wakeonlan` library |
| Process Mgmt | systemd (two services: API + worker) |

---

## Repository Layout

```
netscan/
├── AGENTS.md                  ← YOU ARE HERE
│
├── docs/                      ← All design & specification documents
│   ├── architecture.md        ← System diagram, components, auth, security
│   ├── data_model.md          ← All 13 MySQL table schemas + ERD
│   ├── api_spec.md            ← Full REST API + WebSocket specification
│   └── task_list.md           ← Master task list with dependencies & status
│
├── tasks/                     ← Atomic implementation task files (one per feature)
│   ├── 01_project_scaffold.md
│   ├── 02_database_init.md
│   ├── 03_auth_backend.md
│   ├── 04_users_api.md
│   ├── 05_subnets_api.md
│   ├── 06_hosts_api.md
│   ├── 07_scan_profiles_api.md
│   ├── 08_scan_jobs_api.md
│   ├── 09_icmp_sweep.md
│   ├── 10_tcp_scanner.md
│   ├── 11_udp_scanner.md
│   ├── 12_schedules_api.md
│   ├── 13_wol_api.md
│   ├── 14_scan_worker_core.md
│   ├── 15_dashboard_api.md
│   ├── 16_frontend_scaffold.md
│   ├── 17_frontend_dashboard.md
│   ├── 18_frontend_hosts.md
│   ├── 19_frontend_admin_pages.md
│   ├── 20_nginx_config.md
│   └── 21_scan_cancel_websocket.md
│
├── api/                       ← FastAPI backend (Python)
│   ├── main.py                ← App entrypoint, lifespan, router registration
│   ├── config.py              ← Settings (env vars via pydantic-settings)
│   ├── db.py                  ← MySQL connection pool (aiomysql)
│   ├── auth/
│   │   ├── router.py          ← /api/auth/* endpoints
│   │   ├── models.py          ← Pydantic schemas
│   │   └── utils.py           ← JWT encode/decode, password hashing
│   ├── users/
│   ├── subnets/
│   ├── hosts/
│   ├── scans/
│   ├── profiles/
│   ├── schedules/
│   ├── wol/
│   └── dashboard/
│
├── worker/                    ← Async scan worker (runs inside API process)
│   ├── main.py                ← Worker loop, host identity resolution
│   ├── queue.py               ← asyncio job queue
│   ├── progress.py            ← WebSocket broadcast manager
│   └── pipeline.py            ← Tiered scan pipeline (ICMP→TCP→UDP→FP→Banner→Screenshot)
│
├── frontend/                  ← React SPA
│   ├── src/
│   │   ├── api/client.js      ← Axios instance + JWT refresh interceptor
│   │   ├── context/AuthContext.jsx
│   │   ├── App.jsx            ← Router + auth provider
│   │   ├── components/        ← Shared UI components
│   │   └── pages/             ← One file per route/page
│   ├── vite.config.js         ← Dev proxy → FastAPI
│   └── package.json
│
├── sql/
│   └── schema.sql             ← Full MySQL DDL (all 13 tables)
│
├── nginx/
│   └── netscan.conf           ← Nginx site config
│
└── systemd/
    ├── netscan-api.service
    └── netscan-worker.service  ← (worker runs inside API; kept for reference)
```

---

## Core Concepts to Understand First

### Host Identity
Hosts are identified **primarily by hostname**, not IP. IP and MAC are treated as current attributes that can drift (DHCP). When a scan finds a host:
1. Resolve hostname via reverse DNS.
2. Look up existing host by hostname → update IP/MAC if changed, log to `host_history`.
3. If no hostname, fall back to MAC → then IP as identity key.
4. Flag new hosts and new open ports as `is_new = true`.

### Scan Pipeline (tiered, fastest → slowest)
```
1. ICMP Sweep       — host up/down
2. TCP SYN Scan     — open ports (requires root / CAP_NET_RAW)
3. UDP Scan         — common UDP ports
4. Service FP       — nmap -sV on open ports
5. Banner Grab      — raw socket reads
6. Web Screenshot   — Playwright headless Chromium on HTTP/HTTPS ports
```
Each tier feeds results into the next. Scan Profiles control which tiers run and their parameters.

### Authentication & RBAC
- JWT access token (15 min) + refresh token (7 day), both in httpOnly cookies.
- Three roles: `admin`, `operator`, `viewer`.
- The `users` and `refresh_tokens` tables are **shared** — designed to be reused by other internal tools via the same MySQL instance.

### Wake-on-LAN
- Requires MAC address stored in `hosts.mac`.
- Manual trigger: `POST /api/wol/{host_id}/wake`.
- Scheduled: stored in `wol_schedules`, fired by APScheduler.
- Uses the same APScheduler instance as scan schedules.

---

## Where to Start (Task Dependency Order)

```
01 → 02 → 03 → 04 → 05 → 06 → 07 → 08
                              ↓
                    09 → 10 → 11 → 14 (scan worker core)
                              ↓
                    12 → 13 (schedules + WoL)
                              ↓
                    15 (dashboard API)
                              ↓
          16 → 17 → 18 → 19 (frontend)
                              ↓
                    20 → 21 (nginx + websocket/cancel)
```

Each `tasks/NN_*.md` file contains:
- **Goal** — what this task produces
- **Inputs** — files/tables it depends on
- **Outputs** — files it creates or modifies
- **Full implementation code** — copy-paste ready
- **Acceptance criteria** — how to verify it works

---

## Key Design Decisions (already locked in)

| Decision | Choice |
|---|---|
| IP version | IPv4 only |
| Port default | All 65535 (user-configurable per profile) |
| Scan trigger | Manual + scheduled (APScheduler, cron-style) |
| Screenshot tool | Playwright (headless Chromium) |
| DB connection | aiomysql async pool |
| Frontend build | Vite → `frontend/dist/` → served by Nginx |
| API base path | `/api/` |
| WebSocket path | `/ws/scans/{job_id}` |
| Auth cookie names | `access_token`, `refresh_token` |

---

## Environment Variables (see `api/config.py`)

```env
DATABASE_URL=mysql+aiomysql://user:pass@localhost/netscan
SECRET_KEY=<random 64-char hex>
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
SCREENSHOT_DIR=/var/lib/netscan/screenshots
NMAP_PATH=/usr/bin/nmap
```

---

## Docs Quick Reference

| Question | Go to |
|---|---|
| How does the DB look? | `docs/data_model.md` |
| What endpoints exist? | `docs/api_spec.md` |
| How are components wired? | `docs/architecture.md` |
| What's left to build? | `docs/task_list.md` |
| How do I implement X? | `tasks/NN_<feature>.md` |
