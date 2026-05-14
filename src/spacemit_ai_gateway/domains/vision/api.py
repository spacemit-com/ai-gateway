from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Optional

from fastapi import Depends, FastAPI, File, Form, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .adapters.native import NativeAdapter, ServiceError
from ...gateway.auth import verify_api_key
from .features import compute_similarity, infer_embedding
from .models import ModelRegistry
from .schemas import (
    ApiResponse,
    EngineConfig,
    ErrorCode,
    HealthData,
    JobCreateRequest,
    ModelLoadRequest,
    ModelSwitchRequest,
    ModelUnloadRequest,
    SequenceRequest,
    StatsData,
    VisionParams,
)
from .jobs import JobManager
from .sequence import infer_sequence
from .service import VisionService
from .stream import StreamSessionManager

# ── 全局实例（由 setup() 初始化）────────────────────────────────────

_adapter: Optional[NativeAdapter] = None
_registry: Optional[ModelRegistry] = None
_vision_service: Optional[VisionService] = None
_stream_mgr: Optional[StreamSessionManager] = None
_job_mgr: Optional[JobManager] = None

# 运行时可变参数
_params = VisionParams()
_engine = EngineConfig()
_stats = StatsData()


def setup() -> None:
    """在 lifespan 中调用，初始化 Vision 全局实例。"""
    global _adapter, _registry, _vision_service, _stream_mgr, _job_mgr
    _adapter = NativeAdapter()
    _registry = ModelRegistry(_adapter)
    _vision_service = VisionService(_adapter, _registry)
    _stream_mgr = StreamSessionManager(_adapter, _registry)
    _job_mgr = JobManager(_adapter, _registry)


def shutdown() -> None:
    """在 lifespan 关闭时调用，释放所有已加载的视觉模型。"""
    if _registry is None:
        return
    with _registry._lock:
        model_ids = list(_registry._models.keys())
    for mid in model_ids:
        try:
            _registry.unload_model(mid)
        except Exception:
            pass

app = FastAPI(
    title="Vision OpenAPI",
    version="2.0.0",
    description="Vision domain API aligned with ai-gateway §7",
)


# ── Helpers ─────────────────────────────────────────────────────────

def domain_health_summary() -> dict[str, Any]:
    if _registry is None:
        return {"ready": False, "state": "uninitialized", "backend": "unknown"}
    models = _registry.list_models().data
    if not models:
        return {"ready": False, "state": "uninitialized", "backend": "unknown"}

    ready_models = [m for m in models if m.status == "ready"]
    if ready_models:
        backend = ready_models[0].backend or "unknown"
        return {"ready": True, "state": "ready", "backend": backend}

    # 模型已注册但未就绪时，暴露当前状态用于排障
    first = models[0]
    return {"ready": False, "state": first.status, "backend": first.backend or "unknown"}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))


def _ok(request: Request, data: Any = None) -> JSONResponse:
    payload = ApiResponse(code=int(ErrorCode.OK), message="ok", request_id=_request_id(request), data=data)
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


def _coerce_threshold(value: Any, fallback: Optional[float]) -> Optional[float]:
    """Parse a conf/iou candidate. Returns a positive float or ``fallback``.

    Strings (from query params) are accepted. Non-positive or unparsable values
    fall back to the provided default.
    """
    if value is None or value == "":
        return fallback
    try:
        v = float(value)
    except (TypeError, ValueError):
        return fallback
    return v if v > 0 else fallback


def _timing_infer_ms(timing: Any) -> Optional[float]:
    """Extract infer_ms from timing object, with fallback aggregation."""
    if timing is None:
        return None

    direct = getattr(timing, "infer_ms", None)
    if direct is not None:
        try:
            return float(direct)
        except Exception:
            pass

    # Fallback: sum non-null stage timings.
    fields = (
        "preprocess_ms",
        "model_infer_ms",
        "postprocess_ms",
        "detect_ms",
        "track_ms",
        "embedding_ms",
        "sequence_ms",
        "draw_ms",
    )
    total = 0.0
    seen = False
    for f in fields:
        v = getattr(timing, f, None)
        if v is None:
            continue
        try:
            total += float(v)
            seen = True
        except Exception:
            continue
    return total if seen else None


