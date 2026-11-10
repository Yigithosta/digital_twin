"""
Süreç içi olay dağıtıcısı.

Veri hattı her okumayı ve alarmı buraya yayınlar; /stream (SSE) uç noktası
bağlı tarayıcılara iletir. Yavaş kalan bir abone diğerlerini bekletmez:
kuyruğu dolarsa en eski olayı düşer.
"""

import asyncio
from typing import Set

_subscribers: Set[asyncio.Queue] = set()


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue):
    _subscribers.discard(q)


def publish(event: dict):
    for q in list(_subscribers):
        if q.full():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
        q.put_nowait(event)


def subscriber_count() -> int:
    return len(_subscribers)
