from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models import Program

router = APIRouter(
    prefix="/api/programs",
    tags=["programs"],
    dependencies=[Depends(get_current_user)],
)


class ProgramCreate(BaseModel):
    zone_id: int
    name: str = Field(..., min_length=1, max_length=100)
    active: bool = True
    condition_logic: str = "AND"
    duration_seconds: int = Field(default=120, ge=5, le=3600)
    conditions: list[dict] = []


class ProgramUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    active: bool | None = None
    condition_logic: str | None = None
    duration_seconds: int | None = Field(default=None, ge=5, le=3600)
    conditions: list[dict] | None = None


def _to_dict(p: Program) -> dict:
    return {
        "id": p.id,
        "zone_id": p.zone_id,
        "name": p.name,
        "active": p.active,
        "condition_logic": p.condition_logic,
        "duration_seconds": p.duration_seconds,
        "conditions": p.conditions,
    }


@router.get("/")
async def list_programs(zone_id: int | None = None, db: AsyncSession = Depends(get_db)):
    q = select(Program).order_by(Program.zone_id, Program.id)
    if zone_id is not None:
        q = q.where(Program.zone_id == zone_id)
    result = await db.execute(q)
    return [_to_dict(p) for p in result.scalars().all()]


@router.post("/", status_code=201)
async def create_program(body: ProgramCreate, db: AsyncSession = Depends(get_db)):
    program = Program(
        zone_id=body.zone_id,
        name=body.name,
        active=body.active,
        condition_logic=body.condition_logic,
        duration_seconds=body.duration_seconds,
        conditions=body.conditions,
    )
    db.add(program)
    await db.commit()
    await db.refresh(program)
    return _to_dict(program)


@router.get("/{program_id}")
async def get_program(program_id: int, db: AsyncSession = Depends(get_db)):
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Programa no trobat")
    return _to_dict(program)


@router.put("/{program_id}")
async def update_program(program_id: int, body: ProgramUpdate, db: AsyncSession = Depends(get_db)):
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Programa no trobat")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(program, field, value)
    await db.commit()
    await db.refresh(program)
    return _to_dict(program)


@router.delete("/{program_id}", status_code=204)
async def delete_program(program_id: int, db: AsyncSession = Depends(get_db)):
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Programa no trobat")
    await db.delete(program)
    await db.commit()
