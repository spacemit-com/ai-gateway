"""Per-domain 会话存储。

ASR/TTS 各持一个实例（VAD 无状态不需要），避免 session_id 命名空间冲突
与 TTL 串用。支持 per-record TTL 覆写，默认走 store 级 ttl。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Optional


@dataclass
class SessionRecord:
    session_id: str
    data: dict
    created_at: float
    expires_at: float

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at


class SessionStore:
    def __init__(self, ttl_seconds: int, namespace: str = ""):
        self._ttl = ttl_seconds
        self._namespace = namespace
        self._records: dict[str, SessionRecord] = {}
        self._lock = asyncio.Lock()

    @property
    def namespace(self) -> str:
        return self._namespace

    @property
    def default_ttl(self) -> int:
        return self._ttl

    async def create(self, data: dict, ttl: Optional[int] = None) -> SessionRecord:
        session_id = str(uuid.uuid4())
        now = time.time()
        record = SessionRecord(
            session_id=session_id,
            data=dict(data),
            created_at=now,
            expires_at=now + (ttl if ttl is not None else self._ttl),
        )
        async with self._lock:
            self._records[session_id] = record
        return record

    async def get(self, session_id: str) -> Optional[SessionRecord]:
        async with self._lock:
            record = self._records.get(session_id)
            if record is None:
                return None
            if record.expired:
                del self._records[session_id]
                return None
            return record

    async def pop(self, session_id: str) -> Optional[SessionRecord]:
        async with self._lock:
            record = self._records.pop(session_id, None)
            if record and record.expired:
                return None
            return record

    async def purge_expired(self) -> int:
        now = time.time()
        async with self._lock:
            expired = [sid for sid, r in self._records.items() if r.expires_at <= now]
            for sid in expired:
                del self._records[sid]
            return len(expired)

    async def size(self) -> int:
        async with self._lock:
            return len(self._records)
