"""
Engine de decisions de reg.

Rep un IrrigationContext (lectures, config, historial) i retorna
una IrrigationDecision (regar/no regar, durada, motiu).

No té cap dependència de FastAPI, MQTT, scheduler ni DB.
Tota la lògica de negoci viu aquí.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TriggerType(str, Enum):
    SCHEDULE = "schedule"
    SENSOR = "sensor"
    MANUAL = "manual"


class NoWaterReason(str, Enum):
    HUMIDITY_OK = "humidity_ok"
    COOLDOWN_ACTIVE = "cooldown_active"
    TOO_HOT = "too_hot"
    DISABLED = "disabled"


@dataclass
class SensorReadings:
    soil_humidity_pct: float       # mitjana dels sensors de terra de la zona
    ambient_temp_celsius: Optional[float] = None
    ambient_humidity_pct: Optional[float] = None


@dataclass
class ZoneConfig:
    humidity_min: float            # regar si humitat < humidity_min
    humidity_max: float            # aturar si humitat > humidity_max
    max_temp_to_water: Optional[float] = None
    cooldown_hours: float = 1.0
    active: bool = True


@dataclass
class IrrigationContext:
    zone_id: int
    readings: SensorReadings
    config: ZoneConfig
    trigger: TriggerType
    minutes_since_last_watering: Optional[float] = None
    requested_duration_seconds: Optional[int] = None   # per reg manual


@dataclass
class IrrigationDecision:
    should_water: bool
    duration_seconds: int
    reason: str


def decide(ctx: IrrigationContext) -> IrrigationDecision:
    """Retorna la decisió de reg per a una zona donada el context."""

    if not ctx.config.active:
        return IrrigationDecision(False, 0, NoWaterReason.DISABLED)

    if ctx.trigger == TriggerType.MANUAL:
        duration = ctx.requested_duration_seconds or 60
        return IrrigationDecision(True, duration, TriggerType.MANUAL)

    if _cooldown_active(ctx):
        return IrrigationDecision(False, 0, NoWaterReason.COOLDOWN_ACTIVE)

    if _too_hot(ctx):
        return IrrigationDecision(False, 0, NoWaterReason.TOO_HOT)

    if ctx.readings.soil_humidity_pct >= ctx.config.humidity_min:
        return IrrigationDecision(False, 0, NoWaterReason.HUMIDITY_OK)

    # TODO: ajustar durada en funció del dèficit d'humitat i del tipus de planta
    duration = 120
    return IrrigationDecision(True, duration, ctx.trigger)


def _cooldown_active(ctx: IrrigationContext) -> bool:
    if ctx.minutes_since_last_watering is None:
        return False
    return ctx.minutes_since_last_watering < ctx.config.cooldown_hours * 60


def _too_hot(ctx: IrrigationContext) -> bool:
    if ctx.config.max_temp_to_water is None:
        return False
    if ctx.readings.ambient_temp_celsius is None:
        return False
    return ctx.readings.ambient_temp_celsius > ctx.config.max_temp_to_water
