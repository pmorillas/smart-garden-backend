from sqlalchemy import Integer, String, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

PERIPHERAL_TYPES = (
    "SOIL_ADC",      # Capacitive/resistive soil moisture (ADC1 pin)
    "HTU21D",        # I2C temperature + humidity
    "BH1750",        # I2C light (lux)
    "RELAY",         # Digital output relay (active LOW)
    "HC_SR04",       # Ultrasonic distance (tank level)
    "FLOAT_BINARY",  # Float switch (binary tank level)
    # Future additions — add here without breaking NVS format:
    # "BME280",     # I2C temperature + humidity + pressure
    # "SHT31",      # I2C temperature + humidity (high precision)
    # "SHT40",      # I2C temperature + humidity (high precision)
    # "AHT20",      # I2C temperature + humidity (low cost)
    # "VEML7700",   # I2C ambient light (high range)
    # "RAIN_GAUGE", # Tipping bucket rain gauge (pulse counter)
    # "SOIL_I2C",   # I2C capacitive soil sensor
)

AGGREGATION_MODES = ("AVG", "ANY_BELOW", "ALL_BELOW")


class Peripheral(Base):
    __tablename__ = "peripherals"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    pin1: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pin2: Mapped[int | None] = mapped_column(Integer, nullable=True)
    i2c_address: Mapped[int | None] = mapped_column(Integer, nullable=True)
    i2c_bus: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ZoneSoilSensor(Base):
    """Association between a zone and soil peripheral sensors."""
    __tablename__ = "zone_soil_sensors"

    zone_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("zones.id", ondelete="CASCADE"), primary_key=True
    )
    peripheral_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("peripherals.id", ondelete="CASCADE"), primary_key=True
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
