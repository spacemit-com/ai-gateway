"""ASR 业务编排。

职责：
- 调用 backend.recognize / create_stream
- 管理 session_id（HTTP /stream/session 签发 → WS /stream 取出）
- 按请求 model 字段路由到对应 backend
- 把 backend 异常（AsrBackendUnavailable / AsrInvalidAudio）原样传递

不管：HTTP / WS 协议细节。
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

from ...app.settings import AsrConfig
from ...common.audio_codec import normalize_audio_for_inference
from ...common.backend_selection import resolve_allowed_backends
from ...common.errors import (
    InvalidSessionError,
    JobNotFound,
    ModelAlreadyLoaded,
    ModelNotLoaded,
    ModelUnknown,
)
from ...common.lexicon_store import LexiconStore
from ...common.ready_state import BackendReadyState
from ...common.schemas import ModelInfo
from ...common.sessions import SessionStore
from ...common.task_store import TaskStatus, TaskStore
from .adapters import ASR_REGISTRY, AsrBackend, AsrStreamSession, RecognitionResult
from .schemas import (
    AsrAudioPatch,
    AsrAudioResponse,
    AsrEnginePatch,
    AsrEngineResponse,
    AsrInfoResponse,
    AsrLexiconItem,
    AsrLexiconListResponse,
    AsrLexiconRequest,
    AsrParamsPatch,
    AsrParamsResponse,
    AsrStatsResponse,
    HealthResponse,
    JobCancelResponse,
    JobStatusResponse,
    JobSubmitRequest,
    JobSubmitResponse,
    LanguagesResponse,
    RecognizeParams,
    RecognizeResponse,
    SentenceInfo,
    StreamSessionRequest,
    StreamSessionResponse,
)

logger = logging.getLogger(__name__)

_ASR_MODEL_INFO = {
    "sensevoice": {
        "name": "SenseVoice",
        "capabilities": ["multilingual", "streaming"],
        "languages": ["zh", "en", "ja", "ko", "yue", "auto"],
        "sample_rate": 16000,
    },
    "qwen3-asr": {
        "name": "Qwen3-ASR",
        "capabilities": ["multilingual"],
        "languages": ["zh", "en", "ja", "ko", "yue", "auto"],
        "sample_rate": 16000,
    },
}


class AsrService:
    def __init__(
        self,
        backends: Dict[str, AsrBackend],
        default: str,
        session_store: SessionStore,
        config: Optional[AsrConfig] = None,
        job_store: Optional[TaskStore] = None,
        lexicon_store: Optional[LexiconStore] = None,
    ):
        self._backends = backends
        self._default = default
        self._config = config or AsrConfig()
        self._allowed_backends = resolve_allowed_backends(
            self._config.backends,
            default,
            ASR_REGISTRY,
            self._backends,
        )
        if self._allowed_backends and self._default not in self._allowed_backends:
            self._default = self._allowed_backends[0]
        self._sessions = session_store
        self._job_store = job_store or TaskStore(namespace="asr-job")
        self._lexicon_store = lexicon_store or LexiconStore(namespace="asr")
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
    def backend(self) -> AsrBackend:
        return self._backends[self._default]

    def _model_id(self, model: Optional[str] = None) -> str:
        return model or self._default

    async def _shutdown_loaded_backends(self) -> None:
        for name, backend in list(self._backends.items()):
            logger.info("unloading ASR backend '%s' before loading another model", name)
            self._backends.pop(name, None)
            await backend.shutdown()

    async def _ensure_backend(self, model: Optional[str] = None) -> AsrBackend:
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

            cls = ASR_REGISTRY.get(name)
            if cls is None:
                raise ModelUnknown(
                    f"model '{name}' not registered",
                    details={"available": self._allowed_backends},
                )

            await self._shutdown_loaded_backends()
            cfg = self._config.model_copy(update={"backend": name})
            logger.info("loading ASR backend '%s' on demand", name)
            backend = cls(cfg)
            await backend.warmup()
            self._backends[name] = backend
            self._default = name
            await self._sync_hotwords_to_backends()
            return backend

    def _get_backend(self, model: Optional[str] = None) -> AsrBackend:
        name = model or self._default
        backend = self._backends.get(name)
        if backend is None:
            raise ModelNotLoaded(
                f"model '{name}' not loaded",
                details={"available": list(self._backends.keys())},
            )
        return backend

    async def recognize(
        self, audio: bytes, params: RecognizeParams
    ) -> RecognizeResponse:
        backend = await self._ensure_backend(params.model)
        hotwords = (
            [w.strip() for w in params.hotwords.split(",") if w.strip()]
            if params.hotwords
            else None
        )
        sample_rate = params.sample_rate if params.sample_rate > 0 else 16000
        try:
            result = await backend.recognize(
                audio=audio,
                sample_rate=sample_rate,
                language=params.language,
                punctuation=params.punctuation,
                hotwords=hotwords,
            )
        except Exception:
            self._stats["total_errors"] += 1
            raise
        self._stats["total_requests"] += 1
        self._stats["total_processing_ms"] += result.processing_ms
        self._stats["total_audio_ms"] += result.duration_ms
        if self._event_store:
            self._event_store.record("asr", "recognize")
        return _result_to_response(result)

    async def create_stream_session(
        self, req: StreamSessionRequest
    ) -> StreamSessionResponse:
        await self._ensure_backend(req.model)
        record = await self._sessions.create(
            data={
                "model": req.model,
                "sample_rate": req.sample_rate,
                "encoding": req.encoding,
                "language": req.language,
                "partial_results": req.partial_results,
                "client_id": req.client_id,
            }
        )
        expires_at = datetime.fromtimestamp(
            record.expires_at, tz=timezone.utc
        ).isoformat().replace("+00:00", "Z")
        return StreamSessionResponse(
            session_id=record.session_id,
            expires_at=expires_at,
            sample_rate=req.sample_rate,
            encoding=req.encoding,
            language=req.language,
        )

    async def open_stream(
        self,
        session_id: Optional[str],
        language: str,
        sample_rate: int,
        partial: bool,
    ) -> AsrStreamSession:
        if not session_id:
            raise InvalidSessionError("missing session_id; POST /stream/session first")
        record = await self._sessions.pop(session_id)
        if record is None:
            raise InvalidSessionError("session_id expired or invalid")

        backend = await self._ensure_backend(record.data.get("model"))

        effective_sr = sample_rate or int(record.data.get("sample_rate", 16000))
        effective_lang = language or str(record.data.get("language", "auto"))
        effective_partial = partial if partial is not None else bool(
            record.data.get("partial_results", True)
        )

        return await backend.create_stream(
            sample_rate=effective_sr,
            language=effective_lang,
            partial=effective_partial,
        )

    def get_models(self) -> List[ModelInfo]:
        models = []
        for name in self._allowed_backends:
            backend = self._backends.get(name)
            if backend is not None:
                models.extend(backend.get_models())
                continue
            info = _ASR_MODEL_INFO.get(name, {})
            models.append(ModelInfo(
                id=name,
                name=info.get("name", name),
                capabilities=info.get("capabilities", []),
                languages=info.get("languages", []),
                sample_rate=info.get("sample_rate"),
                loaded=False,
            ))
        return models

    def get_languages(self) -> LanguagesResponse:
        all_langs: set[str] = set()
        for name in self._allowed_backends:
            backend = self._backends.get(name)
            if backend is not None:
                all_langs.update(backend.get_supported_languages())
                continue
            info = _ASR_MODEL_INFO.get(name)
            if info:
                all_langs.update(info["languages"])
        return LanguagesResponse(
            languages=sorted(all_langs),
            default="auto",
        )

    async def healthz(self) -> dict:
        default_backend = self._backends.get(self._default)
        state = default_backend.state if default_backend else BackendReadyState.IDLE
        return HealthResponse(
            ready=state.is_serving,
            state=state.value,
            backend=default_backend.backend_name if default_backend else self._default,
        ).model_dump()

    # ---- params ----

    def get_params(self) -> AsrParamsResponse:
        backend = self._backends.get(self._default)
        data = backend.get_params() if backend else {
            "language": self._config.language if self._config else "auto",
            "punctuation": self._config.punctuation if self._config else True,
            "hotword_weight": None,
            "itn": None,
        }
        return AsrParamsResponse(**data)

    def update_params(self, patch: AsrParamsPatch) -> AsrParamsResponse:
        cfg = self._backends[self._default]._config if self._default in self._backends else self._config
        if patch.language is not None:
            cfg.language = patch.language
        if patch.punctuation is not None:
            cfg.punctuation = patch.punctuation
        return self.get_params()

    # ---- audio ----

    def get_audio_config(self) -> AsrAudioResponse:
        backend = self._backends.get(self._default)
        data = backend.get_audio_config() if backend else {
            "sample_rate": 16000,
            "vad_threshold": None,
            "denoise": False,
            "agc": False,
        }
        return AsrAudioResponse(**data)

    def update_audio_config(self, patch: AsrAudioPatch) -> AsrAudioResponse:
        return self.get_audio_config()

    # ---- engine ----

    def get_engine_config(self) -> AsrEngineResponse:
        backend = self._backends.get(self._default)
        data = backend.get_engine_config() if backend else {
            "num_threads": 1,
            "device": self._config.provider if self._config else "cpu",
            "power_mode": None,
        }
        return AsrEngineResponse(**data, pending_restart=self._engine_pending_restart)

    def update_engine_config(self, patch: AsrEnginePatch) -> AsrEngineResponse:
        self._engine_pending_restart = True
        return self.get_engine_config()

    # ---- stats ----

    def get_stats(self) -> AsrStatsResponse:
        total_req = self._stats["total_requests"]
        total_audio = self._stats["total_audio_ms"]
        total_proc = self._stats["total_processing_ms"]
        rtf_avg = total_proc / total_audio if total_audio > 0 else 0.0
        uptime_s = time.time() - self._stats["started_at"]
        return AsrStatsResponse(
            total_requests=total_req,
            total_errors=self._stats["total_errors"],
            rtf_avg=round(rtf_avg, 4),
            uptime_s=round(uptime_s, 1),
        )

    # ---- info ----

    def get_info(self) -> AsrInfoResponse:
        default_backend = self._backends.get(self._default)
        return AsrInfoResponse(
            initialized=bool(default_backend and default_backend.is_ready),
            backend=default_backend.backend_name if default_backend else self._default,
            model=self._default,
            backends_loaded=list(self._backends.keys()),
        )

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

    async def shutdown(self) -> None:
        await self._shutdown_loaded_backends()

    # ---- jobs ----

    async def submit_job(self, req: JobSubmitRequest) -> JobSubmitResponse:
        await self._ensure_backend(req.model)
        record = await self._job_store.create(data=req.model_dump())
        asyncio.create_task(self._run_job(record.task_id))
        return JobSubmitResponse(job_id=record.task_id, status="PENDING")

    async def _run_job(self, job_id: str) -> None:
        await self._job_store.update(job_id, status=TaskStatus.RUNNING, progress=0.0)
        try:
            record = await self._job_store.get(job_id)
            if record is None or record.status == TaskStatus.CANCELLED:
                return
            data = record.data

            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(data["audio_url"])
                resp.raise_for_status()
                audio = resp.content
                content_type = resp.headers.get("content-type")
                filename = str(resp.url.path)

            normalized = await asyncio.to_thread(
                normalize_audio_for_inference,
                audio,
                input_sample_rate=16000,
                target_sample_rate=self.get_audio_config().sample_rate,
                filename=filename,
                content_type=content_type,
            )

            await self._job_store.update(job_id, progress=50.0)
            record = await self._job_store.get(job_id)
            if record is None or record.status == TaskStatus.CANCELLED:
                return

            backend = await self._ensure_backend(data.get("model"))
            result = await backend.recognize(
                audio=normalized.pcm,
                sample_rate=normalized.sample_rate,
                language=data.get("language", "auto"),
                punctuation=True,
            )
            response = _result_to_response(result)
            await self._job_store.update(
                job_id,
                status=TaskStatus.DONE,
                progress=100.0,
                result=response.model_dump(),
            )
            self._stats["total_requests"] += 1
            self._stats["total_processing_ms"] += result.processing_ms
            self._stats["total_audio_ms"] += result.duration_ms
        except Exception as e:
            logger.exception("ASR job %s failed", job_id)
            self._stats["total_errors"] += 1
            await self._job_store.update(
                job_id, status=TaskStatus.FAILED, error=str(e)
            )

    async def get_job(self, job_id: str) -> JobStatusResponse:
        record = await self._job_store.get(job_id)
        if record is None:
            raise JobNotFound(f"job '{job_id}' not found")
        created_at = datetime.fromtimestamp(
            record.created_at, tz=timezone.utc
        ).isoformat().replace("+00:00", "Z")
        result_data = None
        if record.result is not None:
            result_data = RecognizeResponse(**record.result)
        return JobStatusResponse(
            job_id=record.task_id,
            status=record.status.value,
            progress=record.progress,
            result=result_data,
            error=record.error,
            created_at=created_at,
        )

    async def cancel_job(self, job_id: str) -> JobCancelResponse:
        record = await self._job_store.get(job_id)
        if record is None:
            raise JobNotFound(f"job '{job_id}' not found")
        await self._job_store.update(job_id, status=TaskStatus.CANCELLED)
        return JobCancelResponse(job_id=job_id, status="CANCELLED")

    # ---- lexicons ----

    async def list_lexicons(self) -> AsrLexiconListResponse:
        records = await self._lexicon_store.list_all()
        items = [AsrLexiconItem(**r) for r in records]
        return AsrLexiconListResponse(lexicons=items)

    async def create_lexicon(self, req: AsrLexiconRequest) -> AsrLexiconItem:
        entries = [e.model_dump() for e in req.entries]
        record = await self._lexicon_store.create(entries=entries, scope=req.scope)
        await self._sync_hotwords_to_backends()
        return AsrLexiconItem(**record)

    async def delete_lexicon(self, lexicon_id: str) -> bool:
        deleted = await self._lexicon_store.delete(lexicon_id)
        if deleted:
            await self._sync_hotwords_to_backends()
        return deleted

    async def _sync_hotwords_to_backends(self) -> None:
        records = await self._lexicon_store.list_all()
        all_words: list[str] = []
        for r in records:
            for entry in r.get("entries", []):
                word = entry.get("word", "")
                if word:
                    all_words.append(word)
        for backend in self._backends.values():
            if hasattr(backend, "_engine") and backend._engine and not getattr(backend, "_mock", False):
                try:
                    await asyncio.to_thread(backend._engine.update_hotwords, all_words)
                except Exception:
                    pass


def _result_to_response(result: RecognitionResult) -> RecognizeResponse:
    return RecognizeResponse(
        text=result.text,
        sentences=[
            SentenceInfo(
                text=s.get("text", ""),
                start_ms=int(s.get("start_ms", 0)),
                end_ms=int(s.get("end_ms", 0)),
            )
            for s in result.sentences
        ],
        duration_ms=result.duration_ms,
        processing_ms=result.processing_ms,
        rtf=result.rtf,
        language=result.language,
    )
