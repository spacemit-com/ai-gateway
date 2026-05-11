"""VAD 请求/响应模型。"""

from typing import List, Optional

from pydantic import BaseModel, Field


class AnalyzeResponse(BaseModel):
    is_speech: bool
    probability: float
    smoothed_probability: Optional[float] = None
    processing_ms: float


class SpeechSegment(BaseModel):
    start_ms: float
    end_ms: float
    confidence: float


class SegmentsResponse(BaseModel):
    segments: List[SpeechSegment]
    duration_ms: float
    speech_ratio: float
    processing_ms: float


class ParamsResponse(BaseModel):
    trigger_threshold: float
    stop_threshold: float
    min_speech_ms: int
    max_silence_ms: int
    sample_rate: int


class StreamEvent(BaseModel):
    event: str = Field(..., description="speech_start/speech_end/speech/silence")
    probability: float
    timestamp_ms: float


class HealthResponse(BaseModel):
    ready: bool
    state: str
    backend: str


# ---- params patch ----

class VadParamsPatch(BaseModel):
    trigger_threshold: Optional[float] = None
    stop_threshold: Optional[float] = None
    min_speech_ms: Optional[int] = None
    max_silence_ms: Optional[int] = None


# ---- audio ----

class VadAudioResponse(BaseModel):
    sample_rate: int
    bit_depth: int = 16
    denoise: bool = False


class VadAudioPatch(BaseModel):
    sample_rate: Optional[int] = None
    bit_depth: Optional[int] = None
    denoise: Optional[bool] = None


# ---- engine ----

class VadEngineResponse(BaseModel):
    threads: int
    npu_priority: Optional[str] = None
    memory_limit: Optional[int] = None
    pending_restart: bool = False


class VadEnginePatch(BaseModel):
    threads: Optional[int] = None
    npu_priority: Optional[str] = None
    memory_limit: Optional[int] = None


# ---- stats ----

class VadStatsResponse(BaseModel):
    total_requests: int = 0
    total_errors: int = 0
    latency_ms_avg: float = 0.0
    uptime_s: float = 0.0


# ---- info ----

class VadInfoResponse(BaseModel):
    initialized: bool
    backend: str
    default_model: Optional[str] = None
    backends_loaded: List[str] = Field(default_factory=list)
