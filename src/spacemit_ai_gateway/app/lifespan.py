"""应用生命周期装配。

职责：
- 启动时只装配 service，不实例化 ASR/TTS/VAD 模型 backend
- ASR/TTS 各自独立 SessionStore（VAD 无状态不需要）
- 装配 service + stream handler 到 app.state
- LLM/Embed/Rerank 只初始化模型 DB，不启动默认模型
- 关闭时释放已按需加载的 backend
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..common.backend_selection import select_default_backend
from ..common.event_store import EventStore
from ..common.sessions import SessionStore
from ..domains.asr.adapters import ASR_REGISTRY
from ..domains.asr.service import AsrService
from ..domains.asr.stream import AsrStreamHandler
from ..domains.llm.adapters import build_llm_backends
from ..domains.llm.service import LLMService
from ..domains.embed.adapters import build_embed_backends
from ..domains.embed.service import EmbedService
from ..domains.rerank.adapters import build_rerank_backends
from ..domains.rerank.service import RerankService
from ..domains.tts.adapters import TTS_REGISTRY
from ..domains.tts.service import TtsService
from ..domains.tts.stream import TtsStreamHandler
from ..domains.vad.adapters import VAD_REGISTRY
from ..domains.vad.service import VadService
from ..domains.vad.stream import VadStreamHandler
from ..domains.vlm.adapters import build_vlm_backends
from ..domains.vlm.service import VlmService
try:
    from ..domains.vision import api as vision_api
except ImportError:
    vision_api = None  # type: ignore[assignment]
from .settings import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    logger.info("启动 %s v%s", settings.app.name, settings.app.version)
    logger.info("监听 %s:%s", settings.app.host, settings.app.port)

    llm_backends = build_llm_backends(settings.llm)
    embed_backends = build_embed_backends(settings.embed)
    rerank_backends = build_rerank_backends(settings.rerank)
    vlm_backends = build_vlm_backends(settings.vlm)

    asr_store = SessionStore(
        ttl_seconds=settings.asr.stream.session_ttl_s, namespace="asr"
    )
    tts_store = SessionStore(
        ttl_seconds=settings.tts.stream.session_ttl_s, namespace="tts"
    )

    asr_default = select_default_backend(
        settings.asr.backend, settings.asr.backends, ASR_REGISTRY
    )
    if asr_default != settings.asr.backend:
        logger.warning(
            "asr.backend '%s' not allowed or registered, falling back to '%s'",
            settings.asr.backend, asr_default,
        )
    tts_default = select_default_backend(
        settings.tts.backend, settings.tts.backends, TTS_REGISTRY
    )
    if tts_default != settings.tts.backend:
        logger.warning(
            "tts.backend '%s' not allowed or registered, falling back to '%s'",
            settings.tts.backend, tts_default,
        )
    vad_default = select_default_backend(
        settings.vad.backend, settings.vad.backends, VAD_REGISTRY
    )
    if vad_default != settings.vad.backend:
        logger.warning(
            "vad.backend '%s' not allowed or registered, falling back to '%s'",
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
    vlm_default = settings.vlm.backend
    if not vlm_default or vlm_default not in vlm_backends:
        vlm_default = next(iter(vlm_backends))
        logger.warning(
            "vlm.backend '%s' not in loaded backends, falling back to '%s'",
            settings.vlm.backend, vlm_default,
        )

    event_store = EventStore()

    asr_service = AsrService({}, asr_default, asr_store, config=settings.asr)
    tts_service = TtsService({}, tts_default, tts_store, config=settings.tts)
    vad_service = VadService({}, vad_default, config=settings.vad)
    llm_service = LLMService(llm_backends, llm_default, config=settings.llm)
    await llm_service.initialize()
    embed_service = EmbedService(embed_backends, embed_default, config=settings.embed)
    await embed_service.initialize()
    rerank_service = RerankService(rerank_backends, rerank_default, config=settings.rerank)
    await rerank_service.initialize()
    vlm_service = VlmService(vlm_backends, vlm_default, config=settings.vlm)
    await vlm_service.initialize()

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
    app.state.vlm_service = vlm_service
    app.state.asr_stream_handler = AsrStreamHandler(asr_service)
    app.state.tts_stream_handler = TtsStreamHandler(tts_service)
    app.state.vad_stream_handler = VadStreamHandler(vad_service)

    logger.info(
        "[lifespan] ready — models load lazily (asr=%s tts=%s vad=%s)",
        asr_default,
        tts_default,
        vad_default,
    )

    try:
        yield
    finally:
        logger.info("关闭 SpacemiT AI Gateway...")
        await asyncio.gather(
            asr_service.shutdown(),
            tts_service.shutdown(),
            vad_service.shutdown(),
            llm_service.shutdown(),
            embed_service.shutdown(),
            rerank_service.shutdown(),
            vlm_service.shutdown(),
            return_exceptions=True,
        )
        if vision_api is not None:
            try:
                vision_api.shutdown()
                logger.info("[lifespan] vision shutdown complete")
            except Exception as exc:
                logger.warning("[lifespan] vision shutdown error: %s", exc)
        logger.info("SpacemiT AI Gateway 已关闭")
