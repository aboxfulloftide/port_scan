from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from shared.db import get_db
from shared.models import Subnet, User
from api.auth.dependencies import get_current_user, require_operator, require_admin
from api.subnets.models import SubnetCreate, SubnetUpdate, SubnetOut

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
