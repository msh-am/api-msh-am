"""
SQLite database management for api.msh.am with WAL mode.
"""

from __future__ import annotations

import sqlite3
import logging
from contextlib import contextmanager
from typing import Generator
from src.config import settings

logger = logging.getLogger("msh_am.database")


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(
        str(settings.DATABASE_PATH),
        timeout=10.0,
        detect_types=sqlite3.PARSE_DECLTYPES,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def db_session() -> Generator[sqlite3.Connection, None, None]:
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database transaction error: {e}")
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Initialize database tables and indexes."""
    with db_session() as conn:
        cursor = conn.cursor()

        # Nodes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                num INTEGER,
                short_name TEXT,
                long_name TEXT,
                role TEXT DEFAULT 'CLIENT',
                hw_model TEXT DEFAULT 'UNKNOWN',
                battery_level INTEGER,
                voltage REAL,
                channel_utilization REAL,
                air_util_tx REAL,
                snr REAL,
                rssi REAL,
                hops_away INTEGER DEFAULT 0,
                last_heard INTEGER NOT NULL,
                latitude REAL,
                longitude REAL,
                altitude REAL,
                region TEXT DEFAULT 'Armenia',
                source TEXT DEFAULT 'unknown',
                ignore_mqtt INTEGER DEFAULT 0,
                raw_metadata TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
        """)

        # Telemetry history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                battery_level INTEGER,
                voltage REAL,
                channel_utilization REAL,
                air_util_tx REAL,
                snr REAL,
                rssi REAL,
                FOREIGN KEY (node_id) REFERENCES nodes (id) ON DELETE CASCADE
            );
        """)

        # Position history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                altitude REAL,
                precision REAL,
                FOREIGN KEY (node_id) REFERENCES nodes (id) ON DELETE CASCADE
            );
        """)

        # Public messages log
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                from_id TEXT NOT NULL,
                to_id TEXT DEFAULT '^all',
                text TEXT NOT NULL,
                channel TEXT DEFAULT '0',
                hops INTEGER DEFAULT 0,
                timestamp INTEGER NOT NULL
            );
        """)

        # Neighbors topology
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS neighbors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL,
                neighbor_id TEXT NOT NULL,
                snr REAL,
                timestamp INTEGER NOT NULL,
                FOREIGN KEY (node_id) REFERENCES nodes (id) ON DELETE CASCADE
            );
        """)

        # Ingestors directory
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ingestors (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                protocol TEXT DEFAULT 'Meshtastic',
                connection TEXT,
                last_seen INTEGER NOT NULL
            );
        """)

        # Indexes for query performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_nodes_last_heard ON nodes (last_heard);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_node_ts ON telemetry (node_id, timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_positions_node_ts ON positions (node_id, timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages (timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_neighbors_node ON neighbors (node_id);")

        logger.info("Initialized SQLite database with WAL mode successfully.")
