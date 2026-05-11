import json
import time
import uuid
import logging
from typing import AsyncIterator

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .schemas import DeregisterRequest, LoadRequest, RegisterRequest, SwitchRequest, UnloadRequest
from .service import LLMService
from ...gateway.auth import verify_api_key

router = APIRouter()
compat_router = APIRouter()
logger = logging.getLogger(__name__)


def _get_service(request: Request) -> LLMService:
    return request.app.state.llm_service


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
async def llm_healthz(request: Request):
    svc = _get_service(request)
    info = await svc.healthz()
    return {"status": info["state"], "model": svc.get_current_model()}


# ── 推理代理接口 ──────────────────────────────────────────────────────────────

async def _proxy(path: str, request: Request, stream: bool):
    svc = _get_service(request)
    body = await request.body()
    request_id = str(uuid.uuid4())
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
    else:
        content = await response.aread()
        await response.aclose()
        await client.aclose()
        return JSONResponse(
            content=json.loads(content),
            status_code=response.status_code,
            headers={"X-Request-ID": request_id},
        )


async def _smart_proxy(path: str, request: Request):
    """根据请求体中的 stream 字段决定是否流式。"""
    try:
        body_bytes = await request.body()
        data = json.loads(body_bytes) if body_bytes else {}
        is_stream = bool(data.get("stream", False))
    except Exception:
        is_stream = False

    # 重新包装 request.body() 因为已经读取过了
    async def _receive():
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    request._receive = _receive  # type: ignore[attr-defined]
    return await _proxy(path, request, stream=is_stream)


# ── Ollama 协议转换 ───────────────────────────────────────────────────────────

# Ollama options 请求级参数 → llama-server 字段映射
_OLLAMA_REQUEST_PARAMS: dict[str, str] = {
    "temperature":       "temperature",
    "top_p":             "top_p",
    "top_k":             "top_k",
    "num_predict":       "max_tokens",
    "num_ctx":           "n_ctx",
    "repeat_penalty":    "repeat_penalty",
    "seed":              "seed",
    "stop":              "stop",
    "tfs_z":             "tfs_z",
    "typical_p":         "typical_p",
    "presence_penalty":  "presence_penalty",
    "frequency_penalty": "frequency_penalty",
    "mirostat":          "mirostat",
    "mirostat_tau":      "mirostat_tau",
    "mirostat_eta":      "mirostat_eta",
    "penalize_nl":       "penalize_nl",
    "num_keep":          "n_keep",
}

# Ollama options 服务器级参数 → 对应 llama-server 启动参数（不能 per-request 修改）
_OLLAMA_SERVER_PARAMS: dict[str, str] = {
    "num_thread": "--threads",
    "num_gpu":    "--n-gpu-layers",
    "num_batch":  "--batch-size",
    "low_vram":   "--low-vram",
    "numa":       "--numa",
}


def _ollama_request_to_openai(data: dict, current_ctx_size: int | None = None) -> dict:
    """将 Ollama 请求体转换为 OpenAI/llama-server 格式。

    - 请求级 options 提升到顶层
    - 服务器级 options 返回 400
    - num_ctx 超出 current_ctx_size 时返回 400
    """
    options = data.get("options") or {}

    # 检查服务器级参数
    bad = [k for k in _OLLAMA_SERVER_PARAMS if k in options]
    if bad:
        details = "; ".join(
            f"{k} → extra_args=[\"{_OLLAMA_SERVER_PARAMS[k]}\", \"N\"]" for k in bad
        )
        raise HTTPException(
            400,
            f"Server-level parameters cannot be changed per-request: {details}. "
            "Reload the model with the corresponding extra_args to apply.",
        )

    # 检查 num_ctx 是否超出当前 --ctx-size
    if "num_ctx" in options and current_ctx_size is not None:
        requested = int(options["num_ctx"])
        if requested > current_ctx_size:
            raise HTTPException(
                400,
                f"num_ctx={requested} exceeds current --ctx-size={current_ctx_size}. "
                f"Reload the model with extra_args=[\"--ctx-size\", \"{requested}\"] to apply.",
            )

    result = {k: v for k, v in data.items() if k != "options"}
    for ollama_key, llama_key in _OLLAMA_REQUEST_PARAMS.items():
        if ollama_key in options:
            result[llama_key] = options[ollama_key]
    return result


