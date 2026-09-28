"""
Unit test for MQTT protobuf packet ingestion.
"""

import os
import tempfile
import pytest
from pathlib import Path
from meshtastic.protobuf import mesh_pb2, telemetry_pb2, portnums_pb2, config_pb2

test_db_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
test_db_path = test_db_file.name
test_db_file.close()

from src.config import settings
settings.DATABASE_PATH = Path(test_db_path)
settings.MQTT_ENABLED = True

from src.database import init_db
from src.services.state_manager import state_manager
from src.services.mqtt_consumer import mqtt_consumer


@pytest.fixture(autouse=True)
def setup_database():
    settings.DATABASE_PATH = Path(test_db_path)
    init_db()
    yield
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except OSError:
            pass


@pytest.mark.anyio
async def test_mqtt_protobuf_dispatch():
    # 1. Test NodeInfo packet dispatch
    node_num = 3148422020  # !bba93b84 (mooncat)
    user = mesh_pb2.User(
        id="!bba93b84",
        long_name="mooncat",
        short_name="😺",
        hw_model=mesh_pb2.HardwareModel.T_ECHO,
        role=config_pb2.Config.DeviceConfig.Role.CLIENT,
    )
    payload_bytes = user.SerializeToString()

    await mqtt_consumer._dispatch_decoded(
        node_id="!bba93b84",
        node_num=node_num,
        portnum=portnums_pb2.PortNum.NODEINFO_APP,
        payload=payload_bytes,
        snr=10.5,
        rssi=-75.0,
        hops=2,
    )

    node = state_manager.get_node("!bba93b84")
    assert node is not None
    assert node.shortName == "😺"
    assert node.longName == "mooncat"
    assert node.role == "CLIENT"
    assert node.hwModel == "T_ECHO"

    # 2. Test Telemetry packet dispatch
    telem = telemetry_pb2.Telemetry()
    telem.device_metrics.battery_level = 95
    telem.device_metrics.voltage = 4.14
    telem.device_metrics.channel_utilization = 3.2
    telem.device_metrics.air_util_tx = 1.0

    await mqtt_consumer._dispatch_decoded(
        node_id="!bba93b84",
        node_num=node_num,
        portnum=portnums_pb2.PortNum.TELEMETRY_APP,
        payload=telem.SerializeToString(),
        snr=10.5,
        rssi=-75.0,
        hops=2,
    )

    updated_node = state_manager.get_node("!bba93b84")
    assert updated_node.batteryLevel == 95
    assert updated_node.voltage == 4.14
    assert updated_node.channelUtilization == 3.2

    # 3. Test Position packet dispatch
    pos = mesh_pb2.Position(
        latitude_i=int(40.1792 * 1e7),
        longitude_i=int(44.4991 * 1e7),
        altitude=1050,
    )

    await mqtt_consumer._dispatch_decoded(
        node_id="!bba93b84",
        node_num=node_num,
        portnum=portnums_pb2.PortNum.POSITION_APP,
        payload=pos.SerializeToString(),
        snr=10.5,
        rssi=-75.0,
        hops=2,
    )

    pos_node = state_manager.get_node("!bba93b84")
    assert pos_node.latitude == pytest.approx(40.1792, rel=1e-4)
    assert pos_node.longitude == pytest.approx(44.4991, rel=1e-4)
    assert pos_node.region == "Yerevan"


def test_default_mqtt_credentials():
    assert settings.MQTT_USERNAME == "meshdev"
    assert settings.MQTT_PASSWORD == "large4cats"
    assert settings.MQTT_TOPIC_PREFIX == "msh/EU_868/AM/#"
    assert settings.MQTT_UPLINK_TOPIC_PREFIX == "/msh/EU_868/AM/"


