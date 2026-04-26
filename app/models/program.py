from sqlalchemy import Integer, String, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ProgramZone(Base):
    """Relació many-to-many entre Program i Zone."""

    __tablename__ = "program_zones"

    program_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("programs.id", ondelete="CASCADE"), primary_key=True
    )
    zone_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("zones.id", ondelete="CASCADE"), primary_key=True
    )
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_override_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    program: Mapped["Program"] = relationship("Program", back_populates="program_zones")
    zone: Mapped["Zone"] = relationship("Zone", back_populates="program_zones")  # type: ignore[name-defined]


class Program(Base):
    """
    Programa de reg flexible. Les condicions es guarden com a JSONB:

    [
      {"type": "schedule",      "time": "07:00", "days": [1, 3, 5]},
      {"type": "soil_humidity", "operator": "lt", "value": 40},
      {"type": "temperature",   "operator": "lt", "value": 35},
      {"type": "light_lux",     "operator": "gt", "value": 1000},
      {"type": "time_range",    "from": "06:00",  "to": "21:00"}
    ]

    condition_logic: "AND" | "OR"
    execution_mode: "simultaneous" | "sequential"
    """

    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    execution_mode: Mapped[str] = mapped_column(String(20), default="simultaneous", nullable=False)
    condition_logic: Mapped[str] = mapped_column(String(3), default="AND")
    duration_seconds: Mapped[int] = mapped_column(Integer, default=120)
    conditions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    program_zones: Mapped[list["ProgramZone"]] = relationship(
        "ProgramZone", back_populates="program", cascade="all, delete-orphan"
    )
    watering_events: Mapped[list["WateringEvent"]] = relationship("WateringEvent", back_populates="program")  # type: ignore[name-defined]
