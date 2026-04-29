import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models import Device
from app.models.peripheral import Peripheral, ZoneSoilSensor, PERIPHERAL_TYPES, AGGREGATION_MODES
from app.models.zone import Zone, ZoneConfig
from app.models.tank import WaterTank
from app.state import garden

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


@router.post("/{peripheral_id}/read")
async def read_peripheral_live(device_id: int, peripheral_id: int, db: AsyncSession = Depends(get_db)):
    """Trigger an immediate sensor read and return the raw ADC value + calibrated %."""
    p = await db.get(Peripheral, peripheral_id)
    if p is None or p.device_id != device_id:
        raise HTTPException(status_code=404, detail="Perifèric no trobat")
    if p.type != "SOIL_ADC":
        raise HTTPException(status_code=422, detail="Només SOIL_ADC suportat per lectura en viu")

    zone_soil_result = await db.execute(
        select(ZoneSoilSensor).where(ZoneSoilSensor.peripheral_id == peripheral_id)
    )
    zone_soil = zone_soil_result.scalar_one_or_none()
    if zone_soil is None:
        raise HTTPException(status_code=422, detail="Perifèric no assignat a cap zona")

    # Find this peripheral's index within the zone's ordered sensor list
    all_soil_result = await db.execute(
        select(ZoneSoilSensor)
        .where(ZoneSoilSensor.zone_id == zone_soil.zone_id)
        .order_by(ZoneSoilSensor.order_index)
    )
    all_soil = all_soil_result.scalars().all()
    perif_idx = next((i for i, s in enumerate(all_soil) if s.peripheral_id == peripheral_id), 0)

    # Get calibration values (per-sensor override or zone defaults)
    dry_val, wet_val = 3800, 1200
    if p.extra_config:
        cal_e = p.extra_config.get("cal_empty")
        cal_f = p.extra_config.get("cal_full")
        if cal_e is not None and cal_f is not None:
            dry_val, wet_val = int(cal_e), int(cal_f)
        else:
            cfg_result = await db.execute(select(ZoneConfig).where(ZoneConfig.zone_id == zone_soil.zone_id))
            cfg = cfg_result.scalar_one_or_none()
            if cfg:
                dry_val, wet_val = cfg.soil_dry_value, cfg.soil_wet_value
    else:
        cfg_result = await db.execute(select(ZoneConfig).where(ZoneConfig.zone_id == zone_soil.zone_id))
        cfg = cfg_result.scalar_one_or_none()
        if cfg:
            dry_val, wet_val = cfg.soil_dry_value, cfg.soil_wet_value

    device = await _get_device_or_404(device_id, db)

    from app.irrigation import actions as irrigation_actions
    if irrigation_actions._mqtt_client is None:
        raise HTTPException(status_code=503, detail="MQTT no disponible")

    zone_state = garden.zones.get(zone_soil.zone_id)
    pre_seq = zone_state.reading_seq if zone_state else -1

    irrigation_actions._mqtt_client.publish_sensor_request(device.mac_address)

    # Poll up to 4 seconds for a new reading to arrive
    raw_value = None
    for _ in range(8):
        await asyncio.sleep(0.5)
        zone_state = garden.zones.get(zone_soil.zone_id)
        if zone_state and zone_state.reading_seq != pre_seq:
            if perif_idx < len(zone_state.soil_raw_values):
                raw_value = zone_state.soil_raw_values[perif_idx]
            break

    # Fall back to last known raw value if no new reading arrived
    if raw_value is None and zone_state and perif_idx < len(zone_state.soil_raw_values):
        raw_value = zone_state.soil_raw_values[perif_idx]

    if raw_value is None:
        raise HTTPException(status_code=503, detail="No s'ha rebut cap lectura del sensor")

    calibrated_pct = None
    if dry_val != wet_val:
        pct = 100.0 * (dry_val - raw_value) / (dry_val - wet_val)
        calibrated_pct = round(max(0.0, min(100.0, pct)), 1)

    return {
        "peripheral_id": peripheral_id,
        "zone_id": zone_soil.zone_id,
        "raw_value": raw_value,
        "calibrated_pct": calibrated_pct,
        "cal_empty": dry_val,
        "cal_full": wet_val,
    }