# ── Middleware & Exception Handlers ─────────────────────────────────

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-Id"] = rid
    return response


@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError):
    payload = ApiResponse(code=exc.code, message=exc.message, request_id=_request_id(request))
    return JSONResponse(status_code=exc.http_status, content=payload.model_dump(mode="json"))


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    payload = ApiResponse(code=int(ErrorCode.INVALID_ARGUMENT), message=str(exc), request_id=_request_id(request))
    return JSONResponse(status_code=400, content=payload.model_dump(mode="json"))


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    payload = ApiResponse(
        code=int(ErrorCode.INTERNAL_ERROR),
        message=f"internal error: {exc}",
        request_id=_request_id(request),
    )
    return JSONResponse(status_code=500, content=payload.model_dump(mode="json"))


# ── 7.6 Health ──────────────────────────────────────────────────────

@app.get("/v1/vision/healthz", tags=["health"])
async def healthz(request: Request):
    has_models = len(_registry.list_models().data) > 0
    data = HealthData(status="ok", readiness=has_models, liveness=True)
    return _ok(request, data=data.model_dump())


# ── 7.1 Inference ───────────────────────────────────────────────────

@app.post("/v1/vision/inference", tags=["inference"])
async def inference(
    request: Request,
    file: Optional[UploadFile] = File(default=None),
    tasks: Optional[str] = Form(default=None),
    model_id: Optional[str] = Form(default=None),
    handle: Optional[str] = Form(default=None),
    render: Optional[str] = Form(default=None),
    render_mode: Optional[str] = Form(default=None),
    conf: Optional[float] = Form(default=None),
    iou: Optional[float] = Form(default=None),
    _: None = Depends(verify_api_key),
):
    # 支持 multipart/form-data 和 application/json
    content_type = (request.headers.get("content-type") or "").lower()

    # query param 优先（绕过某些 python-multipart 版本的 Form 截断 bug）
    qs_model_id = request.query_params.get("model_id")
    qs_conf = request.query_params.get("conf")
    qs_iou = request.query_params.get("iou")

    if "application/json" in content_type:
        body = await request.json()
        task_list = body.get("tasks", [])
        mid = qs_model_id or body.get("model_id")
        do_render = bool(body.get("render", False))
        rmode = body.get("render_mode")
        req_conf = body.get("conf")
        req_iou = body.get("iou")
        image_bytes = _vision_service.resolve_image_bytes(
            image_base64=body.get("image_base64"),
            image_url=body.get("image_url"),
            handle=body.get("handle"),
        )
    else:
        task_list = json.loads(tasks) if tasks else []
        mid = qs_model_id or model_id
        do_render = render is not None and render.lower() in ("true", "1", "yes")
        rmode = render_mode
        req_conf = conf
        req_iou = iou
        file_bytes = await file.read() if file else None
        image_bytes = _vision_service.resolve_image_bytes(file_bytes=file_bytes, handle=handle)

    if qs_conf is not None:
        req_conf = qs_conf
    if qs_iou is not None:
        req_iou = qs_iou

    eff_conf = _coerce_threshold(req_conf, _params.conf)
    eff_iou = _coerce_threshold(req_iou, _params.iou)

    data = _vision_service.infer(
        task_list, image_bytes, model_id=mid, render=do_render, render_mode=rmode,
        conf=eff_conf, iou=eff_iou,
    )
    infer_ms = _timing_infer_ms(getattr(data, "timing", None))
    if infer_ms is not None:
        _stats.infer_ms = infer_ms
    return _ok(request, data=data.model_dump(mode="json"))


# ── 7.1 Feature ────────────────────────────────────────────────────

