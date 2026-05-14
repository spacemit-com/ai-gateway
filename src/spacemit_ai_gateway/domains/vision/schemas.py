from __future__ import annotations

from enum import IntEnum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ErrorCode(IntEnum):
    OK = 0
    INVALID_ARGUMENT = 1001
    INVALID_IMAGE_INPUT = 1002
    INVALID_SEQUENCE_INPUT = 1003
    SERVICE_NOT_FOUND = 1005
    MODEL_NOT_FOUND = 1010
    MODEL_ALREADY_LOADED = 1011
    MODEL_RUNTIME_ERROR = 1007
    TOO_MANY_REQUESTS = 1008
    INTERNAL_ERROR = 2001
    MODEL_NOT_READY = 2002
    NOT_IMPLEMENTED = 2003


class ApiResponse(BaseModel):
    code: int = Field(default=ErrorCode.OK)
    message: str = Field(default="ok")
    request_id: str = ""
    data: Any = None


# ── Timing ──────────────────────────────────────────────────────────

class TimingInfo(BaseModel):
    preprocess_ms: Optional[float] = None
    model_infer_ms: Optional[float] = None
    postprocess_ms: Optional[float] = None
    detect_ms: Optional[float] = None
    track_ms: Optional[float] = None
    embedding_ms: Optional[float] = None
    sequence_ms: Optional[float] = None
    draw_ms: Optional[float] = None
    infer_ms: Optional[float] = None


# ── 7.1 Inference ───────────────────────────────────────────────────

class DetectionItem(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    score: float
    label: int
    label_name: Optional[str] = None
    track_id: int = -1


class ClassifyItem(BaseModel):
    label: int
    label_name: Optional[str] = None
    score: float


class PoseKeypoint(BaseModel):
    x: float
    y: float
    visibility: float = 1.0


class PoseItem(BaseModel):
    keypoints: List[PoseKeypoint] = Field(default_factory=list)
    score: float = 0.0


class EmotionItem(BaseModel):
    label: str
    score: float


class InferenceResults(BaseModel):
    detect: Optional[List[DetectionItem]] = None
    classify: Optional[List[ClassifyItem]] = None
    pose: Optional[List[PoseItem]] = None
    segment: Optional[List[Dict[str, Any]]] = None
    emotion: Optional[List[EmotionItem]] = None


class InferenceResponse(BaseModel):
    model_id: str
    results: InferenceResults
    timing: Optional[TimingInfo] = None
    rendered_image_url: Optional[str] = None


# ── 7.1 Feature ─────────────────────────────────────────────────────

class FeatureResponse(BaseModel):
    model_id: str
    embedding: Optional[List[float]] = None
    similarity: Optional[float] = None
    timing: Optional[TimingInfo] = None


# ── 7.2 Stream ──────────────────────────────────────────────────────

class StreamFrameResult(BaseModel):
    event: str = "frame_result"
    stream_id: str
    timestamp_ms: Optional[int] = None
    detections: List[DetectionItem] = Field(default_factory=list)
    pose: Optional[List[PoseItem]] = None
    emotion: Optional[List[EmotionItem]] = None
    classify: Optional[List[ClassifyItem]] = None
    timing: Optional[TimingInfo] = None


class StreamDeleteResponse(BaseModel):
    released: bool
    stream_id: str


# ── 7.3 Jobs ───────────────────────────────────────────────────────

class JobCreateRequest(BaseModel):
    input_uri: str
    tasks: List[str]
    model_id: Optional[str] = None
    model_group: Optional[str] = None
    callback_url: Optional[str] = None
    render: bool = False
    render_mode: Optional[str] = None
    frame_sample_rate: Optional[int] = None


class JobCreateResponse(BaseModel):
    job_id: str
    status: str = "PENDING"
    accepted_at: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int = 0
    results_uri: Optional[str] = None
    artifacts: Optional[Dict[str, Any]] = None


class JobCancelResponse(BaseModel):
    cancelled: bool
    job_id: str


# ── 7.4 Sequence ────────────────────────────────────────────────────

class SequenceRequest(BaseModel):
    sequence_data: List[float]
    window_size: Optional[int] = None
    model_id: Optional[str] = None


class SequenceResponse(BaseModel):
    model_id: str
    scores: List[float]
    top_label: str
    labels: List[str]


# ── 7.4 Models ──────────────────────────────────────────────────────

class ModelInfo(BaseModel):
    model_id: str
    config_path: str = ""
    capabilities: List[str] = Field(default_factory=list)
    defaults: Dict[str, Any] = Field(default_factory=dict)
    status: Literal["ready", "loading", "unloaded", "error"] = "unloaded"
    backend: Optional[str] = None
    error_message: Optional[str] = None


class ModelLoadRequest(BaseModel):
    model_id: str
    config_path: Optional[str] = None
    model_path_override: Optional[str] = None
    lazy_load: bool = False


class ModelLoadResponse(BaseModel):
    loaded: bool
    model_id: str
    engine_state: Optional[Dict[str, Any]] = None


class ModelUnloadRequest(BaseModel):
    model_id: str


class ModelUnloadResponse(BaseModel):
    unloaded: bool
    model_id: str


class ModelSwitchRequest(BaseModel):
    model_id: Optional[str] = None
    model_group: Optional[str] = None


class ModelSwitchResponse(BaseModel):
    switched: bool
    default_model_id: Optional[str] = None
    default_model_group: Optional[str] = None
    effective_scope: str = "new_requests_only"


class ModelsListResponse(BaseModel):
    data: List[ModelInfo]


# ── 7.5 Params / Engine / Stats / Health ────────────────────────────

class VisionParams(BaseModel):
    conf: float = 0.25
    iou: float = 0.45
    roi_masks: List[Any] = Field(default_factory=list)
    input_size: int = 640


class EngineConfig(BaseModel):
    ai_core_group: str = "cluster0"
    threads: int = 4
    precision: str = "int8"
    memory_limit: int = 1024


class StatsData(BaseModel):
    rtf: float = 0.0
    fps: float = 0.0
    queue: int = 0
    infer_ms: float = 0.0
    ai_temp: float = 0.0
    memory_usage: int = 0


class HealthData(BaseModel):
    status: str = "ok"
    readiness: bool = True
    liveness: bool = True
