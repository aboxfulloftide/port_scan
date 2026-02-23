import os
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from shared.models import Base
from shared.db import get_db
from api.main import app

# Derive test DB URL from DATABASE_URL env — same creds, separate DB
_raw = os.getenv("DATABASE_URL", "mysql+pymysql://matheau:password@localhost:3306/port_scan")
TEST_DB_URL = _raw.replace("pymysql", "aiomysql").rsplit("/", 1)[0] + "/port_scan_test"


@pytest_asyncio.fixture
async def test_engine():
    """Fresh schema per test — avoids all event loop scoping issues."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine):
    TestSession = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with TestSession() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    # Reset rate limiter storage so each test starts with a clean slate
    from api.auth.router import limiter as auth_limiter
    auth_limiter._storage.reset()

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_client(client, db_session):
    """Client pre-authenticated as admin."""
    from api.auth.utils import hash_password
    from shared.models import User

    user = User(
        username="testadmin",
        email="testadmin@test.local",
        password_hash=hash_password("testpass"),
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    resp = await client.post("/api/auth/login", json={"username": "testadmin", "password": "testpass"})
    assert resp.status_code == 200
    return client
