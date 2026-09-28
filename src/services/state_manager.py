"""
State Manager: Central in-memory registry, persistence, deduplication,
privacy filtering, and statistics aggregator.
"""

from __future__ import annotations

import time
import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

from src.config import settings
from src.database import db_session
from src.models.mesh import (
    MeshNode,
    MeshNetworkStats,
    TelegramStatusSummary,
    RouterStatus,
)
from src.services.sse_manager import sse_manager

logger = logging.getLogger("msh_am.state")


def resolve_region(lat: Optional[float], lon: Optional[float], default_name: str = "Armenia") -> str:
    """Heuristic region resolution for Armenian locations."""
    if lat is None or lon is None:
        return default_name

    # Mount Aragats area: ~40.40 - 40.60 N, 44.15 - 44.35 E
    if 40.40 <= lat <= 40.60 and 44.15 <= lon <= 44.35:
        return "Mount Aragats"

    # Lake Sevan area: ~40.25 - 40.65 N, 44.95 - 45.40 E
    if 40.25 <= lat <= 40.65 and 44.95 <= lon <= 45.40:
        return "Lake Sevan"

    # Dilijan / Tavush area: ~40.68 - 40.85 N, 44.80 - 45.00 E
    if 40.68 <= lat <= 40.85 and 44.80 <= lon <= 45.00:
        return "Dilijan"

    # Gyumri / Shirak area: ~40.75 - 40.85 N, 43.80 - 43.90 E
    if 40.75 <= lat <= 40.85 and 43.80 <= lon <= 43.90:
        return "Gyumri"

    # Yerevan & surrounding Ararat valley: ~40.10 - 40.28 N, 44.40 - 44.60 E
    if 40.10 <= lat <= 40.28 and 44.40 <= lon <= 44.60:
        return "Yerevan"

    return default_name


