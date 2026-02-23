# NetScan

An internal network port and IP scanner built for homelabs and small networks. Discovers hosts, tracks open ports over time, fingerprints services, takes web screenshots, and sends Wake-on-LAN packets — all through a web UI.

---

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI (Python 3.12, async) |
| Database | MySQL 8 + SQLAlchemy 2.0 async (aiomysql) |
| Auth | JWT via httpOnly cookies (access 8hr / refresh 7d) |
| Scan engine | python-nmap (nmap) |
| Screenshots | Playwright (Chromium) |
| Frontend | React 18 + Vite + TailwindCSS |
| State | TanStack Query v5 |
| Wake-on-LAN | wakeonlan |

---

## Project Structure

```
port_scan/
├── api/                    # FastAPI application
│   ├── main.py             # App entry point, lifespan, router registration
│   ├── config.py           # Settings from .env
│   ├── auth/               # Login, JWT, refresh, logout, dependencies
│   ├── users/              # User CRUD (admin only)
│   ├── subnets/            # Subnet management
│   ├── hosts/              # Host list, detail, ports, screenshots
│   ├── profiles/           # Scan profile CRUD
│   ├── scans/              # Scan job trigger, status, cancel, WebSocket
│   ├── schedules/          # Cron-based scan schedules
│   ├── wol/                # Wake-on-LAN send + log
│   └── dashboard/          # Aggregated summary stats
├── worker/                 # Async scan worker (runs in-process)
│   ├── queue.py            # asyncio.Queue shared with API
│   ├── pipeline.py         # 5-tier nmap scan pipeline
│   ├── progress.py         # WebSocket pub/sub broadcast
│   └── main.py             # Job orchestration + host persistence
├── shared/
│   ├── db.py               # Async engine, session factory
│   └── models.py           # 13 SQLAlchemy ORM models
├── frontend/               # React frontend (Vite)
│   ├── src/
│   │   ├── api/client.js   # Axios + 401/refresh interceptor
│   │   ├── context/        # Auth context
│   │   ├── components/     # Layout, ProtectedRoute, StatusBadge, ScanProgressModal
│   │   ├── pages/          # Login (done), Dashboard, Hosts, etc.
│   │   └── utils/          # Date/duration formatters
│   └── vite.config.js      # Proxies /api to FastAPI, builds to ../static/
├── docs/
│   ├── architecture.md
│   ├── data_model.md
│   ├── api_spec.md
│   └── tasks/              # Per-task implementation docs (01–24)
├── requirements.txt
└── .env                    # Not committed — see .env.example
```

---

## Features

### Backend (complete)

- **Auth** — login with rate limiting (10/min), httpOnly cookie tokens, refresh token rotation, logout with revocation, role-based guards (`viewer` / `operator` / `admin`)
- **Users API** — CRUD for user accounts (admin only)
- **Subnets API** — manage target subnets with CIDR validation
- **Hosts API** — paginated host list with filters (subnet, up/down, new, search), full detail with ports, banners, history, screenshot serving
- **Scan Profiles API** — configurable scan profiles (port range, tiers to enable, concurrency, timeout)
- **Scan Jobs API** — trigger manual scans, list history with pagination, get live job status, cancel queued/running jobs
- **WebSocket** — live scan progress polling at `/api/scans/ws/{job_id}`
- **Schedules API** — cron-based scan schedules with next-run calculation (croniter)
- **Wake-on-LAN API** — send magic packets, view log
- **Dashboard API** — summary stats: host counts, new hosts/ports, active scans, per-subnet breakdown, recent scan history

### Scan Worker (complete)

Runs in-process as an asyncio task. Consumes job IDs from a shared queue and executes a 5-tier pipeline per subnet:

| Tier | Method | Tool |
|---|---|---|
| 1 | ICMP ping sweep | nmap `-sn -PE` |
| 2 | TCP SYN / Connect scan | nmap `-sS` or `-sT` |
| 3 | UDP scan (optional per profile) | nmap `-sU` |
| 4 | Service fingerprinting + banner grab | nmap `-sV --script=banner` |
| 5 | Web screenshots | Playwright (Chromium) |

Host identity is resolved by hostname-first lookup (IP fallback). IP/MAC drift is logged to `host_history`. Ports are upserted with service name, version, and banner. New hosts and ports are flagged `is_new=True`.

### Frontend (scaffold complete)

- Vite + React 18 + TailwindCSS + React Router v6
- Dark sidebar layout with nav
- Auth context with auto-refresh on 401
- Login page
- Stub pages for: Dashboard, Hosts, Host Detail, Subnets, Profiles, Scan Jobs, Schedules, Settings
- `ScanProgressModal` — live WebSocket progress overlay
- `StatusBadge` — colored status pill

---

## Database

13 tables in MySQL:

`users` · `refresh_tokens` · `subnets` · `hosts` · `host_history` · `host_ports` · `port_banners` · `port_screenshots` · `scan_profiles` · `scan_jobs` · `schedules` · `wol_schedules` · `wol_log`

---

## Setup

### Requirements

- Python 3.12+
- MySQL 8
- nmap (`sudo apt install nmap`)
- Node.js 18+ (frontend)

### Backend

```bash
git clone https://github.com/aboxfulloftide/port_scan
cd port_scan

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install "bcrypt==4.1.3"   # passlib compatibility

cp .env.example .env          # edit with your DB creds and JWT secret
```

Create the database:
```sql
CREATE DATABASE port_scan CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Then run the schema SQL from `docs/tasks/02_database.md` and seed data from `docs/tasks/03_seed.md`.

Start the API:
```bash
uvicorn api.main:app --reload --port 8000
```

Swagger UI: `http://localhost:8000/api/docs`

### Frontend (dev)

```bash
cd frontend
npm install
npm run dev       # http://localhost:5173 — proxies /api to :8000
```

### Frontend (build)

```bash
cd frontend
npm run build     # outputs to ../static/
```

---

## Environment Variables

Create a `.env` file at the project root:

```env
DATABASE_URL=mysql+pymysql://user:password@localhost:3306/port_scan
JWT_SECRET=your-secret-here
JWT_ALGORITHM=HS256
JWT_ACCESS_EXPIRE_MINUTES=480
JWT_REFRESH_EXPIRE_DAYS=7
SCREENSHOT_DIR=/path/to/port_scan/screenshots
```

---

## API Roles

| Role | Access |
|---|---|
| `viewer` | Read-only (hosts, scans, profiles, subnets) |
| `operator` | Trigger scans, manage subnets/profiles/schedules, send WoL |
| `admin` | All of the above + user management, delete operations |

Default credentials after seed: `admin` / `changeme`

---

## What's Left

- [ ] Task 17 — Dashboard page (React)
- [ ] Task 18 — Hosts list + detail pages (React)
- [ ] Task 19 — Admin pages: subnets, profiles, schedules, scan jobs, users (React)
- [ ] Task 20 — Nginx reverse proxy config
- [ ] Task 21 — Hard scan cancellation (kill nmap process)
- [ ] Task 22 — Playwright screenshot setup
- [ ] Task 23 — Integration tests
- [ ] Task 24 — Deployment checklist / systemd service
