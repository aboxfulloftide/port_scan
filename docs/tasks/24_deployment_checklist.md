# Task 24: Deployment Checklist & Go-Live

**Depends on:** All previous tasks  
**Complexity:** Low  
**Description:** Final deployment steps, security hardening, and operational runbook for going live with NetScan on the Linux server.

---

## Pre-Deployment Checklist

### Environment
- [ ] `.env` file created at `/home/matheau/code/port_scan/.env` with all required values
- [ ] `SECRET_KEY` is a strong random value (`openssl rand -hex 32`)
- [ ] `DB_PASSWORD` is set and matches MySQL grant
- [ ] `SCREENSHOT_DIR` exists and is writable by `netscan` user

### Database
- [ ] MySQL `netscan` database created (Task 02)
- [ ] All 13 tables created and verified
- [ ] Seed data inserted: admin user + 3 default profiles (Task 03)
- [ ] Alembic migrations initialized

### Backend
- [ ] Python venv created at `/home/matheau/code/port_scan/venv`
- [ ] All pip packages installed (Task 01)
- [ ] Playwright Chromium installed (`playwright install chromium`)
- [ ] `netscan-api.service` systemd unit enabled and started
- [ ] API health check passes: `curl http://localhost:8000/api/health`

### Frontend
- [ ] Node.js installed (`node --version`)
- [ ] `npm install` completed in `/home/matheau/code/port_scan/frontend`
- [ ] `npm run build` completed — output in `/home/matheau/code/port_scan/static`
- [ ] `index.html` present in `/home/matheau/code/port_scan/static`

### Nginx
- [ ] Config file at `/etc/nginx/sites-available/netscan`
- [ ] Symlink in `sites-enabled`
- [ ] `nginx -t` passes
- [ ] Nginx reloaded

### Nmap
- [ ] `nmap --version` works as `netscan` user
- [ ] `nmap` has required capabilities or runs via sudo (see below)

---

## Nmap Permissions

TCP SYN scan (`-sS`) requires raw socket access. Options:

### Option A: setcap (Recommended)
```bash
sudo setcap cap_net_raw,cap_net_admin=eip $(which nmap)
```

### Option B: sudo without password (less secure)
```bash
# /etc/sudoers.d/netscan
netscan ALL=(ALL) NOPASSWD: /usr/bin/nmap
```
Then update `worker/pipeline.py` to prefix nmap calls with `sudo`.

### Option C: Run API as root (not recommended)
Avoid unless in a fully isolated environment.

---

## First Login

1. Open browser → `http://<server-ip>/`
2. Login with `admin` / `changeme`
3. **Immediately change password** (forced on first login)
4. Add subnets via **Subnets** page
5. Verify default scan profiles exist
6. Run a **Quick Ping** scan on a small subnet to verify end-to-end

---

## Systemd Service Management

```bash
# Start / stop / restart API
sudo systemctl start  netscan-api
sudo systemctl stop   netscan-api
sudo systemctl restart netscan-api

# View logs
sudo journalctl -u netscan-api -f

# Check status
sudo systemctl status netscan-api
```

---

## Log Locations

| Component | Log |
|-----------|-----|
| FastAPI / Worker | `journalctl -u netscan-api` |
| Nginx access | `/var/log/nginx/access.log` |
| Nginx error | `/var/log/nginx/error.log` |
| MySQL | `/var/log/mysql/error.log` |

---

## Backup

```bash
# Database backup
mysqldump -u netscan -p netscan > /home/matheau/code/port_scan/backups/netscan_$(date +%Y%m%d).sql

# Screenshots backup
tar -czf /home/matheau/code/port_scan/backups/screenshots_$(date +%Y%m%d).tar.gz /home/matheau/code/port_scan/screenshots/
```

Automate with cron:
```cron
0 3 * * * /home/matheau/code/port_scan/scripts/backup.sh
```

---

## Security Hardening

### Firewall (ufw)
```bash
# Allow SSH and HTTP only from LAN
sudo ufw allow from 192.168.0.0/16 to any port 22
sudo ufw allow from 192.168.0.0/16 to any port 80
sudo ufw allow from 192.168.0.0/16 to any port 443
sudo ufw deny 80
sudo ufw deny 443
sudo ufw enable
```

### File Permissions
```bash
chmod 600 /home/matheau/code/port_scan/.env
chown netscan:netscan /home/matheau/code/port_scan/.env
chmod 750 /home/matheau/code/port_scan/screenshots
```

### MySQL
```bash
# Restrict netscan user to localhost only (already done in Task 02)
# Verify:
mysql -u root -p -e "SELECT user, host FROM mysql.user WHERE user='netscan';"
# Should show: netscan | localhost
```

---

## Updating NetScan

```bash
cd /home/matheau/code/port_scan

# Pull latest code (if using git)
git pull

# Update Python deps
source venv/bin/activate
pip install -r requirements.txt

# Run any new migrations
alembic upgrade head

# Rebuild frontend
cd frontend && npm install && npm run build && cd ..

# Restart API
sudo systemctl restart netscan-api
sudo systemctl reload nginx
```

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| API returns 500 | `journalctl -u netscan-api -n 50` |
| Scans never start | Worker loop running? Check `job_queue` in logs |
| Nmap permission denied | Check `setcap` or sudo config |
| Screenshots blank/missing | Playwright installed? `playwright install chromium` |
| WebSocket disconnects | Nginx `proxy_read_timeout` set to 3600s? |
| Login fails | Check `users` table has admin row; bcrypt hash correct |
| Frontend 404 on refresh | Nginx `try_files $uri /index.html` configured? |

---

## Project Complete ✓

All 24 tasks completed. NetScan is fully operational with:

- ✅ Tiered scan pipeline (ICMP → TCP SYN → UDP → Fingerprint → Screenshot)
- ✅ Host identity tracking with change detection
- ✅ JWT auth with RBAC (admin / operator / viewer)
- ✅ Shared user table for cross-tool auth
- ✅ Scan profiles (user-configurable)
- ✅ Manual + scheduled scans
- ✅ Wake-on-LAN (manual + scheduled)
- ✅ Live scan progress via WebSocket
- ✅ React dashboard with dark UI
- ✅ MySQL persistence with full history
- ✅ Nginx reverse proxy
- ✅ Integration test suite
