"""
Client MQTT per comunicar-se amb l'ESP32.

Subscrit a:
  smartgarden/sensors/soil/{zone_id}
  smartgarden/sensors/ambient
  smartgarden/devices/register

Publica a:
  smartgarden/control/{zone_id}
  smartgarden/config/push
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from app.config import settings
from app.state import garden, ws_manager

logger = logging.getLogger(__name__)


async def _persist_soil_reading(zone_id: int, value: float, timestamp: datetime) -> None:
    from app.database import AsyncSessionLocal
    from app.models import SensorReading

    async with AsyncSessionLocal() as db:
        db.add(SensorReading(zone_id=zone_id, sensor_type="soil_humidity", value=value, timestamp=timestamp))
        await db.commit()


async def _persist_ambient_readings(
    temp: float | None,
    humidity: float | None,
    light_lux: float | None,
    timestamp: datetime,
) -> None:
    from app.database import AsyncSessionLocal
    from app.models import SensorReading

    async with AsyncSessionLocal() as db:
        if temp is not None:
            db.add(SensorReading(sensor_type="ambient_temperature", value=temp, timestamp=timestamp))
        if humidity is not None:
            db.add(SensorReading(sensor_type="ambient_humidity", value=humidity, timestamp=timestamp))
        if light_lux is not None:
            db.add(SensorReading(sensor_type="light_lux", value=light_lux, timestamp=timestamp))
        await db.commit()


async def _handle_device_register(payload: dict, mqtt_client: "MqttClient | None" = None) -> None:
    from app.database import AsyncSessionLocal
    from app.models import Device, Zone
    from sqlalchemy import select

    mac = payload.get("mac")
    if not mac:
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Device).where(Device.mac_address == mac))
        device = result.scalar_one_or_none()
        if device is None:
            short = mac.replace(":", "")[-6:]
            device = Device(mac_address=mac, name=f"ESP32-{short}")
            db.add(device)
            logger.info("Nou dispositiu registrat: %s", mac)
        device.last_seen = datetime.now(timezone.utc)
        if payload.get("firmware"):
            device.firmware_version = payload["firmware"]
        await db.commit()
        logger.info("Dispositiu actualitzat: %s IP=%s FW=%s", mac, payload.get("ip", "?"), payload.get("firmware", "?"))

        if mqtt_client is not None:
            zones_result = await db.execute(select(Zone).where(Zone.device_id == device.id))
            zones = zones_result.scalars().all()
            unsynced = [z for z in zones if not z.config_synced]
            if unsynced:
                config = [
                    {
                        "id": z.id,
                        "relay_pin": z.relay_pin_local,
                        "soil_pin_a": z.soil_pin_a_local,
                        "soil_pin_b": z.soil_pin_b_local,
                    }
                    for z in zones
                ]
                mqtt_client.publish_zone_config(mac, config)
                logger.info("Zone config empesa a %s en registrar: %d zones pendents", mac, len(unsynced))
            else:
                logger.debug("Zone config ja sincronitzada a %s, no s'empeny", mac)

            from app.models.tank import WaterTank
            tanks_result = await db.execute(
                select(WaterTank).where(WaterTank.device_id == device.id, WaterTank.active == True)  # noqa: E712
            )
            tanks = tanks_result.scalars().all()
            if tanks and mac not in mqtt_client._tank_config_synced:
                tank_config = [
                    {
                        "id": t.id,
                        "sensor_type": t.sensor_type,
                        "pin_1": t.gpio_pin_1,
                        "pin_2": t.gpio_pin_2,
                        "cal_empty": t.calibration_empty,
                        "cal_full": t.calibration_full,
                        "low_pct": t.low_threshold_pct,
                        "empty_pct": t.empty_threshold_pct,
                    }
                    for t in tanks
                ]
                mqtt_client.publish_tank_config(mac, tank_config)
                mqtt_client._tank_config_synced.add(mac)
                logger.info("Tank config empesa a %s en registrar: %d tanks", mac, len(tanks))
            elif tanks:
                logger.debug("Tank config ja sincronitzada a %s, no s'empeny", mac)


async def _handle_ota_status(payload: dict) -> None:
    from app.database import AsyncSessionLocal
    from app.models import Device
    from app.models.firmware import FirmwareUpdate, FirmwareRelease
    from sqlalchemy import select

    mac = payload.get("mac")
    status = payload.get("status")
    version = payload.get("version")
    error = payload.get("error")

    if not mac or not status:
        return

    async with AsyncSessionLocal() as db:
        device_result = await db.execute(select(Device).where(Device.mac_address == mac))
        device = device_result.scalar_one_or_none()
        if device is None:
            return

        release_result = await db.execute(
            select(FirmwareRelease).where(FirmwareRelease.version == version)
        ) if version else None
        release = release_result.scalar_one_or_none() if release_result else None

        update_query = (
            select(FirmwareUpdate)
            .where(FirmwareUpdate.device_id == device.id)
            .order_by(FirmwareUpdate.started_at.desc())
        )
        if release:
            update_query = update_query.where(FirmwareUpdate.release_id == release.id)
        update_result = await db.execute(update_query.limit(1))
        update = update_result.scalar_one_or_none()

        if update:
            update.status = status
            if status in ("success", "failed"):
                from datetime import datetime, timezone
                update.completed_at = datetime.now(timezone.utc)
            if error:
                update.error_message = error
            await db.commit()

    logger.info("OTA status rebut: MAC=%s status=%s v=%s error=%s", mac, status, version, error)


async def _persist_tank_reading(tank_id: int, raw_value: float, level_percent: float | None, sensor_state: str, timestamp: datetime) -> None:
    from app.database import AsyncSessionLocal
    from app.models.tank import TankReading

    async with AsyncSessionLocal() as db:
        db.add(TankReading(
            tank_id=tank_id,
            raw_value=raw_value,
            level_percent=level_percent,
            sensor_state=sensor_state,
            timestamp=timestamp,
        ))
        await db.commit()


async def _check_tank_alerts(tank_id: int, sensor_state: str, level_percent: float | None) -> None:
    from app.notifications.push import maybe_create_alert, auto_resolve_alert, get_alert_rule

    tank = garden.tanks.get(tank_id)
    if tank is None:
        return

    if tank.is_empty():
        rule = await get_alert_rule("tank_empty")
        if rule is not None:
            await maybe_create_alert(
                "tank_empty",
                f"Dipòsit {tank.name} buit",
            )
        await auto_resolve_alert("tank_low")
    else:
        await auto_resolve_alert("tank_empty")
        if level_percent is not None and level_percent <= tank.low_threshold_pct:
            rule = await get_alert_rule("tank_low")
            if rule is not None:
                await maybe_create_alert(
                    "tank_low",
                    f"Dipòsit {tank.name} baix ({level_percent:.0f}%)",
                )
        else:
            await auto_resolve_alert("tank_low")


async def _check_humidity_alert(zone_id: int, humidity_pct: float) -> None:
    from sqlalchemy import select as sa_select
    from app.database import AsyncSessionLocal
    from app.models import ZoneConfig
    from app.notifications.push import maybe_create_alert, auto_resolve_alert, get_alert_rule

    rule = await get_alert_rule("humidity_low", zone_id=zone_id)
    if rule is None:
        return

    threshold = rule.threshold
    if threshold is None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(sa_select(ZoneConfig).where(ZoneConfig.zone_id == zone_id))
            config = result.scalar_one_or_none()
            threshold = config.humidity_min if config else 30.0

    if humidity_pct < threshold:
        await maybe_create_alert(
            "humidity_low",
            f"Zona {zone_id}: humitat de terra molt baixa ({humidity_pct:.0f}% < {threshold:.0f}%)",
            zone_id=zone_id,
        )
    else:
        await auto_resolve_alert("humidity_low", zone_id=zone_id)


async def _handle_zone_config_ack(payload: dict, topic: str) -> None:
    if payload.get("config") != "zones":
        return
    mac = topic.rsplit("/", 1)[-1]
    status = payload.get("status")

    from app.database import AsyncSessionLocal
    from app.models import Device, Zone
    from sqlalchemy import select, update

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Device).where(Device.mac_address == mac))
        device = result.scalar_one_or_none()
        if device is None:
            return
        synced = status == "stored"
        await db.execute(
            update(Zone).where(Zone.device_id == device.id).values(config_synced=synced)
        )
        await db.commit()
        logger.info("Zone config ACK de %s: %s → config_synced=%s", mac, status, synced)


async def _update_device_last_seen(mac: str) -> None:
    from app.database import AsyncSessionLocal
    from app.models import Device
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Device).where(Device.mac_address == mac))
        device = result.scalar_one_or_none()
        if device:
            device.last_seen = datetime.now(timezone.utc)
            await db.commit()


class MqttClient:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._ping_sent_at: dict[str, float] = {}
        self._tank_config_synced: set[str] = set()  # MACs amb tank config ja sincronitzada

    def connect(self):
        self._client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=60)
        self._client.loop_start()

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()

    def publish_control(self, zone_id: int, action: str, duration_seconds: int):
        payload = json.dumps({"action": action, "duration_seconds": duration_seconds})
        self._client.publish(f"smartgarden/control/{zone_id}", payload)

    def publish_config(self, payload: dict):
        self._client.publish("smartgarden/config/push", json.dumps(payload))

    def publish_ota_update(self, mac: str, url: str, version: str, checksum_sha256: str):
        payload = json.dumps({"version": version, "url": url, "checksum": checksum_sha256})
        self._client.publish(f"smartgarden/ota/{mac}", payload)
        logger.info("OTA publicat a %s: v%s", mac, version)

    def invalidate_tank_config(self, mac: str) -> None:
        """Marca el tank config com a pendent de re-sincronitzar al proper register."""
        self._tank_config_synced.discard(mac)

    def publish_sensor_request(self, mac: str) -> None:
        self._client.publish(f"smartgarden/sensors/request/{mac}", "{}")
        logger.debug("Sensor request enviat a %s", mac)

    def publish_ping(self, mac: str) -> None:
        self._ping_sent_at[mac] = time.time()
        self._client.publish(f"smartgarden/ping/{mac}", "{}")
        logger.debug("Ping enviat a %s", mac)

    def publish_zone_config(self, device_mac: str, zones: list[dict]) -> None:
        payload = json.dumps({"zones": zones})
        self._client.publish(f"smartgarden/config/zones/{device_mac}", payload)
        logger.info("Zone config publicada a %s (%d zones)", device_mac, len(zones))

    def publish_tank_config(self, device_mac: str, tanks: list[dict]) -> None:
        payload = json.dumps({"tanks": tanks})
        self._client.publish(f"smartgarden/config/tanks/{device_mac}", payload)
        logger.info("Tank config publicada a %s (%d tanks)", device_mac, len(tanks))

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("MQTT connectat")
            client.subscribe("smartgarden/sensors/soil/#")
            client.subscribe("smartgarden/sensors/ambient")
            client.subscribe("smartgarden/sensors/tank/#")
            client.subscribe("smartgarden/devices/register")
            client.subscribe("smartgarden/devices/ota_status")
            client.subscribe("smartgarden/devices/ack/#")
            client.subscribe("smartgarden/pong/#")
        else:
            logger.error("MQTT error connexió: %s", reason_code)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload)
            logger.debug("MQTT rebut: %s -> %s", msg.topic, payload)
            self._dispatch(msg.topic, payload)
        except Exception:
            logger.exception("Error processant missatge MQTT: %s", msg.topic)

    def _dispatch(self, topic: str, payload: dict):
        if topic == "smartgarden/devices/register":
            asyncio.run_coroutine_threadsafe(
                _handle_device_register(payload, self), self._loop
            )
            return

        if topic.startswith("smartgarden/devices/ack/"):
            asyncio.run_coroutine_threadsafe(
                _handle_zone_config_ack(payload, topic), self._loop
            )
            return

        if topic.startswith("smartgarden/pong/"):
            mac = topic.split("/")[-1]
            sent_at = self._ping_sent_at.pop(mac, None)
            latency_ms = round((time.time() - sent_at) * 1000, 1) if sent_at is not None else None
            device = garden.devices.get(mac)
            if device:
                device.last_pong_at = datetime.now(timezone.utc).isoformat()
                device.ping_latency_ms = latency_ms
            logger.debug("Pong de %s: latència=%.1fms", mac, latency_ms or -1)
            return

        if topic == "smartgarden/devices/ota_status":
            asyncio.run_coroutine_threadsafe(
                _handle_ota_status(payload), self._loop
            )
            return

        garden.touch()
        now = datetime.now(timezone.utc)
        mac = payload.get("mac")

        if topic == "smartgarden/sensors/ambient":
            temp = payload.get("temp")
            humidity = payload.get("humidity")
            light_lux = payload.get("light_lux")

            garden.ambient.temp = temp
            garden.ambient.humidity = humidity
            garden.ambient.light_lux = light_lux

            asyncio.run_coroutine_threadsafe(
                _persist_ambient_readings(temp, humidity, light_lux, now),
                self._loop,
            )
            if mac:
                asyncio.run_coroutine_threadsafe(
                    _update_device_last_seen(mac), self._loop
                )

        elif topic.startswith("smartgarden/sensors/soil/"):
            try:
                zone_id = int(topic.rsplit("/", 1)[-1])
            except ValueError:
                return

            zone = garden.zones.get(zone_id)
            if zone is None:
                return

            values = payload.get("values")
            if isinstance(values, list) and values:
                avg = sum(values) / len(values)
            elif "humidity_pct" in payload:
                avg = payload["humidity_pct"]
            else:
                return

            zone.soil_humidity_avg = avg

            asyncio.run_coroutine_threadsafe(
                _persist_soil_reading(zone_id, avg, now), self._loop
            )
            asyncio.run_coroutine_threadsafe(
                _check_humidity_alert(zone_id, avg), self._loop
            )
            if mac:
                asyncio.run_coroutine_threadsafe(
                    _update_device_last_seen(mac), self._loop
                )

        elif topic.startswith("smartgarden/sensors/tank/"):
            try:
                tank_id = int(topic.rsplit("/", 1)[-1])
            except ValueError:
                return

            tank = garden.tanks.get(tank_id)
            if tank is None:
                return

            raw_value = payload.get("raw_value")
            if raw_value is None:
                return

            level_percent = payload.get("level_pct")
            sensor_state = payload.get("state", "ok")

            tank.level_percent = level_percent
            tank.sensor_state = sensor_state
            tank.last_reading_at = now.isoformat()

            asyncio.run_coroutine_threadsafe(
                _persist_tank_reading(tank_id, raw_value, level_percent, sensor_state, now),
                self._loop,
            )
            asyncio.run_coroutine_threadsafe(
                _check_tank_alerts(tank_id, sensor_state, level_percent), self._loop
            )
            if mac:
                asyncio.run_coroutine_threadsafe(
                    _update_device_last_seen(mac), self._loop
                )

        asyncio.run_coroutine_threadsafe(
            ws_manager.broadcast(garden.to_dict()), self._loop
        )
