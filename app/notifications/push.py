import json
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Alert, PushSubscription

logger = logging.getLogger(__name__)


async def create_alert(
    alert_type: str,
    message: str,
    zone_id: int | None = None,
    device_id: int | None = None,
) -> Alert:
    async with AsyncSessionLocal() as db:
        alert = Alert(
            type=alert_type,
            message=message,
            zone_id=zone_id,
            device_id=device_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(alert)
        await db.commit()
        await db.refresh(alert)

    await _send_push_to_all(
        title=_title_for_type(alert_type),
        body=message,
        tag=f"{alert_type}-{zone_id or device_id or 'global'}",
    )
    return alert


async def has_active_alert(alert_type: str, zone_id: int | None = None, device_id: int | None = None) -> bool:
    async with AsyncSessionLocal() as db:
        q = select(Alert).where(Alert.type == alert_type, Alert.resolved == False)  # noqa: E712
        if zone_id is not None:
            q = q.where(Alert.zone_id == zone_id)
        if device_id is not None:
            q = q.where(Alert.device_id == device_id)
        result = await db.execute(q)
        return result.scalar_one_or_none() is not None


async def auto_resolve_alert(
    alert_type: str,
    zone_id: int | None = None,
    device_id: int | None = None,
    tank_id: int | None = None,
) -> None:
    async with AsyncSessionLocal() as db:
        q = select(Alert).where(Alert.type == alert_type, Alert.resolved == False)  # noqa: E712
        if zone_id is not None:
            q = q.where(Alert.zone_id == zone_id)
        if device_id is not None:
            q = q.where(Alert.device_id == device_id)
        result = await db.execute(q)
        for alert in result.scalars().all():
            alert.resolved = True
            alert.resolved_at = datetime.now(timezone.utc)
        await db.commit()


async def _send_push_to_all(title: str, body: str, tag: str = "") -> None:
    if not settings.vapid_private_key or not settings.vapid_public_key:
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(PushSubscription))
        subscriptions = result.scalars().all()

    if not subscriptions:
        return

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.warning("pywebpush no disponible, saltant push")
        return

    data = json.dumps({"title": title, "body": body, "tag": tag})
    dead_endpoints = []

    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=data,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_email},
            )
        except WebPushException as e:
            if e.response and e.response.status_code in (404, 410):
                dead_endpoints.append(sub.id)
            else:
                logger.warning("Push error per %s: %s", sub.endpoint[:40], e)
        except Exception:
            logger.exception("Error enviant push a %s", sub.endpoint[:40])

    if dead_endpoints:
        async with AsyncSessionLocal() as db:
            for sub_id in dead_endpoints:
                sub = await db.get(PushSubscription, sub_id)
                if sub:
                    await db.delete(sub)
            await db.commit()


async def get_alert_rule(alert_type: str, zone_id: int | None = None, tank_id: int | None = None):
    """Finds the best enabled AlertRule.

    For zone alerts: zone-specific first, then global (zone_id=NULL).
    For tank alerts: tank-specific first, then global (tank_id=NULL).
    """
    from app.models.alert_rule import AlertRule
    async with AsyncSessionLocal() as db:
        if tank_id is not None:
            result = await db.execute(
                select(AlertRule).where(
                    AlertRule.alert_type == alert_type,
                    AlertRule.tank_id == tank_id,
                    AlertRule.enabled == True,  # noqa: E712
                )
            )
            rule = result.scalar_one_or_none()
            if rule is not None:
                return rule
            result = await db.execute(
                select(AlertRule).where(
                    AlertRule.alert_type == alert_type,
                    AlertRule.tank_id == None,  # noqa: E711
                    AlertRule.enabled == True,  # noqa: E712
                )
            )
            return result.scalar_one_or_none()

        if zone_id is not None:
            result = await db.execute(
                select(AlertRule).where(
                    AlertRule.alert_type == alert_type,
                    AlertRule.zone_id == zone_id,
                    AlertRule.enabled == True,  # noqa: E712
                )
            )
            rule = result.scalar_one_or_none()
            if rule is not None:
                return rule
        result = await db.execute(
            select(AlertRule).where(
                AlertRule.alert_type == alert_type,
                AlertRule.zone_id == None,  # noqa: E711
                AlertRule.enabled == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()


async def maybe_create_alert(
    alert_type: str,
    message: str,
    zone_id: int | None = None,
    device_id: int | None = None,
    tank_id: int | None = None,
) -> "Alert | None":
    """Create alert only if an enabled rule exists and cooldown has elapsed."""
    rule = await get_alert_rule(alert_type, zone_id=zone_id, tank_id=tank_id)
    if rule is None:
        return None

    if rule.cooldown_minutes > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=rule.cooldown_minutes)
        async with AsyncSessionLocal() as db:
            q = select(Alert).where(Alert.type == alert_type, Alert.created_at >= cutoff)
            if zone_id is not None:
                q = q.where(Alert.zone_id == zone_id)
            if device_id is not None:
                q = q.where(Alert.device_id == device_id)
            result = await db.execute(q)
            if result.scalar_one_or_none() is not None:
                return None

    return await create_alert(alert_type, message, zone_id=zone_id, device_id=device_id)


def _title_for_type(alert_type: str) -> str:
    return {
        "humidity_low":    "Smart Garden — Humitat baixa",
        "device_offline":  "Smart Garden — Dispositiu desconnectat",
        "water_failed":    "Smart Garden — Error de reg",
        "water_completed": "Smart Garden — Reg completat",
        "sensor_error":    "Smart Garden — Error de sensor",
        "tank_level_low":  "Smart Garden — Nivell de dipòsit baix",
    }.get(alert_type, "Smart Garden")
