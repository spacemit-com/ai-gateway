"""TTS 业务编排。"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from ...app.settings import TtsConfig
from ...common.audio_codec import encode_audio
from ...common.backend_selection import resolve_allowed_backends
from ...common.errors import (
    InvalidSessionError,
    ModelAlreadyLoaded,
    ModelNotLoaded,
    ModelUnknown,
    TaskNotFound,
)
from ...common.lexicon_store import LexiconStore
from ...common.ready_state import BackendReadyState
from ...common.schemas import ModelInfo, VoiceInfo
from ...common.sessions import SessionStore
from ...common.task_store import TaskStatus, TaskStore
from .adapters import TTS_REGISTRY, TtsBackend, TtsStreamSession
from .schemas import (
    HealthResponse,
    StreamSessionRequest,
    StreamSessionResponse,
    SynthesizeRequest,
    TaskCancelResponse,
    TaskStatusResponse,
    TaskSubmitRequest,
    TaskSubmitResponse,
    TtsEnginePatch,
    TtsEngineResponse,
    TtsInfoResponse,
    TtsLexiconItem,
    TtsLexiconListResponse,
    TtsLexiconRequest,
    TtsParamsPatch,
    TtsParamsResponse,
    TtsStatsResponse,
)

logger = logging.getLogger(__name__)

_STATIC_VOICES = {
    "matcha_zh": [VoiceInfo(id="default", name="默认中文", language="zh", gender="female")],
    "matcha_en": [VoiceInfo(id="default", name="Default English", language="en", gender="female")],
    "matcha_zh_en": [VoiceInfo(id="default", name="中英混合", language="zh-en", gender="female")],
    "kokoro": [
        VoiceInfo(id="zf_xiaobei", name="小贝（中文女声）", language="zh", gender="female"),
        VoiceInfo(id="zm_yunxi", name="云希（中文男声）", language="zh", gender="male"),
        VoiceInfo(id="af_heart", name="Heart (English female)", language="en", gender="female"),
    ],
}

_STATIC_SAMPLE_RATES = {
    "matcha_zh": 22050,
    "matcha_en": 22050,
    "matcha_zh_en": 16000,
    "kokoro": 24000,
}


class TtsService:
    def __init__(
        self,
        backends: Dict[str, TtsBackend],
        default: str,
        session_store: SessionStore,
        config: Optional[TtsConfig] = None,
    ):
        self._backends = backends
        self._default = default
        self._sessions = session_store
        self._tts_config = config or TtsConfig()
        self._allowed_backends = resolve_allowed_backends(
            self._tts_config.backends or list(TTS_REGISTRY),
            default,
            TTS_REGISTRY,
            self._backends,
        )
        if self._allowed_backends and self._default not in self._allowed_backends:
            self._default = self._allowed_backends[0]
        self._task_store: TaskStore = TaskStore(namespace="tts-task")
        self._lexicon_store: LexiconStore = LexiconStore(namespace="tts")
        self._task_files: dict[str, Path] = {}
        self._event_store = None
        self._stats = {
            "total_requests": 0,
            "total_errors": 0,
            "total_processing_ms": 0.0,
            "total_audio_ms": 0.0,
            "started_at": time.time(),
        }
        self._engine_pending_restart = False
        self._load_lock = asyncio.Lock()

    @property
    def backend(self) -> TtsBackend:
        return self._backends[self._default]

    def _model_id(self, model: Optional[str] = None) -> str:
        return model or self._default

    async def _shutdown_loaded_backends_locked(self) -> None:
        for name, backend in list(self._backends.items()):
            logger.info("unloading TTS backend '%s' before loading another model", name)
            self._backends.pop(name, None)
            await backend.shutdown()

    async def _ensure_backend(self, model: Optional[str] = None) -> TtsBackend:
        async with self._load_lock:
            return await self._ensure_backend_locked(model)

    async def _ensure_backend_locked(self, model: Optional[str] = None) -> TtsBackend:
        name = self._model_id(model)
        existing = self._backends.get(name)
        if existing is not None and existing.state.is_serving:
            return existing

        if name not in self._allowed_backends:
            raise ModelUnknown(
                f"model '{name}' not allowed",
                details={"available": self._allowed_backends},
            )

        cls = TTS_REGISTRY.get(name)
        if cls is None:
            raise ModelUnknown(
                f"model '{name}' not registered",
                details={"available": self._allowed_backends},
            )

        await self._shutdown_loaded_backends_locked()
        cfg = self._tts_config.model_copy(update={"backend": name})
        logger.info("loading TTS backend '%s' on demand", name)
        backend = cls(cfg)
        await backend.warmup()
        self._backends[name] = backend
        self._default = name
        await self._sync_lexicon_to_backends_locked()
        return backend

    async def _shutdown_loaded_backends(self) -> None:
        async with self._load_lock:
            await self._shutdown_loaded_backends_locked()

    def _get_backend(self, model: Optional[str] = None) -> TtsBackend:
        name = model or self._default
        backend = self._backends.get(name)
        if backend is None:
            raise ModelNotLoaded(
                f"model '{name}' not loaded",
                details={"available": list(self._backends.keys())},
            )
        return backend

    async def synthesize(
        self, req: SynthesizeRequest
    ) -> tuple[bytes, str, dict]:
        """返回 (audio_bytes, content_type, metadata)。"""
        try:
            async with self._load_lock:
                backend = await self._ensure_backend_locked(req.model)
            result = await backend.synthesize(
                text=req.text,
                voice_id=req.voice_id,
                speed=req.speed,
                pitch=req.pitch,
                volume=req.volume,
            )
        except Exception:
            self._stats["total_errors"] += 1
            raise
        self._stats["total_requests"] += 1
        self._stats["total_processing_ms"] += result.processing_ms
        self._stats["total_audio_ms"] += result.duration_ms
        if self._event_store:
            self._event_store.record("tts", "synthesize")
        fmt = (req.response_format or "wav").lower()
        audio_bytes, content_type = encode_audio(result.audio, result.sample_rate, fmt)
        meta = {
            "duration_ms": result.duration_ms,
            "processing_ms": result.processing_ms,
            "rtf": result.rtf,
            "sample_rate": result.sample_rate,
            "format": fmt,
        }
        return audio_bytes, content_type, meta

    async def create_stream_session(
        self, req: StreamSessionRequest
    ) -> StreamSessionResponse:
        await self._ensure_backend(req.model)
        record = await self._sessions.create(
            data={
                "model": req.model,
                "voice_id": req.voice_id,
                "speed": req.speed,
                "response_format": req.response_format,
            }
        )
        expires_at = datetime.fromtimestamp(
            record.expires_at, tz=timezone.utc
        ).isoformat().replace("+00:00", "Z")
        return StreamSessionResponse(
            session_id=record.session_id,
            expires_at=expires_at,
            voice_id=req.voice_id,
            response_format=req.response_format,
        )

    async def open_stream(
        self,
        session_id: Optional[str],
        voice_id: Optional[str],
        response_format: str,
    ) -> TtsStreamSession:
        if not session_id:
            raise InvalidSessionError("missing session_id; POST /stream/session first")
        record = await self._sessions.pop(session_id)
        if record is None:
            raise InvalidSessionError("session_id expired or invalid")

        effective_voice = voice_id or record.data.get("voice_id")
        speed = float(record.data.get("speed", 1.0))
        async with self._load_lock:
            backend = await self._ensure_backend_locked(record.data.get("model"))
        return await backend.open_stream(
            voice_id=effective_voice, speed=speed
        )

    def get_voices(self) -> List[VoiceInfo]:
        voices = []
        for model_id in self._allowed_backends:
            backend = self._backends.get(model_id)
            if backend is not None:
                voices.extend(backend.get_voices())
            else:
                voices.extend(_STATIC_VOICES.get(model_id, []))
        return voices

    def get_models(self) -> List[ModelInfo]:
        models = []
        for model_id in self._allowed_backends:
            backend = self._backends.get(model_id)
            if backend is not None:
                entries = backend.get_models()
                for entry in entries:
                    if entry.id == model_id:
                        models.append(entry)
                continue
            voices = _STATIC_VOICES.get(model_id, [])
            models.append(ModelInfo(
                id=model_id,
                name=f"TTS {model_id}",
                capabilities=["tts", "streaming"],
                languages=[v.language for v in voices],
                sample_rate=_STATIC_SAMPLE_RATES.get(model_id),
                loaded=False,
            ))
        return models

    async def healthz(self) -> dict:
        default_backend = self._backends.get(self._default)
        state = default_backend.state if default_backend else BackendReadyState.IDLE
        return HealthResponse(
            ready=state.is_serving,
            state=state.value,
            backend=default_backend.backend_name if default_backend else self._default,
        ).model_dump()

    # ---- params ----

    def get_params(self) -> TtsParamsResponse:
        backend = self._backends.get(self._default)
        data = backend.get_params() if backend else {
            "speed": self._tts_config.speed if self._tts_config else 1.0,
            "pitch": self._tts_config.pitch if self._tts_config else 1.0,
            "volume": self._tts_config.volume if self._tts_config else 1.0,
            "emotion_strength": None,
        }
        return TtsParamsResponse(**data)

    def update_params(self, patch: TtsParamsPatch) -> TtsParamsResponse:
        cfg = self._backends[self._default]._config if self._default in self._backends else self._tts_config
        if patch.speed is not None:
            cfg.speed = patch.speed
        if patch.pitch is not None:
            cfg.pitch = patch.pitch
        if patch.volume is not None:
            cfg.volume = patch.volume
        return self.get_params()

    # ---- engine ----

    def get_engine_config(self) -> TtsEngineResponse:
        backend = self._backends.get(self._default)
        data = backend.get_engine_config() if backend else {
            "threads": 1,
            "sample_rate": (
                self._tts_config.sample_rate
                if self._tts_config and self._tts_config.sample_rate is not None
                else _STATIC_SAMPLE_RATES.get(self._default)
            ),
            "cache_policy": None,
        }
        return TtsEngineResponse(**data, pending_restart=self._engine_pending_restart)

    def update_engine_config(self, patch: TtsEnginePatch) -> TtsEngineResponse:
        self._engine_pending_restart = True
        return self.get_engine_config()

    # ---- stats ----

    def get_stats(self) -> TtsStatsResponse:
        total_req = self._stats["total_requests"]
        total_audio = self._stats["total_audio_ms"]
        total_proc = self._stats["total_processing_ms"]
        rtf_avg = total_proc / total_audio if total_audio > 0 else 0.0
        uptime_s = time.time() - self._stats["started_at"]
        return TtsStatsResponse(
            total_requests=total_req,
            total_errors=self._stats["total_errors"],
            rtf_avg=round(rtf_avg, 4),
            uptime_s=round(uptime_s, 1),
        )

    # ---- info ----

    def get_info(self) -> TtsInfoResponse:
        default_backend = self._backends.get(self._default)
        return TtsInfoResponse(
            initialized=bool(default_backend and default_backend.is_ready),
            backend=default_backend.backend_name if default_backend else self._default,
            num_voices=len(self.get_voices()),
            default_model=self._default,
            backends_loaded=list(self._backends.keys()),
        )

    # ---- model management ----

    async def load_model(self, model_id: str) -> dict:
        async with self._load_lock:
            existing = self._backends.get(model_id)
            if existing is not None and existing.state == BackendReadyState.READY:
                raise ModelAlreadyLoaded(f"model '{model_id}' already loaded")
            backend = await self._ensure_backend_locked(model_id)
        return {"loaded": True, "model_id": model_id, "state": backend.state.value}

    async def unload_model(self, model_id: str) -> dict:
        async with self._load_lock:
            if model_id not in self._backends:
                raise ModelNotLoaded(
                    f"model '{model_id}' not loaded",
                    details={"available": list(self._backends.keys())},
                )
            backend = self._backends.pop(model_id)
            await backend.shutdown()
        return {"unloaded": True, "model_id": model_id}

    async def switch_default(self, model_id: str) -> dict:
        async with self._load_lock:
            await self._ensure_backend_locked(model_id)
            self._default = model_id
        return {"switched": True, "default_model_id": model_id}

    async def shutdown(self) -> None:
        await self._shutdown_loaded_backends()

    # ---- tasks ----

    async def submit_task(self, req: TaskSubmitRequest) -> TaskSubmitResponse:
        await self._ensure_backend(req.model)
        record = await self._task_store.create(data=req.model_dump())
        asyncio.create_task(self._run_task(record.task_id))
        return TaskSubmitResponse(task_id=record.task_id, status="PENDING")

    async def _run_task(self, task_id: str) -> None:
        await self._task_store.update(task_id, status=TaskStatus.RUNNING, progress=0.0)
        try:
            record = await self._task_store.get(task_id)
            if record is None or record.status == TaskStatus.CANCELLED:
                return
            data = record.data

            async with self._load_lock:
                backend = await self._ensure_backend_locked(data.get("model"))
            result = await backend.synthesize(
                text=data["text"],
                voice_id=data.get("voice_id"),
                speed=float(data.get("speed", 1.0)),
                pitch=1.0,
                volume=1.0,
            )
            await self._task_store.update(task_id, progress=80.0)

            fmt = (data.get("response_format") or "wav").lower()
            audio_bytes, _ = encode_audio(result.audio, result.sample_rate, fmt)

            tmp = tempfile.NamedTemporaryFile(
                suffix=f".{fmt}", prefix=f"tts_{task_id}_", delete=False
            )
            tmp.write(audio_bytes)
            tmp.close()
            self._task_files[task_id] = Path(tmp.name)

            download_url = f"/v1/tts/tasks/{task_id}/audio"
            await self._task_store.update(
                task_id,
                status=TaskStatus.DONE,
                progress=100.0,
                result={"download_url": download_url, "duration_ms": result.duration_ms},
            )
            self._stats["total_requests"] += 1
            self._stats["total_processing_ms"] += result.processing_ms
            self._stats["total_audio_ms"] += result.duration_ms
        except Exception as e:
            logger.exception("TTS task %s failed", task_id)
            self._stats["total_errors"] += 1
            await self._task_store.update(
                task_id, status=TaskStatus.FAILED, error=str(e)
            )

    async def get_task(self, task_id: str) -> TaskStatusResponse:
        record = await self._task_store.get(task_id)
        if record is None:
            raise TaskNotFound(f"task '{task_id}' not found")
        created_at = datetime.fromtimestamp(
            record.created_at, tz=timezone.utc
        ).isoformat().replace("+00:00", "Z")
        download_url = None
        duration_ms = None
        if record.result is not None:
            download_url = record.result.get("download_url")
            duration_ms = record.result.get("duration_ms")
        return TaskStatusResponse(
            task_id=record.task_id,
            status=record.status.value,
            progress=record.progress,
            download_url=download_url,
            duration_ms=duration_ms,
            error=record.error,
            created_at=created_at,
        )

    async def cancel_task(self, task_id: str) -> TaskCancelResponse:
        record = await self._task_store.get(task_id)
        if record is None:
            raise TaskNotFound(f"task '{task_id}' not found")
        await self._task_store.update(task_id, status=TaskStatus.CANCELLED)
        return TaskCancelResponse(task_id=task_id, status="CANCELLED")

    def get_task_audio_path(self, task_id: str) -> Optional[Path]:
        return self._task_files.get(task_id)

    # ---- lexicons ----

    async def list_lexicons(self) -> TtsLexiconListResponse:
        records = await self._lexicon_store.list_all()
        items = [TtsLexiconItem(**r) for r in records]
        return TtsLexiconListResponse(lexicons=items)

    async def create_lexicon(self, req: TtsLexiconRequest) -> TtsLexiconItem:
        entries = [e.model_dump() for e in req.entries]
        record = await self._lexicon_store.create(entries=entries)
        await self._sync_lexicon_to_backends()
        return TtsLexiconItem(**record)

    async def delete_lexicon(self, lexicon_id: str) -> bool:
        deleted = await self._lexicon_store.delete(lexicon_id)
        if deleted:
            await self._sync_lexicon_to_backends()
        return deleted

    async def _sync_lexicon_to_backends(self) -> None:
        async with self._load_lock:
            await self._sync_lexicon_to_backends_locked()

    async def _sync_lexicon_to_backends_locked(self) -> None:
        records = await self._lexicon_store.list_all()
        all_entries: list[dict] = []
        for r in records:
            for entry in r.get("entries", []):
                if entry.get("word") and entry.get("phoneme"):
                    all_entries.append(entry)
        for backend in self._backends.values():
            updater = getattr(backend, "update_lexicon", None)
            if updater is None or getattr(backend, "_mock", False):
                continue
            try:
                await updater(all_entries)
            except Exception:
                backend_name = getattr(backend, "backend_name", type(backend).__name__)
                logger.warning(
                    "failed to sync TTS lexicon to backend '%s'",
                    backend_name,
                    exc_info=True,
                )
