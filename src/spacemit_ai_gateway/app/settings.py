"""应用配置。

嵌套结构：app / auth / limits / asr / tts / vad / llm / logging
每个 domain 有自己的 settings，stream 相关参数放在 <domain>.stream.*
"""

import os
from importlib import resources
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class AppConfig(BaseModel):
    name: str = "SpacemiT AI Gateway"
    version: str = "0.1.7"
    host: str = "0.0.0.0"
    port: int = 18790
    debug: bool = False


class AuthConfig(BaseModel):
    enabled: bool = False
    api_keys: list[str] = Field(default_factory=list)
    ip_whitelist: list[str] = Field(default_factory=list)
    ip_whitelist_file: Optional[str] = None


class LimitsConfig(BaseModel):
    max_upload_bytes: int = 50 * 1024 * 1024  # 50 MB


# ---- ASR ----
class AsrQwen3Config(BaseModel):
    endpoint: str = "http://127.0.0.1:8063/v1/chat/completions"
    model: str = "qwen3-asr"
    timeout: int = 60


class AsrStreamConfig(BaseModel):
    session_ttl_s: int = 300
    event_queue_size: int = 64
    partial_results: bool = True


def _default_asr_models() -> list[dict[str, Any]]:
    return [
        {
            "id": "sensevoice",
            "url": "https://archive.spacemit.com/spacemit-ai/model_zoo/asr/sensevoice.tar.gz",
            "archive_name": "sensevoice.tar.gz",
            "archive_subdir": "sensevoice",
        }
    ]


class AsrConfig(BaseModel):
    backend: str = "sensevoice"
    backends: Optional[list[str]] = None
    model_dir: Optional[str] = None
    models: list[dict[str, Any]] = Field(default_factory=_default_asr_models)
    language: str = "auto"
    punctuation: bool = True
    provider: str = "spacemit"
    warmup_audio_ms: int = 1000
    qwen3: AsrQwen3Config = Field(default_factory=AsrQwen3Config)
    stream: AsrStreamConfig = Field(default_factory=AsrStreamConfig)


# ---- TTS ----
class TtsStreamConfig(BaseModel):
    session_ttl_s: int = 300
    event_queue_size: int = 64


def _default_tts_models() -> list[dict[str, Any]]:
    return [
        {
            "id": "matcha_zh_en",
            "url": "https://archive.spacemit.com/spacemit-ai/model_zoo/tts/matcha-tts/"
            "matcha-icefall-zh-en.tar.gz",
            "archive_name": "matcha-icefall-zh-en.tar.gz",
            "vocoder_name": "vocos-16khz-univ.q.onnx",
            "vocoder_url": "https://archive.spacemit.com/spacemit-ai/model_zoo/tts/vocoder/"
            "vocos-16khz-univ.q.onnx",
        },
    ]


def _default_tts_backends() -> list[str]:
    return ["matcha_zh", "matcha_en", "matcha_zh_en", "kokoro"]


class TtsConfig(BaseModel):
    backend: str = "matcha_zh_en"
    backends: Optional[list[str]] = Field(default_factory=_default_tts_backends)
    model_dir: Optional[str] = None
    models: list[dict[str, Any]] = Field(default_factory=_default_tts_models)
    speed: float = 1.0
    volume: float = 50.0
    pitch: float = 1.0
    # None → 用 spacemit_tts preset 默认值（matcha_zh=22050, matcha_zh_en=16000, kokoro=24000）
    sample_rate: Optional[int] = None
    default_format: str = "wav"
    stream: TtsStreamConfig = Field(default_factory=TtsStreamConfig)


# ---- VAD ----
class VadStreamConfig(BaseModel):
    event_queue_size: int = 64


class VadConfig(BaseModel):
    backend: str = "silero"
    backends: Optional[list[str]] = None
    model_dir: Optional[str] = None
    trigger_threshold: float = 0.5
    stop_threshold: float = 0.35
    min_speech_ms: int = 250
    max_silence_ms: int = 500
    sample_rate: int = 16000
    stream: VadStreamConfig = Field(default_factory=VadStreamConfig)


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


