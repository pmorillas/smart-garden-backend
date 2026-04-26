# Smart Garden — Backend

## Stack

- **Runtime:** Python 3.12+
- **Framework:** FastAPI (async)
- **ORM / migracions:** SQLAlchemy (async) + Alembic
- **Base de dades:** PostgreSQL 16
- **MQTT:** Paho-MQTT
- **Scheduler:** APScheduler
- **Configuració:** Pydantic Settings + python-dotenv
- **HTTP client intern:** httpx

---

## Mòduls de `app/`

### `irrigation/` — ENGINE CENTRAL (aïllat de la infra)

Conté **tota** la lògica de decisió de reg. Cap dependència de FastAPI, MQTT ni
scheduler. Rep un context (lectures de sensors, configuració de zona, historial
recent) i retorna una decisió (regar / no regar, durada, motiu).

Testejable de forma completament aïllada amb dades mock. És el lloc on afegir
suport de tipus de planta, predicció meteorològica, ML, etc.

### `mqtt/`

Gestiona la connexió amb el broker Mosquitto:
- Subscripció als topics de sensors de l'ESP32
- Parseja els missatges JSON i desa les lectures a la DB
- Publica ordres de control (relay on/off) i configuració

### `scheduler/`

Gestiona els triggers temporals (APScheduler). Per cada zona activa amb programa
configurat, comprova periòdicament si cal regar. Delega la decisió a `irrigation/`.

### `api/`

Endpoints REST i WebSocket per al frontend:
- Retorna dades llegides de la DB
- Accepta ordres manuals i les executa via `irrigation/`
- WebSocket `/ws/status` envia l'estat de les zones en temps real

### `notifications/`

Envia alertes per email i/o Telegram quan:
- La humitat baixa del mínim configurat
- Un reg falla o supera la durada màxima
- L'ESP32 deixa de publicar (timeout)

---

## Models de base de dades

```
zones
  id, name, active, relay_pin

sensor_readings
  id, zone_id, sensor_type (soil | ambient), value, timestamp

watering_events
  id, zone_id, started_at, ended_at,
  trigger_type (schedule | manual | sensor), duration_seconds

schedules
  id, zone_id, time_start (HH:MM), days_of_week ([0-6]), duration_minutes, active

zone_config
  zone_id (PK/FK), humidity_min, humidity_max,
  max_temp_to_water, cooldown_hours

plant_types  ← futur
  id, name, humidity_ideal_min, humidity_ideal_max

alerts
  id, type, message, resolved, created_at
```

---

## MQTT Topics

| Direcció | Topic | Payload (JSON) |
|---|---|---|
| ESP32 → Backend | `smartgarden/sensors/soil/{zone_id}` | `{"zone_id":1,"values":[42,45],"timestamp":...}` |
| ESP32 → Backend | `smartgarden/sensors/ambient` | `{"temp":22.5,"humidity":60,"timestamp":...}` |
| Backend → ESP32 | `smartgarden/control/{zone_id}` | `{"action":"on","duration_seconds":120}` |
| Backend → ESP32 | `smartgarden/config/push` | `{"schedules":[...]}` |

---

## Endpoints REST (a implementar)

```
GET    /api/zones
PUT    /api/zones/{id}
GET    /api/zones/{id}/config
PUT    /api/zones/{id}/config
GET    /api/zones/{id}/history
POST   /api/zones/{id}/water        ← reg manual
GET    /api/sensors/latest
GET    /api/schedules
POST   /api/schedules
PUT    /api/schedules/{id}
DELETE /api/schedules/{id}
GET    /api/alerts
WS     /ws/status                   ← temps real
```

---

## Variables d'entorn (.env)

```
POSTGRES_USER=smartgarden
POSTGRES_PASSWORD=changeme
POSTGRES_DB=smartgarden
POSTGRES_HOST=db
POSTGRES_PORT=5432

MQTT_HOST=mqtt
MQTT_PORT=1883

NOTIFICATION_EMAIL=           # opcional
TELEGRAM_BOT_TOKEN=           # opcional
TELEGRAM_CHAT_ID=             # opcional
```

---

## Córrer en local

```bash
# Amb Docker Compose (recomanat)
cd smart-garden/
docker compose up

# Sense Docker (dev)
cd smart-garden-backend/
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edita les variables
uvicorn app.main:app --reload
```
