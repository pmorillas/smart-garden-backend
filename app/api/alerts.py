from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models import Alert

router = APIRouter(
    prefix="/api/alerts",
    tags=["alerts"],
    dependencies=[Depends(get_current_user)],
)


def _to_dict(a: Alert) -> dict:
    return {
        "id": a.id,
        "type": a.type,
        "zone_id": a.zone_id,
        "device_id": a.device_id,
        "message": a.message,
        "resolved": a.resolved,
        "created_at": a.created_at.isoformat(),
        "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
    }


@router.get("/")
async def list_alerts(resolved: bool | None = None, db: AsyncSession = Depends(get_db)):
    q = select(Alert).order_by(Alert.created_at.desc())
    if resolved is not None:
        q = q.where(Alert.resolved == resolved)
    result = await db.execute(q)
    return [_to_dict(a) for a in result.scalars().all()]


@router.post("/{alert_id}/resolve")
async def resolve_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    alert = await db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alerta no trobada")
    if alert.resolved:
        raise HTTPException(status_code=409, detail="Alerta ja resolta")
    alert.resolved = True
    alert.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True}


@router.delete("/{alert_id}", status_code=204)
async def delete_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    alert = await db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alerta no trobada")
    await db.delete(alert)
    await db.commit()
