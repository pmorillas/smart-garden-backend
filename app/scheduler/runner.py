import logging
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.irrigation.conditions import evaluate_program
from app.irrigation.actions import trigger_watering
from app.models import Program, WateringEvent, ZoneConfig, Device
from app.state import garden

logger = logging.getLogger(__name__)

DEVICE_OFFLINE_MINUTES = 30

_scheduler: AsyncIOScheduler | None = None


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
    _scheduler.start()
    logger.info("Scheduler iniciat")
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler aturat")


async def _check_programs() -> None:
    now = datetime.now()  # local time — users configure schedules in local time

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Program).where(Program.active == True))  # noqa: E712
        programs = result.scalars().all()

    for program in programs:
        try:
            await _evaluate_and_trigger(program, now)
        except Exception:
            logger.exception("Error avaluant programa %s (%s)", program.id, program.name)


async def _evaluate_and_trigger(program, now: datetime) -> None:
    zone = garden.zones.get(program.zone_id)
    if zone is None or zone.is_watering:
        return

    soil_humidity = zone.soil_humidity_avg
    ambient_temp = garden.ambient.temp

    if not evaluate_program(program, now, soil_humidity, ambient_temp):
        return

    async with AsyncSessionLocal() as db:
        last_result = await db.execute(
            select(WateringEvent)
            .where(WateringEvent.zone_id == program.zone_id)
            .order_by(WateringEvent.started_at.desc())
            .limit(1)
        )
        last_event = last_result.scalar_one_or_none()

        if last_event is not None:
            cfg_result = await db.execute(
                select(ZoneConfig).where(ZoneConfig.zone_id == program.zone_id)
            )
            config = cfg_result.scalar_one_or_none()
            if config and config.cooldown_hours > 0:
                elapsed = datetime.now(timezone.utc) - last_event.started_at
                if elapsed < timedelta(hours=config.cooldown_hours):
                    remaining_h = (timedelta(hours=config.cooldown_hours) - elapsed).total_seconds() / 3600
                    logger.debug(
                        "Zona %s: cooldown actiu (%.1fh restants)",
                        program.zone_id, remaining_h,
                    )
                    return

    logger.info(
        "Programa %s (%s) — zona %s: condicions complides, iniciant reg %ds",
        program.id, program.name, program.zone_id, program.duration_seconds,
    )
    await trigger_watering(
        zone_id=program.zone_id,
        duration_seconds=program.duration_seconds,
        trigger_type="schedule",
        program_id=program.id,
    )


async def _check_device_offline() -> None:
    from app.notifications.push import create_alert, has_active_alert, auto_resolve_alert

    threshold = datetime.now(timezone.utc) - timedelta(minutes=DEVICE_OFFLINE_MINUTES)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Device).where(Device.active == True))  # noqa: E712
        devices = result.scalars().all()

    for device in devices:
        if device.last_seen is None:
            continue
        is_offline = device.last_seen < threshold
        if is_offline:
            if not await has_active_alert("device_offline", device_id=device.id):
                await create_alert(
                    "device_offline",
                    f"Dispositiu '{device.name}' ({device.mac_address}) no respon des de fa més de {DEVICE_OFFLINE_MINUTES} min",
                    device_id=device.id,
                )
        else:
            await auto_resolve_alert("device_offline", device_id=device.id)
