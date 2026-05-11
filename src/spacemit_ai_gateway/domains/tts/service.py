"""TTS 业务编排。"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from ...common.audio_codec import encode_audio
from ...app.settings import TtsConfig
from ...common.ready_state import BackendReadyState
from ...common.errors import (
    InvalidSessionError,
    ModelAlreadyLoaded,
    ModelNotLoaded,
    ModelUnknown,
    ModelUnloadForbidden,
    TaskNotFound,
)
from ...common.lexicon_store import LexiconStore
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
        self._tts_config = config
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

    @property
    def backend(self) -> TtsBackend:
        return self._backends[self._default]

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
        backend = self._get_backend(req.model)
        try:
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
        self._get_backend(req.model)
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

        backend = self._get_backend(record.data.get("model"))
        effective_voice = voice_id or record.data.get("voice_id")
        speed = float(record.data.get("speed", 1.0))
        return await backend.open_stream(
            voice_id=effective_voice, speed=speed
        )

    def get_voices(self) -> List[VoiceInfo]:
        voices = []
        for backend in self._backends.values():
            voices.extend(backend.get_voices())
        return voices

    def get_models(self) -> List[ModelInfo]:
        models = []
        for backend in self._backends.values():
            models.extend(backend.get_models())
        return models

    async def healthz(self) -> dict:
        default_backend = self._backends[self._default]
        state = default_backend.state
        return HealthResponse(
            ready=state.is_serving,
            state=state.value,
            backend=default_backend.backend_name,
        ).model_dump()

    # ---- params ----

    def get_params(self) -> TtsParamsResponse:
        data = self._backends[self._default].get_params()
        return TtsParamsResponse(**data)

    def update_params(self, patch: TtsParamsPatch) -> TtsParamsResponse:
        backend = self._backends[self._default]
        cfg = backend._config
        if patch.speed is not None:
            cfg.speed = patch.speed
        if patch.pitch is not None:
            cfg.pitch = patch.pitch
        if patch.volume is not None:
            cfg.volume = patch.volume
        return self.get_params()

    # ---- engine ----

    def get_engine_config(self) -> TtsEngineResponse:
        data = self._backends[self._default].get_engine_config()
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
        default_backend = self._backends[self._default]
        return TtsInfoResponse(
            initialized=default_backend.is_ready,
            backend=default_backend.backend_name,
            num_voices=len(self.get_voices()),
            default_model=self._default,
            backends_loaded=list(self._backends.keys()),
        )

    # ---- model management ----

    async def load_model(self, model_id: str) -> dict:
        existing = self._backends.get(model_id)
        if existing is not None and existing.state == BackendReadyState.READY:
            raise ModelAlreadyLoaded(f"model '{model_id}' already loaded")
        cls = TTS_REGISTRY.get(model_id)
        if cls is None:
            raise ModelUnknown(
                f"model '{model_id}' not registered",
                details={"available": list(TTS_REGISTRY.keys())},
            )
        cfg = self._tts_config.model_copy(update={"backend": model_id}) if self._tts_config else None
        backend = cls(cfg)
        await backend.warmup()
        if existing is not None:
            logger.info("replacing degraded backend '%s' (state=%s)", model_id, existing.state.value)
            await existing.shutdown()
        self._backends[model_id] = backend
        return {"loaded": True, "model_id": model_id, "state": backend.state.value}

    async def unload_model(self, model_id: str) -> dict:
        if model_id not in self._backends:
            raise ModelNotLoaded(
                f"model '{model_id}' not loaded",
                details={"available": list(self._backends.keys())},
            )
        if model_id == self._default:
            raise ModelUnloadForbidden(f"cannot unload default model '{model_id}'")
        backend = self._backends.pop(model_id)
        await backend.shutdown()
        return {"unloaded": True, "model_id": model_id}

    def switch_default(self, model_id: str) -> dict:
        if model_id not in self._backends:
            raise ModelNotLoaded(
                f"model '{model_id}' not loaded",
                details={"available": list(self._backends.keys())},
            )
        self._default = model_id
        return {"switched": True, "default_model_id": model_id}

    # ---- tasks ----

    async def submit_task(self, req: TaskSubmitRequest) -> TaskSubmitResponse:
        self._get_backend(req.model)
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

            backend = self._get_backend(data.get("model"))
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
        records = await self._lexicon_store.list_all()
        all_entries: list[dict] = []
        for r in records:
            for entry in r.get("entries", []):
                if entry.get("word") and entry.get("phoneme"):
                    all_entries.append(entry)
        for backend in self._backends.values():
            engine = getattr(backend, "_engine", None)
            if engine and hasattr(engine, "update_lexicon") and not getattr(backend, "_mock", False):
                try:
                    await asyncio.to_thread(engine.update_lexicon, all_entries)
                except Exception:
                    pass
