import asyncio
import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Generic, TypeVar

import aiosqlite
import httpx

from .enums import ModelStatus
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

TBackend = TypeVar("TBackend")
TConfig = TypeVar("TConfig")


class BaseModelService(ABC, Generic[TBackend, TConfig]):
    """LLM/Embed/Rerank 三域的通用基类，封装模型生命周期管理逻辑。"""

    def __init__(
        self,
        backends: dict[str, TBackend],
        default: str,
        config: TConfig,
    ):
        self._backends = backends
        self._default = default
        self.settings = config
        self._db: aiosqlite.Connection | None = None
        self._current_model: str | None = None
        self._current_source_type: str | None = None
        self._download_tasks: dict[str, asyncio.Task] = {}
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
        await self._db.commit()
        await self._reset_stale_status()
        await self._sync_preset_models()
        await self._autoload_default_model()

    async def _reset_stale_status(self) -> None:
        """重启后清理 loading/loaded 状态（旧进程已死）。"""
        async with self._db.execute(
            "SELECT id, local_path FROM models WHERE status IN (?, ?) AND source_type != 'remote'",
            (ModelStatus.LOADING, ModelStatus.LOADED),
        ) as cur:
            rows = await cur.fetchall()

        downloaded = 0
        available = 0
        for row in rows:
            local_path = row["local_path"]
            if local_path and Path(local_path).exists():
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

    async def _autoload_default_model(self) -> None:
        default = self.settings.default_model
        if not default:
            return
        row = await self._get_model(default)
        if not row:
            logger.warning("[autoload] default_model '%s' not found in DB", default)
            return
        row = await self._sync_file_status(row)
        if row["status"] == ModelStatus.AVAILABLE and row["source_type"] == "local_url":
            logger.info("[autoload] default_model '%s' file not found, starting background download", default)
            asyncio.create_task(self._download_then_load(default), name=f"autoload-{default}")
            return
        if row["status"] == ModelStatus.DOWNLOADING:
            logger.info("[autoload] default_model '%s' is downloading, skipping", default)
            return
        try:
            await self.switch(default)
            logger.info("[autoload] default_model '%s' loaded and active", default)
        except Exception as e:
            logger.warning("[autoload] failed to load default_model '%s': %s", default, e)

    async def _download_then_load(self, model: str) -> None:
        try:
            await self.download(model)
            task = self._download_tasks.get(model)
            if task:
                await task
            logger.info("[autoload] download complete for '%s', loading...", model)
            await self.switch(model)
            logger.info("[autoload] '%s' loaded and active", model)
        except Exception as e:
            logger.warning("[autoload] download+load failed for '%s': %s", model, e)

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
        backend_impl = self._get_backend_impl()
        await backend_impl.shutdown()
        if self._db:
            await self._db.close()

    async def healthz(self) -> dict:
        """健康检查，返回当前服务状态。"""
        if self._db is None:
            state = BackendReadyState.INITIALIZING
        elif self._current_model is None:
            state = BackendReadyState.FAILED
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
            filename = url.split("/")[-1] if url else f"{m['id']}.gguf"
            expected_path = self.settings.storage.models_path / filename
            if row is None:
                if expected_path.exists():
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
                    if expected_path.exists():
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

    async def _sync_file_status(self, row: dict) -> dict:
        """根据文件是否存在修正 DB 状态，返回修正后的 row。非本地模型直接返回原 row。"""
        if row["source_type"] == "remote":
            return row
        model = row["id"]
        local_path = row.get("local_path")
        if not local_path:
            url = row.get("url", "")
            if url:
                local_path = str(self.settings.storage.models_path / url.split("/")[-1])
        file_exists = bool(local_path and Path(local_path).exists())
        status = row["status"]
        active_statuses = (ModelStatus.DOWNLOADED, ModelStatus.LOADED, ModelStatus.LOADING, ModelStatus.DOWNLOADING)
        if file_exists and status not in active_statuses:
            await self._db.execute(
                "UPDATE models SET status=?, local_path=?, download_progress=1.0 WHERE id=?",
                (ModelStatus.DOWNLOADED, local_path, model),
            )
            await self._db.commit()
            return {**row, "status": ModelStatus.DOWNLOADED, "local_path": local_path}
        if file_exists and not row.get("local_path"):
            await self._db.execute(
                "UPDATE models SET local_path=? WHERE id=?",
                (local_path, model),
            )
            await self._db.commit()
            return {**row, "local_path": local_path}
        if not file_exists and status not in (ModelStatus.AVAILABLE, ModelStatus.DOWNLOADING):
            await self._reset_missing_local_file(model)
            return {**row, "status": ModelStatus.AVAILABLE, "local_path": None}
        return row

    async def _download(self, model: str, url: str, dest: Path) -> None:
        await self._set_status(model, ModelStatus.DOWNLOADING, 0.0)
        dest.parent.mkdir(parents=True, exist_ok=True)
        temp_path = dest.with_suffix(dest.suffix + ".tmp")

        if temp_path.exists():
            temp_path.unlink()

        try:
            async with httpx.AsyncClient(timeout=None, follow_redirects=True, verify=False) as client:
                async with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    total = int(resp.headers.get("content-length", 0))
                    downloaded = 0
                    with open(temp_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total:
                                progress = downloaded / total
                                await self._set_status(model, ModelStatus.DOWNLOADING, progress)
            temp_path.rename(dest)
            await self._db.execute(
                "UPDATE models SET status=?, local_path=?, download_progress=1.0 WHERE id=?",
                (ModelStatus.DOWNLOADED, str(dest), model),
            )
            await self._db.commit()
            logger.info("Download complete: %s -> %s", model, dest)
        except asyncio.CancelledError:
            temp_path.unlink(missing_ok=True)
            await self._set_status(model, ModelStatus.AVAILABLE, 0.0)
            logger.info("Download cancelled for %s", model)
        except Exception as e:
            temp_path.unlink(missing_ok=True)
            logger.error("Download failed for %s: %s", model, e)
            await self._set_status(model, ModelStatus.ERROR)
            raise

    async def download(self, model: str) -> None:
        row = await self._get_model(model)
        if not row:
            raise ValueError(f"Model '{model}' not found")
        if row["source_type"] != "local_url":
            raise ValueError(f"Model '{model}' is not a local_url model")
        if model in self._download_tasks:
            raise ValueError(f"Model '{model}' is already downloading")
        url = row.get("url")
        if not url:
            raise ValueError(f"Model '{model}' has no URL")
        filename = url.split("/")[-1]
        dest = self.settings.storage.models_path / filename
        row = await self._sync_file_status(row)
        if row["status"] == ModelStatus.DOWNLOADED:
            raise ValueError(f"Model '{model}' is already downloaded")
        task = asyncio.create_task(self._download(model, url, dest))
        self._download_tasks[model] = task
        task.add_done_callback(lambda _: self._download_tasks.pop(model, None))

    async def cancel_download(self, model: str) -> None:
        task = self._download_tasks.get(model)
        if not task:
            raise ValueError(f"No active download for '{model}'")
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _do_load(self, model: str, extra_args: list[str] | None = None) -> None:
        """
        核心加载逻辑，被 load() 和 switch() 复用。
        幂等操作：若模型已运行则直接返回。
        """
        row = await self._get_model(model)
        if not row:
            raise ValueError(f"Model '{model}' not found")

        row = await self._sync_file_status(row)
        source_type = row["source_type"]
        local_path = row.get("local_path", "")

        backend_impl = self._get_backend_impl()

        if source_type == "remote":
            if model not in backend_impl._remote_adapters:
                backend_impl.register_remote(model, row["api_base_url"], row["api_key"])
            await self._set_status(model, ModelStatus.LOADED)
            return

        # 并发保护：必须在 is_model_running 检查之前，防止竞态条件
        if model in self._loading_events:
            await self._loading_events[model].wait()
            return

        if backend_impl.is_model_running(model):
            return  # 已运行，幂等

        if source_type != "remote":
            if not local_path:
                raise ValueError(f"Model '{model}' file not found. Please download it again.")
            if model in self._download_tasks:
                raise ValueError(f"Model '{model}' is still downloading")

        event = asyncio.Event()
        self._loading_events[model] = event
        try:
            await self._set_status(model, ModelStatus.LOADING)
            merged_args = self.settings.default_args + (extra_args or [])
            await backend_impl.start_model(model, Path(local_path), merged_args)
            await self._set_status(model, ModelStatus.LOADED)
        finally:
            event.set()
            self._loading_events.pop(model, None)

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
        if local_path and Path(local_path).exists():
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
            raise ValueError(f"Model '{model}' not found")
        row = await self._sync_file_status(row)
        return {
            "model": model,
            "status": row["status"],
            "progress": row.get("download_progress", 0.0),
        }

    async def _resolve_model(self, request_body: bytes) -> tuple[str, str]:
        """
        从请求体解析 model 字段，确保模型已加载并返回 (model_id, source_type)。
        若模型未运行则自动加载（不切换 _current_model 指针）。
        """
        model_id = None
        try:
            data = json.loads(request_body)
            model_id = data.get("model")
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        if not model_id:
            model_id = self._current_model
            if not model_id:
                raise RuntimeError("No model loaded")

        row = await self._get_model(model_id)
        if not row:
            raise RuntimeError(f"Model '{model_id}' not found")

        # 统一走 _do_load，确保模型真的在运行（幂等操作）
        logger.info("Ensuring model '%s' is ready for inference request", model_id)
        await self._do_load(model_id)

        return model_id, row["source_type"]

    async def proxy(self, path: str, request_body: bytes, headers: dict, stream: bool = False):
        model_id, source_type = await self._resolve_model(request_body)
        backend_impl = self._get_backend_impl()
        return await backend_impl.proxy_for(
            model_id, source_type,
            path, request_body, headers, stream,
        )