def test_mqtt_uplink_rules():
    from meshtastic.protobuf import mqtt_pb2
    from src.services.mqtt_uplink import mqtt_uplink

    # 1. OkToMQTT True: bitfield bit 0 set (1)
    packet_ok = mesh_pb2.MeshPacket()
    packet_ok.decoded.portnum = portnums_pb2.PortNum.TEXT_MESSAGE_APP
    packet_ok.decoded.payload = b"Hello Armenia"
    packet_ok.decoded.bitfield = 1  # Bit 0 set (OK_TO_MQTT)
    setattr(packet_ok, "from", 227017411)  # kitD (!0d8802c3)

    eligible, reason = mqtt_uplink.should_uplink(packet_ok, "!0d8802c3")
    assert eligible is True
    assert reason == "eligible"

    # 2. OkToMQTT False: bitfield bit 0 not set (0)
    packet_no_optin = mesh_pb2.MeshPacket()
    packet_no_optin.decoded.portnum = portnums_pb2.PortNum.TEXT_MESSAGE_APP
    packet_no_optin.decoded.payload = b"Local only message"
    packet_no_optin.decoded.bitfield = 0  # Bit 0 not set
    setattr(packet_no_optin, "from", 227017411)

    eligible, reason = mqtt_uplink.should_uplink(packet_no_optin, "!0d8802c3")
    assert eligible is False
    assert "OK_TO_MQTT flag is not set" in reason

    # 3. Loop prevention: via_mqtt True
    packet_via_mqtt = mesh_pb2.MeshPacket()
    packet_via_mqtt.via_mqtt = True
    packet_via_mqtt.decoded.bitfield = 1
    setattr(packet_via_mqtt, "from", 227017411)

    eligible, reason = mqtt_uplink.should_uplink(packet_via_mqtt, "!0d8802c3")
    assert eligible is False
    assert "loop prevention" in reason

    # 4. Encrypted packet without decoded
    packet_encrypted = mesh_pb2.MeshPacket()
    packet_encrypted.encrypted = b"some_ciphertext"
    setattr(packet_encrypted, "from", 227017411)

    eligible, reason = mqtt_uplink.should_uplink(packet_encrypted, "!0d8802c3")
    assert eligible is False
    assert "encrypted or missing decoded" in reason


@pytest.mark.anyio
async def test_mqtt_service_envelope_processing():
    from meshtastic.protobuf import mqtt_pb2

    # Verify ServiceEnvelope parsing in mqtt_consumer
    user = mesh_pb2.User(
        id="!0d8802c3",
        long_name="kita home",
        short_name="kitD",
        hw_model=mesh_pb2.HardwareModel.RAK4631,
        role=config_pb2.Config.DeviceConfig.Role.CLIENT_BASE,
    )

    inner_packet = mesh_pb2.MeshPacket()
    setattr(inner_packet, "from", 227017411)
    inner_packet.decoded.portnum = portnums_pb2.PortNum.NODEINFO_APP
    inner_packet.decoded.payload = user.SerializeToString()
    inner_packet.decoded.bitfield = 1

    envelope = mqtt_pb2.ServiceEnvelope()
    envelope.packet.CopyFrom(inner_packet)
    envelope.channel_id = "LongFast"
    envelope.gateway_id = "!0d8802c3"

    payload = envelope.SerializeToString()

    # Process via mqtt_consumer
    mqtt_consumer._process_packet("/msh/EU_868/AM/2/c/LongFast/!0d8802c3", payload)

    # Allow async dispatch to execute in state manager
    import asyncio
    await asyncio.sleep(0.05)

    node = state_manager.get_node("!0d8802c3")
    assert node is not None
    assert node.shortName == "kitD"
    assert node.longName == "kita home"
    assert node.hwModel == "RAK4631"


@pytest.mark.anyio
async def test_mqtt_encrypted_default_channel_decryption():
    from src.services.crypto import try_decrypt_mesh_packet, DEFAULT_CHANNEL_KEY
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend

    # Create encrypted node info
    user = mesh_pb2.User(
        id="!0d8802c3",
        long_name="kita home",
        short_name="kitD",
        hw_model=mesh_pb2.HardwareModel.RAK4631,
        role=config_pb2.Config.DeviceConfig.Role.CLIENT_BASE,
    )
    data = mesh_pb2.Data(
        portnum=portnums_pb2.PortNum.NODEINFO_APP,
        payload=user.SerializeToString(),
        bitfield=1,
    )
    plain_bytes = data.SerializeToString()

    packet_id = 998877
    from_id = 227017411

    nonce = packet_id.to_bytes(8, "little") + from_id.to_bytes(4, "little") + b"\x00" * 4
    cipher = Cipher(algorithms.AES(DEFAULT_CHANNEL_KEY), modes.CTR(nonce), backend=default_backend())
    ciphertext = cipher.encryptor().update(plain_bytes)

    enc_packet = mesh_pb2.MeshPacket()
    enc_packet.id = packet_id
    setattr(enc_packet, "from", from_id)
    enc_packet.encrypted = ciphertext

    # Decrypt
    decrypted = try_decrypt_mesh_packet(enc_packet)
    assert decrypted is True
    assert enc_packet.HasField("decoded")
    assert enc_packet.decoded.portnum == portnums_pb2.PortNum.NODEINFO_APP
    assert enc_packet.decoded.bitfield == 1

