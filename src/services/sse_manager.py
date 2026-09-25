"""
Server-Sent Events (SSE) manager for live streaming packet updates.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Set, Dict, Any

logger = logging.getLogger("msh_am.sse")


class SSEManager:
    def __init__(self):
        self._subscribers: Set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(q)
        logger.debug(f"New SSE subscriber. Active subscribers: {len(self._subscribers)}")
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)
        logger.debug(f"SSE subscriber removed. Active subscribers: {len(self._subscribers)}")

    async def broadcast(self, event_type: str, data: Dict[str, Any]) -> None:
        if not self._subscribers:
            return

        payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        for q in list(self._subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("Subscriber queue full, discarding slow subscriber.")
                self._subscribers.discard(q)


sse_manager = SSEManager()
