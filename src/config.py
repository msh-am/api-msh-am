"""
Configuration settings for Meshtastic Armenia API (api.msh.am).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List


class Settings:
    # Server configuration
    HOST: str = os.getenv("API_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("API_PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "0").lower() in ("1", "true", "yes")

    # Security & Tokens
    # API_TOKEN used by PotatoMesh ingestors to authenticate POST requests
    API_TOKEN: str = os.getenv("API_TOKEN", "msh_armenia_super_secret_token")

    # Storage
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", "./data"))
    DATABASE_PATH: Path = Path(os.getenv("DATABASE_PATH", str(DATA_DIR / "msh_am.sqlite3")))

    # MQTT Ingestion Configuration (Local Broker: mqtt.msh.am)
    MQTT_ENABLED: bool = os.getenv("MQTT_ENABLED", "true").lower() in ("1", "true", "yes")
    MQTT_BROKER_HOST: str = os.getenv("MQTT_BROKER_HOST", "localhost")
    MQTT_BROKER_PORT: int = int(os.getenv("MQTT_BROKER_PORT", "1883"))
    MQTT_USERNAME: str | None = os.getenv("MQTT_USERNAME", "meshdev")
    MQTT_PASSWORD: str | None = os.getenv("MQTT_PASSWORD", "large4cats")
    MQTT_TOPIC_PREFIX: str = os.getenv("MQTT_TOPIC_PREFIX", "msh/EU_868/AM/#")
    MQTT_FALLBACK_TOPIC: str = os.getenv("MQTT_FALLBACK_TOPIC", "msh/EU_868/#")
    MQTT_CLIENT_ID: str = os.getenv("MQTT_CLIENT_ID", "msh-am-api-ingestor")

    # Upstream Public MQTT Uplink Configuration (mqtt.meshtastic.org)
    MQTT_UPLINK_ENABLED: bool = os.getenv("MQTT_UPLINK_ENABLED", "true").lower() in ("1", "true", "yes")
    MQTT_UPLINK_BROKER_HOST: str = os.getenv("MQTT_UPLINK_BROKER_HOST", "mqtt.meshtastic.org")
    MQTT_UPLINK_BROKER_PORT: int = int(os.getenv("MQTT_UPLINK_BROKER_PORT", "1883"))
    MQTT_UPLINK_USERNAME: str | None = os.getenv("MQTT_UPLINK_USERNAME", "meshdev")
    MQTT_UPLINK_PASSWORD: str | None = os.getenv("MQTT_UPLINK_PASSWORD", "large4cats")
    MQTT_UPLINK_TOPIC_PREFIX: str = os.getenv("MQTT_UPLINK_TOPIC_PREFIX", "/msh/EU_868/AM/")
    MQTT_UPLINK_CLIENT_ID: str = os.getenv("MQTT_UPLINK_CLIENT_ID", "msh-am-uplink-gateway")

    # Mesh Network Parameters
    ONLINE_THRESHOLD_SECONDS: int = int(os.getenv("ONLINE_THRESHOLD_SECONDS", "900"))  # 15 minutes
    INACTIVE_THRESHOLD_SECONDS: int = int(os.getenv("INACTIVE_THRESHOLD_SECONDS", "7200"))  # 2 hours
    DEFAULT_REGION: str = os.getenv("DEFAULT_REGION", "Armenia")
    PRESET_NAME: str = "MediumFast"
    FREQUENCY_BAND: str = "EU_868"
    CENTER_FREQ: str = "869.525 MHz"

    # Privacy & Safety
    ENABLE_LOCATION_FUZZING: bool = os.getenv("ENABLE_LOCATION_FUZZING", "false").lower() in ("1", "true", "yes")
    FUZZING_DECIMALS: int = int(os.getenv("FUZZING_DECIMALS", "2"))  # ~1.1km precision

    # CORS
    CORS_ORIGINS: List[str] = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "https://msh.am,http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000",
        ).split(",")
        if origin.strip()
    ]


settings = Settings()

# Ensure data directory exists
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
