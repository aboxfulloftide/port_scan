import pytest
import pytest_asyncio
from unittest.mock import patch
from datetime import datetime, timezone
from shared.models import Host, Subnet


@pytest_asyncio.fixture
async def wol_host(db_session):
    subnet = Subnet(cidr="192.168.88.0/24", label="WoL Net")
    db_session.add(subnet)
    await db_session.flush()
    host = Host(
        hostname="wol-target.local",
        current_ip="192.168.88.50",
        current_mac="DE:AD:BE:EF:00:01",
        subnet_id=subnet.id,
        is_up=False,
        wol_enabled=True,
        first_seen=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
    )
    db_session.add(host)
    await db_session.commit()
    await db_session.refresh(host)
    return host


@pytest_asyncio.fixture
async def no_mac_host(db_session):
    subnet = Subnet(cidr="192.168.77.0/24", label="No MAC Net")
    db_session.add(subnet)
    await db_session.flush()
    host = Host(
        hostname="no-mac.local",
        current_ip="192.168.77.1",
        current_mac=None,
        subnet_id=subnet.id,
        is_up=False,
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
    mock_wol.assert_called_once()


@pytest.mark.asyncio
async def test_send_wol_no_mac(admin_client, no_mac_host):
    resp = await admin_client.post("/api/wol/send", json={"host_id": no_mac_host.id})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_send_wol_host_not_found(admin_client):
    resp = await admin_client.post("/api/wol/send", json={"host_id": 99999})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_wol_log_created(admin_client, wol_host):
    with patch("wakeonlan.send_magic_packet"):
        await admin_client.post("/api/wol/send", json={"host_id": wol_host.id})

    resp = await admin_client.get(f"/api/wol/log", params={"host_id": wol_host.id})
    assert resp.status_code == 200
    logs = resp.json()
    assert len(logs) >= 1
    assert logs[0]["mac_used"] == "DE:AD:BE:EF:00:01"
    assert logs[0]["success"] is True
