from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # TODO: inicialitzar connexió MQTT
    # TODO: inicialitzar scheduler
    yield
    # TODO: tancar connexions


app = FastAPI(
    title="Smart Garden API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok"}


# TODO: registrar routers de api/
# app.include_router(zones.router, prefix="/api")
# app.include_router(schedules.router, prefix="/api")
# app.include_router(sensors.router, prefix="/api")
# app.include_router(alerts.router, prefix="/api")
# app.include_router(ws.router)