def _openai_to_ollama_response(data: dict, model: str, stream: bool) -> dict:
    """将 OpenAI chat.completions 响应转换为 Ollama 格式。"""
    if stream:
        # 流式 delta chunk
        choice = data.get("choices", [{}])[0]
        delta = choice.get("delta", {})
        finish_reason = choice.get("finish_reason")
        return {
            "model": model,
            "created_at": "",
            "message": {"role": delta.get("role", "assistant"), "content": delta.get("content", "")},
            "done": finish_reason is not None,
            "done_reason": finish_reason or "",
        }
    else:
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage = data.get("usage", {})
        return {
            "model": model,
            "created_at": "",
            "message": {"role": message.get("role", "assistant"), "content": message.get("content", "")},
            "done": True,
            "done_reason": choice.get("finish_reason", "stop"),
            "prompt_eval_count": usage.get("prompt_tokens", 0),
            "eval_count": usage.get("completion_tokens", 0),
        }


def _openai_to_ollama_generate_response(data: dict, model: str) -> dict:
    """将 OpenAI completions 响应转换为 Ollama /api/generate 格式。"""
    choice = data.get("choices", [{}])[0]
    usage = data.get("usage", {})
    return {
        "model": model,
        "created_at": "",
        "response": choice.get("text", ""),
        "done": True,
        "done_reason": choice.get("finish_reason", "stop"),
        "prompt_eval_count": usage.get("prompt_tokens", 0),
        "eval_count": usage.get("completion_tokens", 0),
    }


async def _ollama_chat_proxy(request: Request):
    """Ollama /api/chat：转换请求 options，将响应转为 Ollama 格式。"""
    svc = _get_service(request)
    body_bytes = await request.body()
    try:
        data = json.loads(body_bytes) if body_bytes else {}
    except Exception:
        data = {}

    model = data.get("model", svc.get_current_model() or "")
    is_stream = bool(data.get("stream", False))
    current_ctx_size = await svc.get_current_ctx_size()
    openai_data = _ollama_request_to_openai(data, current_ctx_size=current_ctx_size)
    new_body = json.dumps(openai_data).encode()

    async def _receive():
        return {"type": "http.request", "body": new_body, "more_body": False}

    request._receive = _receive  # type: ignore[attr-defined]

    source_type = svc.get_current_source_type()
    if not source_type:
        raise HTTPException(503, "No model loaded")

    request_id = str(uuid.uuid4())
    headers = {
        "Content-Type": "application/json",
        "X-Request-ID": request_id,
    }

    try:
        client, response = await svc.proxy("/v1/chat/completions", new_body, headers, stream=is_stream)
    except RuntimeError as e:
        raise HTTPException(503, str(e))

    if is_stream:
        async def _iter() -> AsyncIterator[bytes]:
            try:
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                        ollama_chunk = _openai_to_ollama_response(chunk, model, stream=True)
                        yield json.dumps(ollama_chunk).encode() + b"\n"
                    except Exception:
                        pass
                # 发送 done=true 的最终帧
                yield json.dumps({
                    "model": model,
                    "created_at": "",
                    "message": {"role": "assistant", "content": ""},
                    "done": True,
                    "done_reason": "stop",
                }).encode() + b"\n"
            finally:
                await response.aclose()
                await client.aclose()

        return StreamingResponse(
            _iter(),
            status_code=response.status_code,
            media_type="application/x-ndjson",
            headers={"X-Request-ID": request_id},
        )
    else:
        content = await response.aread()
        await response.aclose()
        await client.aclose()
        try:
            openai_resp = json.loads(content)
            ollama_resp = _openai_to_ollama_response(openai_resp, model, stream=False)
        except Exception:
            return JSONResponse(content=json.loads(content), status_code=response.status_code)
        return JSONResponse(content=ollama_resp, status_code=response.status_code, headers={"X-Request-ID": request_id})


