# API Specification
## Internal Port & IP Scanner (NetScan)

**Version:** 1.0  
**Date:** 2026-02-18  
**Base URL:** `https://<server-ip>/api`  
**Auth:** JWT via httpOnly cookie (`access_token`)  
**Format:** JSON request/response unless noted

---

## 1. Authentication

### `POST /api/auth/login`
Authenticate a user and receive JWT tokens.

**Request:**
```json
{
  "username": "admin",
  "password": "changeme"
}
```

**Response `200`:**
```json
{
  "user": {
    "id": 1,
    "username": "admin",
    "role": "admin"
  }
}
```
> Sets `access_token` (8hr) and `refresh_token` (7d) as httpOnly cookies.

**Errors:** `401 Unauthorized` — invalid credentials | `429 Too Many Requests` — rate limited

---

### `POST /api/auth/refresh`
Exchange a valid refresh token for a new access token.

**Response `200`:** New `access_token` cookie set.

---

### `POST /api/auth/logout`
Revoke refresh token and clear cookies.

**Response `204 No Content`**

---

### `GET /api/auth/me`
Return the currently authenticated user.

**Response `200`:**
```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@localhost",
  "role": "admin",
  "last_login": "2026-02-18T08:00:00Z"
}
```

---

## 2. Users *(admin only)*

### `GET /api/users`
List all users.

**Response `200`:**
```json
[
  {
    "id": 1,
    "username": "admin",
    "email": "admin@localhost",
    "role": "admin",
    "is_active": true,
    "last_login": "2026-02-18T08:00:00Z"
  }
]
```

---

### `POST /api/users`
Create a new user.

**Request:**
```json
{
  "username": "jdoe",
  "email": "jdoe@company.com",
  "password": "securepassword",
  "role": "operator"
}
```

**Response `201`:** Created user object (no password_hash).

---

### `PATCH /api/users/{id}`
Update user fields (role, active status, email, password).

**Request (partial):**
```json
{
  "role": "viewer",
  "is_active": false
}
```

**Response `200`:** Updated user object.

---

### `DELETE /api/users/{id}`
Delete a user. Cannot delete own account.

**Response `204 No Content`**

---

## 3. Subnets

### `GET /api/subnets`
List all configured subnets.

**Response `200`:**
```json
[
  {
    "id": 1,
    "label": "Office LAN",
    "cidr": "192.168.1.0/24",
    "description": "Main office network",
    "is_active": true
  }
]
```

---

### `POST /api/subnets`
Add a new subnet. *(admin/operator)*

**Request:**
```json
{
  "label": "IoT Network",
  "cidr": "10.10.20.0/24",
  "description": "Smart devices"
}
```

**Response `201`:** Created subnet object.

---

### `PATCH /api/subnets/{id}`
Update subnet label, description, or active status.

**Response `200`:** Updated subnet object.

---

### `DELETE /api/subnets/{id}`
Remove a subnet. *(admin only)*

**Response `204 No Content`**

---

## 4. Hosts

### `GET /api/hosts`
List all known hosts with current state.

**Query params:**
| Param | Type | Description |
|---|---|---|
| `subnet_id` | int | Filter by subnet |
| `is_up` | bool | Filter by up/down status |
| `is_new` | bool | Filter unacknowledged new hosts |
| `search` | string | Search hostname, IP, or MAC |
| `page` | int | Pagination (default: 1) |
| `per_page` | int | Results per page (default: 50, max: 200) |

**Response `200`:**
```json
{
  "total": 142,
  "page": 1,
  "per_page": 50,
  "hosts": [
    {
      "id": 12,
      "hostname": "printer-office",
      "current_ip": "192.168.1.45",
      "current_mac": "AA:BB:CC:DD:EE:FF",
      "vendor": "HP Inc.",
      "os_guess": "Linux 4.x",
      "is_up": true,
      "is_new": false,
      "wol_enabled": true,
      "first_seen": "2026-01-10T09:00:00Z",
      "last_seen": "2026-02-18T07:55:00Z",
      "open_port_count": 3
    }
  ]
}
```

---

### `GET /api/hosts/{id}`
Get full detail for a single host including ports, banners, and screenshots.

**Response `200`:**
```json
{
  "id": 12,
  "hostname": "printer-office",
  "current_ip": "192.168.1.45",
  "current_mac": "AA:BB:CC:DD:EE:FF",
  "vendor": "HP Inc.",
  "os_guess": "Linux 4.x",
  "is_up": true,
  "is_new": false,
  "wol_enabled": true,
  "notes": "Color laser printer, 3rd floor",
  "first_seen": "2026-01-10T09:00:00Z",
  "last_seen": "2026-02-18T07:55:00Z",
  "ports": [
    {
      "id": 88,
      "port": 80,
      "protocol": "tcp",
      "state": "open",
      "service_name": "http",
      "service_ver": "HP HTTP Server 1.0",
      "is_new": false,
      "first_seen": "2026-01-10T09:00:00Z",
      "last_seen": "2026-02-18T07:55:00Z",
      "banner": "HTTP/1.1 200 OK\r\nServer: HP HTTP Server...",
      "screenshot_url": "/api/hosts/12/ports/88/screenshot"
    }
  ],
  "history": [
    {
      "event_type": "ip_change",
      "old_value": "192.168.1.44",
      "new_value": "192.168.1.45",
      "recorded_at": "2026-02-15T06:00:00Z"
    }
  ]
}
```

