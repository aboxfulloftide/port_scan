# Data Model Specification
## Internal Port & IP Scanner (NetScan)

**Version:** 1.0  
**Date:** 2026-02-18  
**Status:** Approved for Development

---

## 1. Database Overview

- **Engine:** MySQL 8.0+
- **Schema/Database name:** `netscan`
- **ORM:** SQLAlchemy 2.0 (async)
- **Migrations:** Alembic

> The `users` and `roles` tables are intentionally generic and shared. Other internal tools should reference this same database for authentication.

---

## 2. Entity Relationship Diagram

```
users ──────────────────────────────────────────────────────┐
  │                                                          │
  │ (created_by / triggered_by)                             │
  ▼                                                          │
scan_jobs ──────────► scan_results                          │
  │                       │                                  │
  │                       ▼                                  │
  │                   hosts ◄──────────────────────────────┘
  │                     │
  │              ┌──────┴──────────────┐
  │              │                     │
  │           host_ports          host_history
  │              │
  │         port_banners
  │         port_screenshots
  │
scan_profiles ◄── scan_jobs
subnets
schedules ──────► scan_jobs (triggered_by_schedule)
wol_schedules ──► wol_log
```

---

## 3. Table Definitions

---

### 3.1 `users` *(Shared Auth Table)*

```sql
CREATE TABLE users (
    id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(64) NOT NULL UNIQUE,
    email         VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,          -- bcrypt
    role          ENUM('admin','operator','viewer') NOT NULL DEFAULT 'viewer',
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_login    DATETIME NULL
);
```

**Notes:**
- `password_hash` uses bcrypt (cost factor 12)
- `role` is intentionally a simple ENUM for now; can be normalized to a `roles` table when needed by other tools
- This table lives in the `netscan` schema but is designed to be referenced externally

---

### 3.2 `refresh_tokens`

