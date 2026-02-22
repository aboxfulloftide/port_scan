"""
Broadcast scan progress events to connected WebSocket clients.
Each WebSocket subscriber gets its own asyncio.Queue.
"""
import asyncio
from typing import Dict, Set

# job_id -> set of asyncio.Queue (one per WS client)
_subscribers: Dict[int, Set[asyncio.Queue]] = {}


def subscribe(job_id: int) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=256)
    _subscribers.setdefault(job_id, set()).add(q)
    return q


def unsubscribe(job_id: int, q: asyncio.Queue):
    if job_id in _subscribers:
        _subscribers[job_id].discard(q)
        if not _subscribers[job_id]:
            del _subscribers[job_id]


async def broadcast(job_id: int, event: dict):
    for q in list(_subscribers.get(job_id, [])):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass  # slow consumer — drop event
