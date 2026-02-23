import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone
from shared.models import Subnet, ScanProfile, ScanJob


@pytest_asyncio.fixture
async def scan_fixtures(db_session):
    subnet = Subnet(cidr="10.0.99.0/24", label="Test Net")
    profile = ScanProfile(
        name="Test Profile",
        port_range="80,443",
        enable_udp=False,
        enable_screenshot=False,
        max_concurrency=10,
        rate_limit=100,
        timeout_sec=3,
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
        resp = await admin_client.post("/api/scans", json={
            "subnet_ids": [subnet.id],
            "profile_id": profile.id,
        })
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert "job_id" in data


@pytest.mark.asyncio
async def test_list_scans(admin_client):
    resp = await admin_client.get("/api/scans")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "scans" in data


@pytest.mark.asyncio
async def test_get_scan_detail(admin_client, scan_fixtures, db_session):
    subnet, profile = scan_fixtures
    job = ScanJob(
        profile_id=profile.id,
        subnet_ids=[subnet.id],
        status="completed",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    resp = await admin_client.get(f"/api/scans/{job.id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_cancel_queued_scan(admin_client, scan_fixtures, db_session):
    subnet, profile = scan_fixtures
    job = ScanJob(
        profile_id=profile.id,
        subnet_ids=[subnet.id],
        status="queued",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    resp = await admin_client.post(f"/api/scans/{job.id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_completed_scan_fails(admin_client, scan_fixtures, db_session):
    subnet, profile = scan_fixtures
    job = ScanJob(
        profile_id=profile.id,
        subnet_ids=[subnet.id],
        status="completed",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    resp = await admin_client.post(f"/api/scans/{job.id}/cancel")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_trigger_scan_duplicate_rejected(admin_client, scan_fixtures, db_session):
    """A second scan trigger while one is queued/running should return 409."""
    subnet, profile = scan_fixtures
    job = ScanJob(
        profile_id=profile.id,
        subnet_ids=[subnet.id],
        status="queued",
    )
    db_session.add(job)
    await db_session.commit()

    with patch("worker.queue.job_queue.put", new_callable=AsyncMock):
        resp = await admin_client.post("/api/scans", json={
            "subnet_ids": [subnet.id],
            "profile_id": profile.id,
        })
    assert resp.status_code == 409