@app.post("/v1/vision/feature", tags=["feature"])
async def feature(
    request: Request,
    file: Optional[UploadFile] = File(default=None),
    type: Optional[str] = Form(default=None),
    model_id: Optional[str] = Form(default=None),
    file_b: Optional[UploadFile] = File(default=None),
    vector_b: Optional[str] = Form(default=None),
    _: None = Depends(verify_api_key),
):
    content_type = (request.headers.get("content-type") or "").lower()

    if "application/json" in content_type:
        body = await request.json()
        feat_type = body.get("type")
        if feat_type is None:
            raise ServiceError(400, ErrorCode.INVALID_ARGUMENT, "type is required (embedding or similarity)")
        mid = body.get("model_id")
        image_bytes = _vision_service.resolve_image_bytes(
            image_base64=body.get("image_base64"),
            image_url=body.get("image_url"),
        )
        vec_b = body.get("vector_b")
        image_bytes_b = None
    else:
        feat_type = type
        if not feat_type:
            raise ServiceError(400, ErrorCode.INVALID_ARGUMENT, "type is required (embedding or similarity)")
        mid = model_id
        file_bytes = await file.read() if file else None
        image_bytes = _vision_service.resolve_image_bytes(file_bytes=file_bytes)
        image_bytes_b = await file_b.read() if file_b else None
        vec_b = json.loads(vector_b) if vector_b else None

    if feat_type not in ("embedding", "similarity"):
        raise ServiceError(
            400,
            ErrorCode.INVALID_ARGUMENT,
            f"type must be 'embedding' or 'similarity', got: '{feat_type}'",
        )

    if feat_type == "similarity":
        data = compute_similarity(_adapter, _registry, image_bytes, image_bytes_b, vec_b, model_id=mid)
    else:
        data = infer_embedding(_adapter, _registry, image_bytes, model_id=mid)

    return _ok(request, data=data.model_dump(mode="json"))


# ── 7.2 Stream ─────────────────────────────────────────────────────

def _cleanup_stream(old_stream_id: Optional[str]) -> None:
    """安全释放旧会话，避免泄漏。"""
    if old_stream_id:
        try:
            _stream_mgr.delete_session(old_stream_id)
        except Exception:
            pass


