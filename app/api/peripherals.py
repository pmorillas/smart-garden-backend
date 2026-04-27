import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models import Device
from app.models.peripheral import Peripheral, ZoneSoilSensor, PERIPHERAL_TYPES, AGGREGATION_MODES
from app.models.zone import Zone
from app.models.tank import WaterTank

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/devices/{device_id}/peripherals",
    tags=["peripherals"],
    dependencies=[Depends(get_current_user)],
)


class PeripheralCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str
    pin1: int | None = Field(default=None, ge=0, le=39)
    pin2: int | None = Field(default=None, ge=0, le=39)
    i2c_address: int | None = Field(default=None, ge=0, le=127)
    i2c_bus: int = Field(default=0, ge=0, le=1)
    extra_config: dict | None = None
    enabled: bool = True


class PeripheralUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    pin1: int | None = Field(default=None, ge=0, le=39)
    pin2: int | None = Field(default=None, ge=0, le=39)
    i2c_address: int | None = Field(default=None, ge=0, le=127)
    i2c_bus: int | None = Field(default=None, ge=0, le=1)
    extra_config: dict | None = None
    enabled: bool | None = None


class ZoneSoilAssign(BaseModel):
    zone_id: int
    peripheral_ids: list[int]
    aggregation_mode: str = "AVG"


class ZoneRelayAssign(BaseModel):
    zone_id: int
    peripheral_id: int | None


class TankPeripheralAssign(BaseModel):
    tank_id: int
    peripheral_id: int | None


def _peripheral_to_dict(p: Peripheral) -> dict:
    return {
        "id": p.id,
        "device_id": p.device_id,
        "name": p.name,
        "type": p.type,
        "pin1": p.pin1,
        "pin2": p.pin2,
        "i2c_address": p.i2c_address,
        "i2c_bus": p.i2c_bus,
        "extra_config": p.extra_config,
        "enabled": p.enabled,
    }


async def _get_device_or_404(device_id: int, db: AsyncSession) -> Device:
    device = await db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Dispositiu no trobat")
    return device


@router.get("/")
async def list_peripherals(device_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Peripheral).where(Peripheral.device_id == device_id).order_by(Peripheral.id)
    )
    return [_peripheral_to_dict(p) for p in result.scalars().all()]


@router.post("/", status_code=201)
async def create_peripheral(device_id: int, body: PeripheralCreate, db: AsyncSession = Depends(get_db)):
    await _get_device_or_404(device_id, db)
    if body.type not in PERIPHERAL_TYPES:
        raise HTTPException(status_code=422, detail=f"Tipus de perifèric invàlid: {body.type}")

    p = Peripheral(device_id=device_id, **body.model_dump())
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return _peripheral_to_dict(p)


@router.get("/{peripheral_id}")
async def get_peripheral(device_id: int, peripheral_id: int, db: AsyncSession = Depends(get_db)):
    p = await db.get(Peripheral, peripheral_id)
    if p is None or p.device_id != device_id:
        raise HTTPException(status_code=404, detail="Perifèric no trobat")
    return _peripheral_to_dict(p)


@router.put("/{peripheral_id}")
async def update_peripheral(device_id: int, peripheral_id: int, body: PeripheralUpdate, db: AsyncSession = Depends(get_db)):
    p = await db.get(Peripheral, peripheral_id)
    if p is None or p.device_id != device_id:
        raise HTTPException(status_code=404, detail="Perifèric no trobat")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(p, field, value)
    await db.commit()
    return {"ok": True}


@router.delete("/{peripheral_id}", status_code=204)
async def delete_peripheral(device_id: int, peripheral_id: int, db: AsyncSession = Depends(get_db)):
    p = await db.get(Peripheral, peripheral_id)
    if p is None or p.device_id != device_id:
        raise HTTPException(status_code=404, detail="Perifèric no trobat")
    await db.delete(p)
    await db.commit()


@router.post("/assign-zone-soil")
async def assign_zone_soil_sensors(device_id: int, body: ZoneSoilAssign, db: AsyncSession = Depends(get_db)):
    """Replace soil sensor assignments for a zone."""
    await _get_device_or_404(device_id, db)

    if body.aggregation_mode not in AGGREGATION_MODES:
        raise HTTPException(status_code=422, detail=f"Mode d'agregació invàlid: {body.aggregation_mode}")

    zone = await db.get(Zone, body.zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Zona no trobada")

    # Validate all peripherals belong to this device and are SOIL_ADC type
    for pid in body.peripheral_ids:
        p = await db.get(Peripheral, pid)
        if p is None or p.device_id != device_id:
            raise HTTPException(status_code=422, detail=f"Perifèric {pid} no pertany al dispositiu")
        if p.type != "SOIL_ADC":
            raise HTTPException(status_code=422, detail=f"Perifèric {pid} no és de tipus SOIL_ADC")

    # Delete existing assignments
    existing = await db.execute(
        select(ZoneSoilSensor).where(ZoneSoilSensor.zone_id == body.zone_id)
    )
    for row in existing.scalars().all():
        await db.delete(row)

    # Insert new assignments
    for idx, pid in enumerate(body.peripheral_ids):
        db.add(ZoneSoilSensor(zone_id=body.zone_id, peripheral_id=pid, order_index=idx))

    zone.soil_aggregation_mode = body.aggregation_mode
    zone.config_synced = False
    await db.commit()
    return {"ok": True}


@router.post("/assign-zone-relay")
async def assign_zone_relay(device_id: int, body: ZoneRelayAssign, db: AsyncSession = Depends(get_db)):
    """Set (or unset) the relay peripheral for a zone."""
    await _get_device_or_404(device_id, db)

    zone = await db.get(Zone, body.zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Zona no trobada")

    if body.peripheral_id is not None:
        p = await db.get(Peripheral, body.peripheral_id)
        if p is None or p.device_id != device_id:
            raise HTTPException(status_code=422, detail="Perifèric no pertany al dispositiu")
        if p.type != "RELAY":
            raise HTTPException(status_code=422, detail="El perifèric no és de tipus RELAY")

    zone.relay_peripheral_id = body.peripheral_id
    zone.config_synced = False
    await db.commit()
    return {"ok": True}


@router.post("/assign-tank")
async def assign_tank_peripheral(device_id: int, body: TankPeripheralAssign, db: AsyncSession = Depends(get_db)):
    """Set (or unset) the level sensor peripheral for a tank."""
    await _get_device_or_404(device_id, db)

    tank = await db.get(WaterTank, body.tank_id)
    if tank is None:
        raise HTTPException(status_code=404, detail="Dipòsit no trobat")

    if body.peripheral_id is not None:
        p = await db.get(Peripheral, body.peripheral_id)
        if p is None or p.device_id != device_id:
            raise HTTPException(status_code=422, detail="Perifèric no pertany al dispositiu")
        valid_tank_types = ("HC_SR04", "FLOAT_BINARY")
        if p.type not in valid_tank_types:
            raise HTTPException(status_code=422, detail=f"El perifèric ha de ser de tipus: {valid_tank_types}")

    tank.peripheral_id = body.peripheral_id
    await db.commit()
    return {"ok": True}
