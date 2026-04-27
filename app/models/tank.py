from datetime import datetime, timezone

from sqlalchemy import Integer, String, Boolean, Float, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WaterTank(Base):
    __tablename__ = "water_tanks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    device_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    capacity_liters: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_threshold_pct: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    empty_threshold_pct: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    peripheral_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("peripherals.id", ondelete="SET NULL"), nullable=True
    )


class TankReading(Base):
    __tablename__ = "tank_readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    tank_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("water_tanks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw_value: Mapped[float] = mapped_column(Float, nullable=False)
    level_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    sensor_state: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
