from datetime import datetime, timezone

from sqlalchemy import Integer, String, Boolean, Float, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

SENSOR_TYPES = ("binary_single", "binary_dual", "ultrasonic", "pressure_adc", "capacitive_adc")


class WaterTank(Base):
    __tablename__ = "water_tanks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    device_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sensor_type: Mapped[str] = mapped_column(String(20), nullable=False, default="binary_single")
    # pin_1: trigger (ultrasonic) / data pin (binary) / ADC pin
    # pin_2: echo (ultrasonic) / top float (binary_dual)
    gpio_pin_1: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gpio_pin_2: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capacity_liters: Mapped[float | None] = mapped_column(Float, nullable=True)
    # For ultrasonic: distance in cm (empty = sensor far from water, full = sensor close)
    # For ADC: raw ADC value
    calibration_empty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    calibration_full: Mapped[int | None] = mapped_column(Integer, nullable=True)
    low_threshold_pct: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    empty_threshold_pct: Mapped[int] = mapped_column(Integer, default=5, nullable=False)


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
