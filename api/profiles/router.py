from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from shared.db import get_db
from shared.models import ScanProfile, Schedule, User
from api.auth.dependencies import get_current_user, require_operator, require_admin
from api.profiles.models import ProfileCreate, ProfileUpdate, ProfileOut, DEFAULT_PROFILE_NAMES

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

    sched_result = await db.execute(
        select(Schedule).where(Schedule.profile_id == profile_id, Schedule.is_active == True)
    )
    if sched_result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Profile is in use by an active schedule")

    await db.execute(delete(ScanProfile).where(ScanProfile.id == profile_id))
    await db.commit()
