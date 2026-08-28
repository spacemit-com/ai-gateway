from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any

from ...app.settings import File2mdConfig

logger = logging.getLogger(__name__)


class File2mdService:
    """Async-safe wrapper around the native spacemit-file2md wheel.

    The native engine is stateful and is therefore serialized.  The engine is
    created lazily so gateway startup does not allocate OCR/layout models.
    """

    def __init__(self, config: File2mdConfig):
        self._config = config
        self._engine: Any = None
        self._module: Any = None
        self._lock = asyncio.Lock()
        self._state = "idle"

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
        if self._config.model_dir:
            config.model_dir = str(Path(self._config.model_dir).expanduser())
        self._module = file2md
        self._engine = file2md.File2MDEngine(config)
        return self._engine

    def _options(self) -> Any:
        file2md = self._module
        options = file2md.ConvertOptions()
        options.method = {
            "auto": file2md.ParseMethod.AUTO,
            "text": file2md.ParseMethod.TEXT,
            "ocr": file2md.ParseMethod.OCR,
        }[self._config.method]
        options.language = self._config.language
        options.formula = self._config.formula
        options.table = self._config.table
        options.flowchart = self._config.flowchart
        options.image_ocr_caption = self._config.image_ocr_caption
        options.save_images = self._config.save_images
        return options

    async def convert(self, data: bytes, filename: str) -> dict[str, Any]:
        async with self._lock:
            self._state = "busy"
            try:
                suffix = Path(filename).suffix or ".bin"
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as source:
                    source.write(data)
                    source.flush()
                    result = await asyncio.to_thread(
                        self._convert_sync, source.name
                    )
                return result
            finally:
                self._state = "idle"

    def _convert_sync(self, path: str) -> dict[str, Any]:
        engine = self._ensure_engine()
        result = engine.convert(path, self._options())
        manifest: dict[str, Any] = {}
        try:
            import json
            manifest = json.loads(result.manifest_json or "{}")
        except Exception:
            logger.debug("File2MD returned invalid manifest", exc_info=True)
        return {
            "success": bool(result.success),
            "markdown": result.markdown if result.success else "",
            "error": result.error or None,
            "page_count": int(result.page_count),
            "processing_time_ms": float(result.processing_time),
            "output_directory": result.output_directory or None,
            "manifest": manifest,
        }

    async def shutdown(self) -> None:
        async with self._lock:
            if self._engine is not None:
                await asyncio.to_thread(self._engine.shutdown)
                self._engine = None
            self._state = "stopped"

