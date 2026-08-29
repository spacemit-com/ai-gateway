from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from ...app.settings import File2mdConfig

logger = logging.getLogger(__name__)


class File2mdService:
    """Serialized async facade for the native ``spacemit-file2md`` engine.

    The SDK engine owns ONNX/PDF resources and documents that one engine may
    only process one conversion at a time.  The gateway therefore keeps one
    lazily-created engine behind a lock, just like the other native domains.
    """

    def __init__(self, config: File2mdConfig):
        self._config = config
        self._engine: Any = None
        self._module: Any = None
        self._lock = asyncio.Lock()
        self._state = "idle"
        self._started_at = time.time()
        self._stats = {
            "total_requests": 0,
            "total_errors": 0,
            "total_processing_ms": 0.0,
        }
        self._last_error: str | None = None
        self._pending_restart = False

    @property
    def backend(self) -> str:
        return self._config.provider

    @property
    def state(self) -> str:
        return self._state

    def _ensure_engine(self) -> Any:
        if self._engine is not None:
            return self._engine
        try:
            import spacemit_file2md as file2md
        except ImportError as exc:
            raise RuntimeError(
                "spacemit-file2md is not installed; install the File2MD wheel"
            ) from exc

        config = file2md.File2MDConfig.preset(self._config.provider)
        config.output_dir = str(Path(self._config.output_dir).expanduser())
        config.intra_op_threads = self._config.threads
        config.cpu_intra_op_threads = self._config.cpu_threads
        config.pdf_dpi = self._config.pdf_dpi
        config.processing_window_size = self._config.processing_window_size
        if self._config.model_dir:
            config.model_dir = str(Path(self._config.model_dir).expanduser())

        self._module = file2md
        self._engine = file2md.File2MDEngine(config)
        return self._engine

    def _options(self, overrides: dict[str, Any] | None = None) -> Any:
        if self._module is None:
            raise RuntimeError("File2MD engine is not initialized")
        config = self._config.model_copy(update=overrides or {})
        options = self._module.ConvertOptions()
        options.method = {
            "auto": self._module.ParseMethod.AUTO,
            "text": self._module.ParseMethod.TEXT,
            "ocr": self._module.ParseMethod.OCR,
        }[config.method]
        options.language = config.language
        options.formula = config.formula
        options.table = config.table
        options.flowchart = config.flowchart
        options.image_ocr_caption = config.image_ocr_caption
        options.web_image_ocr = config.web_image_ocr
        options.save_images = config.save_images
        options.start_page = int(overrides.get("start_page", 0)) if overrides else 0
        options.end_page = int(overrides.get("end_page", -1)) if overrides else -1
        return options

    async def healthz(self) -> dict[str, Any]:
        async with self._lock:
            engine = self._engine
            models_ready = False
            model_states: list[dict[str, Any]] = []
            if engine is not None:
                try:
                    models_ready = bool(await asyncio.to_thread(engine.are_models_ready))
                    model_states = await asyncio.to_thread(self._model_states_sync)
                except Exception as exc:
                    self._last_error = str(exc)
            state = "stopped" if self._state == "stopped" else self._state
            return {
                "ready": state in {"idle", "busy"} and self._last_error is None,
                "state": state,
                "backend": self.backend,
                "initialized": engine is not None,
                "models_ready": models_ready,
                "models": model_states,
                "last_error": self._last_error,
            }

    def _model_states_sync(self) -> list[dict[str, Any]]:
        if self._engine is None:
            return []
        return [
            {
                "model_name": item.model_name,
                "status": item.status,
                "progress": float(item.progress),
                "error": item.error or None,
            }
            for item in self._engine.get_model_states()
        ]

    async def list_models(self) -> dict[str, Any]:
        async with self._lock:
            if self._engine is None:
                return {"backend": self.backend, "models_ready": False, "models": []}
            return {
                "backend": self.backend,
                "models_ready": bool(await asyncio.to_thread(self._engine.are_models_ready)),
                "models": await asyncio.to_thread(self._model_states_sync),
            }

    async def load_models(self) -> dict[str, Any]:
        async with self._lock:
            self._state = "busy"
            self._last_error = None
            try:
                engine = self._ensure_engine()
                ok = bool(await asyncio.to_thread(engine.preload_models, self._options()))
                if not ok:
                    self._last_error = "File2MD model preload failed"
                    self._stats["total_errors"] += 1
                return {
                    "loaded": ok,
                    "models_ready": bool(await asyncio.to_thread(engine.are_models_ready)),
                    "models": await asyncio.to_thread(self._model_states_sync),
                }
            except Exception as exc:
                self._last_error = str(exc)
                self._stats["total_errors"] += 1
                raise RuntimeError(str(exc)) from exc
            finally:
                self._state = "idle"

    async def unload_models(self) -> dict[str, Any]:
        async with self._lock:
            if self._engine is not None:
                await asyncio.to_thread(self._engine.shutdown)
            self._engine = None
            self._module = None
            self._pending_restart = False
            self._last_error = None
            self._state = "idle"
            return {"unloaded": True}

    def get_params(self) -> dict[str, Any]:
        return self._config.model_dump()

    def update_params(self, values: dict[str, Any]) -> dict[str, Any]:
        self._config = File2mdConfig.model_validate(
            {**self._config.model_dump(), **values}
        )
        return self.get_params()

    def get_engine_config(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "initialized": self._engine is not None,
            "model_dir": self._config.model_dir,
            "output_dir": str(Path(self._config.output_dir).expanduser()),
            "threads": self._config.threads,
            "cpu_threads": self._config.cpu_threads,
            "pdf_dpi": self._config.pdf_dpi,
            "processing_window_size": self._config.processing_window_size,
            "pending_restart": self._pending_restart,
        }

    def update_engine(self, values: dict[str, Any]) -> dict[str, Any]:
        if not values:
            return self.get_engine_config()
        self._config = File2mdConfig.model_validate(
            {**self._config.model_dump(), **values}
        )
        self._pending_restart = self._engine is not None
        return self.get_engine_config()

    def get_stats(self) -> dict[str, Any]:
        total = self._stats["total_requests"]
        avg = self._stats["total_processing_ms"] / total if total else 0.0
        return {
            **self._stats,
            "processing_time_avg_ms": round(avg, 3),
            "uptime_s": round(time.time() - self._started_at, 1),
        }

    async def convert_path(
        self,
        path: str | Path,
        filename: str,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with self._lock:
            self._state = "busy"
            started = time.perf_counter()
            self._stats["total_requests"] += 1
            self._last_error = None
            try:
                result = await asyncio.to_thread(
                    self._convert_sync, str(path), overrides
                )
                if not result["success"]:
                    self._stats["total_errors"] += 1
                return result
            except Exception as exc:
                self._stats["total_errors"] += 1
                self._last_error = str(exc)
                raise
            finally:
                elapsed = (time.perf_counter() - started) * 1000
                self._stats["total_processing_ms"] += elapsed
                self._state = "idle"

    async def convert(
        self,
        data: bytes,
        filename: str,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Compatibility wrapper for callers that already hold bytes."""
        suffix = Path(filename).suffix.lower() or ".bin"
        prefix = f"file2md-{uuid4().hex}-"
        with tempfile.NamedTemporaryFile(prefix=prefix, suffix=suffix, delete=True) as source:
            source.write(data)
            source.flush()
            return await self.convert_path(source.name, filename, overrides)

    def _convert_sync(
        self, path: str, overrides: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        engine = self._ensure_engine()
        result = engine.convert(path, self._options(overrides))
        manifest: dict[str, Any] = {}
        try:
            manifest = json.loads(result.manifest_json or "{}")
        except Exception:
            logger.debug("File2MD returned invalid manifest", exc_info=True)
        return {
            "success": bool(result.success),
            "request_id": result.request_id or None,
            "markdown": result.markdown if result.success else "",
            "error": result.error or None,
            "page_count": int(result.page_count),
            "processing_time_ms": float(result.processing_time),
            "output_directory": result.output_directory or None,
            "manifest": manifest,
            "middle_json": result.middle_json or None,
            "content_list_json": result.content_list_json or None,
            "page_metrics": [
                {
                    "page_index": int(item.page_index),
                    "layout_ms": float(item.layout_ms),
                    "ocr_ms": float(item.ocr_ms),
                    "formula_ms": float(item.formula_ms),
                    "table_ms": float(item.table_ms),
                    "flowchart_ms": float(item.flowchart_ms),
                }
                for item in (result.page_metrics or [])
            ],
        }

    async def shutdown(self) -> None:
        async with self._lock:
            if self._engine is not None:
                await asyncio.to_thread(self._engine.shutdown)
            self._engine = None
            self._module = None
            self._pending_restart = False
            self._state = "stopped"
