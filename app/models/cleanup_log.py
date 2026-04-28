from datetime import datetime, timezone

from sqlalchemy import Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DataCleanupLog(Base):
    __tablename__ = "data_cleanup_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    before_count: Mapped[int] = mapped_column(Integer, nullable=False)
    after_count: Mapped[int] = mapped_column(Integer, nullable=False)
    deleted_by: Mapped[str] = mapped_column(String(100), nullable=False)
