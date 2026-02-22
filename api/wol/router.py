from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import wakeonlan

from shared.db import get_db
from shared.models import Host, WolLog, User
from api.auth.dependencies import get_current_user, require_operator

router = APIRouter(prefix="/wol", tags=["wol"])


class WolSendRequest(BaseModel):
    host_id: int


class WolLogOut(BaseModel):
    id: int
    host_id: int
    mac_used: str
    triggered_by: Optional[int]
    success: bool
    error_message: Optional[str]
    sent_at: str

    class Config:
        from_attributes = True


@router.post("/send")
async def send_wol(
    body: WolSendRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator)
):
    host = await db.get(Host, body.host_id)
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")
    if not host.current_mac:
        raise HTTPException(status_code=400, detail="Host has no MAC address")

    try:
        wakeonlan.send_magic_packet(host.current_mac, ip_address="255.255.255.255", port=9)
        log = WolLog(
            host_id=host.id,
            mac_used=host.current_mac,
            triggered_by=current_user.id,
            success=True
        )
    except Exception as e:
        log = WolLog(
            host_id=host.id,
            mac_used=host.current_mac or "unknown",
            triggered_by=current_user.id,
            success=False,
            error_message=str(e)
        )

    db.add(log)
    await db.commit()
    return {"status": "sent", "mac": host.current_mac}


@router.get("/log", response_model=list[WolLogOut])
async def get_wol_log(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    host_id: Optional[int] = Query(None)
):
    q = select(WolLog).order_by(WolLog.sent_at.desc())
    if host_id is not None:
        q = q.where(WolLog.host_id == host_id)
    q = q.limit(100)
    result = await db.execute(q)
    return result.scalars().all()
