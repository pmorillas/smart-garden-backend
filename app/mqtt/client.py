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


async def _handle_device_register(payload: dict) -> None:
    from app.database import AsyncSessionLocal
    from app.models import Device
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


async def _check_humidity_alert(zone_id: int, humidity_pct: float) -> None:
    from sqlalchemy import select as sa_select
    from app.database import AsyncSessionLocal
    from app.models import ZoneConfig
    from app.notifications.push import create_alert, has_active_alert, auto_resolve_alert

    async with AsyncSessionLocal() as db:
        result = await db.execute(sa_select(ZoneConfig).where(ZoneConfig.zone_id == zone_id))
        config = result.scalar_one_or_none()

    threshold = config.humidity_min if config else 30.0

    if humidity_pct < threshold:
        if not await has_active_alert("humidity_low", zone_id=zone_id):
            await create_alert(
                "humidity_low",
                f"Zona {zone_id}: humitat de terra molt baixa ({humidity_pct:.0f}% < {threshold:.0f}%)",
                zone_id=zone_id,
            )
    else:
        await auto_resolve_alert("humidity_low", zone_id=zone_id)


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

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("MQTT connectat")
            client.subscribe("smartgarden/sensors/soil/#")
            client.subscribe("smartgarden/sensors/ambient")
            client.subscribe("smartgarden/devices/register")
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
                _handle_device_register(payload), self._loop
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

        asyncio.run_coroutine_threadsafe(
            ws_manager.broadcast(garden.to_dict()), self._loop
        )
