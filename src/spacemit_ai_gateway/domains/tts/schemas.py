"""TTS 请求/响应模型。"""

from typing import List, Optional

from pydantic import BaseModel, Field


class SynthesizeRequest(BaseModel):
    text: str = Field(..., description="待合成文本")
    voice_id: Optional[str] = Field(default=None, description="音色 ID")
    model: Optional[str] = Field(default=None, description="模型 ID")
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    pitch: float = Field(default=1.0, ge=0.5, le=2.0)
    volume: float = Field(default=1.0, ge=0.0, le=2.0)
    response_format: str = Field(default="wav", description="wav | pcm")
    sample_rate: Optional[int] = None


class StreamSessionRequest(BaseModel):
    model: Optional[str] = Field(default=None, description="模型 ID")
    voice_id: Optional[str] = None
    speed: float = 1.0
    response_format: str = "pcm"


class StreamSessionResponse(BaseModel):
    session_id: str
    expires_at: str
    voice_id: Optional[str] = None
    response_format: str = "pcm"


class StreamQuery(BaseModel):
    session_id: Optional[str] = None
    voice_id: Optional[str] = None
    response_format: str = "pcm"


class HealthResponse(BaseModel):
    ready: bool
    state: str
    backend: str


# ---- params ----

class TtsParamsResponse(BaseModel):
    speed: float
    pitch: float
    volume: float
    emotion_strength: Optional[float] = None


class TtsParamsPatch(BaseModel):
    speed: Optional[float] = None
    pitch: Optional[float] = None
    volume: Optional[float] = None
    emotion_strength: Optional[float] = None


# ---- engine ----

class TtsEngineResponse(BaseModel):
    threads: int
    sample_rate: Optional[int] = None
    cache_policy: Optional[str] = None
    pending_restart: bool = False


class TtsEnginePatch(BaseModel):
    threads: Optional[int] = None
    sample_rate: Optional[int] = None
    cache_policy: Optional[str] = None


# ---- stats ----

class TtsStatsResponse(BaseModel):
    total_requests: int = 0
    total_errors: int = 0
    rtf_avg: float = 0.0
    uptime_s: float = 0.0


# ---- info ----

class TtsInfoResponse(BaseModel):
    initialized: bool
    backend: str
    num_voices: int = 0
    default_model: Optional[str] = None
    backends_loaded: List[str] = Field(default_factory=list)


# ---- tasks ----

class TaskSubmitRequest(BaseModel):
    text: str = Field(..., description="待合成文本")
    voice_id: Optional[str] = None
    model: Optional[str] = None
    response_format: str = Field(default="wav", description="wav | pcm")
    callback_url: Optional[str] = None


class TaskSubmitResponse(BaseModel):
    task_id: str
    status: str = "PENDING"


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: float = 0.0
    download_url: Optional[str] = None
    duration_ms: Optional[float] = None
    error: Optional[str] = None
    created_at: str


class TaskCancelResponse(BaseModel):
    task_id: str
    status: str = "CANCELLED"


# ---- lexicons ----

class TtsPronunciationEntry(BaseModel):
    word: str
    phoneme: str
    locale: str = "zh"


class TtsLexiconRequest(BaseModel):
    entries: List[TtsPronunciationEntry]


class TtsLexiconItem(BaseModel):
    id: str
    entries: List[TtsPronunciationEntry]
    created_at: str


class TtsLexiconListResponse(BaseModel):
    lexicons: List[TtsLexiconItem]
