from sqlalchemy import Integer, String, Boolean, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    relay_pin_local: Mapped[int | None] = mapped_column(Integer, nullable=True)
    soil_pin_a_local: Mapped[int | None] = mapped_column(Integer, nullable=True)
    soil_pin_b_local: Mapped[int | None] = mapped_column(Integer, nullable=True)
    config_synced: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tank_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("water_tanks.id", ondelete="SET NULL"), nullable=True
    )

    device: Mapped["Device | None"] = relationship("Device", back_populates="zones")  # type: ignore[name-defined]
    config: Mapped["ZoneConfig | None"] = relationship(
        "ZoneConfig", back_populates="zone", uselist=False, cascade="all, delete-orphan"
    )
    sensor_readings: Mapped[list["SensorReading"]] = relationship("SensorReading", back_populates="zone", passive_deletes=True)  # type: ignore[name-defined]
    watering_events: Mapped[list["WateringEvent"]] = relationship("WateringEvent", back_populates="zone", passive_deletes=True)  # type: ignore[name-defined]
    program_zones: Mapped[list["ProgramZone"]] = relationship("ProgramZone", back_populates="zone", cascade="all, delete-orphan", passive_deletes=True)  # type: ignore[name-defined]


class ZoneConfig(Base):
    __tablename__ = "zone_config"

    zone_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("zones.id", ondelete="CASCADE"), primary_key=True
    )
    humidity_min: Mapped[float] = mapped_column(Float, default=30.0)
    humidity_max: Mapped[float] = mapped_column(Float, default=80.0)
    max_temp_to_water: Mapped[float | None] = mapped_column(Float, nullable=True, default=38.0)
    cooldown_hours: Mapped[float] = mapped_column(Float, default=2.0)
    soil_dry_value: Mapped[int] = mapped_column(Integer, default=3800)
    soil_wet_value: Mapped[int] = mapped_column(Integer, default=1200)

    zone: Mapped["Zone"] = relationship("Zone", back_populates="config")
