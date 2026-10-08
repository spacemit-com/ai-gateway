"""HTTP 全局异常 handler。

DomainError 家族定义迁移到 `common/errors.py`；本模块只负责把 HTTP 层的异常
翻成 JSONResponse。WS 异常边界由 `common/streams.ws_error_boundary` 管。
"""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..common.error_log import record_fault
from ..common.errors import DomainError

try:
    from ..domains.vision.adapters.native import ServiceError as VisionServiceError
except ImportError:
    VisionServiceError = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def setup_exception_handlers(app: FastAPI) -> None:
    # 已标记域和模型的下载/加载/推理故障在这里统一记录，供 GET /v1/errors/recent 查询
    @app.exception_handler(DomainError)
    async def _(request: Request, exc: DomainError):
        await record_fault(exc)
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    if VisionServiceError is not None:
        @app.exception_handler(VisionServiceError)
        async def _(request: Request, exc: VisionServiceError):
            await record_fault(exc)
            return JSONResponse(
                status_code=exc.http_status,
                content={
                    "code": exc.code,
                    "message": exc.message,
                    "error": getattr(exc, "error", None) or "vision_error",
                    "retriable": getattr(exc, "retriable", False),
                    "details": getattr(exc, "details", None),
                },
            )

    @app.exception_handler(ValidationError)
    async def _(request: Request, exc: ValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "message": "Request validation failed",
                "retriable": False,
                "details": exc.errors(),
            },
        )

    @app.exception_handler(HTTPException)
    async def _(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "http_error",
                "message": str(exc.detail),
                "retriable": False,
            },
        )

    @app.exception_handler(Exception)
    async def _(request: Request, exc: Exception):
        logger.exception("unhandled HTTP exception: %s", exc)
        await record_fault(exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "Internal server error",
                "retriable": False,
            },
        )
