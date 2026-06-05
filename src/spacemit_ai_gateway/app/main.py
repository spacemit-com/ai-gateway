"""SpacemiT AI Gateway 主入口。

路由分层（对齐设计文档 §1.3）：
- <domain>.api    — HTTP 路由（/recognize /synthesize /analyze 等）
- <domain>.stream — 流式路由（当前仅 WS；未来可扩展 SSE/chunked）

异常：
- HTTP DomainError / ValidationError / HTTPException / Exception → `gateway.errors.setup_exception_handlers`
- WS DomainError / Exception → `common.streams.ws_error_boundary`（各 handler 装饰）
"""

from __future__ import annotations

import ipaddress
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..domains.asr import api as asr_api
from ..domains.asr import stream as asr_stream
from ..domains.llm import api as llm_api
from ..domains.embed import api as embed_api
from ..domains.rerank import api as rerank_api
from ..domains.tts import api as tts_api
from ..domains.tts import stream as tts_stream
from ..domains.vad import api as vad_api
from ..domains.vad import stream as vad_stream
try:
    from ..domains.vlm import api as vlm_api
except Exception:
    vlm_api = None  # type: ignore[assignment]
    logging.getLogger(__name__).warning("VLM domain not available (missing dependencies), skipping")
try:
    from ..domains.vision import api as vision_api
except ImportError:
    vision_api = None  # type: ignore[assignment]
    logging.getLogger(__name__).warning("Vision domain not available (missing dependencies), skipping")
from ..gateway.errors import setup_exception_handlers
from ..gateway.health import router as health_router
from ..gateway.system_stats import router as system_stats_router
from .lifespan import lifespan
from .settings import get_settings

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.logging.level.upper(), logging.INFO),
    format=settings.logging.format,
)

app = FastAPI(
    title=settings.app.name,
    version=settings.app.version,
    description=(
        "SpacemiT AI Gateway — ASR / TTS / VAD / LLM / Embed / Rerank / VLM 统一 API。\n\n"
        "- ASR `/v1/asr/*`  语音识别（HTTP + WS 流式）\n"
        "- TTS `/v1/tts/*`  语音合成（HTTP + WS 流式）\n"
        "- VAD `/v1/vad/*`  语音活动检测（HTTP + WS 流式）\n"
        "- LLM `/v1/llm/*`  大语言模型（OpenAI 兼容）\n"
        "- Embed `/v1/embed/*`  文本嵌入（OpenAI 兼容）\n"
        "- Rerank `/v1/rerank/*`  文本重排序\n"
        "- VLM `/v1/vlm/*`  视觉语言模型（OpenAI 兼容）\n"
        "- Vision `/v1/vision/*`  视觉推理（HTTP + WS 流式）\n\n"

        "鉴权：若启用则在请求头携带 `X-API-Key`；WS 需先 POST `/stream/session` 取 `session_id`。"
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-RTF", "X-Duration-Ms", "X-Processing-Ms", "X-Sample-Rate"],
)


def _load_whitelist_file(path: str | None) -> list[str]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    entries = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            entries.append(line)
    return entries


class IPWhitelistMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, static_entries: list[str], whitelist_file: str | None):
        super().__init__(app)
        self._static = [ipaddress.ip_network(n, strict=False) for n in static_entries]
        self._file = whitelist_file
        self._file_networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        self._file_mtime: float = 0
        self._reload_file()

    def _reload_file(self):
        if not self._file:
            return
        p = Path(self._file)
        if not p.exists():
            self._file_networks = []
            self._file_mtime = 0
            return
        mtime = p.stat().st_mtime
        if mtime != self._file_mtime:
            self._file_mtime = mtime
            self._file_networks = [
                ipaddress.ip_network(n, strict=False) for n in _load_whitelist_file(self._file)
            ]

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        self._reload_file()
        client_ip = ipaddress.ip_address(request.client.host)
        all_networks = self._static + self._file_networks
        if not any(client_ip in net for net in all_networks):
            return JSONResponse(
                status_code=403,
                content={"error": "forbidden", "message": f"IP {client_ip} not allowed"},
            )
        return await call_next(request)


_wl_entries = settings.auth.ip_whitelist + _load_whitelist_file(settings.auth.ip_whitelist_file)
if settings.auth.enabled and (_wl_entries or settings.auth.ip_whitelist_file):
    app.add_middleware(
        IPWhitelistMiddleware,
        static_entries=settings.auth.ip_whitelist,
        whitelist_file=settings.auth.ip_whitelist_file,
    )

setup_exception_handlers(app)

app.include_router(health_router)
app.include_router(system_stats_router)
app.include_router(asr_api.router, prefix="/v1/asr", tags=["ASR"])
app.include_router(asr_stream.router, prefix="/v1/asr", tags=["ASR"])
app.include_router(tts_api.router, prefix="/v1/tts", tags=["TTS"])
app.include_router(tts_stream.router, prefix="/v1/tts", tags=["TTS"])
app.include_router(vad_api.router, prefix="/v1/vad", tags=["VAD"])
app.include_router(vad_stream.router, prefix="/v1/vad", tags=["VAD"])
app.include_router(llm_api.router, prefix="/v1/llm", tags=["LLM"])
app.include_router(llm_api.compat_router, tags=["LLM"])
app.include_router(embed_api.router, prefix="/v1/embed", tags=["Embed"])
app.include_router(embed_api.compat_router, tags=["Embed"])
app.include_router(rerank_api.router, prefix="/v1/rerank", tags=["Rerank"])
app.include_router(rerank_api.compat_router, tags=["Rerank"])
if vlm_api is not None:
    app.include_router(vlm_api.router, prefix="/v1/vlm", tags=["VLM"])
if vision_api is not None:
    app.include_router(vision_api.app.router, tags=["Vision"])


@app.get("/", tags=["Root"])
async def root():
    return {
        "name": settings.app.name,
        "version": settings.app.version,
        "docs": "/docs",
        "domains": {
            "asr": "/v1/asr",
            "tts": "/v1/tts",
            "vad": "/v1/vad",
            "llm": "/v1/llm",
            "embed": "/v1/embed",
            "rerank": "/v1/rerank",
            "vlm": "/v1/vlm",
            "vision": "/v1/vision",
        },
    }


def main():
    import uvicorn

    uvicorn.run(
        "spacemit_ai_gateway.app.main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.debug,
    )


if __name__ == "__main__":
    main()
