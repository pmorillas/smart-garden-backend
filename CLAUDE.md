# Smart Garden — Backend

## Idioma

- **Comunicació amb l'usuari:** català
- **Tot artefacte tècnic (commits, comentaris, noms de variables, docstrings):** anglès

---

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
- Publica ordres de control (relay on/off), configuració i actualitzacions OTA

### `scheduler/`

Gestiona els triggers temporals (APScheduler). Per cada zona activa amb programa
configurat, comprova periòdicament si cal regar. Delega la decisió a `irrigation/`.

### `api/`

Endpoints REST i WebSocket per al frontend:
- Retorna dades llegides de la DB
- Accepta ordres manuals i les executa via `irrigation/`
- WebSocket `/ws/status` envia l'estat de les zones en temps real
- `firmware.py` — gestió de versions i desplegaments OTA

### `notifications/`

Envia alertes per email i/o Telegram quan:
- La humitat baixa del mínim configurat
- Un reg falla o supera la durada màxima
- L'ESP32 deixa de publicar (timeout)

---

## Models de base de dades

```
devices
  id, mac_address, name, firmware_version, active, last_seen, registered_at

zones
  id, device_id, name, active, relay_pin_local, soil_pin_a_local, soil_pin_b_local

sensor_readings
  id, zone_id, sensor_type (soil_humidity | ambient_temperature | ambient_humidity | light_lux), value, raw_value (nullable), timestamp

watering_events
  id, zone_id, program_id, started_at, ended_at, trigger_type, duration_seconds

programs
  id, zone_id, name, active, condition_logic, duration_seconds, conditions (JSONB)

zone_config
  zone_id (PK/FK), humidity_min, humidity_max, max_temp_to_water, cooldown_hours

alerts
  id, type, zone_id, device_id, message, resolved, created_at, resolved_at

firmware_releases
  id, version, filename, checksum_sha256, size_bytes, notes, created_at

firmware_updates
  id, device_id, release_id, status (pending|downloading|flashing|success|failed), started_at, completed_at, error_message
```

---

## MQTT Topics

| Direcció | Topic | Payload (JSON) |
|---|---|---|
| ESP32 → Backend | `smartgarden/sensors/soil/{zone_id}` | `{"zone_id":1,"raw_values":[2100],"mac":"...","timestamp":...}` (firmware≥1.4.0) |
| ESP32 → Backend | `smartgarden/sensors/soil/{zone_id}` | `{"zone_id":1,"values":[42],"mac":"...","timestamp":...}` (legacy, < 1.4.0) |
| ESP32 → Backend | `smartgarden/sensors/ambient` | `{"temp":22.5,"humidity":60,"light_lux":1200,"mac":"..."}` |
| ESP32 → Backend | `smartgarden/devices/register` | `{"mac":"...","ip":"...","firmware":"1.1.0"}` (retained) |
| ESP32 → Backend | `smartgarden/devices/ota_status` | `{"mac":"...","status":"success","version":"1.2.0"}` |
| Backend → ESP32 | `smartgarden/control/{zone_id}` | `{"action":"on","duration_seconds":120}` |
| Backend → ESP32 | `smartgarden/config/push` | `{"schedules":[...]}` |
| Backend → ESP32 | `smartgarden/ota/{mac}` | `{"version":"1.2.0","url":"http://...","checksum":"sha256..."}` |

---

## API Firmware OTA

### Pujar un nou firmware
```bash
curl -X POST http://HOST:8000/api/firmware/ \
  -H "Authorization: Bearer <token>" \
  -F "version=1.2.0" \
  -F "notes=Descripció opcional" \
  -F "file=@firmware.bin"
```

### Llistar versions disponibles
```bash
curl http://HOST:8000/api/firmware/ -H "Authorization: Bearer <token>"
```

### Desplegar a tots els dispositius actius
```bash
curl -X POST http://HOST:8000/api/firmware/1/deploy \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Desplegar a un dispositiu específic
```bash
curl -X POST http://HOST:8000/api/firmware/1/deploy \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"device_id": 1}'
```

### Consultar estat d'actualitzacions d'un dispositiu
```bash
curl http://HOST:8000/api/firmware/devices/1/status -H "Authorization: Bearer <token>"
```

### Descarregar el binari (sense autenticació — accessible per l'ESP32)
```
GET /api/firmware/{id}/download
```

Els binaris es guarden a `uploads/firmware/` al servidor.

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

# URL accessible des de l'ESP32 per descarregar firmwares OTA
OTA_BASE_URL=http://192.168.1.162:8000

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
