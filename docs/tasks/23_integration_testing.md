# Task 23: Integration Testing

**Depends on:** All previous tasks  
**Complexity:** Medium  
**Description:** Write integration tests covering the auth flow, CRUD endpoints, scan job lifecycle, and WoL. Uses pytest + httpx AsyncClient against a test database.

---

## Files to Create

```
tests/
├── conftest.py
├── test_auth.py
├── test_hosts.py
├── test_scans.py
└── test_wol.py
```

---

## `tests/conftest.py`

```python
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from shared.models import Base
from shared.db import get_db
from api.main import app

TEST_DB_URL = "mysql+aiomysql://netscan:netscan_pass@localhost/netscan_test"

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest.fixture
async def db_session(test_engine):
    TestSession = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with TestSession() as session:
        yield session

@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()

@pytest.fixture
async def admin_client(client, db_session):
    """Client pre-authenticated as admin."""
    from auth.utils import hash_password
    from shared.models import User
    user = User(username="testadmin", hashed_password=hash_password("testpass"), role="admin", is_active=True)
    db_session.add(user)
    await db_session.commit()
    resp = await client.post("/api/auth/login", json={"username": "testadmin", "password": "testpass"})
    assert resp.status_code == 200
    return client
```

---

## `tests/test_auth.py`

```python
import pytest

@pytest.mark.asyncio
async def test_login_success(client, db_session):
    from auth.utils import hash_password
    from shared.models import User
    user = User(username="alice", hashed_password=hash_password("secret"), role="viewer", is_active=True)
    db_session.add(user)
    await db_session.commit()

    resp = await client.post("/api/auth/login", json={"username": "alice", "password": "secret"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "alice"
    assert "access_token" in resp.cookies or data.get("access_token")

@pytest.mark.asyncio
async def test_login_wrong_password(client, db_session):
    resp = await client.post("/api/auth/login", json={"username": "alice", "password": "wrong"})
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_me_unauthenticated(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_me_authenticated(admin_client):
    resp = await admin_client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"

@pytest.mark.asyncio
async def test_logout(admin_client):
    resp = await admin_client.post("/api/auth/logout")
    assert resp.status_code == 200
    # Subsequent /me should fail
    resp2 = await admin_client.get("/api/auth/me")
    assert resp2.status_code == 401
```

---

## `tests/test_hosts.py`

```python
import pytest
from shared.models import Host, Subnet
from datetime import datetime, timezone

@pytest.fixture
async def sample_subnet(db_session):
    s = Subnet(cidr="192.168.99.0/24", label="Test Subnet")
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s

@pytest.fixture
async def sample_host(db_session, sample_subnet):
    h = Host(
        hostname="testhost.local",
        ip_address="192.168.99.10",
        mac_address="AA:BB:CC:DD:EE:FF",
        subnet_id=sample_subnet.id,
        status="up",
        is_new=True,
        first_seen=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
    )
    db_session.add(h)
    await db_session.commit()
    await db_session.refresh(h)
    return h

@pytest.mark.asyncio
async def test_list_hosts(admin_client, sample_host):
    resp = await admin_client.get("/api/hosts/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    hostnames = [h["hostname"] for h in data["items"]]
    assert "testhost.local" in hostnames

@pytest.mark.asyncio
async def test_get_host_detail(admin_client, sample_host):
    resp = await admin_client.get(f"/api/hosts/{sample_host.id}")
    assert resp.status_code == 200
    assert resp.json()["hostname"] == "testhost.local"

@pytest.mark.asyncio
async def test_acknowledge_host(admin_client, sample_host):
    resp = await admin_client.post(f"/api/hosts/{sample_host.id}/acknowledge")
    assert resp.status_code == 200
    detail = await admin_client.get(f"/api/hosts/{sample_host.id}")
    assert detail.json()["is_new"] == False

@pytest.mark.asyncio
async def test_update_host_notes(admin_client, sample_host):
    resp = await admin_client.patch(f"/api/hosts/{sample_host.id}", json={"notes": "Important server"})
    assert resp.status_code == 200
    assert resp.json()["notes"] == "Important server"

@pytest.mark.asyncio
async def test_host_not_found(admin_client):
    resp = await admin_client.get("/api/hosts/99999")
    assert resp.status_code == 404
```

---

## `tests/test_scans.py`

