from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.deps import get_current_user
from app.database import get_db
from app.models import User
from app.services.data_cleanup import cleanup_data, VALID_CATEGORIES
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(
    prefix="/api/data",
    tags=["data"],
    dependencies=[Depends(get_current_user)],
)


class CleanupRequest(BaseModel):
    category: str = Field(..., description="Data category to clean up")
    older_than: str = Field(
        ...,
        description="ISO 8601 timestamp (UTC). Rows older than this will be deleted.",
    )


class CleanupResponse(BaseModel):
    deleted_count: int


@router.delete("/cleanup", response_model=CleanupResponse)
async def cleanup_history(
    body: CleanupRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete historical data older than a given timestamp.

    Categories: ``sensor_readings``, ``watering_events``.
    """
    if body.category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Category must be one of {VALID_CATEGORIES}",
        )

    try:
        older_than = datetime.fromisoformat(body.older_than)
        if older_than.tzinfo is None:
            older_than = older_than.replace(tzinfo=datetime.now().astimezone().tzinfo)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ISO 8601 timestamp format")

    deleted = await cleanup_data(db, body.category, older_than, user.username)
    await db.commit()

    return CleanupResponse(deleted_count=deleted)
