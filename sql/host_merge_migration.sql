-- Host Multi-Identity & Merge Feature Migration
-- Run against the port_scan database

-- 1. Add primary_host_id self-referencing FK to hosts
ALTER TABLE hosts
    ADD COLUMN primary_host_id INT UNSIGNED NULL,
    ADD INDEX idx_hosts_primary_host_id (primary_host_id),
    ADD CONSTRAINT fk_hosts_primary_host
        FOREIGN KEY (primary_host_id) REFERENCES hosts(id) ON DELETE SET NULL;

-- 2. Create host_network_ids table
CREATE TABLE IF NOT EXISTS host_network_ids (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    host_id     INT UNSIGNED NOT NULL,
    ip_address  VARCHAR(45) NOT NULL,
    mac_address VARCHAR(17) NULL,
    source      ENUM('scan', 'dhcp', 'manual') NOT NULL DEFAULT 'scan',
    first_seen  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_hni_host_id (host_id),
    INDEX idx_hni_ip (ip_address),
    INDEX idx_hni_mac (mac_address),
    UNIQUE KEY uq_host_ip_mac (host_id, ip_address, mac_address),
    CONSTRAINT fk_hni_host FOREIGN KEY (host_id) REFERENCES hosts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. Create host_merge_log table
CREATE TABLE IF NOT EXISTS host_merge_log (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    primary_host_id  INT UNSIGNED NOT NULL,
    alias_host_id    INT UNSIGNED NOT NULL,
    action           ENUM('merge', 'unmerge') NOT NULL,
    performed_by     INT UNSIGNED NULL,
    performed_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    snapshot         JSON NULL,
    CONSTRAINT fk_hml_primary FOREIGN KEY (primary_host_id) REFERENCES hosts(id) ON DELETE CASCADE,
    CONSTRAINT fk_hml_alias   FOREIGN KEY (alias_host_id)   REFERENCES hosts(id) ON DELETE CASCADE,
    CONSTRAINT fk_hml_user    FOREIGN KEY (performed_by)    REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. Backfill host_network_ids from existing hosts.current_ip / current_mac
INSERT INTO host_network_ids (host_id, ip_address, mac_address, source, first_seen, last_seen)
SELECT id, current_ip, current_mac, 'scan', first_seen, COALESCE(last_seen, first_seen)
FROM hosts
WHERE current_ip IS NOT NULL
ON DUPLICATE KEY UPDATE last_seen = VALUES(last_seen);

-- 5. Backfill from host_history ip_change events (capture old IPs)
INSERT INTO host_network_ids (host_id, ip_address, mac_address, source, first_seen, last_seen)
SELECT hh.host_id, hh.old_value, h.current_mac, 'scan', hh.recorded_at, hh.recorded_at
FROM host_history hh
JOIN hosts h ON h.id = hh.host_id
WHERE hh.event_type = 'ip_change' AND hh.old_value IS NOT NULL
ON DUPLICATE KEY UPDATE
    first_seen = LEAST(host_network_ids.first_seen, VALUES(first_seen)),
    last_seen  = GREATEST(host_network_ids.last_seen, VALUES(last_seen));

-- 6. Backfill from host_history mac_change events (capture old MACs)
INSERT INTO host_network_ids (host_id, ip_address, mac_address, source, first_seen, last_seen)
SELECT hh.host_id, h.current_ip, hh.old_value, 'scan', hh.recorded_at, hh.recorded_at
FROM host_history hh
JOIN hosts h ON h.id = hh.host_id
WHERE hh.event_type = 'mac_change' AND hh.old_value IS NOT NULL
ON DUPLICATE KEY UPDATE
    first_seen = LEAST(host_network_ids.first_seen, VALUES(first_seen)),
    last_seen  = GREATEST(host_network_ids.last_seen, VALUES(last_seen));
