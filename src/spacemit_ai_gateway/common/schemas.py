"""公共 Pydantic 模型。"""

from typing import Any, List, Optional

from pydantic import BaseModel, Field

from .ready_state import BackendReadyState


class ErrorResponse(BaseModel):
    """统一错误响应（HTTP handler 生成）。"""

    error: str
    message: str
    retriable: bool = False
    details: Optional[Any] = None


class TimingInfo(BaseModel):
    duration_ms: float
    processing_ms: float
    rtf: float


class ModelInfo(BaseModel):
    id: str
    name: str
    capabilities: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    sample_rate: Optional[int] = None
    loaded: bool = False


class VoiceInfo(BaseModel):
    id: str
    name: str
    language: str
    gender: Optional[str] = None
    description: Optional[str] = None


class DomainHealth(BaseModel):
    ready: bool
    state: BackendReadyState
    backend: str
    detail: Optional[str] = None


# ---- model management ----

class ModelLoadRequest(BaseModel):
    model_id: str = Field(..., description="模型 ID")


class ModelLoadResponse(BaseModel):
    loaded: bool
    model_id: str
    state: str


class ModelUnloadRequest(BaseModel):
    model_id: str = Field(..., description="模型 ID")


class ModelUnloadResponse(BaseModel):
    unloaded: bool
    model_id: str


class ModelSwitchRequest(BaseModel):
    model_id: str = Field(..., description="模型 ID")


class ModelSwitchResponse(BaseModel):
    switched: bool
    default_model_id: str
