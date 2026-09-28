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

