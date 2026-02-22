# Task 08 — Subnets CRUD API

## Status: COMPLETE ✅

**Completed:** 2026-02-22
**Files created:** `api/subnets/__init__.py`, `api/subnets/models.py`, `api/subnets/router.py`



**Depends on:** Task 06  
**Complexity:** Low  
**Run as:** netscan user

---

## Objective
Implement `/api/subnets` endpoints for managing the list of target subnets to scan. Includes CIDR validation.

---

## Files to Create

### `/home/matheau/code/port_scan/api/subnets/models.py`
```python
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
import ipaddress


class SubnetCreate(BaseModel):
    label: str
    cidr: str
    description: Optional[str] = None

    @field_validator("cidr")
    @classmethod
    def validate_cidr(cls, v):
        try:
            network = ipaddress.IPv4Network(v, strict=False)
            return str(network)  # Normalize to canonical form
        except ValueError:
            raise ValueError(f"Invalid IPv4 CIDR: {v}")


class SubnetUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class SubnetOut(BaseModel):
    id: int
    label: str
    cidr: str
    description: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
```

---

### `/home/matheau/code/port_scan/api/subnets/router.py`
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from shared.db import get_db
from shared.models import Subnet, User
from auth.dependencies import get_current_user, require_operator, require_admin
from subnets.models import SubnetCreate, SubnetUpdate, SubnetOut

router = APIRouter(prefix="/subnets", tags=["subnets"])


@router.get("", response_model=list[SubnetOut])
async def list_subnets(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    result = await db.execute(select(Subnet).order_by(Subnet.label))
    return result.scalars().all()


@router.post("", response_model=SubnetOut, status_code=201)
async def create_subnet(
    body: SubnetCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator)
):
    existing = await db.execute(select(Subnet).where(Subnet.cidr == body.cidr))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Subnet CIDR already exists")

    subnet = Subnet(label=body.label, cidr=body.cidr, description=body.description)
    db.add(subnet)
    await db.commit()
    await db.refresh(subnet)
    return subnet


@router.patch("/{subnet_id}", response_model=SubnetOut)
async def update_subnet(
    subnet_id: int,
    body: SubnetUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator)
):
    result = await db.execute(select(Subnet).where(Subnet.id == subnet_id))
    subnet = result.scalar_one_or_none()
    if not subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")

    updates = body.model_dump(exclude_none=True)
    if updates:
        await db.execute(update(Subnet).where(Subnet.id == subnet_id).values(**updates))
        await db.commit()
        await db.refresh(subnet)
    return subnet


@router.delete("/{subnet_id}", status_code=204)
async def delete_subnet(
    subnet_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    result = await db.execute(select(Subnet).where(Subnet.id == subnet_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Subnet not found")

    await db.execute(delete(Subnet).where(Subnet.id == subnet_id))
    await db.commit()
```

---

## Register Router in `main.py`
```python
from subnets.router import router as subnets_router
app.include_router(subnets_router, prefix="/api")
```

---

## Acceptance Criteria
- [ ] `GET /api/subnets` accessible to all authenticated users
- [ ] `POST /api/subnets` validates CIDR format and normalizes it
- [ ] `POST /api/subnets` returns `409` on duplicate CIDR
- [ ] `PATCH /api/subnets/{id}` updates only provided fields
- [ ] `DELETE /api/subnets/{id}` requires admin role
- [ ] Invalid CIDR (e.g. `999.999.0.0/24`) returns `422`