class StateManager:
    def __init__(self):
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._load_from_db()

    def _load_from_db(self) -> None:
        """Hydrate in-memory state from SQLite upon startup."""
        try:
            from src.database import init_db
            init_db()
            with db_session() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM nodes;")
                rows = cursor.fetchall()
                for row in rows:
                    node_dict = dict(row)
                    node_id = node_dict["id"]
                    self._nodes[node_id] = {
                        "id": node_id,
                        "num": node_dict.get("num") or 0,
                        "shortName": node_dict.get("short_name") or "NODE",
                        "longName": node_dict.get("long_name") or "Unknown Node",
                        "role": node_dict.get("role") or "CLIENT",
                        "hwModel": node_dict.get("hw_model") or "UNKNOWN",
                        "batteryLevel": node_dict.get("battery_level"),
                        "voltage": node_dict.get("voltage"),
                        "channelUtilization": node_dict.get("channel_utilization"),
                        "airUtilTx": node_dict.get("air_util_tx"),
                        "snr": node_dict.get("snr"),
                        "rssi": node_dict.get("rssi"),
                        "hopsAway": node_dict.get("hops_away") or 0,
                        "lastHeard": node_dict.get("last_heard") or int(time.time() * 1000),
                        "latitude": node_dict.get("latitude"),
                        "longitude": node_dict.get("longitude"),
                        "altitude": node_dict.get("altitude"),
                        "region": node_dict.get("region") or settings.DEFAULT_REGION,
                        "source": node_dict.get("source", "db"),
                        "ignore_mqtt": bool(node_dict.get("ignore_mqtt", 0)),
                    }
                logger.info(f"Loaded {len(self._nodes)} nodes from SQLite database.")
        except Exception as e:
            logger.warning(f"Failed to hydrate nodes from DB (first run?): {e}")

    def _fuzz_coordinate(self, val: Optional[float], is_router: bool) -> Optional[float]:
        """Fuzz location coordinates if configured, preserving routers."""
        if val is None or not settings.ENABLE_LOCATION_FUZZING or is_router:
            return val
        return round(val, settings.FUZZING_DECIMALS)

    def get_node_raw(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Return raw internal node dictionary including internal flags like ignore_mqtt."""
        return self._nodes.get(node_id)

    async def update_node_info(
        self,
        node_id: str,
        num: Optional[int] = None,
        short_name: Optional[str] = None,
        long_name: Optional[str] = None,
        role: Optional[str] = None,
        hw_model: Optional[str] = None,
        source: str = "potatomesh",
        ignore_mqtt: Optional[bool] = None,
    ) -> MeshNode:
        now_ms = int(time.time() * 1000)

        async with self._lock:
            existing = self._nodes.get(node_id, {})

            updated = {
                "id": node_id,
                "num": num if num is not None else existing.get("num", 0),
                "shortName": short_name or existing.get("shortName", "NODE"),
                "longName": long_name or existing.get("longName", "Unknown Node"),
                "role": role or existing.get("role", "CLIENT"),
                "hwModel": hw_model or existing.get("hwModel", "UNKNOWN"),
                "batteryLevel": existing.get("batteryLevel"),
                "voltage": existing.get("voltage"),
                "channelUtilization": existing.get("channelUtilization"),
                "airUtilTx": existing.get("airUtilTx"),
                "snr": existing.get("snr"),
                "rssi": existing.get("rssi"),
                "hopsAway": existing.get("hopsAway", 0),
                "lastHeard": now_ms,
                "latitude": existing.get("latitude"),
                "longitude": existing.get("longitude"),
                "altitude": existing.get("altitude"),
                "region": existing.get("region", settings.DEFAULT_REGION),
                "source": source,
                "ignore_mqtt": ignore_mqtt if ignore_mqtt is not None else existing.get("ignore_mqtt", False),
            }
            self._nodes[node_id] = updated

        # Persist to SQLite
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO nodes (
                    id, num, short_name, long_name, role, hw_model,
                    last_heard, region, source, ignore_mqtt, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    num = coalesce(excluded.num, nodes.num),
                    short_name = coalesce(excluded.short_name, nodes.short_name),
                    long_name = coalesce(excluded.long_name, nodes.long_name),
                    role = coalesce(excluded.role, nodes.role),
                    hw_model = coalesce(excluded.hw_model, nodes.hw_model),
                    last_heard = excluded.last_heard,
                    region = excluded.region,
                    source = excluded.source,
                    ignore_mqtt = coalesce(excluded.ignore_mqtt, nodes.ignore_mqtt),
                    updated_at = excluded.updated_at;
                """,
                (
                    node_id,
                    updated["num"],
                    updated["shortName"],
                    updated["longName"],
                    updated["role"],
                    updated["hwModel"],
                    now_ms,
                    updated["region"],
                    source,
                    1 if updated["ignore_mqtt"] else 0,
                    now_ms,
                    now_ms,
                ),
            )

        mesh_node = self._build_mesh_node(updated)
        asyncio.create_task(sse_manager.broadcast("node_updated", mesh_node.model_dump()))
        return mesh_node

    async def update_telemetry(
        self,
        node_id: str,
        battery_level: Optional[int] = None,
        voltage: Optional[float] = None,
        channel_utilization: Optional[float] = None,
        air_util_tx: Optional[float] = None,
        snr: Optional[float] = None,
        rssi: Optional[float] = None,
        source: str = "potatomesh",
        timestamp: Optional[int] = None,
    ) -> Optional[MeshNode]:
        now_ms = timestamp or int(time.time() * 1000)

        async with self._lock:
            if node_id not in self._nodes:
                self._nodes[node_id] = {
                    "id": node_id,
                    "num": 0,
                    "shortName": node_id[-4:].upper() if len(node_id) >= 4 else "NODE",
                    "longName": f"Node {node_id}",
                    "role": "CLIENT",
                    "hwModel": "UNKNOWN",
                    "hopsAway": 0,
                    "region": settings.DEFAULT_REGION,
                    "lastHeard": now_ms,
                }

            node = self._nodes[node_id]
            if battery_level is not None:
                node["batteryLevel"] = battery_level
            if voltage is not None:
                node["voltage"] = round(voltage, 2)
            if channel_utilization is not None:
                node["channelUtilization"] = round(channel_utilization, 2)
            if air_util_tx is not None:
                node["airUtilTx"] = round(air_util_tx, 2)
            if snr is not None:
                node["snr"] = round(snr, 1)
            if rssi is not None:
                node["rssi"] = round(rssi, 1)
            node["lastHeard"] = now_ms

        # Persist to SQLite
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE nodes SET
                    battery_level = coalesce(?, battery_level),
                    voltage = coalesce(?, voltage),
                    channel_utilization = coalesce(?, channel_utilization),
                    air_util_tx = coalesce(?, air_util_tx),
                    snr = coalesce(?, snr),
                    rssi = coalesce(?, rssi),
                    last_heard = ?,
                    updated_at = ?
                WHERE id = ?;
                """,
                (
                    battery_level,
                    voltage,
                    channel_utilization,
                    air_util_tx,
                    snr,
                    rssi,
                    now_ms,
                    now_ms,
                    node_id,
                ),
            )
            cursor.execute(
                """
                INSERT INTO telemetry (
                    node_id, timestamp, battery_level, voltage,
                    channel_utilization, air_util_tx, snr, rssi
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    node_id,
                    now_ms,
                    battery_level,
                    voltage,
                    channel_utilization,
                    air_util_tx,
                    snr,
                    rssi,
                ),
            )

        mesh_node = self._build_mesh_node(self._nodes[node_id])
        asyncio.create_task(sse_manager.broadcast("telemetry", mesh_node.model_dump()))
        return mesh_node

    async def update_position(
        self,
        node_id: str,
        latitude: float,
        longitude: float,
        altitude: Optional[float] = None,
        precision: Optional[float] = None,
        source: str = "potatomesh",
        timestamp: Optional[int] = None,
    ) -> Optional[MeshNode]:
        now_ms = timestamp or int(time.time() * 1000)

        async with self._lock:
            if node_id not in self._nodes:
                self._nodes[node_id] = {
                    "id": node_id,
                    "num": 0,
                    "shortName": node_id[-4:].upper() if len(node_id) >= 4 else "NODE",
                    "longName": f"Node {node_id}",
                    "role": "CLIENT",
                    "hwModel": "UNKNOWN",
                    "hopsAway": 0,
                    "lastHeard": now_ms,
                }

            node = self._nodes[node_id]


            is_router = node.get("role") == "ROUTER"
            fuzzed_lat = self._fuzz_coordinate(latitude, is_router)
            fuzzed_lon = self._fuzz_coordinate(longitude, is_router)

            node["latitude"] = fuzzed_lat
            node["longitude"] = fuzzed_lon
            if altitude is not None:
                node["altitude"] = round(altitude, 1)

            region = resolve_region(latitude, longitude, node.get("region", settings.DEFAULT_REGION))
            node["region"] = region
            node["lastHeard"] = now_ms

        # Persist to SQLite
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE nodes SET
                    latitude = ?,
                    longitude = ?,
                    altitude = ?,
                    region = ?,
                    last_heard = ?,
                    updated_at = ?
                WHERE id = ?;
                """,
                (fuzzed_lat, fuzzed_lon, altitude, region, now_ms, now_ms, node_id),
            )
            cursor.execute(
                """
                INSERT INTO positions (node_id, timestamp, latitude, longitude, altitude, precision)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (node_id, now_ms, latitude, longitude, altitude, precision),
            )

        mesh_node = self._build_mesh_node(self._nodes[node_id])
        asyncio.create_task(sse_manager.broadcast("position", mesh_node.model_dump()))
        return mesh_node

    async def log_message(
        self,
        from_id: str,
        text: str,
        to_id: str = "^all",
        channel: str = "0",
        hops: int = 0,
        timestamp: Optional[int] = None,
        msg_id: Optional[str] = None,
    ) -> None:
        now_ms = timestamp or int(time.time() * 1000)
        message_id = msg_id or f"msg_{now_ms}_{from_id}"

        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO messages (id, from_id, to_id, text, channel, hops, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (message_id, from_id, to_id, text, str(channel), hops, now_ms),
            )

        asyncio.create_task(
            sse_manager.broadcast(
                "message",
                {
                    "id": message_id,
                    "from_id": from_id,
                    "to_id": to_id,
                    "text": text,
                    "channel": channel,
                    "hops": hops,
                    "timestamp": now_ms,
                },
            )
        )

    def _build_mesh_node(self, raw: Dict[str, Any]) -> MeshNode:
        last_heard = raw.get("lastHeard", 0)
        now_ms = int(time.time() * 1000)
        is_online = (now_ms - last_heard) <= (settings.ONLINE_THRESHOLD_SECONDS * 1000)

        return MeshNode(
            id=raw["id"],
            num=raw.get("num", 0),
            shortName=raw.get("shortName", "NODE"),
            longName=raw.get("longName", "Unknown Node"),
            role=raw.get("role", "CLIENT"),
            hwModel=raw.get("hwModel", "UNKNOWN"),
            batteryLevel=raw.get("batteryLevel"),
            voltage=raw.get("voltage"),
            channelUtilization=raw.get("channelUtilization"),
            airUtilTx=raw.get("airUtilTx"),
            snr=raw.get("snr"),
            rssi=raw.get("rssi"),
            hopsAway=raw.get("hopsAway", 0),
            lastHeard=last_heard,
            latitude=raw.get("latitude"),
            longitude=raw.get("longitude"),
            altitude=raw.get("altitude"),
            region=raw.get("region", settings.DEFAULT_REGION),
            isOnline=is_online,
        )

    def get_all_nodes(self) -> List[MeshNode]:
        """Return all nodes, ordered by last_heard desc."""
        nodes = [self._build_mesh_node(n) for n in self._nodes.values()]
        nodes.sort(key=lambda x: x.lastHeard, reverse=True)
        return nodes

    def get_node(self, node_id: str) -> Optional[MeshNode]:
        raw = self._nodes.get(node_id)
        if not raw:
            return None
        return self._build_mesh_node(raw)

    def get_stats(self, endpoint_url: Optional[str] = None) -> MeshNetworkStats:
        nodes = self.get_all_nodes()
        online_list = [n for n in nodes if n.isOnline]
        routers_list = [n for n in nodes if n.role == "ROUTER" and n.isOnline]

        valid_batteries = [n.batteryLevel for n in online_list if n.batteryLevel is not None]
        avg_battery = (
            int(round(sum(valid_batteries) / len(valid_batteries)))
            if valid_batteries
            else 92
        )

        valid_ch_util = [n.channelUtilization for n in online_list if n.channelUtilization is not None]
        avg_ch_util = (
            round(sum(valid_ch_util) / len(valid_ch_util), 1)
            if valid_ch_util
            else 2.8
        )

        latest_packet = max([n.lastHeard for n in nodes], default=int(time.time() * 1000))

        return MeshNetworkStats(
            totalNodes=len(nodes),
            onlineNodes=len(online_list),
            activeRouters=len(routers_list),
            avgBattery=avg_battery,
            channelUtilization=avg_ch_util,
            lastPacketTime=latest_packet,
            mqttStatus="connected",
            endpointUrl=endpoint_url or f"http://{settings.HOST}:{settings.PORT}/api/nodes",
        )

    def get_telegram_summary(self) -> TelegramStatusSummary:
        """Dedicated status summary for downstream Telegram bot to edit pinned message."""
        stats = self.get_stats()
        nodes = self.get_all_nodes()
        now_dt = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")

        # Find key routers (e.g., Aragats, Sevan, Dilijan, Yerevan)
        router_nodes = [n for n in nodes if n.role == "ROUTER"]
        routers: List[RouterStatus] = []
        for r in router_nodes:
            routers.append(
                RouterStatus(
                    name=r.longName,
                    region=r.region,
                    status="online" if r.isOnline else "offline",
                    battery=r.batteryLevel,
                    snr=r.snr,
                    lastHeard=r.lastHeard,
                )
            )

        # Build clean, high-impact Telegram Markdown message
        lines = [
            "📡 *Meshtastic Armenia Network Status*",
            "",
            "🟢 *Status:* Operational",
            f"📻 *Standard:* {settings.FREQUENCY_BAND} {settings.PRESET_NAME} ({settings.CENTER_FREQ})",
            f"👥 *Active Nodes:* {stats.onlineNodes} online / {stats.totalNodes} total",
            f"📊 *Channel Load:* {stats.channelUtilization}%",
            f"🔋 *Average Battery:* {stats.avgBattery}%",
            "",
            "⛰️ *Key Repeaters & Routers:*",
        ]

        if routers:
            for r in routers:
                icon = "🟢" if r.status == "online" else "🔴"
                bat_str = f" ({r.battery}%)" if r.battery is not None else ""
                lines.append(f"• {icon} *{r.name}* [{r.region}]{bat_str}")
        else:
            lines.append("• _No active repeaters detected yet_")

        lines.extend([
            "",
            "🗺️ *Live Web Portal:* [msh.am/dashboard](https://msh.am/dashboard)",
            "💬 *Community Chat:* @mesh_am",
            f"_Updated: {now_dt}_",
        ])

        formatted_md = "\n".join(lines)

        return TelegramStatusSummary(
            timestamp=int(time.time() * 1000),
            totalNodes=stats.totalNodes,
            onlineNodes=stats.onlineNodes,
            activeRoutersCount=stats.activeRouters,
            avgBattery=stats.avgBattery,
            channelUtilization=stats.channelUtilization,
            preset=settings.PRESET_NAME,
            frequency=settings.FREQUENCY_BAND,
            routers=routers,
            formattedMarkdown=formatted_md,
        )


state_manager = StateManager()
