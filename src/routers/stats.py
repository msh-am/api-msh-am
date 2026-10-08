"""
Network statistics and Telegram status summary endpoints.
"""

from __future__ import annotations

import json
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Request, Query

from src.database import db_session
from src.models.mesh import MeshNetworkStats, TelegramStatusSummary
from src.services.state_manager import state_manager

router = APIRouter(prefix="/api", tags=["Statistics & Status"])


@router.get("/stats", response_model=MeshNetworkStats)
async def get_stats(request: Request) -> MeshNetworkStats:
    endpoint_url = str(request.url_for("get_nodes"))
    return state_manager.get_stats(endpoint_url=endpoint_url)


@router.get("/status/summary", response_model=TelegramStatusSummary)
@router.get("/status/telegram", response_model=TelegramStatusSummary)
async def get_telegram_status_summary() -> TelegramStatusSummary:
    """
    Dedicated endpoint returning network health and pre-rendered markdown
    designed for a downstream Telegram bot to edit the pinned status message
    in @mesh_am without notification spam.
    """
    return state_manager.get_telegram_summary()


@router.get("/messages")
async def get_messages(
    limit: int = Query(50, ge=1, le=200),
    channel: Optional[str] = Query(None),
) -> List[Dict[str, Any]]:
    """Get recent public messages heard on the mesh enriched with sender and receiver telemetry."""
    messages = []
    base_sql = """
        SELECT m.id, m.from_id, m.to_id, m.text, m.channel, m.hops, m.timestamp, m.heard_by,
               n.short_name, n.long_name, n.role, n.latitude, n.longitude, n.region
        FROM messages m
        LEFT JOIN nodes n ON m.from_id = n.id
    """
    with db_session() as conn:
        cursor = conn.cursor()
        if channel is not None:
            cursor.execute(
                f"""
                {base_sql}
                WHERE m.channel = ?
                ORDER BY m.timestamp DESC
                LIMIT ?;
                """,
                (str(channel), limit),
            )
        else:
            cursor.execute(
                f"""
                {base_sql}
                ORDER BY m.timestamp DESC
                LIMIT ?;
                """,
                (limit,),
            )
        for row in cursor.fetchall():
            row_dict = dict(row)
            heard_by_raw = row_dict.get("heard_by")
            heard_by_list = []
            if heard_by_raw:
                try:
                    heard_by_list = json.loads(heard_by_raw) if isinstance(heard_by_raw, str) else heard_by_raw
                except Exception:
                    heard_by_list = []

            from_id = row_dict.get("from_id", "")
            short_name = row_dict.pop("short_name", None) or (from_id[-4:].upper() if len(from_id) >= 4 else "NODE")
            long_name = row_dict.pop("long_name", None) or f"Node {from_id}"

            row_dict["from_short_name"] = short_name
            row_dict["from_long_name"] = long_name
            row_dict["heard_by"] = heard_by_list
            messages.append(row_dict)
    return messages
