from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from slowapi import Limiter
from slowapi.util import get_remote_address

from shared.db import get_db
from shared.models import User, RefreshToken
from api.auth.utils import (
    verify_password, create_access_token, create_refresh_token,
    decode_access_token, hash_token, hash_password
)
from api.auth.models import LoginRequest, UserOut, ChangePasswordRequest

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
