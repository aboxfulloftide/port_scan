# Task 05 — Auth Module: Login, JWT, Refresh, Logout

## Status: COMPLETE ✅

**Completed:** 2026-02-22
**Files created:** `api/auth/__init__.py`, `api/auth/utils.py`, `api/auth/models.py`, `api/auth/router.py`, `api/auth/dependencies.py`
**Deviations/fixes:**
- `UserOut.last_login` typed as `Optional[datetime]` (plan had `Optional[str]` — caused 500 on login, fixed)
- Auth verified working: login returns cookies, refresh rotates token, logout clears cookies



**Depends on:** Task 04  
**Complexity:** Medium  
**Run as:** netscan user

---

## Objective
Implement the full authentication backend: password verification, JWT access token generation, refresh token rotation, logout with revocation, and the `/api/auth/*` endpoints.

---

## Files to Create

### `/home/matheau/code/port_scan/api/auth/utils.py`
```python
import os
import hashlib
import secrets
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv("/home/matheau/code/port_scan/.env")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_EXPIRE_MINUTES", 480))
REFRESH_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", 7))


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def create_access_token(user_id: int, username: str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": expire,
        "type": "access"
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token() -> tuple[str, str, datetime]:
    """Returns (raw_token, hashed_token, expires_at)"""
    raw = secrets.token_urlsafe(64)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    expires_at = datetime.utcnow() + timedelta(days=REFRESH_EXPIRE_DAYS)
    return raw, hashed, expires_at


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise JWTError("Not an access token")
        return payload
    except JWTError:
        return {}


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
```

---

### `/home/matheau/code/port_scan/api/auth/models.py`
```python
from pydantic import BaseModel, EmailStr
from typing import Optional


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    role: str
    last_login: Optional[str] = None
    force_password_change: bool = False

    class Config:
        from_attributes = True


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
```

---

### `/home/matheau/code/port_scan/api/auth/router.py`
```python
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from slowapi import Limiter
from slowapi.util import get_remote_address

from shared.db import get_db
from shared.models import User, RefreshToken
from auth.utils import (
    verify_password, create_access_token, create_refresh_token,
    decode_access_token, hash_token
)
from auth.models import LoginRequest, UserOut, ChangePasswordRequest
from auth.utils import hash_password

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
COOKIE_SECURE = False   # Set True when using HTTPS


def set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    response.set_cookie(ACCESS_COOKIE, access_token, httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=28800)
    response.set_cookie(REFRESH_COOKIE, refresh_token, httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=604800)


@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    access_token = create_access_token(user.id, user.username, user.role)
    raw_refresh, hashed_refresh, expires_at = create_refresh_token()

    db.add(RefreshToken(user_id=user.id, token_hash=hashed_refresh, expires_at=expires_at))
    await db.execute(update(User).where(User.id == user.id).values(last_login=datetime.utcnow()))
    await db.commit()

    set_auth_cookies(response, access_token, raw_refresh)
    return {"user": UserOut.model_validate(user)}


@router.post("/refresh")
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if not raw_token:
        raise HTTPException(status_code=401, detail="No refresh token")

    token_hash = hash_token(raw_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == False
        )
    )
    db_token = result.scalar_one_or_none()

    if not db_token or db_token.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user_result = await db.execute(select(User).where(User.id == db_token.user_id))
    user = user_result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    # Rotate refresh token
    db_token.revoked = True
    raw_new, hashed_new, expires_at = create_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=hashed_new, expires_at=expires_at))
    await db.commit()

    access_token = create_access_token(user.id, user.username, user.role)
    set_auth_cookies(response, access_token, raw_new)
    return {"message": "Token refreshed"}


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if raw_token:
        token_hash = hash_token(raw_token)
        await db.execute(
            update(RefreshToken).where(RefreshToken.token_hash == token_hash).values(revoked=True)
        )
        await db.commit()
    response.delete_cookie(ACCESS_COOKIE)
    response.delete_cookie(REFRESH_COOKIE)


@router.get("/me", response_model=UserOut)
async def me(request: Request, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    result = await db.execute(select(User).where(User.id == int(payload["sub"])))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut.model_validate(user)


@router.post("/change-password", status_code=200)
async def change_password(request: Request, body: ChangePasswordRequest, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == int(payload["sub"])))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password incorrect")

    await db.execute(
        update(User).where(User.id == user.id).values(
            password_hash=hash_password(body.new_password),
            force_password_change=False
        )
    )
    await db.commit()
    return {"message": "Password updated"}
```

---

## Acceptance Criteria
- [ ] `POST /api/auth/login` returns 200 and sets both cookies on valid credentials
- [ ] `POST /api/auth/login` returns 401 on bad credentials
- [ ] `POST /api/auth/login` is rate-limited to 10/min per IP
- [ ] `POST /api/auth/refresh` rotates refresh token and issues new access token
- [ ] `POST /api/auth/logout` revokes refresh token and clears cookies
- [ ] `GET /api/auth/me` returns current user from cookie
- [ ] `POST /api/auth/change-password` updates hash and clears `force_password_change`
