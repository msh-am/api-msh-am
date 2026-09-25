#!/usr/bin/env python3
"""
Seed Armenian Mesh Nodes & Telemetry into api.msh.am.
Can write directly to SQLite or push to http://localhost:8000/api via HTTP.
"""

from __future__ import annotations

import os
import sys
import time
import argparse
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import settings
from src.database import init_db
from src.services.state_manager import state_manager
import asyncio

# Key Armenian mesh nodes
ARMENIA_SEED_NODES = [
    {
        "id": "!f24762e0",
        "num": 4064764640,
        "short_name": "YRPT",
        "long_name": "Yundin Repeater",
        "role": "ROUTER",
        "hw_model": "RAK4631",
        "battery_level": 98,
        "voltage": 4.18,
        "channel_utilization": 2.6,
        "air_util_tx": 1.1,
        "snr": 9.5,
        "rssi": -85.0,
        "hops_away": 1,
        "latitude": 40.1792,
        "longitude": 44.4991,
        "altitude": 1050.0,
        "region": "Yerevan",
    },
    {
        "id": "!a1b2c3d4",
        "num": 2712847316,
        "short_name": "ARAG",
        "long_name": "Aragats Backbone Repeater",
        "role": "ROUTER",
        "hw_model": "RAK4631",
        "battery_level": 100,
        "voltage": 4.22,
        "channel_utilization": 1.9,
        "air_util_tx": 0.8,
        "snr": 12.0,
        "rssi": -78.0,
        "hops_away": 1,
        "latitude": 40.5200,
        "longitude": 44.2000,
        "altitude": 3200.0,
        "region": "Mount Aragats",
    },
    {
        "id": "!c4d5e6f7",
        "num": 3302352631,
        "short_name": "SEVN",
        "long_name": "Lake Sevan Peninsula Repeater",
        "role": "ROUTER",
        "hw_model": "RAK4631",
        "battery_level": 94,
        "voltage": 4.12,
        "channel_utilization": 2.1,
        "air_util_tx": 0.9,
        "snr": 8.5,
        "rssi": -92.0,
        "hops_away": 2,
        "latitude": 40.5630,
        "longitude": 44.9750,
        "altitude": 1920.0,
        "region": "Lake Sevan",
    },
    {
        "id": "!4355ec68",
        "num": 1129704552,
        "short_name": "cnac",
        "long_name": "Hacker Embassy hackem.cc",
        "role": "ROUTER",
        "hw_model": "RAK4631",
        "battery_level": 100,
        "voltage": 4.20,
        "channel_utilization": 3.1,
        "air_util_tx": 1.2,
        "snr": 11.2,
        "rssi": -81.0,
        "hops_away": 1,
        "latitude": 40.1850,
        "longitude": 44.5120,
        "altitude": 1020.0,
        "region": "Yerevan",
    },
    {
        "id": "!bba93b84",
        "num": 3148422020,
        "short_name": "😺",
        "long_name": "mooncat",
        "role": "CLIENT",
        "hw_model": "T_ECHO",
        "battery_level": 100,
        "voltage": 4.18,
        "channel_utilization": 2.4,
        "air_util_tx": 0.5,
        "snr": 10.0,
        "rssi": -88.0,
        "hops_away": 2,
        "latitude": 40.1810,
        "longitude": 44.5050,
        "altitude": 1010.0,
        "region": "Yerevan",
    },
    {
        "id": "!d3f8bee5",
        "num": 3556294373,
        "short_name": "him",
        "long_name": "himura",
        "role": "CLIENT",
        "hw_model": "HELTEC_V3",
        "battery_level": 100,
        "voltage": 4.20,
        "channel_utilization": 2.2,
        "air_util_tx": 0.6,
        "snr": 8.0,
        "rssi": -90.0,
        "hops_away": 1,
        "latitude": 40.1920,
        "longitude": 44.4980,
        "altitude": 1030.0,
        "region": "Yerevan",
    },
]


async def seed_direct():
    print(f"Initializing database at {settings.DATABASE_PATH}...")
    init_db()

    for item in ARMENIA_SEED_NODES:
        node_id = item["id"]
        print(f"Seeding {item['short_name']} ({item['long_name']}) [{item['role']}]...")
        await state_manager.update_node_info(
            node_id=node_id,
            num=item["num"],
            short_name=item["short_name"],
            long_name=item["long_name"],
            role=item["role"],
            hw_model=item["hw_model"],
            source="seed",
        )
        await state_manager.update_telemetry(
            node_id=node_id,
            battery_level=item.get("battery_level"),
            voltage=item.get("voltage"),
            channel_utilization=item.get("channel_utilization"),
            air_util_tx=item.get("air_util_tx"),
            snr=item.get("snr"),
            rssi=item.get("rssi"),
            source="seed",
        )
        if item.get("latitude") and item.get("longitude"):
            await state_manager.update_position(
                node_id=node_id,
                latitude=item["latitude"],
                longitude=item["longitude"],
                altitude=item.get("altitude"),
                source="seed",
            )

    stats = state_manager.get_stats()
    print("\n✅ Seeding complete!")
    print(f"Total Nodes: {stats.totalNodes}")
    print(f"Online Nodes: {stats.onlineNodes}")
    print(f"Active Routers: {stats.activeRouters}")
    print(f"Average Battery: {stats.avgBattery}%")


if __name__ == "__main__":
    asyncio.run(seed_direct())