---

### `PATCH /api/hosts/{id}`
Update user-editable host fields.

**Request:**
```json
{
  "notes": "Updated note",
  "wol_enabled": true,
  "is_new": false
}
```

**Response `200`:** Updated host object.

---

### `POST /api/hosts/{id}/acknowledge`
Clear the `is_new` flag on a host and all its new ports.

**Response `200`:**
```json
{ "acknowledged": true }
```

---

### `GET /api/hosts/{id}/ports/{port_id}/screenshot`
Serve the latest screenshot image for a port.

**Response:** `image/png` binary  
**Auth required:** Yes  
**Errors:** `404` if no screenshot exists

---

## 5. Scan Profiles

### `GET /api/profiles`
List all scan profiles.

**Response `200`:**
```json
[
  {
    "id": 1,
    "name": "Full Deep Scan",
    "port_range": "1-65535",
    "enable_icmp": true,
    "enable_tcp_syn": true,
    "enable_udp": true,
    "enable_fingerprint": true,
    "enable_banner": true,
    "enable_screenshot": true,
    "max_concurrency": 50,
    "rate_limit": null,
    "timeout_sec": 30
  }
]
```

---

### `POST /api/profiles`
Create a new scan profile. *(admin/operator)*

**Request:**
```json
{
  "name": "Web Ports Only",
  "port_range": "80,443,8080,8443",
  "enable_icmp": true,
  "enable_tcp_syn": true,
  "enable_udp": false,
  "enable_fingerprint": true,
  "enable_banner": true,
  "enable_screenshot": true,
  "max_concurrency": 30,
  "timeout_sec": 20
}
```

**Response `201`:** Created profile object.

---

### `PATCH /api/profiles/{id}`
Update a scan profile.

**Response `200`:** Updated profile object.

---

### `DELETE /api/profiles/{id}`
Delete a scan profile. Cannot delete if referenced by active schedules.

**Response `204 No Content`**  
**Error `409 Conflict`:** Profile in use by active schedule.

---

## 6. Scan Jobs

### `GET /api/scans`
List scan job history.

**Query params:**
| Param | Type | Description |
|---|---|---|
| `status` | string | Filter: `queued`, `running`, `completed`, `failed` |
| `page` | int | Pagination |
| `per_page` | int | Default 25 |

**Response `200`:**
```json
{
  "total": 88,
  "scans": [
    {
      "id": 55,
      "profile_name": "Standard",
      "status": "completed",
      "hosts_discovered": 142,
      "hosts_up": 98,
      "new_hosts_found": 2,
      "new_ports_found": 5,
      "started_at": "2026-02-18T02:00:00Z",
      "completed_at": "2026-02-18T02:14:33Z",
      "triggered_by": "scheduler"
    }
  ]
}
```

---

### `POST /api/scans`
Trigger a manual scan. *(admin/operator)*

**Request:**
```json
{
  "profile_id": 3,
  "subnet_ids": [1, 2]
}
```

**Response `202 Accepted`:**
```json
{
  "job_id": 56,
  "status": "queued",
  "message": "Scan job queued successfully"
}
```

---

### `GET /api/scans/{id}`
Get full detail and live status of a scan job.

**Response `200`:**
```json
{
  "id": 56,
  "profile_id": 3,
  "status": "running",
  "progress_percent": 42,
  "current_tier": "fingerprint",
  "hosts_discovered": 98,
  "hosts_up": 67,
  "new_hosts_found": 1,
  "new_ports_found": 3,
  "started_at": "2026-02-18T10:00:00Z",
  "completed_at": null
}
```

---

### `POST /api/scans/{id}/cancel`
Cancel a running or queued scan. *(admin/operator)*

**Response `200`:**
```json
{ "status": "cancelled" }
```

---

## 7. Schedules

### `GET /api/schedules`
List all scan schedules.

**Response `200`:**
```json
[
  {
    "id": 1,
    "name": "Nightly Full Scan",
    "profile_id": 3,
    "profile_name": "Full Deep Scan",
    "subnet_ids": [1, 2],
    "cron_expression": "0 2 * * *",
    "is_active": true,
    "last_run_at": "2026-02-18T02:00:00Z",
    "next_run_at": "2026-02-19T02:00:00Z"
  }
]
```

---

### `POST /api/schedules`
Create a new scan schedule. *(admin/operator)*

