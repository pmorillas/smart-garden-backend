from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user
from app.database import get_db
from app.models import Zone, ZoneConfig, WateringEvent
from app.state import garden, ws_manager
from app.irrigation import actions as irrigation_actions

router = APIRouter(
    prefix="/api/zones",
    tags=["zones"],
    dependencies=[Depends(get_current_user)],
)


# --- Schemas ---

class ZoneUpdate(BaseModel):
    name: str | None = None
    active: bool | None = None


class ZoneConfigUpdate(BaseModel):
    humidity_min: float | None = Field(default=None, ge=0, le=100)
    humidity_max: float | None = Field(default=None, ge=0, le=100)
    max_temp_to_water: float | None = Field(default=None, ge=0, le=60)
    cooldown_hours: float | None = Field(default=None, ge=0, le=48)
    soil_dry_value: int | None = Field(default=None, ge=0, le=4095)
    soil_wet_value: int | None = Field(default=None, ge=0, le=4095)


class WaterRequest(BaseModel):
    duration_seconds: int = Field(default=60, ge=5, le=600)


class ZoneDeviceAssign(BaseModel):
    device_id: int | None = None


# --- Helpers ---

def _zone_to_dict(zone: Zone) -> dict:
    cfg = zone.config
    return {
        "id": zone.id,
        "name": zone.name,
        "active": zone.active,
        "device_id": zone.device_id,
        "relay_pin_local": zone.relay_pin_local,
        "soil_pin_a_local": zone.soil_pin_a_local,
        "soil_pin_b_local": zone.soil_pin_b_local,
        "config": {
            "humidity_min": cfg.humidity_min if cfg else 30.0,
            "humidity_max": cfg.humidity_max if cfg else 80.0,
            "max_temp_to_water": cfg.max_temp_to_water if cfg else 38.0,
            "cooldown_hours": cfg.cooldown_hours if cfg else 2.0,
            "soil_dry_value": cfg.soil_dry_value if cfg else 3800,
            "soil_wet_value": cfg.soil_wet_value if cfg else 1200,
        } if cfg else None,
    }


# --- Endpoints ---

@router.get("/")
async def list_zones(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Zone).options(selectinload(Zone.config)).order_by(Zone.id))
    return [_zone_to_dict(z) for z in result.scalars().all()]


@router.get("/{zone_id}")
async def get_zone(zone_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Zone).options(selectinload(Zone.config)).where(Zone.id == zone_id)
    )
    zone = result.scalar_one_or_none()
    if zone is None:
        raise HTTPException(status_code=404, detail=f"Zona {zone_id} no trobada")
    return _zone_to_dict(zone)


@router.put("/{zone_id}")
async def update_zone(zone_id: int, body: ZoneUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Zone).where(Zone.id == zone_id))
    zone = result.scalar_one_or_none()
    if zone is None:
        raise HTTPException(status_code=404, detail=f"Zona {zone_id} no trobada")

    if body.name is not None:
        zone.name = body.name
        mem_zone = garden.zones.get(zone_id)
        if mem_zone:
            mem_zone.name = body.name
    if body.active is not None:
        zone.active = body.active

    await db.commit()
    return {"ok": True}


@router.get("/{zone_id}/config")
async def get_zone_config(zone_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ZoneConfig).where(ZoneConfig.zone_id == zone_id))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Configuració de zona {zone_id} no trobada")
    return {
        "zone_id": cfg.zone_id,
        "humidity_min": cfg.humidity_min,
        "humidity_max": cfg.humidity_max,
        "max_temp_to_water": cfg.max_temp_to_water,
        "cooldown_hours": cfg.cooldown_hours,
        "soil_dry_value": cfg.soil_dry_value,
        "soil_wet_value": cfg.soil_wet_value,
    }


@router.put("/{zone_id}/config")
async def update_zone_config(zone_id: int, body: ZoneConfigUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ZoneConfig).where(ZoneConfig.zone_id == zone_id))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Configuració de zona {zone_id} no trobada")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(cfg, field, value)

    await db.commit()
    return {"ok": True}


@router.get("/{zone_id}/history")
async def get_zone_history(zone_id: int, hours: int = 24, db: AsyncSession = Depends(get_db)):
    from datetime import timedelta
    from sqlalchemy import and_

    from app.models import SensorReading

    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    readings_result = await db.execute(
        select(SensorReading)
        .where(and_(SensorReading.zone_id == zone_id, SensorReading.timestamp >= since))
        .order_by(SensorReading.timestamp)
    )
    readings = readings_result.scalars().all()

    events_result = await db.execute(
        select(WateringEvent)
        .where(and_(WateringEvent.zone_id == zone_id, WateringEvent.started_at >= since))
        .order_by(WateringEvent.started_at)
    )
    events = events_result.scalars().all()

    return {
        "zone_id": zone_id,
        "hours": hours,
        "soil_readings": [
            {"timestamp": r.timestamp.isoformat(), "value": r.value}
            for r in readings
            if r.sensor_type == "soil_humidity"
        ],
        "watering_events": [
            {
                "id": e.id,
                "started_at": e.started_at.isoformat(),
                "ended_at": e.ended_at.isoformat() if e.ended_at else None,
                "duration_seconds": e.duration_seconds,
                "trigger_type": e.trigger_type,
            }
            for e in events
        ],
    }


@router.put("/{zone_id}/device")
async def assign_device(zone_id: int, body: ZoneDeviceAssign, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Zone).where(Zone.id == zone_id))
    zone = result.scalar_one_or_none()
    if zone is None:
        raise HTTPException(status_code=404, detail=f"Zona {zone_id} no trobada")
    zone.device_id = body.device_id
    await db.commit()
    return {"ok": True}


@router.post("/{zone_id}/water")
async def water_zone(zone_id: int, body: WaterRequest):
    zone = garden.zones.get(zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail=f"Zona {zone_id} no trobada")
    if zone.is_watering:
        raise HTTPException(status_code=409, detail="La zona ja està regant")
    if irrigation_actions._mqtt_client is None:
        raise HTTPException(status_code=503, detail="MQTT no disponible")

    await irrigation_actions.trigger_watering(zone_id, body.duration_seconds, "manual")
    return {"zone_id": zone_id, "duration_seconds": body.duration_seconds, "status": "started"}


@router.post("/{zone_id}/stop")
async def stop_zone(zone_id: int):
    zone = garden.zones.get(zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail=f"Zona {zone_id} no trobada")

    event_id = zone.active_event_id

    if irrigation_actions._mqtt_client is not None:
        irrigation_actions._mqtt_client.publish_control(zone_id, "off", 0)

    zone.is_watering = False
    zone.active_event_id = None
    garden.touch()

    await ws_manager.broadcast(garden.to_dict())

    if event_id:
        await irrigation_actions.finish_watering_early(event_id)

    return {"zone_id": zone_id, "status": "stopped"}
