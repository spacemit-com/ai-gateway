"""VAD HTTP 路由（/v1/vad/*）。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Query, UploadFile

from ...app.settings import get_settings
from ...common.schemas import (
    ModelInfo,
    ModelLoadRequest,
    ModelLoadResponse,
    ModelSwitchRequest,
    ModelSwitchResponse,
    ModelUnloadRequest,
    ModelUnloadResponse,
)
from ...common.streams import enforce_max_upload_size
from ...gateway.auth import verify_api_key
from ...gateway.dependencies import get_vad_service
from .schemas import (
    AnalyzeResponse,
    HealthResponse,
    ParamsResponse,
    SegmentsResponse,
    VadAudioPatch,
    VadAudioResponse,
    VadEnginePatch,
    VadEngineResponse,
    VadInfoResponse,
    VadParamsPatch,
    VadStatsResponse,
)
from .service import VadService

logger = logging.getLogger(__name__)
router = APIRouter()

_settings = get_settings()
_max_upload = enforce_max_upload_size(_settings.limits.max_upload_bytes)


@router.post("/analyze", response_model=AnalyzeResponse, summary="短片段检测")
async def analyze(
    file: UploadFile = File(..., description="音频文件"),
    sample_rate: int = Query(default=16000),
    service: VadService = Depends(get_vad_service),
    _: None = Depends(_max_upload),
    __: None = Depends(verify_api_key),
) -> AnalyzeResponse:
    audio = await file.read()
    return await service.analyze(audio, sample_rate)


@router.post("/segments", response_model=SegmentsResponse, summary="音频切分")
async def segments(
    file: UploadFile = File(..., description="音频文件"),
    sample_rate: int = Query(default=16000),
    service: VadService = Depends(get_vad_service),
    _: None = Depends(_max_upload),
    __: None = Depends(verify_api_key),
) -> SegmentsResponse:
    audio = await file.read()
    return await service.segment(audio, sample_rate)


@router.get("/models", response_model=list[ModelInfo], summary="模型列表")
async def list_models(service: VadService = Depends(get_vad_service)) -> list[ModelInfo]:
    return service.get_models()


@router.post("/models/load", response_model=ModelLoadResponse, summary="加载模型")
async def load_model(
    body: ModelLoadRequest,
    service: VadService = Depends(get_vad_service),
) -> ModelLoadResponse:
    data = await service.load_model(body.model_id)
    return ModelLoadResponse(**data)


@router.post("/models/unload", response_model=ModelUnloadResponse, summary="卸载模型")
async def unload_model(
    body: ModelUnloadRequest,
    service: VadService = Depends(get_vad_service),
) -> ModelUnloadResponse:
    data = await service.unload_model(body.model_id)
    return ModelUnloadResponse(**data)


@router.post("/models/switch", response_model=ModelSwitchResponse, summary="切换默认模型")
async def switch_model(
    body: ModelSwitchRequest,
    service: VadService = Depends(get_vad_service),
) -> ModelSwitchResponse:
    data = service.switch_default(body.model_id)
    return ModelSwitchResponse(**data)


@router.get("/params", response_model=ParamsResponse, summary="获取参数")
async def get_params(service: VadService = Depends(get_vad_service)) -> ParamsResponse:
    return service.get_params()


@router.get("/healthz", response_model=HealthResponse, summary="健康检查")
async def healthz(service: VadService = Depends(get_vad_service)) -> HealthResponse:
    data = await service.healthz()
    return HealthResponse(**data)


@router.patch("/params", response_model=ParamsResponse, summary="更新感知参数")
async def update_params(
    body: VadParamsPatch,
    service: VadService = Depends(get_vad_service),
) -> ParamsResponse:
    return service.update_params(body)


@router.get("/audio", response_model=VadAudioResponse, summary="获取音频输入配置")
async def get_audio(service: VadService = Depends(get_vad_service)) -> VadAudioResponse:
    return service.get_audio_config()


@router.patch("/audio", response_model=VadAudioResponse, summary="更新音频输入配置")
async def update_audio(
    body: VadAudioPatch,
    service: VadService = Depends(get_vad_service),
) -> VadAudioResponse:
    return service.update_audio_config(body)


@router.get("/engine", response_model=VadEngineResponse, summary="获取引擎配置")
async def get_engine(service: VadService = Depends(get_vad_service)) -> VadEngineResponse:
    return service.get_engine_config()


@router.patch("/engine", response_model=VadEngineResponse, summary="更新引擎配置")
async def update_engine(
    body: VadEnginePatch,
    service: VadService = Depends(get_vad_service),
) -> VadEngineResponse:
    return service.update_engine_config(body)


@router.get("/stats", response_model=VadStatsResponse, summary="运行状态监控")
async def get_stats(service: VadService = Depends(get_vad_service)) -> VadStatsResponse:
    return service.get_stats()


@router.get("/info", response_model=VadInfoResponse, summary="引擎运行态摘要")
async def get_info(service: VadService = Depends(get_vad_service)) -> VadInfoResponse:
    return service.get_info()
