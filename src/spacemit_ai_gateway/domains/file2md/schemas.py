from typing import Any

from pydantic import Field

from pydantic import BaseModel


class ConvertResponse(BaseModel):
    success: bool
    markdown: str
    error: str | None = None
    page_count: int = 0
    processing_time_ms: float = 0.0
    output_directory: str | None = None
    manifest: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    ready: bool
    state: str
    backend: str
