"""
Data models and schemas for Meshtastic Armenia API (api.msh.am).
Strictly compatible with msh-am frontend (TypeScript) and PotatoMesh ingestors.
"""

from __future__ import annotations

from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# msh-am Web Portal Models (Matches msh-am/src/types/mesh.ts)
# ---------------------------------------------------------------------------

class MeshNode(BaseModel):
    id: str = Field(..., description="Node hex identifier, e.g. !f24762e0")
    num: int = Field(0, description="32-bit numeric node ID")
    shortName: str = Field("NODE", description="4-character callsign / short name")
    longName: str = Field("Unknown Node", description="Full descriptive node name")
    role: str = Field("CLIENT", description="Node role: CLIENT, ROUTER, CLIENT_BASE, etc.")
    hwModel: str = Field("UNKNOWN", description="Hardware model: RAK4631, HELTEC_V3, T_ECHO, etc.")
    batteryLevel: Optional[int] = Field(None, description="Battery percentage (0 - 100)")
    voltage: Optional[float] = Field(None, description="Battery voltage, e.g. 4.18V")
    channelUtilization: Optional[float] = Field(None, description="Channel airtime utilization percentage")
    airUtilTx: Optional[float] = Field(None, description="Node transmission airtime percentage")
    snr: Optional[float] = Field(None, description="Signal-to-noise ratio in dB")
    rssi: Optional[float] = Field(None, description="Received signal strength indicator in dBm")
    hopsAway: int = Field(0, description="Hops away from reporting ingestor/gateway")
    lastHeard: int = Field(..., description="Timestamp of last activity in milliseconds")
    latitude: Optional[float] = Field(None, description="GPS Latitude in decimal degrees")
    longitude: Optional[float] = Field(None, description="GPS Longitude in decimal degrees")
    altitude: Optional[float] = Field(None, description="Altitude in meters")
    region: str = Field("Armenia", description="Region name, e.g. Yerevan, Aragats, Sevan")
    isOnline: bool = Field(True, description="True if heard within the online threshold")


class NodeListResponse(BaseModel):
    updatedAt: int
    nodes: List[MeshNode]


class MeshNetworkStats(BaseModel):
    totalNodes: int
    onlineNodes: int
    activeRouters: int
    avgBattery: int
    channelUtilization: float
    lastPacketTime: int
    mqttStatus: str = "connected"  # connected | disconnected | simulated
    endpointUrl: Optional[str] = None


class RouterStatus(BaseModel):
    name: str
    region: str
    status: str  # online | offline
    battery: Optional[int] = None
    snr: Optional[float] = None
    lastHeard: int


class TelegramStatusSummary(BaseModel):
    timestamp: int
    totalNodes: int
    onlineNodes: int
    activeRoutersCount: int
    avgBattery: int
    channelUtilization: float
    preset: str
    frequency: str
    routers: List[RouterStatus]
    formattedMarkdown: str


# ---------------------------------------------------------------------------
# PotatoMesh-Compatible Ingestor Payloads (HTTP POST APIs)
# ---------------------------------------------------------------------------

class PotatoNodePayload(BaseModel):
    id: Optional[str] = None
    node_id: Optional[str] = None
    num: Optional[int] = None
    short_name: Optional[str] = None
    long_name: Optional[str] = None
    role: Optional[str] = None
    hw_model: Optional[str] = None
    protocol: Optional[str] = "Meshtastic"
    raw: Optional[Dict[str, Any]] = None


class PotatoTelemetryPayload(BaseModel):
    node_id: str
    battery_level: Optional[int] = None
    voltage: Optional[float] = None
    channel_utilization: Optional[float] = None
    air_util_tx: Optional[float] = None
    snr: Optional[float] = None
    rssi: Optional[float] = None
    timestamp: Optional[int] = None


class PotatoPositionPayload(BaseModel):
    node_id: str
    latitude: float
    longitude: float
    altitude: Optional[float] = None
    precision: Optional[float] = None
    timestamp: Optional[int] = None


class PotatoMessagePayload(BaseModel):
    id: Optional[str] = None
    from_id: str
    to_id: Optional[str] = "^all"
    text: str
    channel: Optional[Any] = "0"
    hops: Optional[int] = 0
    timestamp: Optional[int] = None


class PotatoNeighborPayload(BaseModel):
    node_id: str
    neighbor_id: str
    snr: Optional[float] = None
    timestamp: Optional[int] = None


class PotatoTracePayload(BaseModel):
    node_id: str
    route: Optional[List[str]] = None
    snr_list: Optional[List[float]] = None
    timestamp: Optional[int] = None


class PotatoIngestorPayload(BaseModel):
    id: str
    name: str
    protocol: Optional[str] = "Meshtastic"
    connection: Optional[str] = None
