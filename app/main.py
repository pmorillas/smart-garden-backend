import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Zone
from app.mqtt.client import MqttClient
from app.api import ws as ws_module
from app.api import zones as zones_module
from app.api import sensors as sensors_module
from app.api import auth as auth_module
from app.api import programs as programs_module
from app.api import devices as devices_module
from app.api import alerts as alerts_module
from app.api import alert_rules as alert_rules_module
from app.api import push as push_module
from app.api import firmware as firmware_module
from app.api import tanks as tanks_module
from app.api import peripherals as peripherals_module
from app.api import cleanup as cleanup_module
from app.irrigation import actions as irrigation_actions
from app.scheduler import runner as scheduler_runner
from app.services import retention as retention_service
from app.state import garden, ZoneStatus, TankStatus, DeviceStatus

logger = logging.getLogger(__name__)

_mqtt_client: MqttClient | None = None


def _run_migrations() -> None:
    from alembic.config import Config as AlembicConfig
    from alembic import command as alembic_command

    cfg = AlembicConfig("alembic.ini")
    alembic_command.upgrade(cfg, "head")


async def _seed_initial_data() -> None:
    from app.models import Zone, ZoneConfig, User, WaterTank
    from app.models.peripheral import Peripheral, ZoneSoilSensor
    from app.core.security import hash_password

    async with AsyncSessionLocal() as db:
        # Zones per defecte
        result = await db.execute(select(Zone).options(selectinload(Zone.config)))
        zones = result.scalars().all()

        if not zones:
            logger.info("Seed: creant zones i perifèrics per defecte")
            zone1 = Zone(name="Zona 1", active=True)
            zone2 = Zone(name="Zona 2", active=True)
            db.add_all([zone1, zone2])
            await db.flush()
            db.add(ZoneConfig(zone_id=zone1.id))
            db.add(ZoneConfig(zone_id=zone2.id))

            # Default peripherals matching confirmed hardware pinout
            relay1 = Peripheral(name="Bomba Zona 1", type="RELAY", pin1=14)
            relay2 = Peripheral(name="Bomba Zona 2", type="RELAY", pin1=27)
            soil1a = Peripheral(name="Terra Z1-A", type="SOIL_ADC", pin1=32)
            soil1b = Peripheral(name="Terra Z1-B", type="SOIL_ADC", pin1=33)
            soil2a = Peripheral(name="Terra Z2-A", type="SOIL_ADC", pin1=34)
            soil2b = Peripheral(name="Terra Z2-B", type="SOIL_ADC", pin1=35)
            htu21d = Peripheral(name="HTU21D", type="HTU21D", i2c_bus=0)
            bh1750 = Peripheral(name="BH1750", type="BH1750", i2c_bus=0, i2c_address=0x23)
            db.add_all([relay1, relay2, soil1a, soil1b, soil2a, soil2b, htu21d, bh1750])
            await db.flush()

            zone1.relay_peripheral_id = relay1.id
            zone2.relay_peripheral_id = relay2.id
            db.add(ZoneSoilSensor(zone_id=zone1.id, peripheral_id=soil1a.id, order_index=0))
            db.add(ZoneSoilSensor(zone_id=zone1.id, peripheral_id=soil1b.id, order_index=1))
            db.add(ZoneSoilSensor(zone_id=zone2.id, peripheral_id=soil2a.id, order_index=0))
            db.add(ZoneSoilSensor(zone_id=zone2.id, peripheral_id=soil2b.id, order_index=1))

            await db.commit()
            await db.refresh(zone1)
            await db.refresh(zone2)
            zones = [zone1, zone2]

        for z in zones:
            if z.active:
                garden.zones[z.id] = ZoneStatus(z.id, z.name, tank_id=z.tank_id)

        # Dipòsits en memòria
        tanks_result = await db.execute(select(WaterTank).where(WaterTank.active == True))  # noqa: E712
        for t in tanks_result.scalars().all():
            garden.tanks[t.id] = TankStatus(t.id, t.name, t.empty_threshold_pct, t.low_threshold_pct)

        # Dispositius en memòria (per al ping)
        from app.models import Device
        devices_result = await db.execute(select(Device).where(Device.active == True))  # noqa: E712
        for d in devices_result.scalars().all():
            garden.devices[d.mac_address] = DeviceStatus(d.mac_address, d.name, d.poll_interval_seconds)

        # Usuari admin per defecte
        user_result = await db.execute(select(User))
        if user_result.scalars().first() is None:
            logger.info("Seed: creant usuari admin (%s)", settings.admin_username)
            admin = User(
                username=settings.admin_username,
                hashed_password=hash_password(settings.admin_password),
                is_active=True,
            )
            db.add(admin)
            await db.commit()

    logger.info("Zones en memòria: %s", list(garden.zones.keys()))
    logger.info("Dipòsits en memòria: %s", list(garden.tanks.keys()))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _mqtt_client

    logger.info("Executant migracions de base de dades...")
    await asyncio.to_thread(_run_migrations)
    logger.info("Migracions completades")

    await _seed_initial_data()

    loop = asyncio.get_event_loop()
    _mqtt_client = MqttClient(loop=loop)
    _mqtt_client.connect()
    irrigation_actions.set_mqtt_client(_mqtt_client)
    firmware_module.set_mqtt_client(_mqtt_client)
    scheduler_runner.set_mqtt_client(_mqtt_client)

    scheduler_runner.start_scheduler()
    retention_service.start_retention_scheduler()

    yield

    scheduler_runner.stop_scheduler()
    if _mqtt_client:
        _mqtt_client.disconnect()


app = FastAPI(
    title="Smart Garden API",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_module.router)
app.include_router(ws_module.router)
app.include_router(zones_module.router)
app.include_router(sensors_module.router)
app.include_router(programs_module.router)
app.include_router(devices_module.router)
app.include_router(alerts_module.router)
app.include_router(alert_rules_module.router)
app.include_router(push_module.router)
app.include_router(firmware_module.router)
app.include_router(tanks_module.router)
app.include_router(peripherals_module.router)
app.include_router(cleanup_module.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
