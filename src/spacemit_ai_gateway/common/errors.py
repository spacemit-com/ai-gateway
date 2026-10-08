"""Domain 错误家族。

Service 层只抛 DomainError 子类；adapter 把 SDK 原始异常翻译过来；
HTTP 全局 handler / WS 边界装饰器都识别 DomainError。
"""

from typing import Any


class DomainError(Exception):
    """所有业务错误的基类。"""

    code: str = "domain_error"
    status_code: int = 500

    def __init__(
        self,
        message: str,
        *,
        retriable: bool = False,
        details: Any = None,
        code: str | None = None,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.retriable = retriable
        self.details = details
        # 同一类错误在不同接口上沿用各自原有的 HTTP 状态码，允许按实例覆盖
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code

    def to_dict(self) -> dict:
        return {
            "error": self.code,
            "message": self.message,
            "retriable": self.retriable,
            "details": self.details,
        }


# 通用错误（跨域）
class ServiceUnavailableError(DomainError):
    code = "service_unavailable"
    status_code = 503

    def __init__(self, message: str = "service not initialized", **kw):
        super().__init__(message, retriable=True, **kw)


class RequestTooLargeError(DomainError):
    code = "request_too_large"
    status_code = 413


class InvalidSessionError(DomainError):
    code = "invalid_session"
    status_code = 401


class ModelNotLoaded(DomainError):
    code = "model_not_loaded"
    status_code = 404


class ModelAlreadyLoaded(DomainError):
    code = "model_already_loaded"
    status_code = 409


class ModelUnloadForbidden(DomainError):
    code = "model_unload_forbidden"
    status_code = 400


class ModelUnknown(DomainError):
    code = "model_unknown"
    status_code = 404


# ASR
class AsrError(DomainError):
    code = "asr_error"


class AsrBackendUnavailable(AsrError):
    code = "asr_backend_unavailable"
    status_code = 503

    def __init__(self, message: str = "ASR backend unavailable", **kw):
        super().__init__(message, retriable=True, **kw)


class AsrInvalidAudio(AsrError):
    code = "asr_invalid_audio"
    status_code = 400


# TTS
class TtsError(DomainError):
    code = "tts_error"


class TtsBackendUnavailable(TtsError):
    code = "tts_backend_unavailable"
    status_code = 503

    def __init__(self, message: str = "TTS backend unavailable", **kw):
        super().__init__(message, retriable=True, **kw)


class TtsInvalidText(TtsError):
    code = "tts_invalid_text"
    status_code = 400


# VAD
class VadError(DomainError):
    code = "vad_error"


class VadBackendUnavailable(VadError):
    code = "vad_backend_unavailable"
    status_code = 503

    def __init__(self, message: str = "VAD backend unavailable", **kw):
        super().__init__(message, retriable=True, **kw)


class VadInvalidAudio(VadError):
    code = "vad_invalid_audio"
    status_code = 400


# 异步任务
class JobNotFound(DomainError):
    code = "job_not_found"
    status_code = 404


class TaskNotFound(DomainError):
    code = "task_not_found"
    status_code = 404


# 模型下载 / 加载（错误码清单见 common/error_catalog.py）
# LLM/Embed/Rerank/VLM 的接口历史上用 400/404/503，这里保持原状态码不变，只补错误码。
# 例外：POST /models/load 加载失败由原来的 400 改为 503（ModelLoadFailed），与推理时自动加载失败一致。
class ModelNotFound(DomainError):
    code = "model_not_found"
    status_code = 400


class DownloadNotSupported(DomainError):
    code = "download_not_supported"
    status_code = 400


class ModelAlreadyDownloaded(DomainError):
    code = "already_downloaded"
    status_code = 400


class DownloadInProgress(DomainError):
    code = "download_in_progress"
    status_code = 400

    def __init__(self, message: str, **kw):
        super().__init__(message, retriable=True, **kw)


class NoActiveDownload(DomainError):
    code = "no_active_download"
    status_code = 400


class ModelNotDownloaded(DomainError):
    code = "model_not_downloaded"
    status_code = 400


class ModelDownloading(DomainError):
    code = "model_downloading"
    status_code = 400

    def __init__(self, message: str, **kw):
        super().__init__(message, retriable=True, **kw)


class NoModelLoaded(DomainError):
    code = "model_not_loaded"
    status_code = 503


class ModelLoadFailed(DomainError):
    """模型加载失败；code 细分为 load_oom / load_invalid_model / load_invalid_args /
    load_timeout / backend_missing / load_failed。"""

    code = "load_failed"
    status_code = 503


class BackendCrashed(DomainError):
    code = "backend_crashed"
    status_code = 503

    def __init__(self, message: str, **kw):
        super().__init__(message, retriable=True, **kw)
