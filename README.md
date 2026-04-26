# smart-garden-backend

Backend del sistema de reg automàtic. FastAPI + PostgreSQL + MQTT.

## Requisits

- Python 3.12+
- Docker i Docker Compose (recomanat)

## Córrer en local (Docker)

```bash
cd smart-garden/
cp .env.example .env
docker compose up
```

L'API queda disponible a `http://localhost:8000`. Documentació a `/docs`.

## Córrer en local (sense Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## Estructura

```
app/
├── main.py          — entrypoint FastAPI
├── config.py        — configuració via variables d'entorn
├── models/          — models SQLAlchemy
├── api/             — routers REST + WebSocket
├── mqtt/            — client MQTT (Paho)
├── scheduler/       — triggers temporals (APScheduler)
├── irrigation/      — ENGINE de decisions de reg (aïllat)
└── notifications/   — alertes email / Telegram
```

Veure `CLAUDE.md` per a la documentació completa.
