"""应用生命周期装配。

职责：
- 用 build_*_backends 工厂实例化 ASR/TTS 多 backend（按 config.backends 预载）
- VAD 单 backend 不变
- ASR/TTS 各自独立 SessionStore（VAD 无状态不需要）
- 装配 service + stream handler 到 app.state
- warmup 用 asyncio.create_task 异步触发，不阻塞 startup
- 关闭时 cancel warmup、并行 await backend.shutdown()
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..common.event_store import EventStore
from ..common.sessions import SessionStore
from ..domains.asr.adapters import build_asr_backends
from ..domains.asr.service import AsrService
from ..domains.asr.stream import AsrStreamHandler
from ..domains.llm.adapters import build_llm_backends
from ..domains.llm.service import LLMService
from ..domains.embed.adapters import build_embed_backends
from ..domains.embed.service import EmbedService
from ..domains.rerank.adapters import build_rerank_backends
from ..domains.rerank.service import RerankService
from ..domains.tts.adapters import build_tts_backends
from ..domains.tts.service import TtsService
from ..domains.tts.stream import TtsStreamHandler
from ..domains.vad.adapters import build_vad_backends
from ..domains.vad.service import VadService
from ..domains.vad.stream import VadStreamHandler
try:
    from ..domains.vision import api as vision_api
except Exception:
    vision_api = None  # type: ignore[assignment]
from .settings import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    logger.info("启动 %s v%s", settings.app.name, settings.app.version)
    logger.info("监听 %s:%s", settings.app.host, settings.app.port)

    asr_backends = build_asr_backends(settings.asr)
    tts_backends = build_tts_backends(settings.tts)
    vad_backends = build_vad_backends(settings.vad)
    llm_backends = build_llm_backends(settings.llm)
    embed_backends = build_embed_backends(settings.embed)
    rerank_backends = build_rerank_backends(settings.rerank)

    asr_store = SessionStore(
        ttl_seconds=settings.asr.stream.session_ttl_s, namespace="asr"
    )
    tts_store = SessionStore(
        ttl_seconds=settings.tts.stream.session_ttl_s, namespace="tts"
    )

    asr_default = settings.asr.backend
    if asr_default not in asr_backends:
        asr_default = next(iter(asr_backends))
        logger.warning(
            "asr.backend '%s' not in loaded backends, falling back to '%s'",
            settings.asr.backend, asr_default,
        )
    tts_default = settings.tts.backend
    if tts_default not in tts_backends:
        tts_default = next(iter(tts_backends))
        logger.warning(
            "tts.backend '%s' not in loaded backends, falling back to '%s'",
            settings.tts.backend, tts_default,
        )
    vad_default = settings.vad.backend
    if vad_default not in vad_backends:
        vad_default = next(iter(vad_backends))
        logger.warning(
            "vad.backend '%s' not in loaded backends, falling back to '%s'",
            settings.vad.backend, vad_default,
        )
    llm_default = settings.llm.backend
    if not llm_default or llm_default not in llm_backends:
        llm_default = next(iter(llm_backends))
        logger.warning(
            "llm.backend '%s' not in loaded backends, falling back to '%s'",
            settings.llm.backend, llm_default,
        )
    embed_default = settings.embed.backend
    if not embed_default or embed_default not in embed_backends:
        embed_default = next(iter(embed_backends))
        logger.warning(
            "embed.backend '%s' not in loaded backends, falling back to '%s'",
            settings.embed.backend, embed_default,
        )
    rerank_default = settings.rerank.backend
    if not rerank_default or rerank_default not in rerank_backends:
        rerank_default = next(iter(rerank_backends))
        logger.warning(
            "rerank.backend '%s' not in loaded backends, falling back to '%s'",
            settings.rerank.backend, rerank_default,
        )

    event_store = EventStore()

    asr_service = AsrService(asr_backends, asr_default, asr_store, config=settings.asr)
    tts_service = TtsService(tts_backends, tts_default, tts_store, config=settings.tts)
    vad_service = VadService(vad_backends, vad_default, config=settings.vad)
    llm_service = LLMService(llm_backends, llm_default, config=settings.llm)
    await llm_service.initialize()
    embed_service = EmbedService(embed_backends, embed_default, config=settings.embed)
    await embed_service.initialize()
    rerank_service = RerankService(rerank_backends, rerank_default, config=settings.rerank)
    await rerank_service.initialize()

    if vision_api is not None:
        try:
            vision_api.setup()
            native = vision_api._adapter.native_available if vision_api._adapter else False
            logger.info("[lifespan] vision initialized (native=%s)", native)
        except Exception as exc:
            logger.error("[lifespan] vision init failed: %s", exc)

    asr_service._event_store = event_store
    tts_service._event_store = event_store
    vad_service._event_store = event_store

    app.state.settings = settings
    app.state.event_store = event_store
    app.state.asr_service = asr_service
    app.state.tts_service = tts_service
    app.state.vad_service = vad_service
    app.state.llm_service = llm_service
    app.state.embed_service = embed_service
    app.state.rerank_service = rerank_service
    app.state.asr_stream_handler = AsrStreamHandler(asr_service)
    app.state.tts_stream_handler = TtsStreamHandler(tts_service)
    app.state.vad_stream_handler = VadStreamHandler(vad_service)

    all_backends = (
        list(asr_backends.values())
        + list(tts_backends.values())
        + list(vad_backends.values())
        + list(llm_backends.values())
        + list(embed_backends.values())
        + list(rerank_backends.values())
    )
    app.state.warmup_task = asyncio.create_task(
        _warmup_all(all_backends),
        name="spacemit-ai-gateway-warmup",
    )

    asr_names = list(asr_backends.keys())
    tts_names = list(tts_backends.keys())
    vad_names = list(vad_backends.keys())
    logger.info(
        "[lifespan] ready — asr=%s tts=%s vad=%s (warmup running in background)",
        asr_names,
        tts_names,
        vad_names,
    )

    try:
        yield
    finally:
        logger.info("关闭 SpacemiT AI Gateway...")
        task = getattr(app.state, "warmup_task", None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        await asyncio.gather(
            *(b.shutdown() for b in all_backends),
            return_exceptions=True,
        )
        if vision_api is not None:
            try:
                vision_api.shutdown()
                logger.info("[lifespan] vision shutdown complete")
            except Exception as exc:
                logger.warning("[lifespan] vision shutdown error: %s", exc)
        logger.info("SpacemiT AI Gateway 已关闭")


async def _warmup_all(backends) -> None:
    results = await asyncio.gather(
        *(b.warmup() for b in backends),
        return_exceptions=True,
    )
    for backend, r in zip(backends, results):
        name = backend.backend_name
        if isinstance(r, Exception):
            logger.warning("[warmup] %s failed: %s", name, r)
        else:
            logger.info("[warmup] %s ready", name)
