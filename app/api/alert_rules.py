from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.alert_rule import AlertRule, ALERT_TYPES

router = APIRouter(
    prefix="/api/alert-rules",
    tags=["alert-rules"],
    dependencies=[Depends(get_current_user)],
)


class AlertRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    alert_type: str
    enabled: bool = True
    zone_id: int | None = None
    threshold: float | None = None
    cooldown_minutes: int = Field(default=60, ge=0, le=10080)
    notification_channels: list[str] = ["push"]


class AlertRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None
    threshold: float | None = None
    cooldown_minutes: int | None = Field(default=None, ge=0, le=10080)
    notification_channels: list[str] | None = None


def _to_dict(r: AlertRule) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "alert_type": r.alert_type,
        "enabled": r.enabled,
        "zone_id": r.zone_id,
        "threshold": r.threshold,
        "cooldown_minutes": r.cooldown_minutes,
        "notification_channels": r.notification_channels,
    }


@router.get("/")
async def list_alert_rules(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AlertRule).order_by(AlertRule.id))
    return [_to_dict(r) for r in result.scalars().all()]


@router.post("/", status_code=201)
async def create_alert_rule(body: AlertRuleCreate, db: AsyncSession = Depends(get_db)):
    if body.alert_type not in ALERT_TYPES:
        raise HTTPException(status_code=422, detail=f"Tipus d'alerta invàlid: {body.alert_type}")
    rule = AlertRule(**body.model_dump())
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return _to_dict(rule)


@router.put("/{rule_id}")
async def update_alert_rule(rule_id: int, body: AlertRuleUpdate, db: AsyncSession = Depends(get_db)):
    rule = await db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Regla no trobada")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(rule, field, value)
    await db.commit()
    return {"ok": True}


@router.delete("/{rule_id}", status_code=204)
async def delete_alert_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    rule = await db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Regla no trobada")
    await db.delete(rule)
    await db.commit()
