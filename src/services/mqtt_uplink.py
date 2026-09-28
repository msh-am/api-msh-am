"""
Upstream MQTT Uplink Service: Forwards eligible Armenian mesh packets to
the official public Meshtastic MQTT broker (mqtt.meshtastic.org).

Enforces strict compliance with Meshtastic privacy and consent standards:
1. OkToMQTT verification: Only packets with bitfield bit 0 set (OK_TO_MQTT=1) are forwarded.
2. IgnoreMQTT compliance: Packets from nodes with ignore_mqtt enabled are dropped.
3. Loop Prevention: Packets with via_mqtt=True are never re-uplinked.
4. Channel Isolation: Only decrypted community cleartext packets are uplinked.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Tuple

import paho.mqtt.client as mqtt
from meshtastic.protobuf import mesh_pb2, mqtt_pb2

from src.config import settings
from src.services.state_manager import state_manager

logger = logging.getLogger("msh_am.uplink")


class MQTTUplink:
    def __init__(self):
        self._client: Optional[mqtt.Client] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._connected = False

    def is_enabled(self) -> bool:
        return settings.MQTT_UPLINK_ENABLED

    def is_connected(self) -> bool:
        return self._connected

    def start(self) -> None:
        if not settings.MQTT_UPLINK_ENABLED:
            logger.info("Upstream MQTT Uplink is disabled in configuration.")
            return

        self._running = True

        try:
            self._client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=settings.MQTT_UPLINK_CLIENT_ID,
                clean_session=True,
            )
        except (AttributeError, TypeError):
            self._client = mqtt.Client(
                client_id=settings.MQTT_UPLINK_CLIENT_ID,
                clean_session=True,
            )

        if settings.MQTT_UPLINK_USERNAME and settings.MQTT_UPLINK_PASSWORD:
            self._client.username_pw_set(
                settings.MQTT_UPLINK_USERNAME,
                settings.MQTT_UPLINK_PASSWORD,
            )

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="mqtt-uplink")
        self._thread.start()
        logger.info(
            f"MQTT Uplink started in background thread, connecting to "
            f"{settings.MQTT_UPLINK_BROKER_HOST}:{settings.MQTT_UPLINK_BROKER_PORT}..."
        )

    def _run_loop(self) -> None:
        while self._running:
            try:
                logger.info(
                    f"Connecting to upstream MQTT broker "
                    f"{settings.MQTT_UPLINK_BROKER_HOST}:{settings.MQTT_UPLINK_BROKER_PORT}..."
                )
                self._client.connect(
                    settings.MQTT_UPLINK_BROKER_HOST,
                    settings.MQTT_UPLINK_BROKER_PORT,
                    keepalive=60,
                )
                self._client.loop_forever()
            except Exception as e:
                self._connected = False
                logger.warning(f"Upstream MQTT broker connection error: {e}. Retrying in 15 seconds...")
                time.sleep(15)

    def stop(self) -> None:
        self._running = False
        self._connected = False
        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                pass
        logger.info("MQTT Uplink stopped.")

    def _on_connect(self, client: mqtt.Client, userdata, flags, rc, properties=None) -> None:
        if rc == 0:
            self._connected = True
            logger.info(
                f"Connected to upstream MQTT broker ({settings.MQTT_UPLINK_BROKER_HOST})! "
                f"Uplink target prefix: {settings.MQTT_UPLINK_TOPIC_PREFIX}"
            )
        else:
            self._connected = False
            logger.error(f"Upstream MQTT connection refused with result code {rc}")

    def _on_disconnect(self, client: mqtt.Client, userdata, disconnect_flags, rc=None, properties=None) -> None:
        self._connected = False
        logger.warning(f"Disconnected from upstream MQTT broker (rc={rc})")

    def should_uplink(self, packet: mesh_pb2.MeshPacket, node_id: str) -> Tuple[bool, str]:
        """
        Evaluate packet compliance against Meshtastic consent and privacy policies.
        Returns (is_eligible, reason_string).
        """
        # 1. Loop Prevention: Never re-uplink packets that have already passed through MQTT
        if packet.via_mqtt:
            return False, "packet has via_mqtt flag (loop prevention)"

        # 2. Payload Inspection: Only cleartext community channel packets can be evaluated
        if not packet.HasField("decoded"):
            return False, "encrypted or missing decoded payload"

        # 3. OkToMQTT Check: Bit 0 of Data.bitfield
        bitfield = packet.decoded.bitfield
        ok_to_mqtt = bool(bitfield & 0x01)
        if not ok_to_mqtt:
            return False, f"OK_TO_MQTT flag is not set (bitfield={bitfield})"

        # 4. IgnoreMQTT Check: Check if originating node opted out in StateManager
        raw_node = state_manager.get_node_raw(node_id)
        if raw_node and raw_node.get("ignore_mqtt"):
            return False, "node has ignore_mqtt enabled"

        return True, "eligible"

    def uplink_packet(
        self,
        incoming_topic: str,
        packet: mesh_pb2.MeshPacket,
        channel_id: Optional[str] = None,
        gateway_id: Optional[str] = None,
    ) -> bool:
        """
        Package and publish an eligible packet to the public MQTT broker.
        """
        if not self._running or not self._client or not self._connected:
            return False

        from_num = getattr(packet, "from")
        node_id = f"!{from_num:08x}" if from_num else "unknown"

        eligible, reason = self.should_uplink(packet, node_id)
        if not eligible:
            logger.debug(f"Uplink skipped for node {node_id}: {reason}")
            return False

        # Extract hierarchical topic suffix (e.g. 2/c/LongFast/!0d8802c3)
        known_prefixes = [
            "/msh/EU_868/AM/",
            "msh/EU_868/AM/",
            "/msh/AM/",
            "msh/AM/",
            "/msh/EU_868/",
            "msh/EU_868/",
            "msh/",
            "/msh/",
        ]
        suffix = ""
        for prefix in known_prefixes:
            if incoming_topic.startswith(prefix):
                suffix = incoming_topic[len(prefix):].lstrip("/")
                break

        if not suffix:
            chan_name = channel_id or "LongFast"
            suffix = f"2/c/{chan_name}/{node_id}"

        clean_base = settings.MQTT_UPLINK_TOPIC_PREFIX.strip("/")
        topic_with_slash = f"/{clean_base}/{suffix}"
        topic_without_slash = f"{clean_base}/{suffix}"

        # Construct ServiceEnvelope with via_mqtt set to prevent downstream loops
        uplink_envelope = mqtt_pb2.ServiceEnvelope()
        uplink_packet = mesh_pb2.MeshPacket()
        uplink_packet.CopyFrom(packet)
        uplink_packet.via_mqtt = True

        uplink_envelope.packet.CopyFrom(uplink_packet)
        uplink_envelope.channel_id = channel_id or "LongFast"
        uplink_envelope.gateway_id = gateway_id or f"!{node_id.lstrip('!')}"

        serialized_payload = uplink_envelope.SerializeToString()

        try:
            # Publish to both standard slash and non-slash topics for universal client compatibility
            self._client.publish(topic_with_slash, serialized_payload, qos=0)
            self._client.publish(topic_without_slash, serialized_payload, qos=0)
            logger.info(f"Uplinked packet from {node_id} to public MQTT ({topic_with_slash})")
            return True
        except Exception as e:
            logger.warning(f"Failed to publish uplink packet to upstream MQTT: {e}")
            return False


mqtt_uplink = MQTTUplink()
