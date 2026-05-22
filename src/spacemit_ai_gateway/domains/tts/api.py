"""TTS HTTP 路由（/v1/tts/*）。"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response

from ...app.settings import get_settings
from ...common.schemas import (
    ModelInfo,
    ModelLoadRequest,
    ModelLoadResponse,
    ModelSwitchRequest,
    ModelSwitchResponse,
    ModelUnloadRequest,
    ModelUnloadResponse,
    VoiceInfo,
)
from ...common.streams import enforce_max_upload_size
from ...gateway.auth import verify_api_key
from ...gateway.dependencies import get_tts_service
from .schemas import (
    HealthResponse,
    StreamSessionRequest,
    StreamSessionResponse,
    SynthesizeRequest,
    TaskCancelResponse,
    TaskSubmitRequest,
    TaskSubmitResponse,
    TaskStatusResponse,
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
from .service import TtsService

logger = logging.getLogger(__name__)
router = APIRouter()

_settings = get_settings()
_max_upload = enforce_max_upload_size(_settings.limits.max_upload_bytes)


@router.post("/synthesize", summary="同步语音合成")
async def synthesize(
    body: SynthesizeRequest,
    service: TtsService = Depends(get_tts_service),
    _: None = Depends(_max_upload),
    __: None = Depends(verify_api_key),
) -> Response:
    audio_bytes, content_type, meta = await service.synthesize(body)
    headers = {
        "X-Duration-Ms": str(int(meta["duration_ms"])),
        "X-Processing-Ms": str(int(meta["processing_ms"])),
        "X-RTF": f"{meta['rtf']:.3f}",
        "X-Sample-Rate": str(meta["sample_rate"]),
    }
    return Response(content=audio_bytes, media_type=content_type, headers=headers)


@router.post(
    "/stream/session",
    response_model=StreamSessionResponse,
    summary="申请流式合成会话",
)
async def create_stream_session(
    body: StreamSessionRequest,
    service: TtsService = Depends(get_tts_service),
    _: None = Depends(verify_api_key),
) -> StreamSessionResponse:
    return await service.create_stream_session(body)


@router.get("/voices", response_model=List[VoiceInfo], summary="音色列表")
async def list_voices(service: TtsService = Depends(get_tts_service)) -> List[VoiceInfo]:
    return service.get_voices()


@router.get("/models", response_model=List[ModelInfo], summary="模型列表")
async def list_models(service: TtsService = Depends(get_tts_service)) -> List[ModelInfo]:
    return service.get_models()


@router.get("/healthz", response_model=HealthResponse, summary="健康检查")
async def healthz(service: TtsService = Depends(get_tts_service)) -> HealthResponse:
    data = await service.healthz()
    return HealthResponse(**data)


@router.get("/params", response_model=TtsParamsResponse, summary="获取推理参数")
async def get_params(service: TtsService = Depends(get_tts_service)) -> TtsParamsResponse:
    return service.get_params()


@router.patch("/params", response_model=TtsParamsResponse, summary="更新推理参数")
async def update_params(
    body: TtsParamsPatch,
    service: TtsService = Depends(get_tts_service),
) -> TtsParamsResponse:
    return service.update_params(body)


@router.get("/engine", response_model=TtsEngineResponse, summary="获取引擎配置")
async def get_engine(service: TtsService = Depends(get_tts_service)) -> TtsEngineResponse:
    return service.get_engine_config()


@router.patch("/engine", response_model=TtsEngineResponse, summary="更新引擎配置")
async def update_engine(
    body: TtsEnginePatch,
    service: TtsService = Depends(get_tts_service),
) -> TtsEngineResponse:
    return service.update_engine_config(body)


@router.get("/stats", response_model=TtsStatsResponse, summary="性能指标监控")
async def get_stats(service: TtsService = Depends(get_tts_service)) -> TtsStatsResponse:
    return service.get_stats()


@router.get("/info", response_model=TtsInfoResponse, summary="引擎运行态摘要")
async def get_info(service: TtsService = Depends(get_tts_service)) -> TtsInfoResponse:
    return service.get_info()


# ---- model management ----

@router.post("/models/load", response_model=ModelLoadResponse, summary="加载模型")
async def load_model(
    body: ModelLoadRequest,
    service: TtsService = Depends(get_tts_service),
) -> ModelLoadResponse:
    data = await service.load_model(body.model_id)
    return ModelLoadResponse(**data)


@router.post("/models/unload", response_model=ModelUnloadResponse, summary="卸载模型")
async def unload_model(
    body: ModelUnloadRequest,
    service: TtsService = Depends(get_tts_service),
) -> ModelUnloadResponse:
    data = await service.unload_model(body.model_id)
    return ModelUnloadResponse(**data)


@router.post("/models/switch", response_model=ModelSwitchResponse, summary="切换默认模型")
async def switch_model(
    body: ModelSwitchRequest,
    service: TtsService = Depends(get_tts_service),
) -> ModelSwitchResponse:
    data = await service.switch_default(body.model_id)
    return ModelSwitchResponse(**data)


# ---- tasks ----

@router.post("/tasks", response_model=TaskSubmitResponse, summary="提交异步合成任务")
async def submit_task(
    body: TaskSubmitRequest,
    service: TtsService = Depends(get_tts_service),
    _: None = Depends(verify_api_key),
) -> TaskSubmitResponse:
    return await service.submit_task(body)


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse, summary="查询任务状态")
async def get_task(
    task_id: str,
    service: TtsService = Depends(get_tts_service),
) -> TaskStatusResponse:
    return await service.get_task(task_id)


@router.delete("/tasks/{task_id}", response_model=TaskCancelResponse, summary="取消合成任务")
async def cancel_task(
    task_id: str,
    service: TtsService = Depends(get_tts_service),
) -> TaskCancelResponse:
    return await service.cancel_task(task_id)


@router.get("/tasks/{task_id}/audio", summary="下载合成音频")
async def get_task_audio(
    task_id: str,
    service: TtsService = Depends(get_tts_service),
) -> FileResponse:
    path = service.get_task_audio_path(task_id)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="audio not ready or task not found")
    suffix = path.suffix.lstrip(".")
    media = "audio/wav" if suffix == "wav" else f"audio/{suffix}"
    return FileResponse(path, media_type=media, filename=path.name)


# ---- lexicons ----

@router.get("/lexicons", response_model=TtsLexiconListResponse, summary="发音词库列表")
async def list_lexicons(
    service: TtsService = Depends(get_tts_service),
) -> TtsLexiconListResponse:
    return await service.list_lexicons()


@router.post("/lexicons", response_model=TtsLexiconItem, summary="创建发音词库")
async def create_lexicon(
    body: TtsLexiconRequest,
    service: TtsService = Depends(get_tts_service),
    _: None = Depends(verify_api_key),
) -> TtsLexiconItem:
    return await service.create_lexicon(body)


@router.delete("/lexicons/{lexicon_id}", summary="删除发音词库")
async def delete_lexicon(
    lexicon_id: str,
    service: TtsService = Depends(get_tts_service),
    _: None = Depends(verify_api_key),
):
    deleted = await service.delete_lexicon(lexicon_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="lexicon not found")
    return {"ok": True}
