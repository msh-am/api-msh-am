"""
Node endpoints for msh.am Live Dashboard and API consumers.
Supports both /api/nodes and /nodes.
"""

from __future__ import annotations

import time
from typing import List, Optional, Union, Dict, Any

from fastapi import APIRouter, HTTPException, Query, Request

from src.database import db_session
from src.models.mesh import MeshNode, NodeListResponse
from src.services.state_manager import state_manager

router = APIRouter(tags=["Nodes"])


@router.get("/api/nodes", response_model=Union[NodeListResponse, List[MeshNode]])
@router.get("/nodes", response_model=Union[NodeListResponse, List[MeshNode]])
async def get_nodes(
    format: Optional[str] = Query(None, description="Set 'array' for raw list (PotatoMesh style) or 'object' (msh.am style)"),
    is_online: Optional[bool] = Query(None, description="Filter by online status"),
    role: Optional[str] = Query(None, description="Filter by node role (ROUTER, CLIENT, etc.)"),
) -> Union[NodeListResponse, List[MeshNode]]:
    nodes = state_manager.get_all_nodes()

    if is_online is not None:
        nodes = [n for n in nodes if n.isOnline == is_online]

    if role is not None:
        nodes = [n for n in nodes if n.role.upper() == role.upper()]

    if format == "array":
        return nodes

    return NodeListResponse(
        updatedAt=int(time.time() * 1000),
        nodes=nodes,
    )


@router.get("/api/nodes/{node_id}")
async def get_node_detail(node_id: str) -> Dict[str, Any]:
    node = state_manager.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    # Fetch recent telemetry history from SQLite
    telemetry_history = []
    positions_history = []

    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT timestamp, battery_level, voltage, channel_utilization, air_util_tx, snr, rssi
            FROM telemetry
            WHERE node_id = ?
            ORDER BY timestamp DESC
            LIMIT 50;
            """,
            (node_id,),
        )
        for row in cursor.fetchall():
            telemetry_history.append(dict(row))

        cursor.execute(
            """
            SELECT timestamp, latitude, longitude, altitude
            FROM positions
            WHERE node_id = ?
            ORDER BY timestamp DESC
            LIMIT 50;
            """,
            (node_id,),
        )
        for row in cursor.fetchall():
            positions_history.append(dict(row))

    return {
        "node": node.model_dump(),
        "telemetryHistory": telemetry_history,
        "positionsHistory": positions_history,
    }
