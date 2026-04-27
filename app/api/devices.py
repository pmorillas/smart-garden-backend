from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models import Device
from app.state import garden

router = APIRouter(
    prefix="/api/devices",
    tags=["devices"],
    dependencies=[Depends(get_current_user)],
)

ONLINE_THRESHOLD_MINUTES = 15
POLL_INTERVAL_MIN = 10
POLL_INTERVAL_MAX = 3600


def _is_online(last_seen: datetime | None) -> bool:
    if last_seen is None:
        return False
    return (datetime.now(timezone.utc) - last_seen) < timedelta(minutes=ONLINE_THRESHOLD_MINUTES)


def _to_dict(d: Device) -> dict:
    return {
        "id": d.id,
        "mac_address": d.mac_address,
        "name": d.name,
        "firmware_version": d.firmware_version,
        "active": d.active,
        "online": _is_online(d.last_seen),
        "last_seen": d.last_seen.isoformat() if d.last_seen else None,
        "registered_at": d.registered_at.isoformat(),
        "poll_interval_seconds": d.poll_interval_seconds,
        "zones": [{"id": z.id, "name": z.name} for z in d.zones],
    }


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    active: bool | None = None
    poll_interval_seconds: int | None = Field(
        default=None, ge=POLL_INTERVAL_MIN, le=POLL_INTERVAL_MAX
    )


@router.get("/")
async def list_devices(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Device).options(selectinload(Device.zones)).order_by(Device.id)
    )
    return [_to_dict(d) for d in result.scalars().all()]


@router.get("/{device_id}")
async def get_device(device_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Device).options(selectinload(Device.zones)).where(Device.id == device_id)
    )
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail="Dispositiu no trobat")
    return _to_dict(device)


@router.put("/{device_id}")
async def update_device(device_id: int, body: DeviceUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Device).options(selectinload(Device.zones)).where(Device.id == device_id)
    )
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail="Dispositiu no trobat")
    if body.name is not None:
        device.name = body.name
    if body.active is not None:
        device.active = body.active
    if body.poll_interval_seconds is not None:
        device.poll_interval_seconds = body.poll_interval_seconds
        dev_status = garden.devices.get(device.mac_address)
        if dev_status is not None:
            dev_status.poll_interval_seconds = body.poll_interval_seconds
    await db.commit()
    await db.refresh(device)
    return _to_dict(device)


@router.delete("/{device_id}", status_code=204)
async def delete_device(device_id: int, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Dispositiu no trobat")
    await db.delete(device)
    await db.commit()


@router.post("/{device_id}/push-hardware-config")
async def push_hardware_config(device_id: int, db: AsyncSession = Depends(get_db)):
    """Build and publish the full hardware config (peripherals + zones + tanks) to the ESP32."""
    from app.irrigation import actions as irrigation_actions
    from app.mqtt.client import _build_hardware_config
    from sqlalchemy import update
    from app.models.zone import Zone

    device = await db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Dispositiu no trobat")
    if irrigation_actions._mqtt_client is None:
        raise HTTPException(status_code=503, detail="MQTT no disponible")

    payload = await _build_hardware_config(device_id, db)
    irrigation_actions._mqtt_client.publish_hardware_config(device.mac_address, payload)

    await db.execute(update(Zone).where(Zone.device_id == device_id).values(config_synced=False))
    await db.commit()

    return {
        "ok": True,
        "mac": device.mac_address,
        "peripherals": len(payload["peripherals"]),
        "zones": len(payload["zones"]),
        "tanks": len(payload["tanks"]),
    }
