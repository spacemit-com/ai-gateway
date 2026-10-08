import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Generic, TypeVar

import aiosqlite
import httpx

from ..app.settings import DownloadConfig
from .downloader import DownloadError, _to_download_error, fetch_file, partial_size, run_extract
from .error_log import mark_fault, record_fault
from .enums import ModelStatus
from .errors import (
    BackendCrashed,
    DomainError,
    DownloadInProgress,
    DownloadNotSupported,
    ModelAlreadyDownloaded,
    ModelDownloading,
    ModelLoadFailed,
    ModelNotDownloaded,
    ModelNotFound,
    NoActiveDownload,
    NoModelLoaded,
)
from .llama_process import adapter_returncode, process_log_path, read_log_tail
from .proxy_response import classify_stream_errors
from .ready_state import BackendReadyState

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS models (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL DEFAULT 'local_url',
    url TEXT,
    local_path TEXT,
    api_base_url TEXT,
    api_key TEXT,
    status TEXT NOT NULL DEFAULT 'available',
    is_preset INTEGER NOT NULL DEFAULT 0,
    download_progress REAL DEFAULT 0
)
"""

# 下载状态与失败原因（旧库启动时自动补列）
_DOWNLOAD_COLUMNS = (
    ("error_code", "TEXT"),
    ("error_message", "TEXT"),
    ("error_retriable", "INTEGER"),
    ("downloaded_bytes", "INTEGER DEFAULT 0"),
    ("total_bytes", "INTEGER"),
    ("checksum", "TEXT"),
    ("updated_at", "REAL"),
)


def _local_model_ready(path: Path) -> bool:
    """文件非空，或目录（VLM 解压目录）里有 gguf。"""
    try:
        if path.is_dir():
            return any(path.rglob("*.gguf"))
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False

TBackend = TypeVar("TBackend")
TConfig = TypeVar("TConfig")


class BaseModelService(ABC, Generic[TBackend, TConfig]):
    """LLM/Embed/Rerank 三域的通用基类，封装模型生命周期管理逻辑。"""

    domain: str = ""  # 子类填 llm / embed / rerank / vlm，用于故障记录

    def __init__(
        self,
        backends: dict[str, TBackend],
        default: str,
        config: TConfig,
        download_config: DownloadConfig | None = None,
    ):
        self._backends = backends
        self._default = default
        self.settings = config
        self._download_config = download_config or DownloadConfig()
        self._db: aiosqlite.Connection | None = None
        self._current_model: str | None = None
        self._current_source_type: str | None = None
        self._download_tasks: dict[str, asyncio.Task] = {}
        self._user_cancelled: set[str] = set()
        self._loading_events: dict[str, asyncio.Event] = {}

    @property
    def backend_name(self) -> str:
        return self._default

    @property
    def backend(self) -> TBackend:
        return self._backends[self._default]

    def get_current_model(self) -> str | None:
        """返回当前活跃模型的 ID。"""
        return self._current_model

    def get_current_source_type(self) -> str | None:
        """返回当前活跃模型的 source_type。"""
        return self._current_source_type

    @property
    @abstractmethod
    def adapter(self):
        """当前活跃模型的 Adapter，供 api.py 只读访问。子类实现。"""
        pass

    @abstractmethod
    def _get_backend_impl(self) -> Any:
        """返回具体的 Backend 实现（用于访问 _remote_adapters、is_model_running 等）。"""
        pass

    async def initialize(self) -> None:
        db_file = self.settings.storage.db_file
        db_file.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(db_file)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute(CREATE_TABLE_SQL)
        await self._migrate()
        await self._db.commit()
        await self._reset_stale_status()
        await self._sync_preset_models()

    async def _migrate(self) -> None:
        async with self._db.execute("PRAGMA table_info(models)") as cur:
            existing = {row["name"] for row in await cur.fetchall()}
        for name, ddl in _DOWNLOAD_COLUMNS:
            if name not in existing:
                await self._db.execute(f"ALTER TABLE models ADD COLUMN {name} {ddl}")

    async def _reset_stale_status(self) -> None:
        """重启后清理 loading/loaded/downloading 状态（旧进程和下载任务已不存在）。"""
        async with self._db.execute(
            "SELECT id, local_path, status FROM models WHERE status IN (?, ?, ?) AND source_type != 'remote'",
            (ModelStatus.LOADING, ModelStatus.LOADED, ModelStatus.DOWNLOADING),
        ) as cur:
            rows = await cur.fetchall()

        downloaded = 0
        available = 0
        for row in rows:
            local_path = row["local_path"]
            if row["status"] == ModelStatus.DOWNLOADING:
                # 下载被进程退出打断：保留 .gwpart 与已下载字节数，下次下载时续传
                await self._db.execute(
                    "UPDATE models SET status=? WHERE id=?", (ModelStatus.AVAILABLE, row["id"])
                )
                available += 1
                continue
            if local_path and _local_model_ready(Path(local_path)):
                await self._db.execute(
                    "UPDATE models SET status=? WHERE id=?",
                    (ModelStatus.DOWNLOADED, row["id"]),
                )
                downloaded += 1
            else:
                await self._reset_missing_local_file(row["id"], commit=False)
                available += 1

        if rows:
            logger.info(
                "[startup] reset %d stale model(s): %d downloaded, %d available",
                len(rows),
                downloaded,
                available,
            )
        await self._db.commit()

    async def warmup(self) -> None:
        if self._db is None:
            await self.initialize()
        if self._current_model and self._current_source_type != "remote":
            backend_impl = self._get_backend_impl()
            if backend_impl.is_model_running(self._current_model):
                adapter = backend_impl.get_adapter(self._current_model)
                if adapter:
                    await adapter.warmup()

    async def shutdown(self) -> None:
        # 先停下载（保留 .gwpart 供下次续传），再关数据库
        tasks = list(self._download_tasks.values())
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        backend_impl = self._get_backend_impl()
        await backend_impl.shutdown()
        if self._db:
            await self._db.close()

    async def healthz(self) -> dict:
        """健康检查，返回当前服务状态。"""
        if self._db is None:
            state = BackendReadyState.INITIALIZING
        elif self._current_model is None:
            state = BackendReadyState.IDLE
        else:
            source_type = self._current_source_type
            if source_type == "remote":
                state = BackendReadyState.READY
            else:
                # 检查 ModelStatus：LOADING 中 → WARMING_UP
                row = None
                try:
                    row = await self._get_model(self._current_model)
                except Exception:
                    pass
                if row and row["status"] == ModelStatus.LOADING:
                    state = BackendReadyState.WARMING_UP
                elif self.adapter is not None and self.adapter.is_running():
                    state = BackendReadyState.READY
                else:
                    state = BackendReadyState.DEGRADED
        return {
            "ready": state.is_serving,
            "state": state.value,
            "backend": self._current_model,
        }

    async def _sync_preset_models(self) -> None:
        for m in self.settings.preset_models:
            async with self._db.execute("SELECT id, status, local_path FROM models WHERE id = ?", (m["id"],)) as cur:
                row = await cur.fetchone()
            url = m.get("url", "")
            local_dir = m.get("local_dir")
            if local_dir:
                expected_path = self.settings.storage.models_path / local_dir
            else:
                filename = url.split("/")[-1] if url else f"{m['id']}.gguf"
                expected_path = self.settings.storage.models_path / filename
            if row is None:
                if _local_model_ready(expected_path):
                    await self._db.execute(
                        "INSERT INTO models (id, source_type, url, local_path, status, is_preset, download_progress)"
                        " VALUES (?,?,?,?,?,1,1.0)",
                        (m["id"], "local_url", url, str(expected_path), ModelStatus.DOWNLOADED),
                    )
                else:
                    await self._db.execute(
                        "INSERT INTO models (id, source_type, url, status, is_preset)"
                        " VALUES (?,?,?,?,1)",
                        (m["id"], "local_url", url, ModelStatus.AVAILABLE),
                    )
                await self._db.commit()
            else:
                if row["local_path"] != str(expected_path):
                    if _local_model_ready(expected_path):
                        await self._db.execute(
                            "UPDATE models SET local_path=?, status=?, download_progress=1.0 WHERE id=?",
                            (str(expected_path), ModelStatus.DOWNLOADED, m["id"]),
                        )
                    else:
                        await self._db.execute(
                            "UPDATE models SET local_path=NULL, status=?, download_progress=0 WHERE id=?",
                            (ModelStatus.AVAILABLE, m["id"]),
                        )
                    await self._db.commit()

    async def list_models(self) -> list[dict]:
        async with self._db.execute("SELECT * FROM models") as cur:
            rows = await cur.fetchall()
        return [await self._sync_file_status(dict(row)) for row in rows]

    async def register(
        self,
        model: str,
        source_type: str = "local_url",
        url: str | None = None,
        local_path: str | None = None,
        api_base_url: str | None = None,
        api_key: str | None = None,
    ) -> dict:
        existing = await self._get_model(model)
        if existing:
            raise ValueError(f"Model '{model}' already registered")

        if source_type == "local_path":
            if not local_path:
                raise ValueError("local_path is required for source_type=local_path")
            if not Path(local_path).exists():
                raise ValueError(f"File not found: {local_path}")
            status = ModelStatus.DOWNLOADED
        elif source_type == "remote":
            status = ModelStatus.LOADED
        else:
            status = ModelStatus.AVAILABLE

        await self._db.execute(
            "INSERT INTO models (id, source_type, url, local_path, api_base_url, api_key, status, is_preset)"
            " VALUES (?,?,?,?,?,?,?,0)",
            (model, source_type, url or "", local_path or "", api_base_url or "", api_key or "", status),
        )
        await self._db.commit()
        return {"model": model, "status": status}

    async def _get_model(self, model: str) -> dict | None:
        async with self._db.execute("SELECT * FROM models WHERE id = ?", (model,)) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def _set_status(self, model: str, status: ModelStatus, progress: float | None = None) -> None:
        if progress is not None:
            await self._db.execute(
                "UPDATE models SET status=?, download_progress=? WHERE id=?", (status, progress, model)
            )
        else:
            await self._db.execute("UPDATE models SET status=? WHERE id=?", (status, model))
        await self._db.commit()

    async def _reset_missing_local_file(self, model: str, commit: bool = True) -> None:
        await self._db.execute(
            "UPDATE models SET status=?, local_path=NULL, download_progress=0 WHERE id=?",
            (ModelStatus.AVAILABLE, model),
        )
        if commit:
            await self._db.commit()

    async def _update(self, model: str, **fields: Any) -> None:
        fields["updated_at"] = time.time()
        columns = ", ".join(f"{name}=?" for name in fields)
        await self._db.execute(
            f"UPDATE models SET {columns} WHERE id=?", (*fields.values(), model)
        )
        await self._db.commit()

    def _preset_local_dir(self, model: str) -> str | None:
        for m in self.settings.preset_models:
            if m["id"] == model:
                return m.get("local_dir")
        return None

    def _download_dest(self, row: dict) -> Path | None:
        url = row.get("url") or ""
        return self.settings.storage.models_path / url.split("/")[-1] if url else None

    def _expected_local_path(self, row: dict) -> str | None:
        local_dir = self._preset_local_dir(row["id"])
        if local_dir:
            return str(self.settings.storage.models_path / local_dir)
        dest = self._download_dest(row)
        return str(dest) if dest else None

    async def _sync_file_status(self, row: dict) -> dict:
        """根据文件是否就绪修正 DB 状态，返回修正后的 row。非本地模型直接返回原 row。

        - 下载失败（error）在文件不存在时保持 error，直到重新下载
        - 没有对应下载任务的 downloading（进程重启、任务已结束）不再显示为下载中
        """
        if row["source_type"] == "remote":
            return row
        model = row["id"]
        local_path = row.get("local_path") or self._expected_local_path(row)
        ready = bool(local_path) and _local_model_ready(Path(local_path))
        status = row["status"]
        if status == ModelStatus.DOWNLOADING and model not in self._download_tasks:
            status = ModelStatus.DOWNLOADED if ready else ModelStatus.AVAILABLE
            await self._update(model, status=status)
            row = {**row, "status": status}
        active_statuses = (ModelStatus.DOWNLOADED, ModelStatus.LOADED, ModelStatus.LOADING, ModelStatus.DOWNLOADING)
        if ready and status not in active_statuses:
            await self._update(
                model, status=ModelStatus.DOWNLOADED, local_path=local_path,
                download_progress=1.0, error_code=None, error_message=None,
            )
            return {
                **row, "status": ModelStatus.DOWNLOADED, "local_path": local_path,
                "download_progress": 1.0, "error_code": None, "error_message": None,
            }
        if ready and not row.get("local_path"):
            await self._update(model, local_path=local_path)
            return {**row, "local_path": local_path}
        if not ready and status not in (ModelStatus.AVAILABLE, ModelStatus.DOWNLOADING, ModelStatus.ERROR):
            await self._reset_missing_local_file(model)
            return {**row, "status": ModelStatus.AVAILABLE, "local_path": None, "download_progress": 0}
        return row

    async def _download(self, model: str, url: str, dest: Path) -> None:
        local_dir = self._preset_local_dir(model)
        is_archive = bool(local_dir) and str(dest).endswith((".tar.gz", ".tgz"))
        # 旧版本下载留下的临时文件
        dest.with_suffix(dest.suffix + ".tmp").unlink(missing_ok=True)
        await self._update(
            model, status=ModelStatus.DOWNLOADING, download_progress=0.0,
            downloaded_bytes=partial_size(dest), error_code=None, error_message=None,
            error_retriable=None, checksum=None,
        )

        async def report(done: int, total: int | None) -> None:
            await self._update(
                model, downloaded_bytes=done, total_bytes=total,
                download_progress=round(done / total, 4) if total else 0.0,
            )

        try:
            ratio = self._download_config.archive_extract_ratio if is_archive else 0.0
            result = await fetch_file(
                url, dest, config=self._download_config, on_progress=report, extract_ratio=ratio,
                discard_on_cancel=lambda: model in self._user_cancelled,
            )
            final_path = dest
            if is_archive:
                # 解压到临时目录后整体替换，失败不会留下半个目录；成功后删除压缩包
                extract_dir = self.settings.storage.models_path / local_dir
                await run_extract(dest, extract_dir, replace=True)
                dest.unlink(missing_ok=True)
                logger.info("Extracted %s to %s", dest.name, extract_dir)
                final_path = extract_dir
            await self._update(
                model, status=ModelStatus.DOWNLOADED, local_path=str(final_path),
                download_progress=1.0, downloaded_bytes=result.size, total_bytes=result.size,
                checksum=result.checksum,
            )
            logger.info("Download complete: %s -> %s (checksum %s)", model, final_path, result.checksum)
        except asyncio.CancelledError:
            by_user = model in self._user_cancelled
            await self._update(
                model, status=ModelStatus.AVAILABLE,
                download_progress=0.0, downloaded_bytes=0 if by_user else partial_size(dest),
            )
            logger.info("Download %s for %s", "cancelled" if by_user else "interrupted", model)
        except DownloadError as e:
            await self._update(
                model, status=ModelStatus.ERROR, error_code=e.code,
                error_message=e.message, error_retriable=int(e.retriable),
            )
            logger.error("Download failed for %s: [%s] %s", model, e.code, e.message)
            await record_fault(mark_fault(e, self.domain, model))
        except Exception as e:
            logger.exception("Download crashed for %s", model)
            error = _to_download_error(e, url)  # 下载状态与故障记录用同一个分类结果
            await self._update(
                model, status=ModelStatus.ERROR, error_code=error.code,
                error_message=error.message, error_retriable=int(error.retriable),
            )
            await record_fault(mark_fault(error, self.domain, model))
        finally:
            self._user_cancelled.discard(model)

    async def download(self, model: str) -> None:
        row = await self._get_model(model)
        if not row:
            raise ModelNotFound(f"Model '{model}' not found")
        if row["source_type"] != "local_url":
            raise DownloadNotSupported(f"Model '{model}' is not a local_url model")
        if model in self._download_tasks:
            raise DownloadInProgress(f"Model '{model}' is already downloading")
        url = row.get("url")
        if not url:
            raise DownloadNotSupported(f"Model '{model}' has no URL")
        dest = self._download_dest(row)
        row = await self._sync_file_status(row)
        if row["status"] in (ModelStatus.DOWNLOADED, ModelStatus.LOADED, ModelStatus.LOADING):
            raise ModelAlreadyDownloaded(f"Model '{model}' is already downloaded")
        # 取消请求恰好落在上一次下载结束之后时，标记可能没被清掉；不能让它把这次的中断当成用户取消
        self._user_cancelled.discard(model)
        task = asyncio.create_task(self._download(model, url, dest))
        self._download_tasks[model] = task
        task.add_done_callback(lambda _: self._download_tasks.pop(model, None))

    async def cancel_download(self, model: str) -> None:
        """用户取消：删除已下载部分。（进程退出等中断则保留，下次续传）"""
        task = self._download_tasks.get(model)
        if not task:
            raise NoActiveDownload(f"No active download for '{model}'")
        self._user_cancelled.add(model)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _do_load(self, model: str, extra_args: list[str] | None = None) -> None:
        """核心加载逻辑，被 load()、switch() 和推理时的自动加载复用；失败时标记为该模型的加载故障。"""
        try:
            await self._do_load_impl(model, extra_args)
        except Exception as exc:
            mark_fault(exc, self.domain, model)
            raise

    async def _do_load_impl(self, model: str, extra_args: list[str] | None = None) -> None:
        """幂等操作：若模型已运行则直接返回。"""
        row = await self._get_model(model)
        if not row:
            raise ModelNotFound(f"Model '{model}' not found")

        row = await self._sync_file_status(row)
        source_type = row["source_type"]
        local_path = row.get("local_path", "")

        backend_impl = self._get_backend_impl()

        if source_type == "remote" or (source_type == "local_url" and row.get("api_base_url")):
            if model not in backend_impl._remote_adapters:
                backend_impl.register_remote(model, row["api_base_url"], row["api_key"])
            await self._set_status(model, ModelStatus.LOADED)
            return

        # 并发保护：必须在 is_model_running 检查之前，防止竞态条件
        if model in self._loading_events:
            await self._loading_events[model].wait()
            row = await self._get_model(model)
            if row and row["status"] == ModelStatus.LOADED:
                return
            raise ModelLoadFailed(f"Model '{model}' failed to load", retriable=True)

        await self._reap_crashed(model)
        if backend_impl.is_model_running(model):
            await self._set_status(model, ModelStatus.LOADED)
            return

        if source_type != "remote":
            # 下载中 local_path 还没写入，必须先判断下载状态
            if model in self._download_tasks:
                raise ModelDownloading(f"Model '{model}' is still downloading")
            if not local_path:
                raise ModelNotDownloaded(
                    f"Model '{model}' has no local file path (file not found). Please download it again."
                )

        event = asyncio.Event()
        self._loading_events[model] = event
        try:
            await self._set_status(model, ModelStatus.LOADING)
            merged_args = self.settings.default_args + (extra_args or [])
            await backend_impl.start_model(model, Path(local_path), merged_args)
            adapter = backend_impl.get_adapter(model)
            if adapter is not None:
                await adapter.warmup()
            await self._set_status(model, ModelStatus.LOADED)
        except Exception:
            try:
                await backend_impl.stop_model(model)
            except Exception:
                logger.warning("Failed to stop model '%s' after load failure", model, exc_info=True)
            if local_path and _local_model_ready(Path(local_path)):
                await self._set_status(model, ModelStatus.DOWNLOADED, 1.0)
            else:
                await self._reset_missing_local_file(model)
            raise
        finally:
            event.set()
            self._loading_events.pop(model, None)

    async def _reap_crashed(self, model: str) -> None:
        """推理进程已退出但 adapter 还在：记下退出码和日志，释放端口，交给后续重新拉起。"""
        backend_impl = self._get_backend_impl()
        adapter = backend_impl.get_adapter(model)
        if adapter is None or adapter.is_running():
            return
        tail = read_log_tail(process_log_path(self.settings, model))
        logger.warning(
            "llama-server for '%s' exited unexpectedly (returncode=%s); restarting. last log lines:\n%s",
            model, adapter_returncode(adapter), "\n".join(tail),
        )
        await backend_impl.stop_model(model)

    async def load(self, model: str, extra_args: list[str] | None = None) -> None:
        """
        加载模型到新端口，注册到 _adapters。
        只负责启动进程，不切换 _current_model 指针。
        多个模型可同时运行。
        """
        await self._do_load(model, extra_args)

    async def unload(self, model: str) -> None:
        row = await self._get_model(model)
        if not row:
            raise ValueError(f"Model '{model}' not found")
        backend_impl = self._get_backend_impl()
        await backend_impl.stop_model(model)
        if row["source_type"] == "remote":
            backend_impl.unregister_remote(model)
        if self._current_model == model:
            self._current_model = None
            self._current_source_type = None
        if row["source_type"] == "remote":
            await self._set_status(model, ModelStatus.AVAILABLE)
            return

        local_path = row.get("local_path")
        if local_path and _local_model_ready(Path(local_path)):
            await self._set_status(model, ModelStatus.DOWNLOADED)
            return

        logger.warning("Model '%s' unloaded without a valid local file, resetting status to available", model)
        await self._reset_missing_local_file(model)

    async def deregister(self, model: str) -> None:
        row = await self._get_model(model)
        if not row:
            raise ValueError(f"Model '{model}' not found")
        if row["is_preset"]:
            raise ValueError(f"Model '{model}' is a preset model and cannot be unregistered")
        backend_impl = self._get_backend_impl()
        await backend_impl.stop_model(model)
        if row["source_type"] == "remote":
            backend_impl.unregister_remote(model)
        if self._current_model == model:
            self._current_model = None
            self._current_source_type = None
        await self._db.execute("DELETE FROM models WHERE id = ?", (model,))
        await self._db.commit()

    async def switch(self, model: str) -> None:
        """
        切换当前活跃模型指针到指定模型。
        若模型未加载则自动加载，然后切换指针。
        """
        await self._do_load(model)  # 确保已加载（幂等）
        row = await self._get_model(model)
        self._current_model = model
        self._current_source_type = row["source_type"]

    async def get_download_progress(self, model: str) -> dict:
        row = await self._get_model(model)
        if not row:
            raise ModelNotFound(f"Model '{model}' not found", status_code=404)
        row = await self._sync_file_status(row)
        return self._download_view(row)

    def _download_view(self, row: dict) -> dict:
        status = row["status"]
        failed = status == ModelStatus.ERROR
        dest = self._download_dest(row) if row["source_type"] == "local_url" else None
        idle = status in (ModelStatus.AVAILABLE, ModelStatus.ERROR)
        retriable = row.get("error_retriable")
        return {
            "model": row["id"],
            "status": status,
            "progress": row.get("download_progress") or 0.0,
            "downloaded_bytes": row.get("downloaded_bytes") or 0,
            "total_bytes": row.get("total_bytes"),
            "checksum": row.get("checksum") if status != ModelStatus.ERROR else None,
            "error_code": row.get("error_code") if failed else None,
            "error_message": row.get("error_message") if failed else None,
            "retriable": bool(retriable) if failed and retriable is not None else None,
            "resumable": bool(idle and dest is not None and partial_size(dest) > 0),
        }

    async def _resolve_model(self, request_body: bytes) -> tuple[str, str]:
        """
        从请求体解析 model 字段，确保模型已加载并返回 (model_id, source_type)。
        若模型未运行则自动加载（不切换 _current_model 指针）。
        """
        model_id = None
        requested_model = False
        try:
            data = json.loads(request_body)
            model_id = data.get("model")
            requested_model = bool(model_id)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        if not model_id:
            model_id = self._current_model or self.settings.default_model
            if not model_id:
                raise NoModelLoaded("No model loaded")

        row = await self._get_model(model_id)
        if not row:
            raise ModelNotFound(f"Model '{model_id}' not found", status_code=503)

        # 统一走 _do_load，确保模型真的在运行（幂等操作）
        logger.info("Ensuring model '%s' is ready for inference request", model_id)
        try:
            await self._do_load(model_id)
        except (ModelNotDownloaded, ModelDownloading) as exc:
            exc.status_code = 503  # 推理请求：服务暂不可用，而不是请求本身有误
            raise
        if self._current_model is None or not requested_model:
            self._current_model = model_id
            self._current_source_type = row["source_type"]

        return model_id, row["source_type"]

    async def proxy(self, path: str, request_body: bytes, headers: dict, stream: bool = False):
        model_id, source_type = await self._resolve_model(request_body)
        backend_impl = self._get_backend_impl()
        try:
            client, response = await backend_impl.proxy_for(
                model_id, source_type,
                path, request_body, headers, stream,
            )
        except httpx.TransportError as exc:
            raise self._transport_error(model_id, source_type, exc) from exc
        if stream:
            # 流式响应的正文在调用方读取，读到一半断开也要给出分类错误
            classify_stream_errors(
                response, lambda exc: self._transport_error(model_id, source_type, exc, midstream=True)
            )
        return client, response

    def _transport_error(
        self, model_id: str, source_type: str, exc: httpx.TransportError, *, midstream: bool = False
    ) -> DomainError:
        when = "connection lost mid-response" if midstream else "unreachable"
        if source_type == "remote":
            error: DomainError = DomainError(
                f"remote API for model '{model_id}' {when}: {exc!r}",
                code="upstream_error", status_code=502, retriable=True,
            )
        else:
            adapter = self._get_backend_impl().get_adapter(model_id)
            log_path = process_log_path(self.settings, model_id)
            error = BackendCrashed(
                f"inference backend for model '{model_id}' {when}: {exc!r}",
                details={
                    "returncode": adapter_returncode(adapter),
                    "log_tail": read_log_tail(log_path),
                    "log_path": str(log_path),
                },
            )
        if midstream:
            logger.error("[%s] %s", error.code, error.message)
        return mark_fault(error, self.domain, model_id)
