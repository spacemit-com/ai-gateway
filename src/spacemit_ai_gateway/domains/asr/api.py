"""ASR HTTP 路由（/v1/asr/*）。

只负责协议转换：参数解析、调 service、序列化响应。
异常由 gateway.errors 的全局 handler 统一翻译。
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

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
from ...gateway.dependencies import get_asr_service
from .schemas import (
    AsrAudioPatch,
    AsrAudioResponse,
    AsrEnginePatch,
    AsrEngineResponse,
    AsrInfoResponse,
    AsrLexiconItem,
    AsrLexiconListResponse,
    AsrLexiconRequest,
    AsrParamsPatch,
    AsrParamsResponse,
    AsrStatsResponse,
    HealthResponse,
    JobCancelResponse,
    JobStatusResponse,
    JobSubmitRequest,
    JobSubmitResponse,
    LanguagesResponse,
    RecognizeParams,
    RecognizeResponse,
    StreamSessionRequest,
    StreamSessionResponse,
)
from .service import AsrService

logger = logging.getLogger(__name__)
router = APIRouter()

_settings = get_settings()
_max_upload = enforce_max_upload_size(_settings.limits.max_upload_bytes)


@router.post("/recognize", response_model=RecognizeResponse, summary="同步语音识别")
async def recognize(
    file: UploadFile = File(..., description="音频文件（WAV/PCM）"),
    model: str | None = Form(default=None, description="模型 ID"),
    language: str = Form(default="zh"),
    sample_rate: int = Form(default=0),
    punctuation: bool = Form(default=True),
    hotwords: str | None = Form(default=None),
    service: AsrService = Depends(get_asr_service),
    _: None = Depends(_max_upload),
    __: None = Depends(verify_api_key),
) -> RecognizeResponse:
    params = RecognizeParams(
        model=model,
        language=language,
        sample_rate=sample_rate,
        punctuation=punctuation,
        hotwords=hotwords,
    )
    audio = await file.read()
    return await service.recognize(audio, params)


@router.post(
    "/stream/session",
    response_model=StreamSessionResponse,
    summary="申请流式会话",
)
async def create_stream_session(
    body: StreamSessionRequest,
    service: AsrService = Depends(get_asr_service),
    _: None = Depends(verify_api_key),
) -> StreamSessionResponse:
    return await service.create_stream_session(body)


@router.get("/models", response_model=List[ModelInfo], summary="模型列表")
async def list_models(
    service: AsrService = Depends(get_asr_service),
) -> List[ModelInfo]:
    return service.get_models()


@router.get("/languages", response_model=LanguagesResponse, summary="支持语种")
async def list_languages(
    service: AsrService = Depends(get_asr_service),
) -> LanguagesResponse:
    return service.get_languages()


@router.get("/healthz", response_model=HealthResponse, summary="健康检查")
async def healthz(service: AsrService = Depends(get_asr_service)) -> HealthResponse:
    data = await service.healthz()
    return HealthResponse(**data)


@router.get("/params", response_model=AsrParamsResponse, summary="获取推理参数")
async def get_params(service: AsrService = Depends(get_asr_service)) -> AsrParamsResponse:
    return service.get_params()


@router.patch("/params", response_model=AsrParamsResponse, summary="更新推理参数")
async def update_params(
    body: AsrParamsPatch,
    service: AsrService = Depends(get_asr_service),
) -> AsrParamsResponse:
    return service.update_params(body)


@router.get("/audio", response_model=AsrAudioResponse, summary="获取音频预处理配置")
async def get_audio(service: AsrService = Depends(get_asr_service)) -> AsrAudioResponse:
    return service.get_audio_config()


@router.patch("/audio", response_model=AsrAudioResponse, summary="更新音频预处理配置")
async def update_audio(
    body: AsrAudioPatch,
    service: AsrService = Depends(get_asr_service),
) -> AsrAudioResponse:
    return service.update_audio_config(body)


@router.get("/engine", response_model=AsrEngineResponse, summary="获取引擎配置")
async def get_engine(service: AsrService = Depends(get_asr_service)) -> AsrEngineResponse:
    return service.get_engine_config()


@router.patch("/engine", response_model=AsrEngineResponse, summary="更新引擎配置")
async def update_engine(
    body: AsrEnginePatch,
    service: AsrService = Depends(get_asr_service),
) -> AsrEngineResponse:
    return service.update_engine_config(body)


@router.get("/stats", response_model=AsrStatsResponse, summary="性能指标监控")
async def get_stats(service: AsrService = Depends(get_asr_service)) -> AsrStatsResponse:
    return service.get_stats()


@router.get("/info", response_model=AsrInfoResponse, summary="引擎运行态摘要")
async def get_info(service: AsrService = Depends(get_asr_service)) -> AsrInfoResponse:
    return service.get_info()


# ---- model management ----

@router.post("/models/load", response_model=ModelLoadResponse, summary="加载模型")
async def load_model(
    body: ModelLoadRequest,
    service: AsrService = Depends(get_asr_service),
) -> ModelLoadResponse:
    data = await service.load_model(body.model_id)
    return ModelLoadResponse(**data)


@router.post("/models/unload", response_model=ModelUnloadResponse, summary="卸载模型")
async def unload_model(
    body: ModelUnloadRequest,
    service: AsrService = Depends(get_asr_service),
) -> ModelUnloadResponse:
    data = await service.unload_model(body.model_id)
    return ModelUnloadResponse(**data)


@router.post("/models/switch", response_model=ModelSwitchResponse, summary="切换默认模型")
async def switch_model(
    body: ModelSwitchRequest,
    service: AsrService = Depends(get_asr_service),
) -> ModelSwitchResponse:
    data = service.switch_default(body.model_id)
    return ModelSwitchResponse(**data)


# ---- jobs ----

@router.post("/jobs", response_model=JobSubmitResponse, summary="提交异步转写任务")
async def submit_job(
    body: JobSubmitRequest,
    service: AsrService = Depends(get_asr_service),
    _: None = Depends(verify_api_key),
) -> JobSubmitResponse:
    return await service.submit_job(body)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse, summary="查询任务状态")
async def get_job(
    job_id: str,
    service: AsrService = Depends(get_asr_service),
) -> JobStatusResponse:
    return await service.get_job(job_id)


@router.delete("/jobs/{job_id}", response_model=JobCancelResponse, summary="取消任务")
async def cancel_job(
    job_id: str,
    service: AsrService = Depends(get_asr_service),
) -> JobCancelResponse:
    return await service.cancel_job(job_id)


# ---- lexicons ----

@router.get("/lexicons", response_model=AsrLexiconListResponse, summary="热词词库列表")
async def list_lexicons(
    service: AsrService = Depends(get_asr_service),
) -> AsrLexiconListResponse:
    return await service.list_lexicons()


@router.post("/lexicons", response_model=AsrLexiconItem, summary="创建热词词库")
async def create_lexicon(
    body: AsrLexiconRequest,
    service: AsrService = Depends(get_asr_service),
    _: None = Depends(verify_api_key),
) -> AsrLexiconItem:
    return await service.create_lexicon(body)


@router.delete("/lexicons/{lexicon_id}", summary="删除热词词库")
async def delete_lexicon(
    lexicon_id: str,
    service: AsrService = Depends(get_asr_service),
    _: None = Depends(verify_api_key),
):
    deleted = await service.delete_lexicon(lexicon_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="lexicon not found")
    return {"ok": True}
