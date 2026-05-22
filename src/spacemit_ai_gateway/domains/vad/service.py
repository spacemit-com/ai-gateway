"""VAD 业务编排。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List, Optional

from ...app.settings import VadConfig
from ...common.backend_selection import resolve_allowed_backends
from ...common.errors import (
    ModelAlreadyLoaded,
    ModelNotLoaded,
    ModelUnknown,
)
from ...common.ready_state import BackendReadyState
from ...common.schemas import ModelInfo
from .adapters import VAD_REGISTRY, VadBackend, VadStreamSession
from .schemas import (
    AnalyzeResponse,
    HealthResponse,
    ParamsResponse,
    SegmentsResponse,
    SpeechSegment,
    VadAudioPatch,
    VadAudioResponse,
    VadEnginePatch,
    VadEngineResponse,
    VadInfoResponse,
    VadParamsPatch,
    VadStatsResponse,
)

logger = logging.getLogger(__name__)


class VadService:
    def __init__(
        self,
        backends: Dict[str, VadBackend],
        default: str,
        config: Optional[VadConfig] = None,
    ):
        self._backends = backends
        self._default = default
        self._config = config or VadConfig()
        self._allowed_backends = resolve_allowed_backends(
            self._config.backends,
            default,
            VAD_REGISTRY,
            self._backends,
        )
        if self._allowed_backends and self._default not in self._allowed_backends:
            self._default = self._allowed_backends[0]
        self._event_store = None
        self._stats = {
            "total_requests": 0,
            "total_errors": 0,
            "total_processing_ms": 0.0,
            "started_at": time.time(),
        }
        self._engine_pending_restart = False
        self._load_lock = asyncio.Lock()

    @property
    def backend(self) -> VadBackend:
        return self._backends[self._default]

    def _model_id(self, model: Optional[str] = None) -> str:
        return model or self._default

    async def _shutdown_loaded_backends(self) -> None:
        for name, backend in list(self._backends.items()):
            logger.info("unloading VAD backend '%s' before loading another model", name)
            self._backends.pop(name, None)
            await backend.shutdown()

    async def _ensure_backend(self, model: Optional[str] = None) -> VadBackend:
        name = self._model_id(model)
        async with self._load_lock:
            existing = self._backends.get(name)
            if existing is not None and existing.state.is_serving:
                return existing

            if name not in self._allowed_backends:
                raise ModelUnknown(
                    f"model '{name}' not allowed",
                    details={"available": self._allowed_backends},
                )

            cls = VAD_REGISTRY.get(name)
            if cls is None:
                raise ModelUnknown(
                    f"model '{name}' not registered",
                    details={"available": self._allowed_backends},
                )

            await self._shutdown_loaded_backends()
            cfg = self._config.model_copy(update={"backend": name})
            logger.info("loading VAD backend '%s' on demand", name)
            backend = cls(cfg)
            await backend.warmup()
            self._backends[name] = backend
            self._default = name
            return backend

    def _get_backend(self, model: Optional[str] = None) -> VadBackend:
        name = model or self._default
        backend = self._backends.get(name)
        if backend is None:
            raise ModelNotLoaded(
                f"model '{name}' not loaded",
                details={"available": list(self._backends.keys())},
            )
        return backend

    async def analyze(self, audio: bytes, sample_rate: int) -> AnalyzeResponse:
        try:
            backend = await self._ensure_backend()
            a = await backend.analyze(audio, sample_rate)
        except Exception:
            self._stats["total_errors"] += 1
            raise
        self._stats["total_requests"] += 1
        self._stats["total_processing_ms"] += a.processing_ms
        if self._event_store:
            self._event_store.record("vad", "analyze")
        return AnalyzeResponse(
            is_speech=a.is_speech,
            probability=a.probability,
            smoothed_probability=a.smoothed_probability,
            processing_ms=a.processing_ms,
        )

    async def segment(self, audio: bytes, sample_rate: int) -> SegmentsResponse:
        start = time.perf_counter()
        backend = await self._ensure_backend()
        segments, duration_ms = await backend.segment(audio, sample_rate)
        processing_ms = (time.perf_counter() - start) * 1000

        speech_duration = sum(s.end_ms - s.start_ms for s in segments)
        speech_ratio = speech_duration / duration_ms if duration_ms > 0 else 0.0

        return SegmentsResponse(
            segments=[
                SpeechSegment(start_ms=s.start_ms, end_ms=s.end_ms, confidence=s.confidence)
                for s in segments
            ],
            duration_ms=duration_ms,
            speech_ratio=speech_ratio,
            processing_ms=processing_ms,
        )

    async def open_stream(self, sample_rate: int) -> VadStreamSession:
        backend = await self._ensure_backend()
        return await backend.open_stream(sample_rate)

    def get_models(self) -> List[ModelInfo]:
        models = []
        for name in self._allowed_backends:
            backend = self._backends.get(name)
            models.append(ModelInfo(
                id=name,
                name=backend.backend_name if backend else name,
                loaded=bool(backend and backend.is_ready),
            ))
        return models

    def get_params(self) -> ParamsResponse:
        backend = self._backends.get(self._default)
        if backend:
            return ParamsResponse(**backend.get_params())
        return ParamsResponse(
            trigger_threshold=self._config.trigger_threshold if self._config else 0.5,
            stop_threshold=self._config.stop_threshold if self._config else 0.35,
            min_speech_ms=self._config.min_speech_ms if self._config else 250,
            max_silence_ms=self._config.max_silence_ms if self._config else 500,
            sample_rate=self._config.sample_rate if self._config else 16000,
        )

    async def healthz(self) -> dict:
        backend = self._backends.get(self._default)
        state = backend.state if backend else BackendReadyState.IDLE
        return HealthResponse(
            ready=state.is_serving,
            state=state.value,
            backend=backend.backend_name if backend else self._default,
        ).model_dump()

    # ---- model management ----

    async def load_model(self, model_id: str) -> dict:
        existing = self._backends.get(model_id)
        if existing is not None and existing.state == BackendReadyState.READY:
            raise ModelAlreadyLoaded(f"model '{model_id}' already loaded")
        backend = await self._ensure_backend(model_id)
        return {"loaded": True, "model_id": model_id, "state": backend.state.value}

    async def unload_model(self, model_id: str) -> dict:
        if model_id not in self._backends:
            raise ModelNotLoaded(
                f"model '{model_id}' not loaded",
                details={"available": list(self._backends.keys())},
            )
        backend = self._backends.pop(model_id)
        await backend.shutdown()
        return {"unloaded": True, "model_id": model_id}

    async def switch_default(self, model_id: str) -> dict:
        await self._ensure_backend(model_id)
        self._default = model_id
        return {"switched": True, "default_model_id": model_id}

    # ---- params PATCH ----

    def update_params(self, patch: VadParamsPatch) -> ParamsResponse:
        cfg = self._backends[self._default]._config if self._default in self._backends else self._config
        if patch.trigger_threshold is not None:
            cfg.trigger_threshold = patch.trigger_threshold
        if patch.stop_threshold is not None:
            cfg.stop_threshold = patch.stop_threshold
        if patch.min_speech_ms is not None:
            cfg.min_speech_ms = patch.min_speech_ms
        if patch.max_silence_ms is not None:
            cfg.max_silence_ms = patch.max_silence_ms
        return self.get_params()

    # ---- audio ----

    def get_audio_config(self) -> VadAudioResponse:
        backend = self._backends.get(self._default)
        data = backend.get_audio_config() if backend else {
            "sample_rate": self._config.sample_rate if self._config else 16000,
            "bit_depth": 16,
            "denoise": False,
        }
        return VadAudioResponse(**data)

    def update_audio_config(self, patch: VadAudioPatch) -> VadAudioResponse:
        cfg = self._backends[self._default]._config if self._default in self._backends else self._config
        if patch.sample_rate is not None:
            cfg.sample_rate = patch.sample_rate
        return self.get_audio_config()

    # ---- engine ----

    def get_engine_config(self) -> VadEngineResponse:
        backend = self._backends.get(self._default)
        data = backend.get_engine_config() if backend else {
            "threads": 1,
            "npu_priority": None,
            "memory_limit": None,
        }
        return VadEngineResponse(**data, pending_restart=self._engine_pending_restart)

    def update_engine_config(self, patch: VadEnginePatch) -> VadEngineResponse:
        self._engine_pending_restart = True
        return self.get_engine_config()

    # ---- stats ----

    def get_stats(self) -> VadStatsResponse:
        total_req = self._stats["total_requests"]
        total_proc = self._stats["total_processing_ms"]
        latency_avg = total_proc / total_req if total_req > 0 else 0.0
        uptime_s = time.time() - self._stats["started_at"]
        return VadStatsResponse(
            total_requests=total_req,
            total_errors=self._stats["total_errors"],
            latency_ms_avg=round(latency_avg, 2),
            uptime_s=round(uptime_s, 1),
        )

    # ---- info ----

    def get_info(self) -> VadInfoResponse:
        backend = self._backends.get(self._default)
        return VadInfoResponse(
            initialized=bool(backend and backend.is_ready),
            backend=backend.backend_name if backend else self._default,
            default_model=self._default,
            backends_loaded=list(self._backends.keys()),
        )

    async def shutdown(self) -> None:
        await self._shutdown_loaded_backends()
