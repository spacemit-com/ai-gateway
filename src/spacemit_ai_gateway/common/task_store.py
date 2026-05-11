"""异步任务状态管理（内存存储）。

ASR jobs / TTS tasks 各持一个实例。
模式同 SessionStore：内存 dict + asyncio.Lock，适合嵌入式单进程部署。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class TaskRecord:
    task_id: str
    status: TaskStatus
    data: dict
    result: Any = None
    error: Optional[str] = None
    progress: float = 0.0
    created_at: float = 0.0
    updated_at: float = 0.0


class TaskStore:
    def __init__(self, namespace: str = ""):
        self._namespace = namespace
        self._records: dict[str, TaskRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, data: dict) -> TaskRecord:
        task_id = str(uuid.uuid4())
        now = time.time()
        record = TaskRecord(
            task_id=task_id,
            status=TaskStatus.PENDING,
            data=dict(data),
            created_at=now,
            updated_at=now,
        )
        async with self._lock:
            self._records[task_id] = record
        return record

    async def get(self, task_id: str) -> Optional[TaskRecord]:
        async with self._lock:
            return self._records.get(task_id)

    async def update(self, task_id: str, **fields) -> Optional[TaskRecord]:
        async with self._lock:
            record = self._records.get(task_id)
            if record is None:
                return None
            for k, v in fields.items():
                if hasattr(record, k):
                    setattr(record, k, v)
            record.updated_at = time.time()
            return record

    async def delete(self, task_id: str) -> bool:
        async with self._lock:
            return self._records.pop(task_id, None) is not None

    async def list_all(self) -> list[TaskRecord]:
        async with self._lock:
            return list(self._records.values())
