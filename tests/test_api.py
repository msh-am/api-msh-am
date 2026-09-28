"""
Automated test suite for Meshtastic Armenia API (api.msh.am).
"""

import os
import pytest
from fastapi.testclient import TestClient

import os
import tempfile
import pytest
from fastapi.testclient import TestClient

# Configure test environment with temp database file
test_db_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
test_db_path = test_db_file.name
test_db_file.close()

os.environ["DATABASE_PATH"] = test_db_path
os.environ["API_TOKEN"] = "test_armenia_token"
os.environ["MQTT_ENABLED"] = "false"

from pathlib import Path
from src.config import settings
from src.main import app
from src.database import init_db
from src.services.state_manager import state_manager


@pytest.fixture(autouse=True)
def setup_database():
    settings.DATABASE_PATH = Path(test_db_path)
    settings.API_TOKEN = "test_armenia_token"
    init_db()
    yield
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except OSError:
            pass


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_healthz(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_version_and_metrics(client):
    res = client.get("/version")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Meshtastic Armenia Community API"
    assert data["frequency"] == "EU_868"
    assert data["preset"] == "MediumFast"

    metrics_res = client.get("/metrics")
    assert metrics_res.status_code == 200
    assert "msh_total_nodes" in metrics_res.text


def test_potatomesh_auth(client):
    # Missing auth header -> 401
    res = client.post("/api/nodes", json={"node_id": "!test0001"})
    assert res.status_code == 401

    # Invalid token -> 403
    res = client.post(
        "/api/nodes",
        json={"node_id": "!test0001"},
        headers={"Authorization": "Bearer wrong_token"},
    )
    assert res.status_code == 403


def test_potatomesh_ingestion_and_msh_am_dashboard_query(client):
    auth_headers = {"Authorization": "Bearer test_armenia_token"}

    # 1. Ingest node metadata (Yundin Repeater)
    res = client.post(
        "/api/nodes",
        json={
            "node_id": "!f24762e0",
            "num": 4064764640,
            "short_name": "YRPT",
            "long_name": "Yundin Repeater",
            "role": "ROUTER",
            "hw_model": "RAK4631",
        },
        headers=auth_headers,
    )
    assert res.status_code == 200

    # 2. Ingest telemetry
    res = client.post(
        "/api/telemetry",
        json={
            "node_id": "!f24762e0",
            "battery_level": 98,
            "voltage": 4.18,
            "channel_utilization": 2.4,
            "air_util_tx": 1.1,
            "snr": 9.5,
            "rssi": -85.0,
        },
        headers=auth_headers,
    )
    assert res.status_code == 200

    # 3. Ingest GPS coordinates (Yerevan)
    res = client.post(
        "/api/positions",
        json={
            "node_id": "!f24762e0",
            "latitude": 40.1792,
            "longitude": 44.4991,
            "altitude": 1050.0,
        },
        headers=auth_headers,
    )
    assert res.status_code == 200

    # 4. Ingest Aragats Backbone Router
    client.post(
        "/api/nodes",
        json={
            "node_id": "!a1b2c3d4",
            "num": 2712847316,
            "short_name": "ARAG",
            "long_name": "Aragats Backbone",
            "role": "ROUTER",
            "hw_model": "RAK4631",
        },
        headers=auth_headers,
    )
    client.post(
        "/api/positions",
        json={
            "node_id": "!a1b2c3d4",
            "latitude": 40.5200,
            "longitude": 44.2000,
            "altitude": 3200.0,
        },
        headers=auth_headers,
    )
    client.post(
        "/api/telemetry",
        json={
            "node_id": "!a1b2c3d4",
            "battery_level": 100,
            "voltage": 4.21,
            "channel_utilization": 1.8,
            "snr": 12.0,
            "rssi": -78.0,
        },
        headers=auth_headers,
    )

    # 5. Query GET /api/nodes (used by msh.am Live Dashboard)
    res = client.get("/api/nodes")
    assert res.status_code == 200
    data = res.json()
    assert "nodes" in data
    assert "updatedAt" in data
    assert len(data["nodes"]) >= 2

    # Verify Yundin repeater fields match msh.am contract
    yundin = next(n for n in data["nodes"] if n["id"] == "!f24762e0")
    assert yundin["shortName"] == "YRPT"
    assert yundin["longName"] == "Yundin Repeater"
    assert yundin["role"] == "ROUTER"
    assert yundin["hwModel"] == "RAK4631"
    assert yundin["batteryLevel"] == 98
    assert yundin["voltage"] == 4.18
    assert yundin["region"] == "Yerevan"
    assert yundin["isOnline"] is True

    # Verify Aragats resolved to Mount Aragats
    aragats = next(n for n in data["nodes"] if n["id"] == "!a1b2c3d4")
    assert aragats["region"] == "Mount Aragats"

    # 6. Query GET /nodes alias
    res_alias = client.get("/nodes")
    assert res_alias.status_code == 200

    # 7. Query GET /api/stats
    stats_res = client.get("/api/stats")
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["totalNodes"] >= 2
    assert stats["onlineNodes"] >= 2
    assert stats["activeRouters"] >= 2
    assert stats["avgBattery"] >= 95

    # 8. Query GET /api/status/telegram (for future Telegram bot pinned message)
    tg_res = client.get("/api/status/telegram")
    assert tg_res.status_code == 200
    tg_data = tg_res.json()
    assert "formattedMarkdown" in tg_data
    assert "Aragats Backbone" in tg_data["formattedMarkdown"]
    assert "Yundin Repeater" in tg_data["formattedMarkdown"]
    assert "msh.am/dashboard" in tg_data["formattedMarkdown"]


def test_online_24h_and_one_week_retention(client):
    import time
    from src.services.state_manager import state_manager

    now_ms = int(time.time() * 1000)

    # Node heard 10 hours ago -> Online (< 24h)
    state_manager._nodes["!test_10h"] = {
        "id": "!test_10h",
        "num": 1001,
        "shortName": "T10H",
        "longName": "Test Node 10h",
        "role": "CLIENT",
        "hwModel": "HELTEC_V3",
        "lastHeard": now_ms - (10 * 3600 * 1000),
    }

    # Node heard 2 days ago -> Offline (> 24h), but within 1 week (< 7d) -> included in Total
    state_manager._nodes["!test_2d"] = {
        "id": "!test_2d",
        "num": 1002,
        "shortName": "T2D",
        "longName": "Test Node 2d",
        "role": "CLIENT",
        "hwModel": "HELTEC_V3",
        "lastHeard": now_ms - (2 * 24 * 3600 * 1000),
    }

    # Node heard 8 days ago -> Inactive (> 7d) -> auto-removed from Total
    state_manager._nodes["!test_8d"] = {
        "id": "!test_8d",
        "num": 1003,
        "shortName": "T8D",
        "longName": "Test Node 8d",
        "role": "CLIENT",
        "hwModel": "HELTEC_V3",
        "lastHeard": now_ms - (8 * 24 * 3600 * 1000),
    }

    res = client.get("/api/nodes")
    assert res.status_code == 200
    nodes = res.json()["nodes"]
    node_ids = [n["id"] for n in nodes]

    # !test_10h should be present and online
    n_10h = next((n for n in nodes if n["id"] == "!test_10h"), None)
    assert n_10h is not None
    assert n_10h["isOnline"] is True

    # !test_2d should be present but offline
    n_2d = next((n for n in nodes if n["id"] == "!test_2d"), None)
    assert n_2d is not None
    assert n_2d["isOnline"] is False

    # !test_8d should be auto-removed from Total nodes
    assert "!test_8d" not in node_ids
    assert state_manager.get_node("!test_8d") is None

