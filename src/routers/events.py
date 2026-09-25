"""
Server-Sent Events (SSE) live streaming endpoint.
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.services.sse_manager import sse_manager

router = APIRouter(prefix="/api", tags=["Real-Time Streaming"])


async def event_generator(request: Request) -> AsyncGenerator[str, None]:
    q = sse_manager.subscribe()
    try:
        # Initial hello event
        yield "event: connected\ndata: {\"status\": \"connected\"}\n\n"

        while True:
            if await request.is_disconnected():
                break

            try:
                # Wait for next event or 15-second heartbeat
                payload = await asyncio.wait_for(q.get(), timeout=15.0)
                yield payload
            except asyncio.TimeoutError:
                # Keep-alive comment to keep proxies from closing connection
                yield ": keep-alive\n\n"
    finally:
        sse_manager.unsubscribe(q)


@router.get("/events")
async def sse_events(request: Request):
    """
    Live stream of node updates, telemetry, and messages via Server-Sent Events (SSE).
    """
    return StreamingResponse(
        event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
