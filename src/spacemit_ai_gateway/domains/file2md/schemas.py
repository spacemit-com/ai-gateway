from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ConvertResponse(BaseModel):
    success: bool
    request_id: str | None = None
    markdown: str = ""
    error: str | None = None
    manifest_error: str | None = None
    manifest_json_raw: str | None = None
    page_count: int = 0
    processing_time_ms: float = 0.0
    output_directory: str | None = None
    manifest: dict[str, Any] = Field(default_factory=dict)
    middle_json: str | None = None
    content_list_json: str | None = None
    page_metrics: list[dict[str, Any]] = Field(default_factory=list)


class ConvertOptionsForm(BaseModel):
    method: Literal["auto", "text", "ocr"] | None = None
    language: str | None = None
    formula: bool | None = None
    table: bool | None = None
    flowchart: bool | None = None
    image_ocr_caption: bool | None = None
    web_image_ocr: bool | None = None
    save_images: bool | None = None
    start_page: int | None = Field(default=None, ge=0)
    end_page: int | None = Field(default=None, ge=-1)

    def as_overrides(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class HealthResponse(BaseModel):
    ready: bool
    state: str
    backend: str
    initialized: bool = False
    models_ready: bool = False
    models: list[dict[str, Any]] = Field(default_factory=list)
    last_error: str | None = None


class ModelsResponse(BaseModel):
    backend: str
    models_ready: bool
    models: list[dict[str, Any]] = Field(default_factory=list)


class ModelActionResponse(ModelsResponse):
    loaded: bool | None = None
    unloaded: bool | None = None


class ParamsResponse(BaseModel):
    provider: str
    model_dir: str | None
    output_dir: str
    method: str
    language: str
    threads: int
    cpu_threads: int
    pdf_dpi: int
    processing_window_size: int
    formula: bool
    table: bool
    flowchart: bool
    image_ocr_caption: bool
    web_image_ocr: bool
    save_images: bool


class ParamsPatch(BaseModel):
    method: Literal["auto", "text", "ocr"] | None = None
    language: str | None = None
    formula: bool | None = None
    table: bool | None = None
    flowchart: bool | None = None
    image_ocr_caption: bool | None = None
    web_image_ocr: bool | None = None
    save_images: bool | None = None


class EngineResponse(BaseModel):
    backend: str
    initialized: bool
    model_dir: str | None
    output_dir: str
    threads: int
    cpu_threads: int
    pdf_dpi: int
    processing_window_size: int
    pending_restart: bool = False


class EnginePatch(BaseModel):
    provider: Literal["k3-int8", "cpu"] | None = None
    model_dir: str | None = None
    output_dir: str | None = None
    threads: int | None = Field(default=None, gt=0, le=64)
    cpu_threads: int | None = Field(default=None, gt=0, le=64)
    pdf_dpi: int | None = Field(default=None, gt=0, le=600)
    processing_window_size: int | None = Field(default=None, gt=0, le=128)


class StatsResponse(BaseModel):
    total_requests: int = 0
    total_errors: int = 0
    total_processing_ms: float = 0.0
    processing_time_avg_ms: float = 0.0
    uptime_s: float = 0.0
