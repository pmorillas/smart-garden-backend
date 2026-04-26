import asyncio
import logging
from datetime import datetime, timezone

from app.database import AsyncSessionLocal
from app.models import WateringEvent
from app.state import garden, ws_manager

logger = logging.getLogger(__name__)

_mqtt_client = None


def set_mqtt_client(client) -> None:
    global _mqtt_client
    _mqtt_client = client


async def trigger_watering(
    zone_id: int,
    duration_seconds: int,
    trigger_type: str,
    program_id: int | None = None,
) -> bool:
    zone = garden.zones.get(zone_id)
    if zone is None or zone.is_watering:
        return False

    if zone.tank_id is not None:
        tank = garden.tanks.get(zone.tank_id)
        if tank is not None and tank.is_empty():
            logger.warning("Zona %d: reg bloquejat — dipòsit %d buit (%s)", zone_id, zone.tank_id, tank.sensor_state)
            from app.notifications.push import maybe_create_alert
            await maybe_create_alert(
                "tank_empty",
                f"Reg de la zona {zone_id} bloquejat — dipòsit {tank.name} buit",
            )
            return False

    if _mqtt_client is not None:
        _mqtt_client.publish_control(zone_id, "on", duration_seconds)

    async with AsyncSessionLocal() as db:
        event = WateringEvent(
            zone_id=zone_id,
            program_id=program_id,
            started_at=datetime.now(timezone.utc),
            trigger_type=trigger_type,
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)
        event_id = event.id

    zone.is_watering = True
    zone.last_watered_at = datetime.now(timezone.utc).isoformat()
    zone.active_event_id = event_id
    garden.touch()

    await ws_manager.broadcast(garden.to_dict())
    asyncio.create_task(_auto_stop(zone_id, duration_seconds, event_id))
    return True


async def finish_watering_early(event_id: int) -> None:
    async with AsyncSessionLocal() as db:
        event = await db.get(WateringEvent, event_id)
        if event and event.ended_at is None:
            event.ended_at = datetime.now(timezone.utc)
            event.duration_seconds = int((event.ended_at - event.started_at).total_seconds())
            await db.commit()


async def _auto_stop(zone_id: int, delay: int, event_id: int | None = None) -> None:
    await asyncio.sleep(delay)
    zone = garden.zones.get(zone_id)
    if zone and zone.is_watering:
        if _mqtt_client is not None:
            _mqtt_client.publish_control(zone_id, "off", 0)
        zone.is_watering = False
        zone.active_event_id = None
        garden.touch()
        await ws_manager.broadcast(garden.to_dict())
        if event_id is not None:
            await _finish_watering_event(event_id, delay)
        from app.notifications.push import maybe_create_alert
        await maybe_create_alert(
            "water_completed",
            f"Reg completat a la zona {zone_id} ({delay}s)",
            zone_id=zone_id,
        )


async def _finish_watering_event(event_id: int, duration_seconds: int) -> None:
    async with AsyncSessionLocal() as db:
        event = await db.get(WateringEvent, event_id)
        if event and event.ended_at is None:
            event.ended_at = datetime.now(timezone.utc)
            event.duration_seconds = duration_seconds
            await db.commit()
