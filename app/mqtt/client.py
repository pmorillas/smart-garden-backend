"""
Client MQTT per comunicar-se amb l'ESP32.

Subscrit a:
  smartgarden/sensors/soil/{zone_id}
  smartgarden/sensors/ambient

Publica a:
  smartgarden/control/{zone_id}
  smartgarden/config/push
"""

import json
import logging

import paho.mqtt.client as mqtt

from app.config import settings

logger = logging.getLogger(__name__)


class MqttClient:
    def __init__(self):
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

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("MQTT connectat")
            client.subscribe("smartgarden/sensors/soil/#")
            client.subscribe("smartgarden/sensors/ambient")
        else:
            logger.error("MQTT error connexió: %s", reason_code)

    def _on_message(self, client, userdata, msg):
        # TODO: parseja el missatge i desa la lectura a la DB
        logger.debug("MQTT rebut: %s -> %s", msg.topic, msg.payload)
