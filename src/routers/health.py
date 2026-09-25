"""
Health, version, and monitoring endpoints.
"""

from __future__ import annotations

import time
from typing import Dict, Any
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from src.config import settings
from src.services.state_manager import state_manager

router = APIRouter(tags=["Health & Monitoring"])


@router.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {"status": "ok"}


@router.get("/version")
async def version() -> Dict[str, Any]:
    """PotatoMesh-compatible instance metadata and public config."""
    stats = state_manager.get_stats()
    return {
        "name": "Meshtastic Armenia Community API",
        "version": "1.0.0",
        "instance": "api.msh.am",
        "preset": settings.PRESET_NAME,
        "frequency": settings.FREQUENCY_BAND,
        "center_frequency": settings.CENTER_FREQ,
        "nodes_online": stats.onlineNodes,
        "nodes_total": stats.totalNodes,
        "mqtt_enabled": settings.MQTT_ENABLED,
    }


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> str:
    """Prometheus metrics exporter."""
    stats = state_manager.get_stats()
    lines = [
        "# HELP msh_total_nodes Total discovered nodes in the registry",
        "# TYPE msh_total_nodes gauge",
        f"msh_total_nodes {stats.totalNodes}",
        "",
        "# HELP msh_online_nodes Nodes heard within the online threshold",
        "# TYPE msh_online_nodes gauge",
        f"msh_online_nodes {stats.onlineNodes}",
        "",
        "# HELP msh_active_routers Online repeaters and router nodes",
        "# TYPE msh_active_routers gauge",
        f"msh_active_routers {stats.activeRouters}",
        "",
        "# HELP msh_avg_battery Average battery percentage of online nodes",
        "# TYPE msh_avg_battery gauge",
        f"msh_avg_battery {stats.avgBattery}",
        "",
        "# HELP msh_channel_utilization Current estimated spectrum load",
        "# TYPE msh_channel_utilization gauge",
        f"msh_channel_utilization {stats.channelUtilization}",
        "",
    ]
    return "\n".join(lines)
