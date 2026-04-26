"""
Estat en memòria del jardí i gestor de connexions WebSocket.

Singleton compartit entre el client MQTT i el router WS.
Actua com a cache en temps real; la persistència és a PostgreSQL.
"""

import json
from datetime import datetime, timezone
from typing import Optional, Set

from fastapi import WebSocket


class ZoneStatus:
    def __init__(self, zone_id: int, name: str = ""):
        self.id = zone_id
        self.name = name
        self.soil_humidity_avg: Optional[float] = None
        self.is_watering: bool = False
        self.last_watered_at: Optional[str] = None
        self.active_event_id: Optional[int] = None  # ID del WateringEvent actiu a DB

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "soil_humidity_avg": self.soil_humidity_avg,
            "is_watering": self.is_watering,
            "last_watered_at": self.last_watered_at,
        }


class AmbientStatus:
    def __init__(self):
        self.temp: Optional[float] = None
        self.humidity: Optional[float] = None
        self.light_lux: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "temp": self.temp,
            "humidity": self.humidity,
            "light_lux": self.light_lux,
        }


class GardenState:
    def __init__(self):
        self.zones: dict[int, ZoneStatus] = {}  # populat des de DB a l'arrencada
        self.ambient = AmbientStatus()
        self.updated_at: Optional[str] = None

    def touch(self):
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "zones": [z.to_dict() for z in self.zones.values()],
            "ambient": self.ambient.to_dict(),
            "updated_at": self.updated_at,
        }


class ConnectionManager:
    def __init__(self):
        self._connections: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket):
        self._connections.discard(ws)

    async def broadcast(self, data: dict):
        if not self._connections:
            return
        payload = json.dumps(data)
        dead: Set[WebSocket] = set()
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._connections.discard(ws)


# Singletons globals
garden = GardenState()
ws_manager = ConnectionManager()
