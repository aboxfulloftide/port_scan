from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from shared.db import get_db
from shared.models import WirelessAP, User
from shared.crypto import encrypt
from api.auth.dependencies import get_current_user, require_operator
from api.wireless_aps.models import WirelessAPCreate, WirelessAPUpdate, WirelessAPOut

router = APIRouter(prefix="/wireless-aps", tags=["wireless-aps"])


def _ap_to_out(ap: WirelessAP) -> WirelessAPOut:
    return WirelessAPOut(
        id=ap.id,
        name=ap.name,
        brand=ap.brand,
        url=ap.url,
        username=ap.username,
        enabled=ap.enabled,
        notes=ap.notes,
        last_scraped=ap.last_scraped,
        scrape_interval_min=ap.scrape_interval_min,
        created_at=ap.created_at,
        updated_at=ap.updated_at,
        password_set=ap.password_enc is not None,
    )


@router.get("", response_model=list[WirelessAPOut])
async def list_wireless_aps(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(WirelessAP).order_by(WirelessAP.name))
    aps = result.scalars().all()
    return [_ap_to_out(ap) for ap in aps]


@router.post("", response_model=WirelessAPOut, status_code=201)
async def create_wireless_ap(
    body: WirelessAPCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    valid_brands = {"tplink_deco", "netgear"}
    if body.brand not in valid_brands:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid brand. Must be one of: {', '.join(sorted(valid_brands))}",
        )

    try:
        password_enc = encrypt(body.password)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    ap = WirelessAP(
        name=body.name,
        brand=body.brand,
        url=body.url,
        username=body.username,
        password_enc=password_enc,
        enabled=body.enabled,
        notes=body.notes,
        scrape_interval_min=body.scrape_interval_min,
    )
    db.add(ap)
    await db.commit()
    await db.refresh(ap)
    return _ap_to_out(ap)


@router.patch("/{ap_id}", response_model=WirelessAPOut)
async def update_wireless_ap(
    ap_id: int,
    body: WirelessAPUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    result = await db.execute(select(WirelessAP).where(WirelessAP.id == ap_id))
    ap = result.scalar_one_or_none()
    if not ap:
        raise HTTPException(status_code=404, detail="Wireless AP not found")

    updates = body.model_dump(exclude_none=True)

    # Extract plaintext password before applying updates
    new_password = updates.pop("password", None)
    if new_password is not None:
        try:
            updates["password_enc"] = encrypt(new_password)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    if updates.get("brand") and updates["brand"] not in {"tplink_deco", "netgear"}:
        raise HTTPException(
            status_code=422,
            detail="Invalid brand. Must be one of: tplink_deco, netgear",
        )

    for field, value in updates.items():
        setattr(ap, field, value)

    await db.commit()
    await db.refresh(ap)
    return _ap_to_out(ap)


@router.delete("/{ap_id}", status_code=204)
async def delete_wireless_ap(
    ap_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    result = await db.execute(select(WirelessAP).where(WirelessAP.id == ap_id))
    ap = result.scalar_one_or_none()
    if not ap:
        raise HTTPException(status_code=404, detail="Wireless AP not found")

    await db.execute(delete(WirelessAP).where(WirelessAP.id == ap_id))
    await db.commit()


@router.post("/{ap_id}/scrape", response_model=dict)
async def trigger_ap_scrape(
    ap_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operator),
):
    """Manually trigger a wireless scrape for a single AP. Returns client count."""
    result = await db.execute(select(WirelessAP).where(WirelessAP.id == ap_id))
    ap = result.scalar_one_or_none()
    if not ap:
        raise HTTPException(status_code=404, detail="Wireless AP not found")
    if not ap.enabled:
        raise HTTPException(status_code=400, detail="Wireless AP is disabled")

    from shared.crypto import decrypt
    from worker.wireless_scraper import scrape_deco, scrape_netgear, persist_wireless_data

    # Decrypt password for the scraper
    plaintext_password = None
    if ap.password_enc:
        try:
            plaintext_password = decrypt(ap.password_enc)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to decrypt AP password: {exc}")

    # Build proxy with plaintext password
    class _APProxy:
        pass

    proxy = _APProxy()
    for attr in ("id", "name", "brand", "url", "username", "enabled",
                 "notes", "scrape_interval_min"):
        setattr(proxy, attr, getattr(ap, attr))
    proxy.password_enc = plaintext_password  # type: ignore[attr-defined]

    try:
        if ap.brand == "tplink_deco":
            entries = await scrape_deco(proxy)  # type: ignore[arg-type]
        elif ap.brand == "netgear":
            entries = await scrape_netgear(proxy)  # type: ignore[arg-type]
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported brand: {ap.brand}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Scrape failed: {exc}")

    for entry in entries:
        entry["ap_id"] = ap_id

    await persist_wireless_data(entries)

    return {"ap_id": ap_id, "client_count": len(entries)}