**Request:**
```json
{
  "name": "Hourly Quick Ping",
  "profile_id": 1,
  "subnet_ids": [1],
  "cron_expression": "0 * * * *"
}
```

**Response `201`:** Created schedule object.

---

### `PATCH /api/schedules/{id}`
Update a schedule (name, cron, active state, subnets).

**Response `200`:** Updated schedule object.

---

### `DELETE /api/schedules/{id}`
Delete a schedule. *(admin only)*

**Response `204 No Content`**

---

## 8. Wake-on-LAN

### `POST /api/hosts/{id}/wol`
Send an immediate WoL magic packet to a host. *(admin/operator)*

**Response `200`:**
```json
{
  "success": true,
  "mac_used": "AA:BB:CC:DD:EE:FF",
  "sent_at": "2026-02-18T10:05:00Z"
}
```

**Errors:**  
`400` — Host has no MAC address stored  
`400` — WoL not enabled for this host  

---

### `GET /api/hosts/{id}/wol/schedules`
List WoL schedules for a host.

**Response `200`:**
```json
[
  {
    "id": 3,
    "cron_expression": "0 7 * * 1-5",
    "is_active": true,
    "last_run_at": "2026-02-18T07:00:00Z",
    "next_run_at": "2026-02-19T07:00:00Z"
  }
]
```

---

### `POST /api/hosts/{id}/wol/schedules`
Create a WoL schedule for a host. *(admin/operator)*

**Request:**
```json
{
  "cron_expression": "0 7 * * 1-5"
}
```

**Response `201`:** Created WoL schedule object.

---

### `PATCH /api/hosts/{id}/wol/schedules/{schedule_id}`
Update or toggle a WoL schedule.

**Request:**
```json
{
  "is_active": false
}
```

**Response `200`:** Updated WoL schedule object.

---

### `DELETE /api/hosts/{id}/wol/schedules/{schedule_id}`
Delete a WoL schedule.

**Response `204 No Content`**

---

### `GET /api/wol/log`
View WoL event log. *(admin/operator)*

**Query params:** `host_id`, `page`, `per_page`

**Response `200`:**
```json
{
  "total": 44,
  "logs": [
    {
      "id": 10,
      "host_id": 12,
      "hostname": "workstation-01",
      "mac_used": "AA:BB:CC:DD:EE:FF",
      "triggered_by": "admin",
      "success": true,
      "sent_at": "2026-02-18T07:00:00Z"
    }
  ]
}
```

---

## 9. Dashboard / Summary

### `GET /api/dashboard`
Return summary stats for the dashboard home page.

**Response `200`:**
```json
{
  "total_hosts": 142,
  "hosts_up": 98,
  "hosts_down": 44,
  "new_hosts": 2,
  "new_ports": 5,
  "last_scan": {
    "id": 55,
    "completed_at": "2026-02-18T02:14:33Z",
    "profile_name": "Standard"
  },
  "active_scan": null,
  "subnets": [
    {
      "id": 1,
      "label": "Office LAN",
      "cidr": "192.168.1.0/24",
      "hosts_up": 78,
      "hosts_total": 110
    }
  ]
}
```

---

## 10. Error Response Format

All errors follow a consistent envelope:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Host with id 99 not found",
    "detail": null
  }
}
```

**Standard HTTP status codes used:**
| Code | Meaning |
|---|---|
| `200` | OK |
| `201` | Created |
| `202` | Accepted (async job queued) |
| `204` | No Content (delete success) |
| `400` | Bad Request |
| `401` | Unauthorized (not logged in) |
| `403` | Forbidden (insufficient role) |
| `404` | Not Found |
| `409` | Conflict |
| `422` | Validation Error |
| `429` | Rate Limited |
| `500` | Internal Server Error |

---

## 11. WebSocket (Live Scan Progress)

### `WS /api/ws/scans/{job_id}`
Subscribe to live progress updates for a running scan job.

**Messages received (JSON):**
```json
{
  "type": "progress",
  "job_id": 56,
  "progress_percent": 67,
  "current_tier": "banner",
  "hosts_up": 89,
  "new_hosts_found": 1,
  "new_ports_found": 4
}
```

```json
{
  "type": "completed",
  "job_id": 56,
  "summary": {
    "hosts_discovered": 142,
    "hosts_up": 98,
    "new_hosts_found": 1,
    "new_ports_found": 4,
    "duration_sec": 874
  }
}
```

```json
{
  "type": "error",
  "job_id": 56,
  "message": "Scan failed: nmap not found"
}
```

---

## 12. Rate Limiting

| Endpoint | Limit |
|---|---|
| `POST /api/auth/login` | 10 requests / minute / IP |
| `POST /api/scans` | 5 requests / minute / user |
| `POST /api/hosts/{id}/wol` | 10 requests / minute / user |
| All other endpoints | 120 requests / minute / user |
