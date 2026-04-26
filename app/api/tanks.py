import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.tank import WaterTank, TankReading, SENSOR_TYPES
from app.models import Device
from app.state import garden, TankStatus
from app.irrigation import actions as irrigation_actions

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/tanks",
    tags=["tanks"],
    dependencies=[Depends(get_current_user)],
)


class TankCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    device_id: int | None = None
    sensor_type: str = "binary_single"
    gpio_pin_1: int | None = Field(default=None, ge=0, le=39)
    gpio_pin_2: int | None = Field(default=None, ge=0, le=39)
    capacity_liters: float | None = Field(default=None, gt=0)
    calibration_empty: int | None = Field(default=None, ge=0)
    calibration_full: int | None = Field(default=None, ge=0)
    low_threshold_pct: int = Field(default=20, ge=0, le=100)
    empty_threshold_pct: int = Field(default=5, ge=0, le=100)


class TankUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    active: bool | None = None
    device_id: int | None = None
    sensor_type: str | None = None
    gpio_pin_1: int | None = Field(default=None, ge=0, le=39)
    gpio_pin_2: int | None = Field(default=None, ge=0, le=39)
    capacity_liters: float | None = Field(default=None, gt=0)
    calibration_empty: int | None = Field(default=None, ge=0)
    calibration_full: int | None = Field(default=None, ge=0)
    low_threshold_pct: int | None = Field(default=None, ge=0, le=100)
    empty_threshold_pct: int | None = Field(default=None, ge=0, le=100)


def _to_dict(tank: WaterTank, status: TankStatus | None = None) -> dict:
    return {
        "id": tank.id,
        "name": tank.name,
        "device_id": tank.device_id,
        "active": tank.active,
        "sensor_type": tank.sensor_type,
        "gpio_pin_1": tank.gpio_pin_1,
        "gpio_pin_2": tank.gpio_pin_2,
        "capacity_liters": tank.capacity_liters,
        "calibration_empty": tank.calibration_empty,
        "calibration_full": tank.calibration_full,
        "low_threshold_pct": tank.low_threshold_pct,
        "empty_threshold_pct": tank.empty_threshold_pct,
        "status": status.to_dict() if status else None,
    }


async def _push_tank_config(device_id: int, db: AsyncSession) -> None:
    if irrigation_actions._mqtt_client is None:
        return
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        return
    tanks_result = await db.execute(select(WaterTank).where(WaterTank.device_id == device_id, WaterTank.active == True))  # noqa: E712
    tanks = tanks_result.scalars().all()
    config = [
        {
            "id": t.id,
            "sensor_type": t.sensor_type,
            "pin_1": t.gpio_pin_1,
            "pin_2": t.gpio_pin_2,
            "cal_empty": t.calibration_empty,
            "cal_full": t.calibration_full,
            "low_pct": t.low_threshold_pct,
            "empty_pct": t.empty_threshold_pct,
        }
        for t in tanks
    ]
    irrigation_actions._mqtt_client.publish_tank_config(device.mac_address, config)
    logger.info("Tank config enviada a %s (%d tanks)", device.mac_address, len(tanks))


@router.get("/")
async def list_tanks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WaterTank).order_by(WaterTank.id))
    tanks = result.scalars().all()
    return [_to_dict(t, garden.tanks.get(t.id)) for t in tanks]


@router.post("/", status_code=201)
async def create_tank(body: TankCreate, db: AsyncSession = Depends(get_db)):
    if body.sensor_type not in SENSOR_TYPES:
        raise HTTPException(status_code=422, detail=f"Tipus de sensor invàlid: {body.sensor_type}")
    tank = WaterTank(**body.model_dump())
    db.add(tank)
    await db.commit()
    await db.refresh(tank)

    garden.tanks[tank.id] = TankStatus(tank.id, tank.name, tank.empty_threshold_pct, tank.low_threshold_pct)

    if body.device_id is not None:
        await _push_tank_config(body.device_id, db)

    return _to_dict(tank, garden.tanks.get(tank.id))


