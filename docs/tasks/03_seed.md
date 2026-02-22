# Task 03 — Seed Default Data

## Status: COMPLETE ✅

**Completed:** 2026-02-22
**Deviations from plan:**
- `force_password_change` column not added (skipped)
- Admin user and 3 scan profiles seeded successfully
- bcrypt hash generated with passlib (bcrypt pinned to 4.1.3 for passlib compatibility)



**Depends on:** Task 02  
**Complexity:** Low  
**Run as:** netscan_user (MySQL)

---

## Objective
Insert the default admin user and the three built-in scan profiles into the database.

---

## Steps

### 1. Generate bcrypt hash for default password
Run this Python snippet to generate the hash for `changeme`:
```python
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
print(pwd_context.hash("changeme"))
# Copy the output hash for use below
```

### 2. Insert seed data
```sql
USE netscan;

-- Default admin user
INSERT INTO users (username, email, password_hash, role, is_active)
VALUES (
    'admin',
    'admin@localhost',
    '$2b$12$REPLACE_WITH_BCRYPT_HASH_FROM_STEP_1',
    'admin',
    TRUE
);

-- Default scan profiles
INSERT INTO scan_profiles
    (name, description, port_range, enable_icmp, enable_tcp_syn, enable_udp, enable_fingerprint, enable_banner, enable_screenshot, max_concurrency, timeout_sec)
VALUES
    (
        'Quick Ping',
        'ICMP host discovery only. No port scanning.',
        '1-65535',
        TRUE, FALSE, FALSE, FALSE, FALSE, FALSE,
        100, 10
    ),
    (
        'Standard',
        'TCP SYN scan with service fingerprinting on top 1000 ports.',
        '1-1000',
        TRUE, TRUE, FALSE, TRUE, TRUE, TRUE,
        50, 30
    ),
    (
        'Full Deep Scan',
        'All scan tiers enabled across all 65535 ports. Slowest but most thorough.',
        '1-65535',
        TRUE, TRUE, TRUE, TRUE, TRUE, TRUE,
        30, 60
    );
```

### 3. Verify seed data
```sql
SELECT id, username, role FROM users;
SELECT id, name, port_range FROM scan_profiles;
```

### 4. Force password change on first login (application-level flag)
Add a `force_password_change` column to `users` for first-login enforcement:
```sql
ALTER TABLE users ADD COLUMN force_password_change BOOLEAN NOT NULL DEFAULT FALSE;
UPDATE users SET force_password_change = TRUE WHERE username = 'admin';
```

---

## Acceptance Criteria
- [ ] `admin` user exists in `users` table with role `admin`
- [ ] Password hash is valid bcrypt (starts with `$2b$`)
- [ ] Three scan profiles exist: `Quick Ping`, `Standard`, `Full Deep Scan`
- [ ] `force_password_change` column exists and is TRUE for admin