```sql
CREATE TABLE refresh_tokens (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id     INT UNSIGNED NOT NULL,
    token_hash  VARCHAR(255) NOT NULL UNIQUE,     -- SHA-256 of the raw token
    expires_at  DATETIME NOT NULL,
    revoked     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

---

### 3.3 `subnets`

```sql
CREATE TABLE subnets (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    label       VARCHAR(128) NOT NULL,            -- e.g. "Office LAN"
    cidr        VARCHAR(18) NOT NULL UNIQUE,      -- e.g. "192.168.1.0/24"
    description TEXT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

### 3.4 `hosts` *(Core Identity Table)*

```sql
CREATE TABLE hosts (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    hostname        VARCHAR(255) NULL,            -- PRIMARY identity anchor
    current_ip      VARCHAR(45) NOT NULL,         -- Current IPv4
    current_mac     VARCHAR(17) NULL,             -- Current MAC (AA:BB:CC:DD:EE:FF)
    subnet_id       INT UNSIGNED NULL,
    vendor          VARCHAR(255) NULL,            -- MAC OUI vendor lookup
    os_guess        VARCHAR(255) NULL,            -- nmap OS detection
    is_up           BOOLEAN NOT NULL DEFAULT FALSE,
    is_new          BOOLEAN NOT NULL DEFAULT TRUE,  -- Flagged until acknowledged
    first_seen      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen       DATETIME NULL,
    notes           TEXT NULL,                    -- User-editable notes
    wol_enabled     BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (subnet_id) REFERENCES subnets(id) ON DELETE SET NULL,
    INDEX idx_hostname (hostname),
    INDEX idx_current_ip (current_ip),
    INDEX idx_current_mac (current_mac)
);
```

**Notes:**
- `hostname` is NULL-able for hosts that cannot be resolved
- `is_new` is set TRUE on creation, cleared when an admin/operator acknowledges the host
- `current_ip` and `current_mac` are always the most recent observed values

---

### 3.5 `host_history`

Tracks every time a host's IP or MAC changes.

```sql
CREATE TABLE host_history (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    host_id     INT UNSIGNED NOT NULL,
    event_type  ENUM('ip_change','mac_change','hostname_change','status_change') NOT NULL,
    old_value   VARCHAR(255) NULL,
    new_value   VARCHAR(255) NULL,
    scan_job_id INT UNSIGNED NULL,
    recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (host_id) REFERENCES hosts(id) ON DELETE CASCADE,
    INDEX idx_host_id (host_id),
    INDEX idx_recorded_at (recorded_at)
);
```

---

### 3.6 `host_ports`

```sql
CREATE TABLE host_ports (
    id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    host_id      INT UNSIGNED NOT NULL,
    port         SMALLINT UNSIGNED NOT NULL,
    protocol     ENUM('tcp','udp') NOT NULL DEFAULT 'tcp',
    state        ENUM('open','closed','filtered') NOT NULL,
    service_name VARCHAR(128) NULL,              -- e.g. "http", "ssh"
    service_ver  VARCHAR(255) NULL,              -- e.g. "nginx 1.21.0"
    is_new       BOOLEAN NOT NULL DEFAULT TRUE,  -- Flagged until acknowledged
    first_seen   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen    DATETIME NULL,
    FOREIGN KEY (host_id) REFERENCES hosts(id) ON DELETE CASCADE,
    UNIQUE KEY uq_host_port_proto (host_id, port, protocol),
    INDEX idx_host_id (host_id),
    INDEX idx_port (port)
);
```

---

### 3.7 `port_banners`

```sql
CREATE TABLE port_banners (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    host_port_id INT UNSIGNED NOT NULL,
    banner_text TEXT NULL,
    captured_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (host_port_id) REFERENCES host_ports(id) ON DELETE CASCADE
);
```

---

### 3.8 `port_screenshots`

```sql
CREATE TABLE port_screenshots (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    host_port_id    INT UNSIGNED NOT NULL,
    file_path       VARCHAR(512) NOT NULL,        -- relative path under /home/matheau/code/port_scan/screenshots/
    url_captured    VARCHAR(512) NULL,            -- e.g. "https://192.168.1.10:8443"
    captured_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (host_port_id) REFERENCES host_ports(id) ON DELETE CASCADE
);
```

---

### 3.9 `scan_profiles`

```sql
CREATE TABLE scan_profiles (
    id                  INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name                VARCHAR(128) NOT NULL UNIQUE,
    description         TEXT NULL,
    port_range          VARCHAR(255) NOT NULL DEFAULT '1-65535',  -- e.g. "1-1024,8080,8443"
    enable_icmp         BOOLEAN NOT NULL DEFAULT TRUE,
    enable_tcp_syn      BOOLEAN NOT NULL DEFAULT TRUE,
    enable_udp          BOOLEAN NOT NULL DEFAULT FALSE,
    enable_fingerprint  BOOLEAN NOT NULL DEFAULT TRUE,
    enable_banner       BOOLEAN NOT NULL DEFAULT TRUE,
    enable_screenshot   BOOLEAN NOT NULL DEFAULT TRUE,
    max_concurrency     SMALLINT UNSIGNED NOT NULL DEFAULT 50,
    rate_limit          SMALLINT UNSIGNED NULL,   -- packets/sec, NULL = no limit
    timeout_sec         SMALLINT UNSIGNED NOT NULL DEFAULT 30,
    created_by          INT UNSIGNED NULL,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);
```

**Default profiles seeded on install:**
| Name | Description |
|---|---|
| `Quick Ping` | ICMP only, no port scan |
| `Standard` | ICMP + TCP SYN + Fingerprint, top 1000 ports |
| `Full Deep Scan` | All tiers, all 65535 ports |

---

### 3.10 `scan_jobs`

```sql
CREATE TABLE scan_jobs (
    id                  INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    profile_id          INT UNSIGNED NOT NULL,
    subnet_ids          JSON NOT NULL,            -- Array of subnet IDs scanned
    status              ENUM('queued','running','completed','failed','cancelled') NOT NULL DEFAULT 'queued',
    triggered_by        INT UNSIGNED NULL,        -- user_id (NULL if scheduled)
    schedule_id         INT UNSIGNED NULL,        -- FK to schedules if auto-triggered
    hosts_discovered    SMALLINT UNSIGNED NULL,
    hosts_up            SMALLINT UNSIGNED NULL,
    new_hosts_found     SMALLINT UNSIGNED NULL,
    new_ports_found     SMALLINT UNSIGNED NULL,
    started_at          DATETIME NULL,
    completed_at        DATETIME NULL,
    error_message       TEXT NULL,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (profile_id) REFERENCES scan_profiles(id),
    FOREIGN KEY (triggered_by) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
);
```

---

### 3.11 `schedules`

```sql
CREATE TABLE schedules (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(128) NOT NULL,
    profile_id      INT UNSIGNED NOT NULL,
    subnet_ids      JSON NOT NULL,               -- Array of subnet IDs to scan
    cron_expression VARCHAR(128) NOT NULL,        -- e.g. "0 2 * * *"
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_by      INT UNSIGNED NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_run_at     DATETIME NULL,
    next_run_at     DATETIME NULL,
    FOREIGN KEY (profile_id) REFERENCES scan_profiles(id),
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);
```

---

### 3.12 `wol_schedules`

```sql
CREATE TABLE wol_schedules (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    host_id         INT UNSIGNED NOT NULL,
    cron_expression VARCHAR(128) NOT NULL,        -- e.g. "0 7 * * 1-5"
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_by      INT UNSIGNED NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_run_at     DATETIME NULL,
    next_run_at     DATETIME NULL,
    FOREIGN KEY (host_id) REFERENCES hosts(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);
```

---

### 3.13 `wol_log`

```sql
CREATE TABLE wol_log (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    host_id         INT UNSIGNED NOT NULL,
    mac_used        VARCHAR(17) NOT NULL,
    triggered_by    INT UNSIGNED NULL,           -- user_id (NULL if scheduled)
    schedule_id     INT UNSIGNED NULL,
    success         BOOLEAN NOT NULL DEFAULT TRUE,
    error_message   TEXT NULL,
    sent_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (host_id) REFERENCES hosts(id) ON DELETE CASCADE,
    FOREIGN KEY (triggered_by) REFERENCES users(id) ON DELETE SET NULL
);
```

---

## 4. Indexes Summary

| Table | Index | Purpose |
|---|---|---|
| `hosts` | `idx_hostname` | Fast hostname lookup for identity resolution |
| `hosts` | `idx_current_ip` | Fast IP lookup during scan result processing |
| `hosts` | `idx_current_mac` | MAC-based deduplication |
| `host_ports` | `uq_host_port_proto` | Prevent duplicate port records |
| `host_history` | `idx_recorded_at` | Time-range queries for change history |
| `scan_jobs` | `idx_status` | Filter active/queued jobs |
| `scan_jobs` | `idx_created_at` | Scan history pagination |

---

## 5. Data Retention Policy

| Data | Retention |
|---|---|
| `scan_jobs` | Keep all (lightweight) |
| `host_history` | Keep all |
| `port_banners` | Keep last 5 per port (application-level cleanup) |
| `port_screenshots` | Keep last 3 per port; old files deleted from disk |
| `wol_log` | Keep 90 days |
| `refresh_tokens` | Purge expired tokens nightly (APScheduler job) |

---

## 6. Seed Data

On first install, the following data is seeded:

```sql
-- Default admin user (password must be changed on first login)
INSERT INTO users (username, email, password_hash, role)
VALUES ('admin', 'admin@localhost', '<bcrypt_of_changeme>', 'admin');

-- Default scan profiles
INSERT INTO scan_profiles (name, description, port_range, enable_icmp, enable_tcp_syn, enable_udp, enable_fingerprint, enable_banner, enable_screenshot)
VALUES
  ('Quick Ping',     'ICMP host discovery only',              '1-65535', TRUE,  FALSE, FALSE, FALSE, FALSE, FALSE),
  ('Standard',       'TCP SYN + fingerprint, top 1000 ports', '1-1000',  TRUE,  TRUE,  FALSE, TRUE,  TRUE,  TRUE),
  ('Full Deep Scan', 'All tiers, all ports',                  '1-65535', TRUE,  TRUE,  TRUE,  TRUE,  TRUE,  TRUE);
```