async def _ollama_generate_proxy(request: Request):
    """Ollama /api/generate：转换请求 options，将响应转为 Ollama generate 格式。"""
    svc = _get_service(request)
    body_bytes = await request.body()
    try:
        data = json.loads(body_bytes) if body_bytes else {}
    except Exception:
        data = {}

    model = data.get("model", svc.get_current_model() or "")
    ctx_size = await svc.get_current_ctx_size()
    openai_data = _ollama_request_to_openai(data, current_ctx_size=ctx_size)
    # Ollama generate 用 prompt，OpenAI completions 也用 prompt，字段名一致
    new_body = json.dumps(openai_data).encode()

    source_type = svc.get_current_source_type()
    if not source_type:
        raise HTTPException(503, "No model loaded")

    request_id = str(uuid.uuid4())
    headers = {"Content-Type": "application/json", "X-Request-ID": request_id}

    try:
        client, response = await svc.proxy("/v1/completions", new_body, headers, stream=False)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    content = await response.aread()
    await response.aclose()
    await client.aclose()
    try:
        openai_resp = json.loads(content)
        ollama_resp = _openai_to_ollama_generate_response(openai_resp, model)
    except Exception:
        return JSONResponse(content=json.loads(content), status_code=response.status_code)
    return JSONResponse(content=ollama_resp, status_code=response.status_code, headers={"X-Request-ID": request_id})


# ── llama-server 原生接口代理 ─────────────────────────────────────────────────

@router.post("/chat/completions")
async def chat_completions(request: Request, _: None = Depends(verify_api_key)):
    return await _smart_proxy("/v1/chat/completions", request)


@router.post("/completions")
async def completions(request: Request, _: None = Depends(verify_api_key)):
    return await _smart_proxy("/v1/completions", request)


@router.post("/completion")
async def completion(request: Request, _: None = Depends(verify_api_key)):
    return await _smart_proxy("/completion", request)


@router.post("/api/chat")
async def api_chat(request: Request, _: None = Depends(verify_api_key)):
    """Ollama 风格 chat，转换 options 参数并将响应转为 Ollama 格式。"""
    return await _ollama_chat_proxy(request)


@router.post("/api/generate")
async def api_generate(request: Request, _: None = Depends(verify_api_key)):
    """Ollama 风格单次生成，对应 /v1/completions。"""
    return await _ollama_generate_proxy(request)


@router.get("/api/tags")
async def api_tags(request: Request):
    """Ollama 风格模型列表别名。"""
    svc = _get_service(request)
    current_id = svc.get_current_model()
    models = []
    if current_id:
        models.append({"name": current_id, "model": current_id})
    return {"models": models}


@router.post("/api/show")
async def api_show(request: Request):
    """返回模板、能力、模型摘要（透传到 llama-server）。"""
    return await _smart_proxy("/api/show", request)


@router.post("/responses")
async def responses(request: Request, _: None = Depends(verify_api_key)):
    return await _smart_proxy("/v1/responses", request)


@router.post("/tokenize")
async def tokenize(request: Request, _: None = Depends(verify_api_key)):
    return await _smart_proxy("/tokenize", request)


@router.post("/detokenize")
async def detokenize(request: Request, _: None = Depends(verify_api_key)):
    return await _smart_proxy("/detokenize", request)


@router.post("/apply-template")
async def apply_template(request: Request, _: None = Depends(verify_api_key)):
    return await _smart_proxy("/apply-template", request)


@router.post("/infill")
async def infill(request: Request, _: None = Depends(verify_api_key)):
    return await _smart_proxy("/infill", request)


@router.get("/props")
async def get_props(request: Request):
    svc = _get_service(request)
    source_type = svc.get_current_source_type()
    if not source_type or source_type == "remote":
        raise HTTPException(503, "No local model loaded")
    if not svc.adapter or not svc.adapter.is_running():
        raise HTTPException(503, "No model loaded")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{svc.adapter.base_url}/props")
    return JSONResponse(content=resp.json(), status_code=resp.status_code)


@router.post("/props")
async def set_props(request: Request, _: None = Depends(verify_api_key)):
    svc = _get_service(request)
    source_type = svc.get_current_source_type()
    if not source_type or source_type == "remote":
        raise HTTPException(503, "No local model loaded")
    if not svc.adapter or not svc.adapter.is_running():
        raise HTTPException(503, "No model loaded")
    body = await request.body()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{svc.adapter.base_url}/props",
            content=body,
            headers={"Content-Type": "application/json"},
        )
    return JSONResponse(content=resp.json(), status_code=resp.status_code)


