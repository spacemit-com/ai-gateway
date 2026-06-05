import json
import logging
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ...gateway.auth import verify_api_key
from .schemas import DeregisterRequest, LoadRequest, RegisterRequest, SwitchRequest, UnloadRequest
from .service import VlmService

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_service(request: Request) -> VlmService:
    return request.app.state.vlm_service


# ── 模型管理接口 ──────────────────────────────────────────────────────────────

@router.get("/models")
async def list_models(request: Request):
    svc = _get_service(request)
    return await svc.list_models()


@router.post("/models/register")
async def register_model(body: RegisterRequest, request: Request, _: None = Depends(verify_api_key)):
    svc = _get_service(request)
    try:
        return await svc.register(
            body.model or "",
            source_type=body.source_type,
            url=body.url,
            local_path=body.local_path,
            api_base_url=body.api_base_url,
            api_key=body.api_key,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/models/deregister")
async def deregister_model(body: DeregisterRequest, request: Request, _: None = Depends(verify_api_key)):
    svc = _get_service(request)
    try:
        await svc.deregister(body.model)
        return {"model": body.model, "status": "deregistered"}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/models/load")
async def load_model(body: LoadRequest, request: Request, _: None = Depends(verify_api_key)):
    svc = _get_service(request)
    try:
        await svc.load(body.model, extra_args=body.extra_args)
        return {"model": body.model, "status": "loaded"}
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))


@router.post("/models/{model}/download")
async def start_download(model: str, request: Request, _: None = Depends(verify_api_key)):
    svc = _get_service(request)
    try:
        await svc.download(model)
        return {"model": model, "status": "downloading"}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/models/{model}/download")
async def cancel_download(model: str, request: Request, _: None = Depends(verify_api_key)):
    svc = _get_service(request)
    try:
        await svc.cancel_download(model)
        return {"model": model, "status": "available"}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/models/{model}/download")
async def download_progress(model: str, request: Request):
    svc = _get_service(request)
    try:
        return await svc.get_download_progress(model)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/models/unload")
async def unload_model(body: UnloadRequest, request: Request, _: None = Depends(verify_api_key)):
    svc = _get_service(request)
    try:
        await svc.unload(body.model)
        return {"model": body.model, "status": "unloaded"}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/models/switch")
async def switch_model(body: SwitchRequest, request: Request, _: None = Depends(verify_api_key)):
    svc = _get_service(request)
    try:
        await svc.switch(body.model)
        return {"model": body.model, "status": "loaded"}
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))


@router.get("/healthz")
async def vlm_healthz(request: Request):
    svc = _get_service(request)
    info = await svc.healthz()
    return {"status": info["state"], "model": svc.get_current_model()}


# ── 推理代理接口 ──────────────────────────────────────────────────────────────

async def _proxy(path: str, request: Request, stream: bool):
    svc = _get_service(request)
    body = await request.body()
    request_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    headers = {
        "Content-Type": request.headers.get("Content-Type", "application/json"),
        "X-Request-ID": request_id,
    }

    try:
        client, response = await svc.proxy(path, body, headers, stream=stream)
    except RuntimeError as e:
        raise HTTPException(503, str(e))

    if stream:
        async def _iter() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
                await client.aclose()

        return StreamingResponse(
            _iter(),
            status_code=response.status_code,
            media_type="text/event-stream",
            headers={"X-Request-ID": request_id},
        )

    content = await response.aread()
    await response.aclose()
    await client.aclose()
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return Response(
            content=content,
            status_code=response.status_code,
            media_type=response.headers.get("content-type", "application/octet-stream"),
            headers={"X-Request-ID": request_id},
        )
    return JSONResponse(
        content=parsed,
        status_code=response.status_code,
        headers={"X-Request-ID": request_id},
    )


async def _smart_proxy(path: str, request: Request):
    try:
        body_bytes = await request.body()
        data = json.loads(body_bytes) if body_bytes else {}
        is_stream = bool(data.get("stream", False))
    except Exception:
        is_stream = False

    async def _receive():
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    request._receive = _receive  # type: ignore[attr-defined]
    return await _proxy(path, request, stream=is_stream)


@router.post("/chat/completions")
async def chat_completions(request: Request, _: None = Depends(verify_api_key)):
    return await _smart_proxy("/v1/chat/completions", request)

