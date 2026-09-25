"""
Network statistics and Telegram status summary endpoints.
"""

from __future__ import annotations

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
    """Get recent public messages heard on the mesh."""
    messages = []
    with db_session() as conn:
        cursor = conn.cursor()
        if channel is not None:
            cursor.execute(
                """
                SELECT id, from_id, to_id, text, channel, hops, timestamp
                FROM messages
                WHERE channel = ?
                ORDER BY timestamp DESC
                LIMIT ?;
                """,
                (channel, limit),
            )
        else:
            cursor.execute(
                """
                SELECT id, from_id, to_id, text, channel, hops, timestamp
                FROM messages
                ORDER BY timestamp DESC
                LIMIT ?;
                """,
                (limit,),
            )
        for row in cursor.fetchall():
            messages.append(dict(row))
    return messages