@router.get("/slots")
async def get_slots(request: Request):
    svc = _get_service(request)
    source_type = svc.get_current_source_type()
    if not source_type or source_type == "remote":
        raise HTTPException(503, "No local model loaded")
    if not svc.adapter or not svc.adapter.is_running():
        raise HTTPException(503, "No model loaded")
    fail_on_no_slot = request.query_params.get("fail_on_no_slot", "false")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{svc.adapter.base_url}/slots",
            params={"fail_on_no_slot": fail_on_no_slot},
        )
    return JSONResponse(content=resp.json(), status_code=resp.status_code)


@router.post("/slots/{id_slot}")
async def slot_action(id_slot: int, request: Request, _: None = Depends(verify_api_key)):
    svc = _get_service(request)
    source_type = svc.get_current_source_type()
    if not source_type or source_type == "remote":
        raise HTTPException(503, "No local model loaded")
    if not svc.adapter or not svc.adapter.is_running():
        raise HTTPException(503, "No model loaded")
    action = request.query_params.get("action", "")
    body = await request.body()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{svc.adapter.base_url}/slots/{id_slot}",
            params={"action": action},
            content=body,
            headers={"Content-Type": "application/json"},
        )
    return JSONResponse(content=resp.json(), status_code=resp.status_code)


@router.get("/metrics")
async def metrics(request: Request):
    svc = _get_service(request)
    source_type = svc.get_current_source_type()
    if not source_type or source_type == "remote":
        raise HTTPException(503, "No local model loaded")
    if not svc.adapter or not svc.adapter.is_running():
        raise HTTPException(503, "No model loaded")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{svc.adapter.base_url}/metrics")
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(content=resp.text, status_code=resp.status_code)


@router.get("/lora-adapters")
async def get_lora_adapters(request: Request):
    svc = _get_service(request)
    source_type = svc.get_current_source_type()
    if not source_type or source_type == "remote":
        raise HTTPException(503, "No local model loaded")
    if not svc.adapter or not svc.adapter.is_running():
        raise HTTPException(503, "No model loaded")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{svc.adapter.base_url}/lora-adapters")
    return JSONResponse(content=resp.json(), status_code=resp.status_code)


@router.post("/lora-adapters")
async def set_lora_adapters(request: Request, _: None = Depends(verify_api_key)):
    svc = _get_service(request)
    source_type = svc.get_current_source_type()
    if not source_type or source_type == "remote":
        raise HTTPException(503, "No local model loaded")
    if not svc.adapter or not svc.adapter.is_running():
        raise HTTPException(503, "No model loaded")
    body = await request.body()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{svc.adapter.base_url}/lora-adapters",
            content=body,
            headers={"Content-Type": "application/json"},
        )
    return JSONResponse(content=resp.json(), status_code=resp.status_code)


@router.get("/models/openai")
async def openai_models(request: Request):
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


# ── OpenAI 兼容路由（无前缀，供标准客户端直接对接）────────────────────────────

@compat_router.post("/v1/chat/completions")
async def chat_completions_compat(request: Request, _: None = Depends(verify_api_key)):
    return await _smart_proxy("/v1/chat/completions", request)


@compat_router.post("/v1/completions")
async def completions_compat(request: Request, _: None = Depends(verify_api_key)):
    return await _smart_proxy("/v1/completions", request)


@compat_router.post("/v1/responses")
async def responses_compat(request: Request, _: None = Depends(verify_api_key)):
    return await _smart_proxy("/v1/responses", request)


@compat_router.get("/v1/models")
async def openai_models_compat(request: Request):
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


@compat_router.get("/models")
async def models_alias(request: Request):
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


@compat_router.post("/chat/completions")
async def chat_completions_alias(request: Request, _: None = Depends(verify_api_key)):
    return await _smart_proxy("/v1/chat/completions", request)


@compat_router.post("/completions")
async def completions_alias(request: Request, _: None = Depends(verify_api_key)):
    return await _smart_proxy("/v1/completions", request)


# ── Anthropic 兼容路由 ────────────────────────────────────────────────────────

@compat_router.post("/v1/messages")
async def anthropic_messages(request: Request, _: None = Depends(verify_api_key)):
    return await _smart_proxy("/v1/messages", request)


@compat_router.post("/v1/messages/count_tokens")
async def anthropic_count_tokens(request: Request, _: None = Depends(verify_api_key)):
    body = await request.body()

    async def _receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = _receive  # type: ignore[attr-defined]
    return await _proxy("/v1/messages/count_tokens", request, stream=False)
