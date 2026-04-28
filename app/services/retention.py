import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.database import AsyncSessionLocal
from app.services.data_cleanup import cleanup_data

logger = logging.getLogger(__name__)


async def _run_retention() -> None:
    """Delete data older than *data_retention_days* for sensor_readings and
    watering_events. No-op when retention_days <= 0."""
    retention_days = settings.data_retention_days
    if retention_days <= 0:
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    logger.info("Retention policy: running (cutoff=%s, days=%d)", cutoff.isoformat(), retention_days)

    for category in ("sensor_readings", "watering_events"):
        try:
            async with AsyncSessionLocal() as db:
                deleted = await cleanup_data(db, category, cutoff, "system")
            if deleted > 0:
                logger.info("Retention policy: %s — %d rows pruned", category, deleted)
        except Exception:
            logger.exception("Retention policy: error cleaning %s", category)


def start_retention_scheduler() -> None:
    """Schedule _run_retention() every 24 hours, starting in 1 hour."""
    asyncio.get_event_loop().call_later(
        3600,
        lambda: asyncio.create_task(_run_retention()),
    )
    logger.info("Retention policy scheduler started (every 24h, retention=%d days)", retention_days)

