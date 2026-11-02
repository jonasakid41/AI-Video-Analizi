"""Arayüze anlık olay yayını (WebSocket). İş parçacıklarından güvenle çağrılabilir."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

_lock = threading.Lock()
_subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()


def subscribe(loop: asyncio.AbstractEventLoop) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=1000)
    with _lock:
        _subscribers.add((loop, q))
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    with _lock:
        for item in list(_subscribers):
            if item[1] is q:
                _subscribers.discard(item)


def publish(kind: str, **data: Any) -> None:
    msg = {"type": kind, **data}
    with _lock:
        subs = list(_subscribers)
    for loop, q in subs:
        try:
            loop.call_soon_threadsafe(_put, q, msg)
        except RuntimeError:
            pass


def _put(q: asyncio.Queue, msg: dict) -> None:
    if q.full():
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            pass
    q.put_nowait(msg)