@router.get("/{tank_id}")
async def get_tank(tank_id: int, db: AsyncSession = Depends(get_db)):
    tank = await db.get(WaterTank, tank_id)
    if tank is None:
        raise HTTPException(status_code=404, detail="Dipòsit no trobat")
    return _to_dict(tank, garden.tanks.get(tank_id))


@router.put("/{tank_id}")
async def update_tank(tank_id: int, body: TankUpdate, db: AsyncSession = Depends(get_db)):
    tank = await db.get(WaterTank, tank_id)
    if tank is None:
        raise HTTPException(status_code=404, detail="Dipòsit no trobat")

    if body.sensor_type is not None and body.sensor_type not in SENSOR_TYPES:
        raise HTTPException(status_code=422, detail=f"Tipus de sensor invàlid: {body.sensor_type}")

    old_device_id = tank.device_id
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(tank, field, value)
    await db.commit()

    # Update in-memory status thresholds
    status = garden.tanks.get(tank_id)
    if status:
        if body.name is not None:
            status.name = body.name
        if body.empty_threshold_pct is not None:
            status.empty_threshold_pct = body.empty_threshold_pct
        if body.low_threshold_pct is not None:
            status.low_threshold_pct = body.low_threshold_pct

    device_id = tank.device_id or old_device_id
    if device_id is not None:
        await _push_tank_config(device_id, db)

    return {"ok": True}


@router.delete("/{tank_id}", status_code=204)
async def delete_tank(tank_id: int, db: AsyncSession = Depends(get_db)):
    tank = await db.get(WaterTank, tank_id)
    if tank is None:
        raise HTTPException(status_code=404, detail="Dipòsit no trobat")
    device_id = tank.device_id
    await db.delete(tank)
    await db.commit()
    garden.tanks.pop(tank_id, None)
    if device_id is not None:
        await _push_tank_config(device_id, db)


@router.get("/{tank_id}/readings")
async def get_tank_readings(tank_id: int, hours: int = Query(default=24, ge=1, le=168), db: AsyncSession = Depends(get_db)):
    tank = await db.get(WaterTank, tank_id)
    if tank is None:
        raise HTTPException(status_code=404, detail="Dipòsit no trobat")
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(TankReading)
        .where(TankReading.tank_id == tank_id, TankReading.timestamp >= since)
        .order_by(TankReading.timestamp)
    )
    readings = result.scalars().all()
    return {
        "tank_id": tank_id,
        "hours": hours,
        "readings": [
            {
                "timestamp": r.timestamp.isoformat(),
                "raw_value": r.raw_value,
                "level_percent": r.level_percent,
                "sensor_state": r.sensor_state,
            }
            for r in readings
        ],
    }


@router.post("/{tank_id}/calibrate")
async def calibrate_tank(tank_id: int, level: str = Query(..., pattern="^(empty|full)$"), db: AsyncSession = Depends(get_db)):
    tank = await db.get(WaterTank, tank_id)
    if tank is None:
        raise HTTPException(status_code=404, detail="Dipòsit no trobat")

    # Use latest reading's raw_value as calibration point
    result = await db.execute(
        select(TankReading)
        .where(TankReading.tank_id == tank_id)
        .order_by(TankReading.timestamp.desc())
        .limit(1)
    )
    reading = result.scalar_one_or_none()
    if reading is None:
        raise HTTPException(status_code=400, detail="No hi ha lectures del sensor. Assegura't que l'ESP32 publica dades del dipòsit.")

    cal_value = int(reading.raw_value)
    if level == "empty":
        tank.calibration_empty = cal_value
    else:
        tank.calibration_full = cal_value
    await db.commit()

    if tank.device_id is not None:
        await _push_tank_config(tank.device_id, db)

    return {"ok": True, "level": level, "calibration_value": cal_value}