# ---- LLM ----
class PortPoolConfig(BaseModel):
    start: int = 18800
    end: int = 18900


class BaseStorageConfig(BaseModel):
    """存储配置基类。"""
    base_dir: str
    models_dir: str
    db_path: str

    @property
    def models_path(self) -> Path:
        return Path(self.models_dir).expanduser()

    @property
    def db_file(self) -> Path:
        return Path(self.db_path).expanduser()


class BaseModelConfig(BaseModel):
    """模型服务配置基类。"""
    host: str = "127.0.0.1"
    default_args: list[str]
    backend: Optional[str] = None
    backends: Optional[list[str]] = None
    port_pool: PortPoolConfig = Field(default_factory=PortPoolConfig)
    storage: BaseStorageConfig
    models: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def default_model(self) -> Optional[str]:
        return self.backend

    @property
    def preset_models(self) -> list[dict[str, Any]]:
        return self.models


class LlmStorageConfig(BaseStorageConfig):
    base_dir: str = "~/.cache/spacemit-ai-gateway/llm"
    models_dir: str = "~/.cache/models/llm"
    db_path: str = "~/.cache/spacemit-ai-gateway/llm/db.sqlite"


class LlmConfig(BaseModelConfig):
    default_args: list[str] = ["--ctx-size", "4096", "--threads", "8"]
    storage: LlmStorageConfig = Field(default_factory=LlmStorageConfig)


# ---- Embed ----
class EmbedStorageConfig(BaseStorageConfig):
    base_dir: str = "~/.cache/spacemit-ai-gateway/embed"
    models_dir: str = "~/.cache/models/embed"
    db_path: str = "~/.cache/spacemit-ai-gateway/embed/db.sqlite"


class EmbedConfig(BaseModelConfig):
    default_args: list[str] = ["--embedding", "--threads", "8"]
    storage: EmbedStorageConfig = Field(default_factory=EmbedStorageConfig)

# ---- Rerank ----
class RerankStorageConfig(BaseStorageConfig):
    base_dir: str = "~/.cache/spacemit-ai-gateway/rerank"
    models_dir: str = "~/.cache/models/rerank"
    db_path: str = "~/.cache/spacemit-ai-gateway/rerank/db.sqlite"


class RerankConfig(BaseModelConfig):
    default_args: list[str] = ["--reranking", "--threads", "8"]
    storage: RerankStorageConfig = Field(default_factory=RerankStorageConfig)


class Settings(BaseSettings):
    app: AppConfig = Field(default_factory=AppConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    asr: AsrConfig = Field(default_factory=AsrConfig)
    tts: TtsConfig = Field(default_factory=TtsConfig)
    vad: VadConfig = Field(default_factory=VadConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    embed: EmbedConfig = Field(default_factory=EmbedConfig)
    rerank: RerankConfig = Field(default_factory=RerankConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    class Config:
        env_prefix = "SPACEMIT_AI_GATEWAY_"
        env_nested_delimiter = "__"


def _load_yaml_file(config_path: Path) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_yaml_config(config_path: Optional[str] = None) -> dict:
    if config_path is None:
        config_path = os.getenv("SPACEMIT_AI_GATEWAY_CONFIG")

    if config_path:
        explicit_path = Path(config_path).expanduser()
        if explicit_path.exists():
            return _load_yaml_file(explicit_path)
        return {}

    package_config = resources.files("spacemit_ai_gateway").joinpath("configs", "base.yaml")
    if package_config.is_file():
        return yaml.safe_load(package_config.read_text(encoding="utf-8")) or {}

    return {}


@lru_cache
def get_settings() -> Settings:
    yaml_config = load_yaml_config()
    return Settings(**yaml_config)