@app.websocket("/v1/vision/stream")
async def stream_ws(ws: WebSocket):
    await ws.accept()
    stream_id: Optional[str] = None
    session = None

    # 解析握手 Query 参数：任意参数存在即创建会话
    qs_model_id = ws.query_params.get("model_id")
    qs_model_group = ws.query_params.get("model_group")
    qs_fps_limit = ws.query_params.get("fps_limit")
    qs_priority = ws.query_params.get("priority")
    qs_conf = ws.query_params.get("conf")
    qs_iou = ws.query_params.get("iou")
    has_qs = any(v is not None for v in (qs_model_id, qs_model_group, qs_fps_limit, qs_priority, qs_conf, qs_iou))

    if has_qs:
        try:
            session = _stream_mgr.create_session(
                model_id=qs_model_id,
                model_group=qs_model_group,
                fps_limit=int(qs_fps_limit) if qs_fps_limit else None,
                priority=int(qs_priority) if qs_priority else None,
                conf=_coerce_threshold(qs_conf, _params.conf),
                iou=_coerce_threshold(qs_iou, _params.iou),
            )
            stream_id = session.stream_id
            await ws.send_json(_stream_mgr.build_ready_event(session, qs_model_group))
        except ServiceError as exc:
            await ws.send_json({"event": "error", "code": exc.code, "message": exc.message})
            await ws.close()
            return

    try:
        while True:
            # Wait for either a WebSocket message or external cancellation
            recv_task = asyncio.ensure_future(ws.receive())
            if session is not None:
                cancel_task = asyncio.ensure_future(session.cancelled.wait())
                done, pending = await asyncio.wait(
                    {recv_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
                if cancel_task in done:
                    await ws.send_json({"event": "stream_end", "stream_id": stream_id, "reason": "deleted"})
                    await ws.close()
                    stream_id = None
                    session = None
                    return
                message = recv_task.result()
            else:
                message = await recv_task

            # 二进制帧 → 图像推理
            if "bytes" in message and message["bytes"]:
                image_bytes = message["bytes"]
                if session is None:
                    session = _stream_mgr.create_session(
                        conf=_params.conf,
                        iou=_params.iou,
                    )
                    stream_id = session.stream_id
                    await ws.send_json(_stream_mgr.build_ready_event(session))

                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, _stream_mgr.process_frame, session, image_bytes)
                await ws.send_json(result.model_dump(mode="json"))

            # JSON 控制帧
            elif "text" in message and message["text"]:
                try:
                    ctrl = json.loads(message["text"])
                except json.JSONDecodeError:
                    await ws.send_json({"event": "error", "message": "invalid JSON"})
                    continue

                signal = ctrl.get("signal")

                if signal == "start":
                    # start 覆盖已有会话：先释放旧的，再建新的
                    _cleanup_stream(stream_id)
                    session = _stream_mgr.create_session(
                        model_id=ctrl.get("model_id"),
                        model_group=ctrl.get("model_group"),
                        fps_limit=ctrl.get("fps_limit"),
                        priority=ctrl.get("priority"),
                        conf=_coerce_threshold(ctrl.get("conf"), _params.conf),
                        iou=_coerce_threshold(ctrl.get("iou"), _params.iou),
                    )
                    stream_id = session.stream_id
                    await ws.send_json(_stream_mgr.build_ready_event(session, ctrl.get("model_group")))

                elif signal == "update_params":
                    if session is not None:
                        _stream_mgr.update_session_thresholds(
                            session,
                            conf=_coerce_threshold(ctrl.get("conf"), None),
                            iou=_coerce_threshold(ctrl.get("iou"), None),
                        )
                        await ws.send_json({
                            "event": "params_updated",
                            "stream_id": stream_id,
                            "conf": session.conf,
                            "iou": session.iou,
                        })
                    else:
                        await ws.send_json({"event": "error", "message": "no active session"})

                elif signal == "heartbeat":
                    await ws.send_json({"event": "heartbeat_ack", "stream_id": stream_id})

                elif signal == "end":
                    _cleanup_stream(stream_id)
                    await ws.send_json({"event": "stream_end", "stream_id": stream_id})
                    stream_id = None
                    session = None
                    await ws.close()
                    return

                elif "image_base64" in ctrl:
                    import base64 as b64mod
                    image_bytes = b64mod.b64decode(ctrl["image_base64"])
                    ts = ctrl.get("timestamp_ms")
                    if session is None:
                        session = _stream_mgr.create_session(
                            model_id=ctrl.get("model_id"),
                            model_group=ctrl.get("model_group"),
                            conf=_coerce_threshold(ctrl.get("conf"), _params.conf),
                            iou=_coerce_threshold(ctrl.get("iou"), _params.iou),
                        )
                        stream_id = session.stream_id
                        await ws.send_json(_stream_mgr.build_ready_event(session))
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None, _stream_mgr.process_frame, session, image_bytes, ts)
                    await ws.send_json(result.model_dump(mode="json"))

                else:
                    await ws.send_json({"event": "unknown_signal", "signal": signal})

    except WebSocketDisconnect:
        pass
    except ServiceError as exc:
        try:
            await ws.send_json({"event": "error", "code": exc.code, "message": exc.message})
            await ws.close()
        except Exception:
            pass
    except Exception as exc:
        try:
            await ws.send_json({"event": "error", "message": str(exc)})
            await ws.close()
        except Exception:
            pass
    finally:
        _cleanup_stream(stream_id)


@app.delete("/v1/vision/stream/{stream_id}", tags=["stream"])
async def stream_delete(request: Request, stream_id: str):
    data = _stream_mgr.delete_session(stream_id)
    return _ok(request, data=data.model_dump(mode="json"))


# ── 7.3 Jobs ──────────────────────────────────────────────────────

