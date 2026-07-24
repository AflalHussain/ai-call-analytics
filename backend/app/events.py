"""In-process pub/sub for the SSE stream.

Single-process only, which is exactly right here: one uvicorn worker serving one
demo room. If this ever needs to scale out, swap the broker for Postgres
LISTEN/NOTIFY — the interface stays the same.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

_subscribers: set[asyncio.Queue] = set()


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


def publish(event: str, data: Any) -> None:
    """Fan out to every connected dashboard. Never blocks; drops on a full queue."""
    payload = f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
    for q in list(_subscribers):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            # A wedged client must not stall ingest.
            unsubscribe(q)


def subscriber_count() -> int:
    return len(_subscribers)
