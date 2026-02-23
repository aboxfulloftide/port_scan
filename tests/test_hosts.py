import pytest
import pytest_asyncio
from datetime import datetime, timezone
from shared.models import Host, Subnet


@pytest_asyncio.fixture
async def sample_subnet(db_session):
    s = Subnet(cidr="192.168.99.0/24", label="Test Subnet")
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


@pytest_asyncio.fixture
async def sample_host(db_session, sample_subnet):
    h = Host(
        hostname="testhost.local",
        current_ip="192.168.99.10",
        current_mac="AA:BB:CC:DD:EE:FF",
        subnet_id=sample_subnet.id,
        is_up=True,
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
    resp = await admin_client.get("/api/hosts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    ips = [h["current_ip"] for h in data["hosts"]]
    assert "192.168.99.10" in ips


@pytest.mark.asyncio
async def test_list_hosts_filter_up(admin_client, sample_host):
    resp = await admin_client.get("/api/hosts", params={"is_up": True})
    assert resp.status_code == 200
    hosts = resp.json()["hosts"]
    assert all(h["is_up"] for h in hosts)


@pytest.mark.asyncio
async def test_get_host_detail(admin_client, sample_host):
    resp = await admin_client.get(f"/api/hosts/{sample_host.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["hostname"] == "testhost.local"
    assert data["current_ip"] == "192.168.99.10"


@pytest.mark.asyncio
async def test_host_not_found(admin_client):
    resp = await admin_client.get("/api/hosts/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_acknowledge_host(admin_client, sample_host):
    resp = await admin_client.post(f"/api/hosts/{sample_host.id}/acknowledge")
    assert resp.status_code == 200
    detail = await admin_client.get(f"/api/hosts/{sample_host.id}")
    assert detail.json()["is_new"] is False


@pytest.mark.asyncio
async def test_update_host_notes(admin_client, sample_host):
    resp = await admin_client.patch(f"/api/hosts/{sample_host.id}", json={"notes": "Important server"})
    assert resp.status_code == 200
    assert resp.json()["notes"] == "Important server"
