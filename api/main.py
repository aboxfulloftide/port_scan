import os
import sys
import asyncio
import logging
from contextlib import asynccontextmanager

# Add project root to path so shared/ and api/ are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from api.auth.router import router as auth_router
from api.hosts.router import router as hosts_router
from api.scans.router import router as scans_router
from api.profiles.router import router as profiles_router
from api.schedules.router import router as schedules_router
from api.users.router import router as users_router
from api.wol.router import router as wol_router
from api.subnets.router import router as subnets_router
from api.dashboard.router import router as dashboard_router

logger = logging.getLogger("api")

_worker_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _worker_task
    from worker.main import worker_loop
    _worker_task = asyncio.create_task(worker_loop(), name="scan-worker")
    logger.info("Scan worker started")
    yield
    # Shutdown: send stop signal and wait
    from worker.queue import job_queue
    await job_queue.put(None)
    if _worker_task and not _worker_task.done():
        try:
            await asyncio.wait_for(_worker_task, timeout=10.0)
        except asyncio.TimeoutError:
            _worker_task.cancel()
    logger.info("Scan worker stopped")


app = FastAPI(
    title="NetScan API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount screenshots as static files
SCREENSHOT_DIR = os.getenv(
    "SCREENSHOT_DIR",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "screenshots")
)
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
app.mount("/screenshots", StaticFiles(directory=SCREENSHOT_DIR), name="screenshots")

# Register routers
app.include_router(auth_router, prefix="/api")
app.include_router(hosts_router, prefix="/api")
app.include_router(scans_router, prefix="/api")
app.include_router(profiles_router, prefix="/api")
app.include_router(schedules_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(wol_router, prefix="/api")
app.include_router(subnets_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "netscan-api"}
