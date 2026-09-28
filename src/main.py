"""
Main application entry point for api.msh.am.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.database import init_db
from src.routers import (
    nodes_router,
    stats_router,
    ingest_router,
    events_router,
    health_router,
)
from src.services.mqtt_consumer import mqtt_consumer
from src.services.mqtt_uplink import mqtt_uplink

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("msh_am.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Initializing api.msh.am...")
    init_db()

    # Start MQTT consumer in background thread attached to current asyncio loop
    loop = asyncio.get_running_loop()
    mqtt_consumer.start(loop)

    # Start upstream MQTT uplink to public broker (mqtt.meshtastic.org)
    mqtt_uplink.start()

    logger.info("api.msh.am is ready to serve.")
    yield

    logger.info("Shutting down api.msh.am...")
    mqtt_uplink.stop()
    mqtt_consumer.stop()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Meshtastic Armenia Community API",
    description="Dual-ingestion backend (PotatoMesh + MQTT) powering msh.am Live Dashboard and community tools.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for msh.am frontend and local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if settings.CORS_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(health_router)
app.include_router(nodes_router)
app.include_router(stats_router)
app.include_router(ingest_router)
app.include_router(events_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
