# Task 02 — MySQL Schema Creation & Migrations

## Status: COMPLETE ✅

**Completed:** 2026-02-22
**Deviations from plan:**
- Database named `port_scan` (not `netscan`), user `matheau` (not `netscan_user`)
- No Alembic setup — tables created directly via raw SQL in MySQL
- All 13 tables created and verified working



**Depends on:** Task 01  
**Complexity:** Low  
**Run as:** MySQL root or admin user

---

## Objective
Create the `netscan` MySQL database, a dedicated DB user, and run all table creation scripts. Set up Alembic for future migrations.

---

## Steps

### 1. Create MySQL database and user
```sql
CREATE DATABASE IF NOT EXISTS netscan CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'netscan_user'@'localhost' IDENTIFIED BY 'CHANGE_ME_DB_PASSWORD';

GRANT ALL PRIVILEGES ON netscan.* TO 'netscan_user'@'localhost';
FLUSH PRIVILEGES;
```

### 2. Create all tables
Run the following in order against the `netscan` database:

```sql
USE netscan;

-- Users (shared auth table)
CREATE TABLE users (
    id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(64) NOT NULL UNIQUE,
    email         VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role          ENUM('admin','operator','viewer') NOT NULL DEFAULT 'viewer',
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_login    DATETIME NULL
);

-- Refresh tokens
CREATE TABLE refresh_tokens (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id     INT UNSIGNED NOT NULL,
    token_hash  VARCHAR(255) NOT NULL UNIQUE,
    expires_at  DATETIME NOT NULL,
    revoked     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Subnets
CREATE TABLE subnets (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    label       VARCHAR(128) NOT NULL,
    cidr        VARCHAR(18) NOT NULL UNIQUE,
    description TEXT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Hosts
CREATE TABLE hosts (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    hostname        VARCHAR(255) NULL,
    current_ip      VARCHAR(45) NOT NULL,
    current_mac     VARCHAR(17) NULL,
    subnet_id       INT UNSIGNED NULL,
    vendor          VARCHAR(255) NULL,
    os_guess        VARCHAR(255) NULL,
    is_up           BOOLEAN NOT NULL DEFAULT FALSE,
    is_new          BOOLEAN NOT NULL DEFAULT TRUE,
    first_seen      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen       DATETIME NULL,
    notes           TEXT NULL,
    wol_enabled     BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (subnet_id) REFERENCES subnets(id) ON DELETE SET NULL,
    INDEX idx_hostname (hostname),
    INDEX idx_current_ip (current_ip),
    INDEX idx_current_mac (current_mac)
);

-- Host history
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

-- Host ports
CREATE TABLE host_ports (
    id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    host_id      INT UNSIGNED NOT NULL,
    port         SMALLINT UNSIGNED NOT NULL,
    protocol     ENUM('tcp','udp') NOT NULL DEFAULT 'tcp',
    state        ENUM('open','closed','filtered') NOT NULL,
    service_name VARCHAR(128) NULL,
    service_ver  VARCHAR(255) NULL,
    is_new       BOOLEAN NOT NULL DEFAULT TRUE,
    first_seen   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen    DATETIME NULL,
    FOREIGN KEY (host_id) REFERENCES hosts(id) ON DELETE CASCADE,
    UNIQUE KEY uq_host_port_proto (host_id, port, protocol),
    INDEX idx_host_id (host_id),
    INDEX idx_port (port)
);

-- Port banners
CREATE TABLE port_banners (
    id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    host_port_id INT UNSIGNED NOT NULL,
    banner_text  TEXT NULL,
    captured_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (host_port_id) REFERENCES host_ports(id) ON DELETE CASCADE
);

-- Port screenshots
CREATE TABLE port_screenshots (
    id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    host_port_id INT UNSIGNED NOT NULL,
    file_path    VARCHAR(512) NOT NULL,
    url_captured VARCHAR(512) NULL,
    captured_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (host_port_id) REFERENCES host_ports(id) ON DELETE CASCADE
);

-- Scan profiles
CREATE TABLE scan_profiles (
    id                  INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name                VARCHAR(128) NOT NULL UNIQUE,
    description         TEXT NULL,
    port_range          VARCHAR(255) NOT NULL DEFAULT '1-65535',
    enable_icmp         BOOLEAN NOT NULL DEFAULT TRUE,
    enable_tcp_syn      BOOLEAN NOT NULL DEFAULT TRUE,
    enable_udp          BOOLEAN NOT NULL DEFAULT FALSE,
    enable_fingerprint  BOOLEAN NOT NULL DEFAULT TRUE,
    enable_banner       BOOLEAN NOT NULL DEFAULT TRUE,
    enable_screenshot   BOOLEAN NOT NULL DEFAULT TRUE,
    max_concurrency     SMALLINT UNSIGNED NOT NULL DEFAULT 50,
    rate_limit          SMALLINT UNSIGNED NULL,
    timeout_sec         SMALLINT UNSIGNED NOT NULL DEFAULT 30,
    created_by          INT UNSIGNED NULL,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);

-- Scan jobs
CREATE TABLE scan_jobs (
    id                  INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    profile_id          INT UNSIGNED NOT NULL,
    subnet_ids          JSON NOT NULL,
    status              ENUM('queued','running','completed','failed','cancelled') NOT NULL DEFAULT 'queued',
    triggered_by        INT UNSIGNED NULL,
    schedule_id         INT UNSIGNED NULL,
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

-- Schedules
CREATE TABLE schedules (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(128) NOT NULL,
    profile_id      INT UNSIGNED NOT NULL,
    subnet_ids      JSON NOT NULL,
    cron_expression VARCHAR(128) NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_by      INT UNSIGNED NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_run_at     DATETIME NULL,
    next_run_at     DATETIME NULL,
    FOREIGN KEY (profile_id) REFERENCES scan_profiles(id),
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);

-- WoL schedules
CREATE TABLE wol_schedules (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    host_id         INT UNSIGNED NOT NULL,
    cron_expression VARCHAR(128) NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_by      INT UNSIGNED NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_run_at     DATETIME NULL,
    next_run_at     DATETIME NULL,
    FOREIGN KEY (host_id) REFERENCES hosts(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);

-- WoL log
CREATE TABLE wol_log (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    host_id         INT UNSIGNED NOT NULL,
    mac_used        VARCHAR(17) NOT NULL,
    triggered_by    INT UNSIGNED NULL,
    schedule_id     INT UNSIGNED NULL,
    success         BOOLEAN NOT NULL DEFAULT TRUE,
    error_message   TEXT NULL,
    sent_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (host_id) REFERENCES hosts(id) ON DELETE CASCADE,
    FOREIGN KEY (triggered_by) REFERENCES users(id) ON DELETE SET NULL
);
```

### 3. Initialize Alembic
```bash
cd /home/matheau/code/port_scan
sudo -u netscan /home/matheau/code/port_scan/venv/bin/alembic init alembic
```

Update `alembic.ini` — set `sqlalchemy.url`:
```ini
sqlalchemy.url = mysql+pymysql://netscan_user:CHANGE_ME_DB_PASSWORD@127.0.0.1/netscan
```

Create initial migration snapshot:
```bash
sudo -u netscan /home/matheau/code/port_scan/venv/bin/alembic revision --autogenerate -m "initial_schema"
sudo -u netscan /home/matheau/code/port_scan/venv/bin/alembic stamp head
```

---

## Acceptance Criteria
- [ ] `netscan` database exists in MySQL
- [ ] `netscan_user` can connect and has full privileges on `netscan`
- [ ] All 13 tables created without errors
- [ ] All foreign keys and indexes verified with `SHOW CREATE TABLE`
- [ ] Alembic initialized and stamped at `head`
