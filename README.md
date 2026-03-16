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
| DHCP scraper | Playwright (TP-Link router API) |
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
│   ├── pipeline.py         # 5-tier nmap scan pipeline + hard cancel
│   ├── progress.py         # WebSocket pub/sub broadcast
│   ├── main.py             # Job orchestration + host persistence
│   └── dhcp_scraper.py     # TP-Link router DHCP hostname scraper
├── shared/
│   ├── db.py               # Async engine, session factory
│   └── models.py           # 13 SQLAlchemy ORM models
├── frontend/               # React frontend (Vite)
│   ├── src/
│   │   ├── api/client.js   # Axios + 401/refresh interceptor
│   │   ├── context/        # Auth context
│   │   ├── components/     # Layout, ProtectedRoute, StatusBadge, ScanProgressModal
│   │   ├── pages/          # Dashboard, Hosts, HostDetail, Subnets, Profiles,
│   │   │                   # ScanJobs, Schedules, Settings, Login
│   │   └── utils/          # Date/duration formatters
│   └── vite.config.js      # Proxies /api to FastAPI, builds to ../static/
├── nginx/
│   └── netscan.conf        # Nginx reverse proxy config
├── systemd/
│   └── netscan-api.service # systemd unit file
├── scripts/
│   ├── backup.sh           # DB + screenshots backup script
│   └── test_screenshot.py  # Playwright test utility
├── tests/                  # Integration tests (pytest + httpx)
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_hosts.py
│   ├── test_scans.py
│   └── test_wol.py
├── docs/
│   ├── architecture.md
│   ├── data_model.md
│   ├── api_spec.md
│   └── tasks/              # Per-task implementation docs (01–24)
├── requirements.txt
├── pytest.ini
└── .env                    # Not committed — see .env.example
```

---

## Features

### Backend

- **Auth** — login with rate limiting (10/min), httpOnly cookie tokens, refresh token rotation, logout with revocation, role-based guards (`viewer` / `operator` / `admin`)
- **Users API** — CRUD for user accounts (admin only)
- **Subnets API** — manage target subnets with CIDR validation
- **Hosts API** — paginated host list with filters (subnet, up/down, new, search), full detail with ports, banners, history, screenshot serving, DHCP sync from router
- **Scan Profiles API** — configurable scan profiles (port range, tiers to enable, concurrency, timeout)
- **Scan Jobs API** — trigger manual scans, list history with pagination, get live job status, hard-cancel queued/running jobs (kills nmap subprocess)
- **WebSocket** — live scan progress at `/api/scans/ws/{job_id}`
- **Schedules API** — cron-based scan schedules with next-run calculation
- **Wake-on-LAN API** — send magic packets, view log
- **Dashboard API** — summary stats: host counts, new hosts/ports, active scans, per-subnet breakdown, recent scan history

### Scan Worker

Runs in-process as an asyncio task. Executes a 5-tier pipeline per subnet:

| Tier | Method | Tool |
|---|---|---|
| 1 | ICMP ping sweep | nmap `-sn -PE` |
| 2 | TCP SYN / Connect scan | nmap `-sS` or `-sT` |
| 3 | UDP scan (optional per profile) | nmap `-sU` |
| 4 | Service fingerprinting + banner grab | nmap `-sV --script=banner` |
| 5 | Web screenshots | Playwright (Chromium) |

After the ICMP sweep, known hosts from the database that didn't respond to ping are automatically included in TCP/UDP/fingerprint scans — catching hosts that block ICMP.
TCP and UDP scan tiers run in parallel when UDP is enabled, then results are merged before fingerprinting.

Host identity resolved by hostname-first lookup (IP fallback). IP/MAC drift logged to `host_history`. Ports upserted with service name, version, and banner. New hosts and ports flagged `is_new=True`. Hard cancel kills nmap subprocesses immediately.

### DHCP Hostname Scraper

Scrapes the TP-Link router's DHCP client table to enrich host records with hostnames and MAC addresses. Supports:

- **Manual sync** — "Sync DHCP" button on the Hosts page (`POST /api/hosts/dhcp-sync`)
- **Auto sync** — periodic background task (configurable via `DHCP_SCRAPE_INTERVAL_MIN`)
- **Host creation** — DHCP entries that don't match an existing host are created as new records with subnet auto-assignment

Authenticates via the router's JS widget encryption (RSA-encrypted password + stok session token).

### Frontend

- Dark sidebar layout — Dashboard, Hosts, Subnets, Profiles, Scan Jobs, Schedules, Settings
- Dashboard with stat cards, subnet bar chart, manual scan trigger, recent jobs table
- Hosts list with search/filter, DHCP sync button, host detail with ports, banners, history diff, WoL button
- Admin pages: subnet CRUD, profile card grid, schedule management, user management
- Live scan progress WebSocket overlay (`ScanProgressModal`)
- Auth context with auto-refresh on 401

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
- Node.js 18+

### 1. Clone & configure

```bash
git clone https://github.com/aboxfulloftide/port_scan
cd port_scan

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install "bcrypt==4.1.3"   # passlib compatibility

