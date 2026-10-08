"""模型故障记录：下载 / 加载 / 推理阶段的错误按"域 + 模型"落盘，供 GET /v1/errors/recent 查询。

出错的地方用 mark_fault() 标上域和模型；HTTP 异常处理、WS 错误边界、流式错误帧、
后台下载任务等出口调用 record_fault() 统一记录。没有标记的错误（调用方参数错误等）不记录。

记录存 SQLite（~/.cache/spacemit-ai-gateway/errors.sqlite），gateway 或开发板重启后仍可查询；
只保留最近 max_rows 条。数据库打不开或写失败时退回内存，不影响业务请求。
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .error_catalog import lookup
from .errors import DomainError

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path("~/.cache/spacemit-ai-gateway/errors.sqlite")
MAX_ROWS = 2000

# 只记录模型故障。没加载 / 没下载 / 正在下载是调用顺序问题，用户取消下载也不算故障
_FAULT_PHASES = {"download", "load", "inference"}
_SKIP_CODES = {"model_not_loaded", "model_not_downloaded", "model_downloading", "cancelled"}

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS errors (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL NOT NULL,
    domain    TEXT NOT NULL,
    model     TEXT,
    code      TEXT NOT NULL,
    phase     TEXT NOT NULL,
    message   TEXT,
    retriable INTEGER,
    details   TEXT
)
"""


class ErrorLog:
    def __init__(self, max_rows: int = MAX_ROWS) -> None:
        self._max_rows = max_rows
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        self._memory: deque[dict] = deque(maxlen=max_rows)  # 没能落盘的记录

    def open(self, path: Path) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path, check_same_thread=False)
            conn.execute(_CREATE_SQL)
            conn.commit()
        except (OSError, sqlite3.Error) as exc:
            logger.warning("cannot open error log %s, keeping errors in memory only: %s", path, exc)
            return
        with self._lock:
            self._conn = conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    async def add(self, entry: dict) -> None:
        await asyncio.to_thread(self._add_sync, entry)

    def _add_sync(self, entry: dict) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.execute(
                        "INSERT INTO errors (ts, domain, model, code, phase, message, retriable, details)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (entry["ts"], entry["domain"], entry["model"], entry["code"], entry["phase"],
                         entry["message"], int(bool(entry["retriable"])),
                         json.dumps(entry["details"], ensure_ascii=False, default=str)),
                    )
                    self._conn.execute(
                        "DELETE FROM errors WHERE id <= "
                        "(SELECT id FROM errors ORDER BY id DESC LIMIT 1 OFFSET ?)",
                        (self._max_rows,),
                    )
                    self._conn.commit()
                    return
                except sqlite3.Error as exc:
                    logger.warning("failed to persist error record, keeping it in memory: %s", exc)
            self._memory.append(entry)

    async def query(
        self,
        *,
        domain: Optional[str] = None,
        model: Optional[str] = None,
        since: Optional[float] = None,
        limit: int = 100,
    ) -> list[dict]:
        return await asyncio.to_thread(self._query_sync, domain, model, since, limit)

    def _query_sync(self, domain, model, since, limit) -> list[dict]:
        def keep(e: dict) -> bool:
            return ((domain is None or e["domain"] == domain)
                    and (model is None or e["model"] == model)
                    and (since is None or e["ts"] > since))

        rows: list[dict] = []
        with self._lock:
            if self._conn is not None:
                sql = "SELECT ts, domain, model, code, phase, message, retriable, details FROM errors WHERE 1=1"
                args: list[Any] = []
                for column, value in (("domain", domain), ("model", model)):
                    if value is not None:
                        sql += f" AND {column} = ?"
                        args.append(value)
                if since is not None:
                    sql += " AND ts > ?"
                    args.append(since)
                sql += " ORDER BY id DESC LIMIT ?"
                args.append(limit)
                for r in self._conn.execute(sql, args).fetchall():
                    rows.append({
                        "ts": r[0], "domain": r[1], "model": r[2], "code": r[3], "phase": r[4],
                        "message": r[5], "retriable": bool(r[6]),
                        "details": json.loads(r[7]) if r[7] else None,
                    })
            rows.extend(e for e in self._memory if keep(e))
        rows.sort(key=lambda e: e["ts"], reverse=True)
        return [_view(e) for e in rows[:limit]]


def _view(entry: dict) -> dict:
    return {**entry, "time": datetime.fromtimestamp(entry["ts"]).astimezone().isoformat(timespec="seconds")}


_store = ErrorLog()


def open_log(path: Path = DEFAULT_PATH) -> None:
    _store.open(Path(path).expanduser())


def close_log() -> None:
    _store.close()


async def query_faults(**filters) -> list[dict]:
    return await _store.query(**filters)


def mark_fault(exc: BaseException, domain: str, model: Optional[str]) -> BaseException:
    """标记错误属于哪个域、哪个模型。已有标记不覆盖（最内层的标记最准确）。"""
    if domain and getattr(exc, "fault_domain", None) is None:
        exc.fault_domain = domain  # type: ignore[attr-defined]
        exc.fault_model = model  # type: ignore[attr-defined]
    return exc


def _code_of(exc: BaseException) -> str:
    if isinstance(exc, DomainError):
        return exc.code
    error = getattr(exc, "error", None)  # Vision ServiceError 的字符串错误码
    return error if isinstance(error, str) and error else "internal_error"


async def record_fault(exc: BaseException) -> None:
    """记录已标记的模型故障；同一个异常对象只记一次。记录失败不影响调用方。"""
    domain = getattr(exc, "fault_domain", None)
    if domain is None or getattr(exc, "fault_recorded", False):
        return
    code = _code_of(exc)
    item = lookup(code)
    if item is None or item["phase"] not in _FAULT_PHASES or code in _SKIP_CODES:
        return
    exc.fault_recorded = True  # type: ignore[attr-defined]
    try:
        await _store.add({
            "ts": time.time(),
            "domain": domain,
            "model": getattr(exc, "fault_model", None),
            "code": code,
            "phase": item["phase"],
            "message": getattr(exc, "message", None) or str(exc),
            "retriable": bool(getattr(exc, "retriable", False)),
            "details": getattr(exc, "details", None),
        })
    except Exception:
        logger.warning("failed to record model fault", exc_info=True)
