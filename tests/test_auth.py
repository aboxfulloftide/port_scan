import pytest
import pytest_asyncio
from shared.models import User
from api.auth.utils import hash_password


@pytest_asyncio.fixture
async def viewer_user(db_session):
    user = User(
        username="alice",
        email="alice@test.local",
        password_hash=hash_password("secret"),
        role="viewer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_login_success(client, viewer_user):
    resp = await client.post("/api/auth/login", json={"username": "alice", "password": "secret"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["username"] == "alice"
    assert "access_token" in resp.cookies


@pytest.mark.asyncio
async def test_login_wrong_password(client, viewer_user):
    resp = await client.post("/api/auth/login", json={"username": "alice", "password": "wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user(client):
    resp = await client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
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
    assert resp.status_code == 204
    # Cookie should be cleared — subsequent /me should fail
    resp2 = await admin_client.get("/api/auth/me")
    assert resp2.status_code == 401