cp .env.example .env          # fill in DB creds and JWT secret
```

### 2. Database

```sql
CREATE DATABASE port_scan CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Run the schema SQL from `docs/tasks/02_database.md`, then seed from `docs/tasks/03_seed.md`.

### 3. Playwright (screenshots)

```bash
playwright install chromium
sudo venv/bin/playwright install-deps chromium
```

Test: `python scripts/test_screenshot.py http://192.168.1.1 /tmp/test.png`

### 4. Frontend

```bash
cd frontend
npm install
npm run build       # outputs to ../static/
```

### 5. Dev server

```bash
# Terminal 1 — API
source venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend (hot reload)
cd frontend && npm run dev    # http://localhost:5173
```

Swagger UI: `http://localhost:8000/api/docs`

---

## Production Deployment

### Nginx

```bash
sudo cp nginx/netscan.conf /etc/nginx/sites-available/netscan
sudo ln -s /etc/nginx/sites-available/netscan /etc/nginx/sites-enabled/netscan
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### systemd service

```bash
sudo cp systemd/netscan-api.service /etc/systemd/system/netscan-api.service
sudo systemctl daemon-reload
sudo systemctl enable --now netscan-api
```

The service unit grants `CAP_NET_RAW` + `CAP_NET_ADMIN` so nmap SYN scans work without root.

Manage:
```bash
sudo systemctl status  netscan-api
sudo systemctl restart netscan-api
sudo journalctl -u netscan-api -f
```

### File permissions

```bash
chmod 600 .env
mkdir -p screenshots backups
```

---

## Environment Variables

```env
DATABASE_URL=mysql+pymysql://user:password@localhost:3306/port_scan
JWT_SECRET=generate-with-openssl-rand-hex-32
JWT_ALGORITHM=HS256
JWT_ACCESS_EXPIRE_MINUTES=480
JWT_REFRESH_EXPIRE_DAYS=7
SCREENSHOT_DIR=/home/matheau/code/port_scan/screenshots
SCREENSHOT_TIMEOUT_MS=8000

# DHCP hostname scraper (TP-Link router)
ROUTER_URL=https://192.168.1.1
ROUTER_USERNAME=admin
ROUTER_PASSWORD=your-router-password
DHCP_SCRAPE_INTERVAL_MIN=30
```

---

## API Roles

| Role | Access |
|---|---|
| `viewer` | Read-only (hosts, scans, profiles, subnets) |
| `operator` | Trigger scans, manage subnets/profiles/schedules, send WoL |
| `admin` | All of the above + user management, delete operations |

Default credentials after seed: `admin` / `changeme` — **change immediately after first login.**

---

## Testing

```bash
# Create test database (one-time)
mysql -u <user> -p -e "CREATE DATABASE port_scan_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# Run tests
source venv/bin/activate
venv/bin/pytest tests/ -v
```

22 integration tests covering auth, hosts, scan jobs, and Wake-on-LAN.

---

## Backup

```bash
# Manual
bash scripts/backup.sh

# Automated (cron) — daily at 3am
0 3 * * * /home/matheau/code/port_scan/scripts/backup.sh
```

Retains 30 days of DB dumps and screenshot archives in `backups/`.

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| API returns 500 | `journalctl -u netscan-api -n 50` |
| Scans never start | Worker running? Check logs for job queue activity |
| Nmap permission denied | Service has `CAP_NET_RAW`? `systemctl status netscan-api` |
| Screenshots blank | HTTPS redirect? Uses `networkidle` + `ignore_https_errors=True` |
| WebSocket disconnects | Nginx `proxy_read_timeout 3600s` set on `/api/scans/ws/`? |
| Login 429 | Rate limit 10/min per IP — wait or restart API in dev |
| Frontend 404 on refresh | Nginx `try_files $uri /index.html` configured? |
