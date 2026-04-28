import logging
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SensorReading, WateringEvent, DataCleanupLog

logger = logging.getLogger(__name__)

VALID_CATEGORIES = ("sensor_readings", "watering_events")


async def cleanup_data(
    db: AsyncSession,
    category: str,
    older_than: datetime,
    deleted_by: str,
) -> int:
    """Delete historical data older than *older_than* and log the operation.

    Returns the number of deleted rows.
    """
    if category not in VALID_CATEGORIES:
        raise ValueError(f"Category must be one of {VALID_CATEGORIES}")

    if category == "sensor_readings":
        model = SensorReading
        time_col = SensorReading.timestamp
    elif category == "watering_events":
        model = WateringEvent
        time_col = WateringEvent.started_at
    else:
        raise NotImplementedError

    before_result = await db.execute(select(func.count()).select_from(model))
    before_count = before_result.scalar()

    stmt = select(func.count()).select_from(model).where(time_col < older_than)
    count_result = await db.execute(stmt)
    to_delete = count_result.scalar()

    if to_delete == 0:
        logger.info("Cleanup %s: no rows older than %s", category, older_than.isoformat())
        await db.flush()
        return 0

    await db.execute(model.__table__.delete().where(time_col < older_than))
    await db.flush()

    after_result = await db.execute(select(func.count()).select_from(model))
    after_count = after_result.scalar()

    log_entry = DataCleanupLog(
        category=category,
        before_count=before_count,
        after_count=after_count,
        deleted_by=deleted_by,
    )
    db.add(log_entry)
    await db.flush()

    logger.info(
        "Cleanup %s: deleted %d rows (before=%d, after=%d, cutoff=%s, by=%s)",
        category, to_delete, before_count, after_count, older_than.isoformat(), deleted_by,
    )

    return to_delete
