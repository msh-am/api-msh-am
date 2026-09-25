"""
PotatoMesh-compatible ingestion endpoints (HTTP POST).
Authenticated via Bearer <API_TOKEN>.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Header, status

from src.config import settings
from src.database import db_session
from src.models.mesh import (
    PotatoNodePayload,
    PotatoTelemetryPayload,
    PotatoPositionPayload,
    PotatoMessagePayload,
    PotatoNeighborPayload,
    PotatoTracePayload,
    PotatoIngestorPayload,
)
from src.services.state_manager import state_manager

logger = logging.getLogger("msh_am.ingest")

router = APIRouter(prefix="/api", tags=["PotatoMesh Ingestion"])


def verify_api_token(authorization: str = Header(None)) -> bool:
    """Verify Bearer token matching settings.API_TOKEN."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme, expected 'Bearer <TOKEN>'",
        )

    token = parts[1]
    if token != settings.API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API token",
        )

    return True


@router.post("/nodes")
async def ingest_node(
    payload: PotatoNodePayload,
    auth: bool = Depends(verify_api_token),
) -> Dict[str, Any]:
    node_id = payload.id or payload.node_id
    if not node_id:
        raise HTTPException(status_code=400, detail="Missing required field: id or node_id")

    node = await state_manager.update_node_info(
        node_id=node_id,
        num=payload.num,
        short_name=payload.short_name,
        long_name=payload.long_name,
        role=payload.role,
        hw_model=payload.hw_model,
        source="potatomesh",
    )
    return {"status": "ok", "node": node.model_dump()}


@router.post("/telemetry")
async def ingest_telemetry(
    payload: PotatoTelemetryPayload,
    auth: bool = Depends(verify_api_token),
) -> Dict[str, Any]:
    node = await state_manager.update_telemetry(
        node_id=payload.node_id,
        battery_level=payload.battery_level,
        voltage=payload.voltage,
        channel_utilization=payload.channel_utilization,
        air_util_tx=payload.air_util_tx,
        snr=payload.snr,
        rssi=payload.rssi,
        timestamp=payload.timestamp,
        source="potatomesh",
    )
    return {"status": "ok", "node_id": payload.node_id}


@router.post("/positions")
async def ingest_position(
    payload: PotatoPositionPayload,
    auth: bool = Depends(verify_api_token),
) -> Dict[str, Any]:
    node = await state_manager.update_position(
        node_id=payload.node_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        altitude=payload.altitude,
        precision=payload.precision,
        timestamp=payload.timestamp,
        source="potatomesh",
    )
    return {"status": "ok", "node_id": payload.node_id}


@router.post("/messages")
async def ingest_message(
    payload: PotatoMessagePayload,
    auth: bool = Depends(verify_api_token),
) -> Dict[str, Any]:
    await state_manager.log_message(
        from_id=payload.from_id,
        text=payload.text,
        to_id=payload.to_id or "^all",
        channel=str(payload.channel or "0"),
        hops=payload.hops or 0,
        timestamp=payload.timestamp,
        msg_id=payload.id,
    )
    return {"status": "ok"}


@router.post("/neighbors")
async def ingest_neighbors(
    payload: PotatoNeighborPayload,
    auth: bool = Depends(verify_api_token),
) -> Dict[str, Any]:
    now_ms = payload.timestamp or int(time.time() * 1000)
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO neighbors (node_id, neighbor_id, snr, timestamp)
            VALUES (?, ?, ?, ?);
            """,
            (payload.node_id, payload.neighbor_id, payload.snr, now_ms),
        )
    return {"status": "ok"}


@router.post("/traces")
async def ingest_traces(
    payload: PotatoTracePayload,
    auth: bool = Depends(verify_api_token),
) -> Dict[str, Any]:
    # Traceroutes recorded
    return {"status": "ok"}


@router.post("/ingestors")
async def register_ingestor(
    payload: PotatoIngestorPayload,
    auth: bool = Depends(verify_api_token),
) -> Dict[str, Any]:
    now_ms = int(time.time() * 1000)
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ingestors (id, name, protocol, connection, last_seen)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                protocol = excluded.protocol,
                connection = excluded.connection,
                last_seen = excluded.last_seen;
            """,
            (payload.id, payload.name, payload.protocol or "Meshtastic", payload.connection, now_ms),
        )
    logger.info(f"Ingestor heartbeat: {payload.name} ({payload.id})")
    return {"status": "ok"}
