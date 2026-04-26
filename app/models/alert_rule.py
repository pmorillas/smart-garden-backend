from sqlalchemy import Integer, String, Boolean, Float, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

ALERT_TYPES = (
    "humidity_low",
    "device_offline",
    "water_completed",
    "water_failed",
    "sensor_error",
)


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    zone_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("zones.id", ondelete="CASCADE"), nullable=True
    )
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    notification_channels: Mapped[list] = mapped_column(JSON, nullable=False, default=lambda: ["push"])
