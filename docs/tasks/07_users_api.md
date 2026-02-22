# Task 07 — Users CRUD API

## Status: COMPLETE ✅

**Completed:** 2026-02-22
**Files created:** `api/users/__init__.py`, `api/users/models.py`, `api/users/router.py`



**Depends on:** Task 06  
**Complexity:** Low  
**Run as:** netscan user

---

## Objective
Implement the `/api/users` endpoints for listing, creating, updating, and deleting users. All endpoints require admin role.

---

## Files to Create

### `/home/matheau/code/port_scan/api/users/models.py`
```python
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str = "viewer"


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    force_password_change: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True
```

---

### `/home/matheau/code/port_scan/api/users/router.py`
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from shared.db import get_db
from shared.models import User
from auth.dependencies import require_admin, get_current_user
from auth.utils import hash_password
from users.models import UserCreate, UserUpdate, UserOut

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    result = await db.execute(select(User).order_by(User.username))
    return result.scalars().all()


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin)
):
    if body.role not in ("admin", "operator", "viewer"):
        raise HTTPException(status_code=422, detail="Invalid role")

    existing = await db.execute(select(User).where(
        (User.username == body.username) | (User.email == body.email)
    ))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username or email already exists")

    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
        force_password_change=True
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    updates = {}
    if body.email is not None:
        updates["email"] = body.email
    if body.role is not None:
        if body.role not in ("admin", "operator", "viewer"):
            raise HTTPException(status_code=422, detail="Invalid role")
        updates["role"] = body.role
    if body.is_active is not None:
        updates["is_active"] = body.is_active
    if body.password is not None:
        updates["password_hash"] = hash_password(body.password)
        updates["force_password_change"] = True

    if updates:
        await db.execute(update(User).where(User.id == user_id).values(**updates))
        await db.commit()
        await db.refresh(user)

    return user


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
```

---

## Register Router in `main.py`
Add to `/home/matheau/code/port_scan/api/main.py`:
```python
from users.router import router as users_router
app.include_router(users_router, prefix="/api")
```

---

## Acceptance Criteria
- [ ] `GET /api/users` returns list of all users (admin only)
- [ ] `POST /api/users` creates user with hashed password and `force_password_change=True`
- [ ] `POST /api/users` returns `409` if username or email already exists
- [ ] `PATCH /api/users/{id}` updates allowed fields only
- [ ] `DELETE /api/users/{id}` returns `400` when trying to delete own account
- [ ] All endpoints return `403` for non-admin roles
