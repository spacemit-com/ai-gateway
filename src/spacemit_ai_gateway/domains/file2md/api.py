from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from ...gateway.auth import verify_api_key
from .schemas import ConvertResponse, HealthResponse
from .service import File2mdService

router = APIRouter()


def _service(request: Request) -> File2mdService:
    return request.app.state.file2md_service


@router.get("/healthz", response_model=HealthResponse)
async def healthz(request: Request) -> HealthResponse:
    svc = _service(request)
    return HealthResponse(ready=svc.state == "idle", state=svc.state, backend=svc.backend)


@router.post("/convert", response_model=ConvertResponse)
async def convert(
    request: Request,
    file: UploadFile = File(..., description="待转换的 PDF、Office、图片或文本文件"),
    _: None = Depends(verify_api_key),
) -> ConvertResponse:
    svc = _service(request)
    data = await file.read()
    max_bytes = request.app.state.settings.limits.max_upload_bytes
    if len(data) > max_bytes:
        raise HTTPException(413, "uploaded file exceeds max_upload_bytes")
    if not data:
        raise HTTPException(400, "uploaded file is empty")
    try:
        result = await svc.convert(data, file.filename or "input.bin")
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return ConvertResponse(**result)
