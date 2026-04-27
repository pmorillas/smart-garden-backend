import asyncio
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import AsyncSessionLocal
from app.irrigation.conditions import evaluate_program
from app.irrigation.actions import trigger_watering
from app.models import Program, ProgramZone, WateringEvent, ZoneConfig, Device
from app.state import garden

logger = logging.getLogger(__name__)

DEVICE_OFFLINE_MINUTES = 30

_scheduler: AsyncIOScheduler | None = None
_running_sequences: set[int] = set()  # program_ids amb seqüència activa
_mqtt_client = None


def set_mqtt_client(client) -> None:
    global _mqtt_client
    _mqtt_client = client


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _check_programs,
        CronTrigger(second=0),
        id="check_programs",
        name="Avaluació de programes",
        replace_existing=True,
    )
    _scheduler.add_job(
        _check_device_offline,
        CronTrigger(minute="*/10"),
        id="check_devices",
        name="Comprovació dispositius offline",
        replace_existing=True,
    )
    _scheduler.add_job(
        _poll_sensors,
        "interval",
        seconds=settings.sensor_poll_interval_seconds,
        id="poll_sensors",
        name="Polling sensors ESP32",
        replace_existing=True,
    )
    _scheduler.add_job(
        _ping_devices,
        "interval",
        seconds=settings.sensor_ping_interval_seconds,
        id="ping_devices",
        name="Ping dispositius",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler iniciat")
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler aturat")


async def _check_programs() -> None:
    now = datetime.now(ZoneInfo(settings.local_tz))

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Program)
            .where(Program.active == True)  # noqa: E712
            .options(selectinload(Program.program_zones))
        )
        programs = result.scalars().all()

    for program in programs:
        try:
            await _evaluate_and_trigger(program, now)
        except Exception:
            logger.exception("Error avaluant programa %s (%s)", program.id, program.name)


async def _check_cooldown(zone_id: int) -> bool:
    """Retorna True si el cooldown ha expirat (es pot regar)."""
    async with AsyncSessionLocal() as db:
        last_result = await db.execute(
            select(WateringEvent)
            .where(WateringEvent.zone_id == zone_id)
            .order_by(WateringEvent.started_at.desc())
            .limit(1)
        )
        last_event = last_result.scalar_one_or_none()
        if last_event is None:
            return True

        cfg_result = await db.execute(
            select(ZoneConfig).where(ZoneConfig.zone_id == zone_id)
        )
        config = cfg_result.scalar_one_or_none()
        if config and config.cooldown_hours > 0:
            elapsed = datetime.now(timezone.utc) - last_event.started_at
            if elapsed < timedelta(hours=config.cooldown_hours):
                return False
    return True


async def _evaluate_and_trigger(program: Program, now: datetime) -> None:
    if not program.program_zones:
        logger.debug("Programa %s (%s): sense zones, saltant", program.id, program.name)
        return

    if program.execution_mode == "sequential" and program.id in _running_sequences:
        return

    soil_humidity = None
    ambient_temp = garden.ambient.temp

    # For condition evaluation, use first zone's humidity as representative
    first_zone_id = program.program_zones[0].zone_id
    first_zone_state = garden.zones.get(first_zone_id)
    if first_zone_state:
        soil_humidity = first_zone_state.soil_humidity_avg

    if not evaluate_program(program, now, soil_humidity, ambient_temp):
        logger.debug(
            "Programa %s (%s): condicions no complides (hora=%s, hum=%.1f, temp=%s)",
            program.id, program.name,
            now.strftime("%H:%M"),
            soil_humidity if soil_humidity is not None else -1,
            ambient_temp,
        )
        return

    # Determine which zones are eligible (not watering + cooldown elapsed)
    eligible: list[tuple[int, int]] = []  # (zone_id, duration_seconds)
    for pz in sorted(program.program_zones, key=lambda x: x.order_index):
        zone_state = garden.zones.get(pz.zone_id)
        if zone_state is None:
            logger.warning("Programa %s: zona %s no trobada en memòria, saltant", program.id, pz.zone_id)
            continue
        if zone_state.is_watering:
            logger.debug("Programa %s: zona %s ja regant, saltant", program.id, pz.zone_id)
            continue
        if not await _check_cooldown(pz.zone_id):
            logger.debug("Zona %s: cooldown actiu, saltant", pz.zone_id)
            continue
        duration = pz.duration_override_seconds or program.duration_seconds
        eligible.append((pz.zone_id, duration))

    if not eligible:
        logger.debug("Programa %s (%s): cap zona elegible", program.id, program.name)
        return

    if program.execution_mode == "simultaneous":
        for zone_id, duration in eligible:
            logger.info("Programa %s (%s) — zona %s: simultani, reg %ds", program.id, program.name, zone_id, duration)
            await trigger_watering(zone_id=zone_id, duration_seconds=duration, trigger_type="schedule", program_id=program.id)

    else:  # sequential
        logger.info("Programa %s (%s): iniciant seqüència amb %d zones", program.id, program.name, len(eligible))
        _running_sequences.add(program.id)
        asyncio.create_task(
            _run_sequential_sequence(program.id, program.name, eligible)
        )


