"""
MQTT Ingestion Worker: Subscribes to Mosquitto (mqtt.msh.am) on msh/AM/#,
decodes Meshtastic Protocol Buffers, and updates the central StateManager.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Optional

import paho.mqtt.client as mqtt

from meshtastic.protobuf import mesh_pb2, telemetry_pb2, portnums_pb2, config_pb2
from src.config import settings
from src.services.state_manager import state_manager

logger = logging.getLogger("msh_am.mqtt")


def node_num_to_id(node_num: int) -> str:
    """Format numeric node ID to standard Meshtastic hex ID, e.g. !f24762e0."""
    return f"!{node_num:08x}"


class MQTTConsumer:
    def __init__(self):
        self._client: Optional[mqtt.Client] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if not settings.MQTT_ENABLED:
            logger.info("MQTT Ingestion is disabled in settings.")
            return

        self._loop = loop
        self._running = True

        # Initialize Paho MQTT client
        try:
            # Paho MQTT 2.x API callback version
            self._client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=settings.MQTT_CLIENT_ID,
                clean_session=True,
            )
        except (AttributeError, TypeError):
            # Fallback for older Paho MQTT 1.x
            self._client = mqtt.Client(
                client_id=settings.MQTT_CLIENT_ID,
                clean_session=True,
            )

        if settings.MQTT_USERNAME and settings.MQTT_PASSWORD:
            self._client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="mqtt-consumer")
        self._thread.start()
        logger.info(f"MQTT Consumer started in background thread, connecting to {settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT}...")

    def _run_loop(self) -> None:
        while self._running:
            try:
                logger.info(f"Connecting to MQTT broker {settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT}...")
                self._client.connect(settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT, keepalive=60)
                self._client.loop_forever()
            except Exception as e:
                logger.warning(f"MQTT broker connection error: {e}. Retrying in 10 seconds...")
                time.sleep(10)

    def stop(self) -> None:
        self._running = False
        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                pass
        logger.info("MQTT Consumer stopped.")

    def _on_connect(self, client: mqtt.Client, userdata, flags, rc, properties=None) -> None:
        if rc == 0:
            logger.info(f"Connected to MQTT broker! Subscribing to topics: {settings.MQTT_TOPIC_PREFIX}, {settings.MQTT_FALLBACK_TOPIC}")
            client.subscribe(settings.MQTT_TOPIC_PREFIX)
            client.subscribe(settings.MQTT_FALLBACK_TOPIC)
        else:
            logger.error(f"MQTT connection refused with result code {rc}")

    def _on_disconnect(self, client: mqtt.Client, userdata, disconnect_flags, rc=None, properties=None) -> None:
        logger.warning(f"Disconnected from MQTT broker (rc={rc})")

    def _on_message(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
        try:
            self._process_packet(msg.topic, msg.payload)
        except Exception as e:
            logger.debug(f"Failed to process packet on topic {msg.topic}: {e}")

    def _process_packet(self, topic: str, payload: bytes) -> None:
        """Parse incoming protobuf ServiceEnvelope or MeshPacket."""
        if not payload:
            return

        envelope = mesh_pb2.ServiceEnvelope()
        packet = mesh_pb2.MeshPacket()

        try:
            envelope.ParseFromString(payload)
            if envelope.HasField("packet"):
                packet = envelope.packet
            else:
                packet.ParseFromString(payload)
        except Exception:
            try:
                packet.ParseFromString(payload)
            except Exception:
                # Encrypted packet or raw binary not matching protobuf schema
                return

        from_num = getattr(packet, "from")
        if not from_num:
            return

        node_id = node_num_to_id(from_num)
        hops_away = (packet.hop_start - packet.hop_limit) if (packet.hop_start and packet.hop_limit) else 0
        if hops_away < 0:
            hops_away = 0

        rx_snr = packet.rx_snr if packet.rx_snr else None
        rx_rssi = packet.rx_rssi if packet.rx_rssi else None

        # Check decoded payload
        if not packet.HasField("decoded"):
            # Secondary channel encrypted packet: ignore cleartext extraction per privacy rules
            return

        decoded = packet.decoded
        portnum = decoded.portnum
        sub_payload = decoded.payload

        # Schedule async processing in the main event loop
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._dispatch_decoded(node_id, from_num, portnum, sub_payload, rx_snr, rx_rssi, hops_away),
                self._loop,
            )

    async def _dispatch_decoded(
        self,
        node_id: str,
        node_num: int,
        portnum: int,
        payload: bytes,
        snr: Optional[float],
        rssi: Optional[float],
        hops: int,
    ) -> None:
        # 1. NODEINFO_APP
        if portnum == portnums_pb2.PortNum.NODEINFO_APP:
            try:
                user = mesh_pb2.User()
                user.ParseFromString(payload)
                short_name = user.short_name or "NODE"
                long_name = user.long_name or f"Node {node_id}"
                hw_model = mesh_pb2.HardwareModel.Name(user.hw_model) if user.hw_model else "UNKNOWN"
                role = config_pb2.Config.DeviceConfig.Role.Name(user.role) if user.role else "CLIENT"

                await state_manager.update_node_info(
                    node_id=node_id,
                    num=node_num,
                    short_name=short_name,
                    long_name=long_name,
                    role=role,
                    hw_model=hw_model,
                    source="mqtt",
                )
                logger.info(f"MQTT NodeInfo: {short_name} ({long_name}) [{role}]")
            except Exception as e:
                logger.debug(f"Error parsing NODEINFO_APP: {e}")

        # 2. POSITION_APP
        elif portnum == portnums_pb2.PortNum.POSITION_APP:
            try:
                pos = mesh_pb2.Position()
                pos.ParseFromString(payload)
                if pos.latitude_i != 0 and pos.longitude_i != 0:
                    lat = pos.latitude_i / 1e7
                    lon = pos.longitude_i / 1e7
                    alt = float(pos.altitude) if pos.altitude else None
                    precision = float(pos.precision_bits) if pos.precision_bits else None

                    await state_manager.update_position(
                        node_id=node_id,
                        latitude=lat,
                        longitude=lon,
                        altitude=alt,
                        precision=precision,
                        source="mqtt",
                    )
                    logger.info(f"MQTT Position: {node_id} ({lat:.4f}, {lon:.4f})")
            except Exception as e:
                logger.debug(f"Error parsing POSITION_APP: {e}")

        # 3. TELEMETRY_APP
        elif portnum == portnums_pb2.PortNum.TELEMETRY_APP:
            try:
                telemetry = telemetry_pb2.Telemetry()
                telemetry.ParseFromString(payload)

                bat = None
                volt = None
                ch_util = None
                air_tx = None

                if telemetry.HasField("device_metrics"):
                    dm = telemetry.device_metrics
                    bat = dm.battery_level if dm.battery_level else None
                    volt = dm.voltage if dm.voltage else None
                    ch_util = dm.channel_utilization if dm.channel_utilization else None
                    air_tx = dm.air_util_tx if dm.air_util_tx else None

                await state_manager.update_telemetry(
                    node_id=node_id,
                    battery_level=bat,
                    voltage=volt,
                    channel_utilization=ch_util,
                    air_util_tx=air_tx,
                    snr=snr,
                    rssi=rssi,
                    source="mqtt",
                )
                logger.info(f"MQTT Telemetry: {node_id} Bat={bat}% Volt={volt}V Util={ch_util}%")
            except Exception as e:
                logger.debug(f"Error parsing TELEMETRY_APP: {e}")

        # 4. TEXT_MESSAGE_APP (Public community channel only)
        elif portnum == portnums_pb2.PortNum.TEXT_MESSAGE_APP:
            try:
                text = payload.decode("utf-8", errors="ignore")
                await state_manager.log_message(
                    from_id=node_id,
                    text=text,
                    hops=hops,
                )
                logger.info(f"MQTT Public Message from {node_id}: {text}")
            except Exception as e:
                logger.debug(f"Error parsing TEXT_MESSAGE_APP: {e}")


mqtt_consumer = MQTTConsumer()
