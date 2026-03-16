-- Merge Suggestion Ignore Feature Migration
-- Run against the port_scan database

CREATE TABLE IF NOT EXISTS merge_suggestion_ignores (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    host_id_a     INT UNSIGNED NOT NULL,
    host_id_b     INT UNSIGNED NOT NULL,
    dismissed_by  INT UNSIGNED NULL,
    dismissed_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_ignore_pair (host_id_a, host_id_b),
    CONSTRAINT fk_msi_host_a FOREIGN KEY (host_id_a) REFERENCES hosts(id) ON DELETE CASCADE,
    CONSTRAINT fk_msi_host_b FOREIGN KEY (host_id_b) REFERENCES hosts(id) ON DELETE CASCADE,
    CONSTRAINT fk_msi_user   FOREIGN KEY (dismissed_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
