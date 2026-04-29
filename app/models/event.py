from datetime import datetime, timezone

from sqlalchemy import Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

TRIGGER_TYPES = ("manual", "schedule", "sensor")


class WateringEvent(Base):
    __tablename__ = "watering_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    zone_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("zones.id", ondelete="CASCADE"), nullable=False
    )
    program_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("programs.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    skip_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    zone: Mapped["Zone"] = relationship("Zone", back_populates="watering_events")  # type: ignore[name-defined]
    program: Mapped["Program | None"] = relationship("Program", back_populates="watering_events")  # type: ignore[name-defined]