```python
import pytest
from unittest.mock import patch, AsyncMock
from shared.models import Subnet, ScanProfile

@pytest.fixture
async def scan_fixtures(db_session):
    subnet = Subnet(cidr="10.0.99.0/24")
    profile = ScanProfile(
        name="Test Profile", port_range="80,443",
        enable_udp=False, enable_screenshots=False,
        concurrency=10, rate_limit=100, timeout=3
    )
    db_session.add_all([subnet, profile])
    await db_session.commit()
    await db_session.refresh(subnet)
    await db_session.refresh(profile)
    return subnet, profile

@pytest.mark.asyncio
async def test_trigger_scan(admin_client, scan_fixtures):
    subnet, profile = scan_fixtures
    with patch("worker.queue.job_queue.put", new_callable=AsyncMock):
        resp = await admin_client.post("/api/scans/", json={
            "subnet_id": subnet.id,
            "profile_id": profile.id
        })
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "queued"
    assert data["subnet_id"] == subnet.id

@pytest.mark.asyncio
async def test_list_scans(admin_client, scan_fixtures):
    resp = await admin_client.get("/api/scans/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

@pytest.mark.asyncio
async def test_cancel_queued_scan(admin_client, scan_fixtures, db_session):
    subnet, profile = scan_fixtures
    from shared.models import ScanJob
    from datetime import datetime, timezone
    job = ScanJob(subnet_id=subnet.id, profile_id=profile.id, status="queued",
                  triggered_by="manual", started_at=datetime.now(timezone.utc))
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    resp = await admin_client.post(f"/api/scans/{job.id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

@pytest.mark.asyncio
async def test_cancel_completed_scan_fails(admin_client, scan_fixtures, db_session):
    subnet, profile = scan_fixtures
    from shared.models import ScanJob
    from datetime import datetime, timezone
    job = ScanJob(subnet_id=subnet.id, profile_id=profile.id, status="completed",
                  triggered_by="manual", started_at=datetime.now(timezone.utc))
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    resp = await admin_client.post(f"/api/scans/{job.id}/cancel")
    assert resp.status_code == 400
```

---

## `tests/test_wol.py`

```python
import pytest
from unittest.mock import patch
from shared.models import Host, Subnet
from datetime import datetime, timezone

@pytest.fixture
async def wol_host(db_session):
    subnet = Subnet(cidr="192.168.88.0/24")
    db_session.add(subnet)
    await db_session.flush()
    host = Host(
        hostname="wol-target.local",
        ip_address="192.168.88.50",
        mac_address="DE:AD:BE:EF:00:01",
        subnet_id=subnet.id,
        status="down",
        wol_enabled=True,
        first_seen=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
    )
    db_session.add(host)
    await db_session.commit()
    await db_session.refresh(host)
    return host

@pytest.mark.asyncio
async def test_send_wol_success(admin_client, wol_host):
    with patch("wakeonlan.send_magic_packet") as mock_wol:
        resp = await admin_client.post("/api/wol/send", json={"host_id": wol_host.id})
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"
    mock_wol.assert_called_once_with("DE:AD:BE:EF:00:01", ip_address="255.255.255.255", port=9)

@pytest.mark.asyncio
async def test_send_wol_no_mac(admin_client, db_session):
    subnet = Subnet(cidr="192.168.77.0/24")
    db_session.add(subnet)
    await db_session.flush()
    host = Host(
        hostname="no-mac.local", ip_address="192.168.77.1",
        mac_address=None, subnet_id=subnet.id, wol_enabled=True,
        first_seen=datetime.now(timezone.utc), last_seen=datetime.now(timezone.utc),
    )
    db_session.add(host)
    await db_session.commit()
    await db_session.refresh(host)

    resp = await admin_client.post("/api/wol/send", json={"host_id": host.id})
    assert resp.status_code == 400

@pytest.mark.asyncio
async def test_wol_log_created(admin_client, wol_host, db_session):
    with patch("wakeonlan.send_magic_packet"):
        await admin_client.post("/api/wol/send", json={"host_id": wol_host.id})
    resp = await admin_client.get(f"/api/wol/log?host_id={wol_host.id}")
    assert resp.status_code == 200
    logs = resp.json()
    assert len(logs) >= 1
    assert logs[0]["triggered_by"] == "manual"
    assert logs[0]["success"] == True
```

---

## Running Tests

```bash
cd /home/matheau/code/port_scan
source venv/bin/activate

# Install test deps
pip install pytest pytest-asyncio httpx

# Create test database
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS netscan_test; GRANT ALL ON netscan_test.* TO 'netscan'@'localhost';"

# Run all tests
pytest tests/ -v

# Run specific module
pytest tests/test_auth.py -v

# Run with coverage
pip install pytest-cov
pytest tests/ --cov=. --cov-report=term-missing
```

---

## `pytest.ini`

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```
