import json
import time
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from .schemas import DeregisterRequest, LoadRequest, RegisterRequest, SwitchRequest, UnloadRequest
from .service import EmbedService
from ...gateway.auth import verify_api_key

router = APIRouter()
compat_router = APIRouter()
logger = logging.getLogger(__name__)


def _get_service(request: Request) -> EmbedService:
    return request.app.state.embed_service


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
async def embed_healthz(request: Request):
    svc = _get_service(request)
    info = await svc.healthz()
    return {"status": info["state"], "model": svc.get_current_model()}


# ── 推理代理接口 ──────────────────────────────────────────────────────────────

async def _proxy(path: str, request: Request):
    """代理 embeddings 请求到后端（llama-server 或 remote API）。"""
    svc = _get_service(request)
    body = await request.body()
    request_id = str(uuid.uuid4())
    headers = {
        "Content-Type": request.headers.get("Content-Type", "application/json"),
        "X-Request-ID": request_id,
    }

    try:
        client, response = await svc.proxy(path, body, headers, stream=False)
    except RuntimeError as e:
        raise HTTPException(503, str(e))

    content = await response.aread()
    await response.aclose()
    await client.aclose()

    return JSONResponse(
        content=json.loads(content),
        status_code=response.status_code,
        headers={"X-Request-ID": request_id},
    )


@router.post("/embeddings")
async def embeddings(request: Request, _: None = Depends(verify_api_key)):
    """Embed 域的 embeddings 接口（带 /v1/embed 前缀）。"""
    return await _proxy("/v1/embeddings", request)


# ── OpenAI 兼容路由 ───────────────────────────────────────────────────────────

@compat_router.get("/v1/models")
async def openai_models_compat(request: Request):
    """OpenAI 兼容的 /v1/models 接口，返回当前加载的模型。"""
    svc = _get_service(request)
    current_id = svc.get_current_model()
    models = []
    if current_id:
        models.append({
            "id": current_id,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "spacemit-ai-gateway",
        })
    return {"object": "list", "data": models}


@compat_router.post("/v1/embeddings")
async def embeddings_compat(request: Request, _: None = Depends(verify_api_key)):
    """OpenAI 兼容的 /v1/embeddings 接口（无域前缀）。"""
    return await _proxy("/v1/embeddings", request)
