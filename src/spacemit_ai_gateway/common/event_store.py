"""AI 调用事件环形缓冲区。"""

from __future__ import annotations

import time
from collections import deque


class EventStore:
    def __init__(self, maxlen: int = 3600):
        self._events: deque[dict] = deque(maxlen=maxlen)

    def record(self, domain: str, endpoint: str) -> None:
        self._events.append(
            {"domain": domain, "endpoint": endpoint, "ts": time.time()}
        )

    def since(self, ts: float) -> list[dict]:
        return [e for e in self._events if e["ts"] > ts]
