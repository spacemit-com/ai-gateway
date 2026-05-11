"""词库内存存储。

ASR 热词词库 / TTS 发音词典各持一个实例。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional


class LexiconStore:
    def __init__(self, namespace: str = ""):
        self._namespace = namespace
        self._records: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def list_all(self) -> list[dict]:
        async with self._lock:
            return list(self._records.values())

    async def create(self, entries: list[dict], **extra) -> dict:
        lexicon_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        record = {
            "id": lexicon_id,
            "entries": list(entries),
            "created_at": now,
            **extra,
        }
        async with self._lock:
            self._records[lexicon_id] = record
        return record

    async def get(self, lexicon_id: str) -> Optional[dict]:
        async with self._lock:
            return self._records.get(lexicon_id)

    async def delete(self, lexicon_id: str) -> bool:
        async with self._lock:
            return self._records.pop(lexicon_id, None) is not None
