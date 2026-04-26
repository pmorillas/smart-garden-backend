import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_current_user
from app.database import get_db
from app.models import Device
from app.models.firmware import FirmwareRelease, FirmwareUpdate

logger = logging.getLogger(__name__)

FIRMWARE_DIR = Path("uploads/firmware")

_mqtt_client = None


def set_mqtt_client(client) -> None:
    global _mqtt_client
    _mqtt_client = client


router = APIRouter(prefix="/api/firmware", tags=["firmware"])

auth = Depends(get_current_user)


@router.post("/", status_code=201, dependencies=[auth])
async def upload_firmware(
    version: str = Form(...),
    notes: str | None = Form(default=None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(FirmwareRelease).where(FirmwareRelease.version == version))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Versió {version} ja existeix")

    content = await file.read()
    checksum = hashlib.sha256(content).hexdigest()
    filename = f"firmware_{version}.bin"

    FIRMWARE_DIR.mkdir(parents=True, exist_ok=True)
    (FIRMWARE_DIR / filename).write_bytes(content)

    release = FirmwareRelease(
        version=version,
        filename=filename,
        checksum_sha256=checksum,
        size_bytes=len(content),
        notes=notes,
    )
    db.add(release)
    await db.commit()
    await db.refresh(release)
    logger.info("Firmware pujat: v%s (%d bytes, sha256=%s...)", version, len(content), checksum[:12])
    return _release_dict(release)


@router.get("/", dependencies=[auth])
async def list_firmware(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FirmwareRelease).order_by(FirmwareRelease.created_at.desc()))
    return [_release_dict(r) for r in result.scalars().all()]


@router.get("/{firmware_id}/download")
async def download_firmware(firmware_id: int, db: AsyncSession = Depends(get_db)):
    """Sense autenticació — accessible des de l'ESP32."""
    release = await db.get(FirmwareRelease, firmware_id)
    if release is None:
        raise HTTPException(status_code=404, detail="Firmware no trobat")
    filepath = FIRMWARE_DIR / release.filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Fitxer no trobat al servidor")
    return FileResponse(filepath, media_type="application/octet-stream", filename=release.filename)


@router.post("/{firmware_id}/deploy", status_code=202, dependencies=[auth])
async def deploy_firmware(
    firmware_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    Desplega el firmware a un dispositiu específic o a tots els actius.
    Body: {"device_id": int}  o  {} per a tots els dispositius actius.
    """
    if _mqtt_client is None:
        raise HTTPException(status_code=503, detail="MQTT no disponible")

    release = await db.get(FirmwareRelease, firmware_id)
    if release is None:
        raise HTTPException(status_code=404, detail="Firmware no trobat")

    device_id = body.get("device_id")
    if device_id is not None:
        result = await db.execute(select(Device).where(Device.id == device_id))
        devices = [result.scalar_one_or_none()]
        if devices[0] is None:
            raise HTTPException(status_code=404, detail="Dispositiu no trobat")
    else:
        result = await db.execute(select(Device).where(Device.active == True))  # noqa: E712
        devices = list(result.scalars().all())

    url = f"{settings.ota_base_url}/api/firmware/{release.id}/download"
    updates = []
    for device in devices:
        update = FirmwareUpdate(device_id=device.id, release_id=release.id, status="pending")
        db.add(update)
        await db.flush()
        _mqtt_client.publish_ota_update(device.mac_address, url, release.version, release.checksum_sha256)
        updates.append({"device_id": device.id, "update_id": update.id})
        logger.info("OTA iniciat: device=%s v%s url=%s", device.mac_address, release.version, url)

    await db.commit()
    return {"firmware_version": release.version, "dispatched": updates}


@router.get("/updates/recent", dependencies=[auth])
async def list_recent_updates(limit: int = 20, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(FirmwareUpdate).order_by(FirmwareUpdate.started_at.desc()).limit(limit)
    )
    return [_update_dict(u) for u in result.scalars().all()]


@router.get("/devices/{device_id}/status", dependencies=[auth])
async def get_device_ota_status(device_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(FirmwareUpdate)
        .where(FirmwareUpdate.device_id == device_id)
        .order_by(FirmwareUpdate.started_at.desc())
        .limit(10)
    )
    return [_update_dict(u) for u in result.scalars().all()]


def _release_dict(r: FirmwareRelease) -> dict:
    return {
        "id": r.id,
        "version": r.version,
        "checksum_sha256": r.checksum_sha256,
        "size_bytes": r.size_bytes,
        "notes": r.notes,
        "created_at": r.created_at.isoformat(),
    }


def _update_dict(u: FirmwareUpdate) -> dict:
    return {
        "id": u.id,
        "device_id": u.device_id,
        "release_id": u.release_id,
        "status": u.status,
        "started_at": u.started_at.isoformat(),
        "completed_at": u.completed_at.isoformat() if u.completed_at else None,
        "error_message": u.error_message,
    }
