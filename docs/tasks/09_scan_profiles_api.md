# Task 09 — Scan Profiles CRUD API

## Status: COMPLETE ✅

**Completed:** 2026-02-22
**Files created:** `api/profiles/__init__.py`, `api/profiles/models.py`, `api/profiles/router.py`



**Depends on:** Task 06  
**Complexity:** Low  
**Run as:** netscan user

---

## Objective
Implement `/api/profiles` endpoints for managing scan profiles. Includes port range validation and protection of default profiles.

---

## Files to Create

### `/home/matheau/code/port_scan/api/profiles/models.py`
```python
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
import re

PORT_RANGE_PATTERN = re.compile(r'^(\d+(-\d+)?)(,\d+(-\d+)?)*$')

DEFAULT_PROFILE_NAMES = {"Quick Ping", "Standard", "Full Deep Scan"}


class ProfileCreate(BaseModel):
    name: str
    description: Optional[str] = None
    port_range: str = "1-65535"
    enable_icmp: bool = True
    enable_tcp_syn: bool = True
    enable_udp: bool = False
    enable_fingerprint: bool = True
    enable_banner: bool = True
    enable_screenshot: bool = True
    max_concurrency: int = 50
    rate_limit: Optional[int] = None
    timeout_sec: int = 30

    @field_validator("port_range")
    @classmethod
    def validate_port_range(cls, v):
        if not PORT_RANGE_PATTERN.match(v):
            raise ValueError("Invalid port range format. Use e.g. '1-1024,8080,8443'")
        # Validate all port numbers are in range
        for part in v.split(","):
            if "-" in part:
                start, end = part.split("-")
                if not (1 <= int(start) <= 65535 and 1 <= int(end) <= 65535 and int(start) <= int(end)):
                    raise ValueError(f"Port range {part} is invalid")
            else:
                if not (1 <= int(part) <= 65535):
                    raise ValueError(f"Port {part} is out of range")
        return v

    @field_validator("max_concurrency")
    @classmethod
    def validate_concurrency(cls, v):
        if not (1 <= v <= 200):
            raise ValueError("max_concurrency must be between 1 and 200")
        return v


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    port_range: Optional[str] = None
    enable_icmp: Optional[bool] = None
    enable_tcp_syn: Optional[bool] = None
    enable_udp: Optional[bool] = None
    enable_fingerprint: Optional[bool] = None
    enable_banner: Optional[bool] = None
    enable_screenshot: Optional[bool] = None
    max_concurrency: Optional[int] = None
    rate_limit: Optional[int] = None
    timeout_sec: Optional[int] = None


class ProfileOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    port_range: str
    enable_icmp: bool
    enable_tcp_syn: bool
    enable_udp: bool
    enable_fingerprint: bool
    enable_banner: bool
    enable_screenshot: bool
    max_concurrency: int
    rate_limit: Optional[int] = None
    timeout_sec: int
    created_at: datetime

    class Config:
        from_attributes = True
```

---

### `/home/matheau/code/port_scan/api/profiles/router.py`
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from shared.db import get_db
from shared.models import ScanProfile, Schedule, User
from auth.dependencies import get_current_user, require_operator, require_admin
from profiles.models import ProfileCreate, ProfileUpdate, ProfileOut, DEFAULT_PROFILE_NAMES

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=list[ProfileOut])
async def list_profiles(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    result = await db.execute(select(ScanProfile).order_by(ScanProfile.name))
    return result.scalars().all()


@router.post("", response_model=ProfileOut, status_code=201)
async def create_profile(
    body: ProfileCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator)
):
    existing = await db.execute(select(ScanProfile).where(ScanProfile.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Profile name already exists")

    profile = ScanProfile(**body.model_dump(), created_by=current_user.id)
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.patch("/{profile_id}", response_model=ProfileOut)
async def update_profile(
    profile_id: int,
    body: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator)
):
    result = await db.execute(select(ScanProfile).where(ScanProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    updates = body.model_dump(exclude_none=True)
    if updates:
        await db.execute(update(ScanProfile).where(ScanProfile.id == profile_id).values(**updates))
        await db.commit()
        await db.refresh(profile)
    return profile


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    result = await db.execute(select(ScanProfile).where(ScanProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    if profile.name in DEFAULT_PROFILE_NAMES:
        raise HTTPException(status_code=400, detail="Cannot delete a default system profile")

    # Check if referenced by active schedules
    sched_result = await db.execute(
        select(Schedule).where(Schedule.profile_id == profile_id, Schedule.is_active == True)
    )
    if sched_result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Profile is in use by an active schedule")

    await db.execute(delete(ScanProfile).where(ScanProfile.id == profile_id))
    await db.commit()
```

---

## Register Router in `main.py`
```python
from profiles.router import router as profiles_router
app.include_router(profiles_router, prefix="/api")
```

---

## Acceptance Criteria
- [ ] `GET /api/profiles` returns all profiles to any authenticated user
- [ ] `POST /api/profiles` validates port range format
- [ ] `POST /api/profiles` returns `409` on duplicate name
- [ ] `DELETE /api/profiles/{id}` returns `400` for default system profiles
- [ ] `DELETE /api/profiles/{id}` returns `409` if referenced by active schedule
- [ ] Port range `999999` returns `422`
- [ ] Port range `80,443,8080-8090` is accepted
