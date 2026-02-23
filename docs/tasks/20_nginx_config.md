# Task 20: Nginx Configuration

## Status: COMPLETE ✅

**Deviations from plan:**
- Config saved to `nginx/netscan.conf` in the repo (not directly to `/etc/nginx/`) — deploy instructions are in the file header.
- WebSocket location changed from `/ws/` to `/api/scans/ws/` to match the actual endpoint path and avoid conflicting with the `/api/` proxy block.

**Depends on:** Task 01, Task 16  
**Complexity:** Low  
**Description:** Configure Nginx to serve the React SPA static files, proxy API requests to FastAPI, proxy WebSocket connections, and serve screenshot files.

---

## File to Create

`/etc/nginx/sites-available/netscan`

---

## Nginx Config

```nginx
# /etc/nginx/sites-available/netscan

upstream netscan_api {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 80;
    server_name _;          # Replace with your hostname or IP if desired

    # ── Security headers ──────────────────────────────────────────────────────
    add_header X-Frame-Options        "SAMEORIGIN"   always;
    add_header X-Content-Type-Options "nosniff"      always;
    add_header Referrer-Policy        "strict-origin" always;

    # ── Gzip ──────────────────────────────────────────────────────────────────
    gzip on;
    gzip_types text/plain text/css application/json application/javascript
               text/xml application/xml image/svg+xml;
    gzip_min_length 1024;

    # ── Static frontend (React SPA) ───────────────────────────────────────────
    root /home/matheau/code/port_scan/static;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;   # SPA fallback
    }

    # ── API proxy ─────────────────────────────────────────────────────────────
    location /api/ {
        proxy_pass         http://netscan_api;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }

    # ── WebSocket proxy ───────────────────────────────────────────────────────
    location /ws/ {
        proxy_pass         http://netscan_api;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade    $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host       $host;
        proxy_read_timeout 3600s;   # keep WS alive during long scans
    }

    # ── Screenshot files (served directly by Nginx for performance) ───────────
    # Alternatively, FastAPI serves these — remove this block if using FastAPI
    location /screenshots/ {
        alias /home/matheau/code/port_scan/screenshots/;
        expires 1d;
        add_header Cache-Control "public, immutable";
        # Restrict to internal network only
        allow 10.0.0.0/8;
        allow 172.16.0.0/12;
        allow 192.168.0.0/16;
        allow 127.0.0.1;
        deny all;
    }

    # ── Deny hidden files ─────────────────────────────────────────────────────
    location ~ /\. {
        deny all;
    }
}
```

---

## Enable & Reload

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/netscan /etc/nginx/sites-enabled/netscan

# Remove default site if present
sudo rm -f /etc/nginx/sites-enabled/default

# Test config
sudo nginx -t

# Reload
sudo systemctl reload nginx
```

---

## Optional: HTTPS with Self-Signed Certificate

For LAN use, a self-signed cert is sufficient:

```bash
sudo openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout /etc/ssl/private/netscan.key \
  -out /etc/ssl/certs/netscan.crt \
  -subj "/CN=netscan.local"
```

Then update the server block:
```nginx
server {
    listen 443 ssl;
    ssl_certificate     /etc/ssl/certs/netscan.crt;
    ssl_certificate_key /etc/ssl/private/netscan.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    # ... rest of config
}

server {
    listen 80;
    return 301 https://$host$request_uri;
}
```

---

## Notes

- The React build output (`npm run build`) writes to `/home/matheau/code/port_scan/static/` (configured in `vite.config.js`).
- FastAPI runs on `127.0.0.1:8000` via systemd (configured in Task 01).
- WebSocket connections for live scan progress use the `/ws/` prefix.
- Screenshot files can be served by either Nginx (faster) or FastAPI (auth-gated). The FastAPI route at `/api/hosts/screenshots/{filename}` is the auth-gated option.
