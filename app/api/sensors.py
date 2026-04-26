from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models import SensorReading
from app.state import garden

router = APIRouter(
    prefix="/api/sensors",
    tags=["sensors"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/latest")
async def get_latest_sensors(db: AsyncSession = Depends(get_db)):
    """Retorna l'última lectura de cada tipus de sensor."""

    # Subquery: màxim timestamp per cada (sensor_type, zone_id)
    subq = (
        select(
            SensorReading.sensor_type,
            SensorReading.zone_id,
            func.max(SensorReading.timestamp).label("max_ts"),
        )
        .group_by(SensorReading.sensor_type, SensorReading.zone_id)
        .subquery()
    )

    result = await db.execute(
        select(SensorReading).join(
            subq,
            (SensorReading.sensor_type == subq.c.sensor_type)
            & (SensorReading.zone_id == subq.c.zone_id)
            & (SensorReading.timestamp == subq.c.max_ts),
        )
    )
    readings = result.scalars().all()

    soil: list[dict] = []
    ambient: dict[str, dict | None] = {
        "temperature": None,
        "humidity": None,
        "light_lux": None,
    }

    for r in readings:
        entry = {"value": r.value, "timestamp": r.timestamp.isoformat()}
        if r.sensor_type == "soil_humidity":
            soil.append({"zone_id": r.zone_id, **entry})
        elif r.sensor_type == "ambient_temperature":
            ambient["temperature"] = entry
        elif r.sensor_type == "ambient_humidity":
            ambient["humidity"] = entry
        elif r.sensor_type == "light_lux":
            ambient["light_lux"] = entry

    return {"soil": soil, "ambient": ambient}


@router.get("/ambient/latest")
async def get_latest_ambient():
    """Retorna les lectures ambient actuals de la memòria (temps real)."""
    return garden.ambient.to_dict()


@router.get("/ambient/history")
async def get_ambient_history(hours: int = 24, db: AsyncSession = Depends(get_db)):
    """Retorna l'historial de lectures ambientals (temperatura, humitat, llum)."""
    from datetime import timedelta
    from sqlalchemy import and_

    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    result = await db.execute(
        select(SensorReading)
        .where(
            and_(
                SensorReading.sensor_type.in_(["ambient_temperature", "ambient_humidity", "light_lux"]),
                SensorReading.timestamp >= since,
            )
        )
        .order_by(SensorReading.timestamp)
    )
    readings = result.scalars().all()

    temperature, ambient_humidity, light_lux = [], [], []
    for r in readings:
        entry = {"timestamp": r.timestamp.isoformat(), "value": r.value}
        if r.sensor_type == "ambient_temperature":
            temperature.append(entry)
        elif r.sensor_type == "ambient_humidity":
            ambient_humidity.append(entry)
        elif r.sensor_type == "light_lux":
            light_lux.append(entry)

    return {
        "hours": hours,
        "temperature": temperature,
        "ambient_humidity": ambient_humidity,
        "light_lux": light_lux,
    }