@app.post("/v1/vision/jobs", tags=["jobs"])
async def create_job(request: Request, body: JobCreateRequest, _: None = Depends(verify_api_key)):
    data = _job_mgr.create_job(
        input_uri=body.input_uri,
        tasks=body.tasks,
        model_id=body.model_id,
        model_group=body.model_group,
        callback_url=body.callback_url,
        render=body.render,
        render_mode=body.render_mode,
        frame_sample_rate=body.frame_sample_rate,
    )
    return _ok(request, data=data.model_dump(mode="json"))


@app.get("/v1/vision/jobs/{job_id}", tags=["jobs"])
async def get_job(request: Request, job_id: str):
    data = _job_mgr.get_job(job_id)
    return _ok(request, data=data.model_dump(mode="json"))


@app.delete("/v1/vision/jobs/{job_id}", tags=["jobs"])
async def cancel_job(request: Request, job_id: str, _: None = Depends(verify_api_key)):
    data = _job_mgr.cancel_job(job_id)
    return _ok(request, data=data.model_dump(mode="json"))


# ── 7.4 Sequence ────────────────────────────────────────────────────

@app.post("/v1/vision/sequence", tags=["sequence"])
async def sequence(request: Request, body: SequenceRequest, _: None = Depends(verify_api_key)):
    data = infer_sequence(_adapter, _registry, body)
    return _ok(request, data=data.model_dump(mode="json"))


# ── 7.5 Models ──────────────────────────────────────────────────────

@app.get("/v1/vision/models", tags=["models"])
async def list_models(
    request: Request,
    tags: Optional[str] = Query(default=None),
    backend: Optional[str] = Query(default=None),
):
    data = _registry.list_models(tags=tags, backend=backend)
    return _ok(request, data=data.model_dump(mode="json"))


@app.post("/v1/vision/models/load", tags=["models"])
async def load_model(request: Request, body: ModelLoadRequest):
    with _registry._lock:
        for mid in list(_registry._models.keys()):
            if mid != body.model_id:
                _stream_mgr.cancel_sessions_for_model(mid)
    data = _registry.load_model(
        model_id=body.model_id,
        config_path=body.config_path,
        model_path_override=body.model_path_override or "",
        lazy_load=body.lazy_load,
    )
    return _ok(request, data=data.model_dump(mode="json"))


@app.post("/v1/vision/models/unload", tags=["models"])
async def unload_model(request: Request, body: ModelUnloadRequest):
    _stream_mgr.cancel_sessions_for_model(body.model_id)
    data = _registry.unload_model(model_id=body.model_id)
    return _ok(request, data=data.model_dump(mode="json"))


@app.post("/v1/vision/models/switch", tags=["models"])
async def switch_model(request: Request, body: ModelSwitchRequest):
    data = _registry.switch_model(model_id=body.model_id, model_group=body.model_group)
    return _ok(request, data=data.model_dump(mode="json"))


# ── 7.6 Params ──────────────────────────────────────────────────────

@app.get("/v1/vision/params", tags=["params"])
async def get_params(request: Request):
    return _ok(request, data=_params.model_dump(mode="json"))


@app.patch("/v1/vision/params", tags=["params"])
async def patch_params(request: Request):
    global _params
    body = await request.json()
    current = _params.model_dump()
    current.update(body)
    _params = VisionParams(**current)
    return _ok(request, data=_params.model_dump(mode="json"))


# ── 7.6 Engine ──────────────────────────────────────────────────────

@app.get("/v1/vision/engine", tags=["engine"])
async def get_engine(request: Request):
    return _ok(request, data=_engine.model_dump(mode="json"))


@app.patch("/v1/vision/engine", tags=["engine"])
async def patch_engine(request: Request):
    global _engine
    body = await request.json()
    current = _engine.model_dump()
    current.update(body)
    _engine = EngineConfig(**current)
    return _ok(request, data=_engine.model_dump(mode="json"))


# ── 7.6 Stats ───────────────────────────────────────────────────────

@app.get("/v1/vision/stats", tags=["stats"])
async def get_stats(request: Request):
    return _ok(request, data=_stats.model_dump(mode="json"))
