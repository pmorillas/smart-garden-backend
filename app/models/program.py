from sqlalchemy import Integer, String, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


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
    """

    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(primary_key=True)
    zone_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("zones.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    condition_logic: Mapped[str] = mapped_column(String(3), default="AND")
    duration_seconds: Mapped[int] = mapped_column(Integer, default=120)
    conditions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    zone: Mapped["Zone"] = relationship("Zone", back_populates="programs")  # type: ignore[name-defined]
    watering_events: Mapped[list["WateringEvent"]] = relationship("WateringEvent", back_populates="program")  # type: ignore[name-defined]
