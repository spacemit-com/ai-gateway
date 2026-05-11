"""ASR 请求/响应模型。"""

from typing import List, Optional

from pydantic import BaseModel, Field


class RecognizeParams(BaseModel):
    model: Optional[str] = Field(default=None, description="模型 ID，与 /v1/asr/models 对齐")
    language: str = Field(default="zh", description="语种: zh/en/ja/ko/yue/auto")
    sample_rate: int = Field(default=0, description="采样率，0 表示自动探测")
    punctuation: bool = Field(default=True, description="是否添加标点")
    word_timestamps: bool = Field(default=False, description="是否返回词级时间戳")
    hotwords: Optional[str] = Field(default=None, description="热词，逗号分隔")


class SentenceInfo(BaseModel):
    text: str
    start_ms: int
    end_ms: int


class RecognizeResponse(BaseModel):
    text: str
    sentences: List[SentenceInfo] = Field(default_factory=list)
    duration_ms: float
    processing_ms: float
    rtf: float
    language: Optional[str] = None


class StreamSessionRequest(BaseModel):
    model: Optional[str] = Field(default=None, description="模型 ID")
    sample_rate: int = Field(default=16000)
    encoding: str = Field(default="pcm_s16le")
    language: str = Field(default="zh")
    partial_results: bool = Field(default=True)
    client_id: Optional[str] = None


class StreamSessionResponse(BaseModel):
    session_id: str
    expires_at: str
    sample_rate: int
    encoding: str
    language: str


class StreamQuery(BaseModel):
    session_id: Optional[str] = None
    language: str = "zh"
    sample_rate: int = 16000
    partial: bool = True


class LanguagesResponse(BaseModel):
    languages: List[str]
    default: str = "zh"


class HealthResponse(BaseModel):
    ready: bool
    state: str
    backend: str


# ---- params ----

class AsrParamsResponse(BaseModel):
    language: str
    punctuation: bool
    hotword_weight: Optional[float] = None
    itn: Optional[bool] = None


class AsrParamsPatch(BaseModel):
    language: Optional[str] = None
    punctuation: Optional[bool] = None
    hotword_weight: Optional[float] = None
    itn: Optional[bool] = None


# ---- audio ----

class AsrAudioResponse(BaseModel):
    sample_rate: int
    vad_threshold: Optional[float] = None
    denoise: bool = False
    agc: bool = False


class AsrAudioPatch(BaseModel):
    sample_rate: Optional[int] = None
    vad_threshold: Optional[float] = None
    denoise: Optional[bool] = None
    agc: Optional[bool] = None


# ---- engine ----

class AsrEngineResponse(BaseModel):
    num_threads: int
    device: str
    power_mode: Optional[str] = None
    pending_restart: bool = False


class AsrEnginePatch(BaseModel):
    num_threads: Optional[int] = None
    device: Optional[str] = None
    power_mode: Optional[str] = None


# ---- stats ----

class AsrStatsResponse(BaseModel):
    total_requests: int = 0
    total_errors: int = 0
    rtf_avg: float = 0.0
    uptime_s: float = 0.0


# ---- info ----

class AsrInfoResponse(BaseModel):
    initialized: bool
    backend: str
    model: Optional[str] = None
    backends_loaded: List[str] = Field(default_factory=list)


# ---- jobs ----

class JobSubmitRequest(BaseModel):
    audio_url: str = Field(..., description="音频可拉取地址")
    callback_url: Optional[str] = Field(default=None, description="完成回调地址")
    language: str = Field(default="zh")
    model: Optional[str] = None
    priority: int = Field(default=0)


class JobSubmitResponse(BaseModel):
    job_id: str
    status: str = "PENDING"


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: float = 0.0
    result: Optional[RecognizeResponse] = None
    error: Optional[str] = None
    created_at: str


class JobCancelResponse(BaseModel):
    job_id: str
    status: str


# ---- lexicons ----

class AsrLexiconEntry(BaseModel):
    word: str
    weight: float = 1.0


class AsrLexiconRequest(BaseModel):
    entries: List[AsrLexiconEntry]
    scope: str = "global"


class AsrLexiconItem(BaseModel):
    id: str
    entries: List[AsrLexiconEntry]
    scope: str = "global"
    created_at: str


class AsrLexiconListResponse(BaseModel):
    lexicons: List[AsrLexiconItem]
