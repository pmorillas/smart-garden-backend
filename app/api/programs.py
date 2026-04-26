from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user
from app.database import get_db
from app.models import Program, ProgramZone, Zone

router = APIRouter(
    prefix="/api/programs",
    tags=["programs"],
    dependencies=[Depends(get_current_user)],
)


class ProgramZoneInput(BaseModel):
    zone_id: int
    order_index: int = 0
    duration_override_seconds: int | None = Field(default=None, ge=5, le=3600)


class ProgramCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    active: bool = True
    execution_mode: str = "simultaneous"
    condition_logic: str = "AND"
    duration_seconds: int = Field(default=120, ge=5, le=3600)
    conditions: list[dict] = []
    zones: list[ProgramZoneInput] = []


class ProgramUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    active: bool | None = None
    execution_mode: str | None = None
    condition_logic: str | None = None
    duration_seconds: int | None = Field(default=None, ge=5, le=3600)
    conditions: list[dict] | None = None
    zones: list[ProgramZoneInput] | None = None


def _to_dict(p: Program) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "active": p.active,
        "execution_mode": p.execution_mode,
        "condition_logic": p.condition_logic,
        "duration_seconds": p.duration_seconds,
        "conditions": p.conditions,
        "zones": [
            {
                "zone_id": pz.zone_id,
                "order_index": pz.order_index,
                "duration_override_seconds": pz.duration_override_seconds,
            }
            for pz in sorted(p.program_zones, key=lambda x: x.order_index)
        ],
    }


@router.get("/")
async def list_programs(zone_id: int | None = None, db: AsyncSession = Depends(get_db)):
    q = (
        select(Program)
        .options(selectinload(Program.program_zones))
        .order_by(Program.id)
    )
    result = await db.execute(q)
    programs = result.scalars().all()

    if zone_id is not None:
        programs = [p for p in programs if any(pz.zone_id == zone_id for pz in p.program_zones)]

    return [_to_dict(p) for p in programs]


@router.post("/", status_code=201)
async def create_program(body: ProgramCreate, db: AsyncSession = Depends(get_db)):
    if body.execution_mode not in ("simultaneous", "sequential"):
        raise HTTPException(status_code=422, detail="execution_mode ha de ser 'simultaneous' o 'sequential'")

    program = Program(
        name=body.name,
        active=body.active,
        execution_mode=body.execution_mode,
        condition_logic=body.condition_logic,
        duration_seconds=body.duration_seconds,
        conditions=body.conditions,
    )
    db.add(program)
    await db.flush()

    for z_input in body.zones:
        db.add(ProgramZone(
            program_id=program.id,
            zone_id=z_input.zone_id,
            order_index=z_input.order_index,
            duration_override_seconds=z_input.duration_override_seconds,
        ))

    await db.commit()
    await db.refresh(program)

    result = await db.execute(
        select(Program).options(selectinload(Program.program_zones)).where(Program.id == program.id)
    )
    program = result.scalar_one()
    return _to_dict(program)


@router.get("/{program_id}")
async def get_program(program_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Program).options(selectinload(Program.program_zones)).where(Program.id == program_id)
    )
    program = result.scalar_one_or_none()
    if program is None:
        raise HTTPException(status_code=404, detail="Programa no trobat")
    return _to_dict(program)


@router.put("/{program_id}")
async def update_program(program_id: int, body: ProgramUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Program).options(selectinload(Program.program_zones)).where(Program.id == program_id)
    )
    program = result.scalar_one_or_none()
    if program is None:
        raise HTTPException(status_code=404, detail="Programa no trobat")

    if body.execution_mode is not None and body.execution_mode not in ("simultaneous", "sequential"):
        raise HTTPException(status_code=422, detail="execution_mode ha de ser 'simultaneous' o 'sequential'")

    for field in ("name", "active", "execution_mode", "condition_logic", "duration_seconds", "conditions"):
        val = getattr(body, field)
        if val is not None:
            setattr(program, field, val)

    if body.zones is not None:
        for pz in list(program.program_zones):
            await db.delete(pz)
        await db.flush()
        for z_input in body.zones:
            db.add(ProgramZone(
                program_id=program.id,
                zone_id=z_input.zone_id,
                order_index=z_input.order_index,
                duration_override_seconds=z_input.duration_override_seconds,
            ))

    await db.commit()

    result = await db.execute(
        select(Program).options(selectinload(Program.program_zones)).where(Program.id == program_id)
    )
    program = result.scalar_one()
    return _to_dict(program)


@router.delete("/{program_id}", status_code=204)
async def delete_program(program_id: int, db: AsyncSession = Depends(get_db)):
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Programa no trobat")
    await db.delete(program)
    await db.commit()
