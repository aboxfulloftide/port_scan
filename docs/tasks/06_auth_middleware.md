# Task 06 — Auth Middleware & Role Guards

## Status: COMPLETE ✅

**Completed:** 2026-02-22
**Files created:** `api/auth/dependencies.py`, `api/main.py`, `api/config.py`
**Deviations from plan:**
- `main.py` uses `asynccontextmanager` lifespan (not separate `startup`/`shutdown` functions)
- Worker loop started as asyncio task in lifespan startup
- `subnets` router was initially missing from main.py (fixed after first 404)



**Depends on:** Task 05  
**Complexity:** Medium  
**Run as:** netscan user

---

## Objective
Build FastAPI dependency functions that protect all routes. Implement `get_current_user`, `require_operator`, and `require_admin` guards. Also build the main FastAPI `app` entry point that wires all routers together.

---

## Files to Create

### `/home/matheau/code/port_scan/api/auth/dependencies.py`
```python
from fastapi import Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from shared.db import get_db
from shared.models import User
from auth.utils import decode_access_token

ACCESS_COOKIE = "access_token"


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    result = await db.execute(select(User).where(User.id == int(payload["sub"])))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    return user


async def require_operator(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="Operator or Admin role required")
    return current_user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user
```

---

### `/home/matheau/code/port_scan/api/main.py`
```python
import os
import sys
sys.path.insert(0, "/home/matheau/code/port_scan")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from dotenv import load_dotenv

load_dotenv("/home/matheau/code/port_scan/.env")

from auth.router import router as auth_router
from hosts.router import router as hosts_router
from scans.router import router as scans_router
from profiles.router import router as profiles_router
from schedules.router import router as schedules_router
from wol.router import router as wol_router

app = FastAPI(
    title="NetScan API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# Rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — restrict to LAN in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten to specific LAN origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount screenshots as static files (auth enforced at API level)
SCREENSHOT_DIR = os.getenv("SCREENSHOT_DIR", "/home/matheau/code/port_scan/screenshots")
app.mount("/screenshots", StaticFiles(directory=SCREENSHOT_DIR), name="screenshots")

# Register routers
app.include_router(auth_router, prefix="/api")
app.include_router(hosts_router, prefix="/api")
app.include_router(scans_router, prefix="/api")
app.include_router(profiles_router, prefix="/api")
app.include_router(schedules_router, prefix="/api")
app.include_router(wol_router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "netscan-api"}
```

---

### `/home/matheau/code/port_scan/api/config.py`
```python
import os
from dotenv import load_dotenv

load_dotenv("/home/matheau/code/port_scan/.env")

class Settings:
    DB_HOST: str = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT: int = int(os.getenv("DB_PORT", 3306))
    DB_NAME: str = os.getenv("DB_NAME", "netscan")
    DB_USER: str = os.getenv("DB_USER", "netscan_user")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    SCREENSHOT_DIR: str = os.getenv("SCREENSHOT_DIR", "/home/matheau/code/port_scan/screenshots")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    NMAP_PATH: str = os.getenv("NMAP_PATH", "/usr/bin/nmap")
    MAX_SCAN_CONCURRENCY: int = int(os.getenv("MAX_SCAN_CONCURRENCY", 50))

settings = Settings()
```

---

### Create `__init__.py` stubs for all API subpackages
```bash
touch /home/matheau/code/port_scan/api/__init__.py
touch /home/matheau/code/port_scan/api/auth/__init__.py
touch /home/matheau/code/port_scan/api/hosts/__init__.py
touch /home/matheau/code/port_scan/api/scans/__init__.py
touch /home/matheau/code/port_scan/api/profiles/__init__.py
touch /home/matheau/code/port_scan/api/schedules/__init__.py
touch /home/matheau/code/port_scan/api/wol/__init__.py
```

---

## Acceptance Criteria
- [ ] `GET /api/health` returns `{"status": "ok"}` without auth
- [ ] Any protected route without a cookie returns `401`
- [ ] A viewer-role user hitting an operator-only route returns `403`
- [ ] A viewer-role user hitting an admin-only route returns `403`
- [ ] An operator-role user hitting an admin-only route returns `403`
- [ ] An admin-role user can access all route tiers
- [ ] FastAPI app starts with `uvicorn main:app` without import errors
- [ ] `/api/docs` Swagger UI loads and shows all routers
