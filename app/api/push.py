from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_current_user
from app.database import get_db
from app.models import PushSubscription, User

router = APIRouter(
    prefix="/api/push",
    tags=["push"],
    dependencies=[Depends(get_current_user)],
)


class SubscribeBody(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


@router.get("/vapid-public-key")
async def get_vapid_key():
    return {"public_key": settings.vapid_public_key}


@router.post("/subscribe", status_code=201)
async def subscribe(
    body: SubscribeBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return {"id": existing.id, "ok": True}

    user_agent = request.headers.get("user-agent", "")[:256]
    sub = PushSubscription(
        user_id=current_user.id,
        endpoint=body.endpoint,
        p256dh=body.p256dh,
        auth=body.auth,
        user_agent=user_agent,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return {"id": sub.id, "ok": True}


@router.delete("/subscribe/{sub_id}", status_code=204)
async def unsubscribe(
    sub_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sub = await db.get(PushSubscription, sub_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Subscripció no trobada")
    if sub.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No autoritzat")
    await db.delete(sub)
    await db.commit()
