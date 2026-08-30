from __future__ import annotations

import asyncio
import tempfile
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from ...app.settings import get_settings
from ...common.streams import enforce_max_upload_size
from ...gateway.auth import verify_api_key
from ...gateway.dependencies import get_file2md_service
from .schemas import (
    ConvertOptionsForm,
    ConvertResponse,
    EnginePatch,
    EngineResponse,
    HealthResponse,
    ModelActionResponse,
    ModelsResponse,
    ParamsPatch,
    ParamsResponse,
    StatsResponse,
)
from .service import File2mdService

router = APIRouter()
_max_upload = enforce_max_upload_size(get_settings().limits.max_upload_bytes)
_UPLOAD_CHUNK_SIZE = 1024 * 1024


async def _write_upload_to_temp(
    file: UploadFile, max_bytes: int, filename: str
) -> Path:
    """Stream an UploadFile to disk while enforcing a hard file-size limit."""
    suffix = Path(filename).suffix.lower() or ".bin"
    temp = tempfile.NamedTemporaryFile(
        prefix="file2md-upload-", suffix=suffix, delete=False
    )
    path = Path(temp.name)
    total = 0
    keep_path = False
    try:
        while True:
            chunk = await file.read(_UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail="uploaded file exceeds max_upload_bytes",
                )
            await asyncio.to_thread(temp.write, chunk)
        temp.flush()
        if total == 0:
            raise HTTPException(status_code=400, detail="uploaded file is empty")
        keep_path = True
        return path
    finally:
        temp.close()
        if not keep_path:
            path.unlink(missing_ok=True)


@router.get("/healthz", response_model=HealthResponse, summary="健康检查")
async def healthz(
    service: File2mdService = Depends(get_file2md_service),
) -> HealthResponse:
    return HealthResponse(**await service.healthz())


@router.post("/convert", response_model=ConvertResponse, summary="文档转 Markdown")
async def convert(
    request: Request,
    file: UploadFile = File(..., description="待转换的 PDF、Office、图片或文本文件"),
    method: Optional[str] = Form(default=None),
    language: Optional[str] = Form(default=None),
    formula: Optional[bool] = Form(default=None),
    table: Optional[bool] = Form(default=None),
    flowchart: Optional[bool] = Form(default=None),
    image_ocr_caption: Optional[bool] = Form(default=None),
    web_image_ocr: Optional[bool] = Form(default=None),
    save_images: Optional[bool] = Form(default=None),
    start_page: Optional[int] = Form(default=None, ge=0),
    end_page: Optional[int] = Form(default=None, ge=-1),
    service: File2mdService = Depends(get_file2md_service),
    _: None = Depends(_max_upload),
    __: None = Depends(verify_api_key),
) -> ConvertResponse:
    max_bytes = request.app.state.settings.limits.max_upload_bytes
    options = ConvertOptionsForm(
        method=method,
        language=language,
        formula=formula,
        table=table,
        flowchart=flowchart,
        image_ocr_caption=image_ocr_caption,
        web_image_ocr=web_image_ocr,
        save_images=save_images,
        start_page=start_page,
        end_page=end_page,
    )
    path = await _write_upload_to_temp(file, max_bytes, file.filename or "input.bin")
    try:
        result = await service.convert_path(
            path, file.filename or "input.bin", options.as_overrides()
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        path.unlink(missing_ok=True)
    return ConvertResponse(**result)


@router.get("/models", response_model=ModelsResponse, summary="模型状态")
async def list_models(
    service: File2mdService = Depends(get_file2md_service),
) -> ModelsResponse:
    return ModelsResponse(**await service.list_models())


@router.post("/models/load", response_model=ModelActionResponse, summary="预加载模型")
async def load_models(
    service: File2mdService = Depends(get_file2md_service),
    _: None = Depends(verify_api_key),
) -> ModelActionResponse:
    try:
        return ModelActionResponse(**await service.load_models())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/models/unload", response_model=ModelActionResponse, summary="卸载模型")
async def unload_models(
    service: File2mdService = Depends(get_file2md_service),
    _: None = Depends(verify_api_key),
) -> ModelActionResponse:
    return ModelActionResponse(**await service.unload_models())


@router.get("/params", response_model=ParamsResponse, summary="获取转换参数")
async def get_params(
    service: File2mdService = Depends(get_file2md_service),
) -> ParamsResponse:
    return ParamsResponse(**service.get_params())


@router.patch("/params", response_model=ParamsResponse, summary="更新转换参数")
async def update_params(
    body: ParamsPatch,
    service: File2mdService = Depends(get_file2md_service),
    _: None = Depends(verify_api_key),
) -> ParamsResponse:
    try:
        return ParamsResponse(**service.update_params(body.model_dump(exclude_unset=True)))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/engine", response_model=EngineResponse, summary="获取引擎配置")
async def get_engine(
    service: File2mdService = Depends(get_file2md_service),
) -> EngineResponse:
    return EngineResponse(**service.get_engine_config())


@router.patch("/engine", response_model=EngineResponse, summary="更新引擎配置")
async def update_engine(
    body: EnginePatch,
    service: File2mdService = Depends(get_file2md_service),
    _: None = Depends(verify_api_key),
) -> EngineResponse:
    try:
        return EngineResponse(**service.update_engine(body.model_dump(exclude_unset=True)))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stats", response_model=StatsResponse, summary="性能指标")
async def get_stats(
    service: File2mdService = Depends(get_file2md_service),
) -> StatsResponse:
    return StatsResponse(**service.get_stats())