async def _run_sequential_sequence(
    program_id: int,
    program_name: str,
    ordered_zones: list[tuple[int, int]],
) -> None:
    """Executa zones seqüencialment. Continua a la següent si hi ha error transitori."""
    try:
        for zone_id, duration in ordered_zones:
            zone_state = garden.zones.get(zone_id)
            if zone_state is None:
                logger.warning("Sequential prog %s: zona %s no trobada, saltant", program_id, zone_id)
                continue

            try:
                logger.info("Sequential prog %s (%s): zona %s, %ds", program_id, program_name, zone_id, duration)
                await trigger_watering(zone_id=zone_id, duration_seconds=duration, trigger_type="schedule", program_id=program_id)
            except Exception as e:
                logger.warning("Sequential prog %s: error iniciant zona %s: %s, continuant", program_id, zone_id, e)
                continue

            # Espera que la zona acabi (màx duration + 90s buffer)
            timeout_s = duration + 90
            for _ in range(timeout_s // 3):
                await asyncio.sleep(3)
                zs = garden.zones.get(zone_id)
                if zs is None or not zs.is_watering:
                    break

            # Pausa breu entre zones
            await asyncio.sleep(3)
    finally:
        _running_sequences.discard(program_id)
        logger.info("Sequential prog %s: seqüència completada", program_id)


async def _check_device_offline() -> None:
    from app.notifications.push import maybe_create_alert, auto_resolve_alert, get_alert_rule

    rule = await get_alert_rule("device_offline")
    if rule is None:
        return

    offline_minutes = int(rule.threshold) if rule.threshold is not None else DEVICE_OFFLINE_MINUTES
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=offline_minutes)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Device).where(Device.active == True))  # noqa: E712
        devices = result.scalars().all()

    for device in devices:
        if device.last_seen is None:
            continue
        if device.last_seen < cutoff:
            await maybe_create_alert(
                "device_offline",
                f"Dispositiu '{device.name}' ({device.mac_address}) no respon des de fa més de {offline_minutes} min",
                device_id=device.id,
            )
        else:
            await auto_resolve_alert("device_offline", device_id=device.id)


async def _poll_sensors() -> None:
    if _mqtt_client is None:
        return
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Device).where(Device.active == True))  # noqa: E712
        devices = result.scalars().all()
    for device in devices:
        _mqtt_client.publish_sensor_request(device.mac_address)
    logger.debug("Sensor poll enviat a %d dispositius", len(devices))


async def _ping_devices() -> None:
    if _mqtt_client is None:
        return
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Device).where(Device.active == True))  # noqa: E712
        devices = result.scalars().all()
    for device in devices:
        _mqtt_client.publish_ping(device.mac_address)
    logger.debug("Ping enviat a %d dispositius", len(devices))
