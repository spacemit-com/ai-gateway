"""音频编解码 helper。

- decode_audio: 字节流 → int16 numpy 数组 + 采样率
  支持 WAV/PCM（最小依赖）；其它格式抛 NotImplementedError 让 adapter 自己处理。
- normalize_audio_for_inference: 用户上传音频 → mono PCM16 raw bytes。
- encode_wav: int16 PCM + sample_rate → WAV 字节流（服务端最常用响应格式）
- encode_pcm / encode_mp3 / encode_opus: 占位，真正需要时在 adapter 层按需引入 ffmpeg/soundfile
"""

from __future__ import annotations

import io
import os
import shutil
import struct
import subprocess
import wave
from dataclasses import dataclass
from typing import Optional

import numpy as np

_DEFAULT_INFERENCE_SAMPLE_RATE = 16000
_FFMPEG_TIMEOUT_SECONDS = 30

_COMPRESSED_EXTENSIONS = {
    ".aac",
    ".flac",
    ".m4a",
    ".mp3",
    ".oga",
    ".ogg",
    ".opus",
    ".webm",
}
_COMPRESSED_CONTENT_TYPES = {
    "audio/aac",
    "audio/flac",
    "audio/m4a",
    "audio/mp3",
    "audio/mp4",
    "audio/mpeg",
    "audio/ogg",
    "audio/opus",
    "audio/webm",
}


@dataclass(frozen=True)
class NormalizedAudio:
    pcm: bytes
    sample_rate: int
    source_sample_rate: int
    source_format: str


class AudioDecodeError(ValueError):
    def __init__(self, message: str, *, details: object = None):
        super().__init__(message)
        self.details = details


def decode_audio(
    data: bytes,
    target_sample_rate: Optional[int] = None,
) -> tuple[np.ndarray, int]:
    """解码音频为 int16 numpy 数组。

    判断规则：
    - 以 RIFF 开头 → 按 WAV 解析
    - 否则按 int16 PCM 处理（调用方必须给 target_sample_rate）
    """
    if data[:4] == b"RIFF":
        return _decode_wav(data)

    if target_sample_rate is None:
        raise ValueError("raw PCM requires target_sample_rate")
    pcm = np.frombuffer(data, dtype=np.int16)
    return pcm, target_sample_rate


def normalize_audio_for_inference(
    data: bytes,
    *,
    input_sample_rate: int = 0,
    target_sample_rate: int = _DEFAULT_INFERENCE_SAMPLE_RATE,
    filename: str | None = None,
    content_type: str | None = None,
) -> NormalizedAudio:
    """Decode uploaded audio into mono PCM16 bytes for ASR/VAD backends.

    Raw PCM cannot carry its sample rate. If the caller does not provide one,
    keep compatibility with the existing HTTP API and assume the target rate.
    """
    if not data:
        raise AudioDecodeError("empty audio")
    if target_sample_rate <= 0:
        raise AudioDecodeError(f"invalid target sample rate: {target_sample_rate}")

    source_format = _detect_source_format(data, filename, content_type)
    if source_format == "compressed":
        pcm = _decode_with_ffmpeg(data, target_sample_rate)
        return NormalizedAudio(
            pcm=pcm.tobytes(),
            sample_rate=target_sample_rate,
            source_sample_rate=target_sample_rate,
            source_format=source_format,
        )

    if source_format == "wav":
        try:
            pcm, source_sample_rate = _decode_wav(data)
        except (EOFError, wave.Error, ValueError) as exc:
            raise AudioDecodeError(f"invalid WAV audio: {exc}") from exc
    else:
        source_sample_rate = input_sample_rate or target_sample_rate
        pcm = _decode_raw_pcm(data, source_sample_rate)

    normalized = _resample_pcm16(pcm, source_sample_rate, target_sample_rate)
    return NormalizedAudio(
        pcm=normalized.tobytes(),
        sample_rate=target_sample_rate,
        source_sample_rate=source_sample_rate,
        source_format=source_format,
    )


def _decode_wav(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data), "rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
        frames = wf.readframes(n_frames)

    if sample_width != 2:
        raise ValueError(f"only 16-bit PCM WAV supported, got {sample_width * 8}-bit")

    pcm = np.frombuffer(frames, dtype=np.int16)
    if n_channels > 1:
        pcm = pcm.reshape(-1, n_channels).mean(axis=1).astype(np.int16)
    return pcm, sample_rate


def _decode_raw_pcm(data: bytes, sample_rate: int) -> np.ndarray:
    if sample_rate <= 0:
        raise AudioDecodeError(f"invalid raw PCM sample rate: {sample_rate}")
    if len(data) % 2:
        raise AudioDecodeError("raw PCM16 audio must contain an even number of bytes")
    return np.frombuffer(data, dtype=np.int16)


def _detect_source_format(
    data: bytes,
    filename: str | None,
    content_type: str | None,
) -> str:
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if _has_compressed_magic(data):
        return "compressed"

    ext = os.path.splitext(filename or "")[1].lower()
    if ext in _COMPRESSED_EXTENSIONS:
        return "compressed"

    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if media_type in _COMPRESSED_CONTENT_TYPES:
        return "compressed"

    return "raw"


def _has_compressed_magic(data: bytes) -> bool:
    if data.startswith((b"ID3", b"OggS", b"fLaC")):
        return True
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return True
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return True
    return len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0


def _decode_with_ffmpeg(data: bytes, target_sample_rate: int) -> np.ndarray:
    _require_ffmpeg(
        "compressed audio requires ffmpeg; install ffmpeg or upload PCM/WAV"
    )

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-i",
        "pipe:0",
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "-ac",
        "1",
        "-ar",
        str(target_sample_rate),
        "pipe:1",
    ]
    stdout = _run_ffmpeg(
        cmd,
        data,
        timeout_message="ffmpeg audio decode timed out",
        failure_message="ffmpeg failed to decode audio",
        empty_message="decoded audio is empty",
    )
    return np.frombuffer(stdout, dtype=np.int16)


def _require_ffmpeg(message: str) -> None:
    if shutil.which("ffmpeg") is None:
        raise AudioDecodeError(message, details={"dependency": "ffmpeg"})


def _run_ffmpeg(
    cmd: list[str],
    data: bytes,
    *,
    timeout_message: str,
    failure_message: str,
    empty_message: str,
) -> bytes:
    try:
        proc = subprocess.run(
            cmd,
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=_FFMPEG_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AudioDecodeError(timeout_message) from exc

    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise AudioDecodeError(
            failure_message,
            details={"stderr": stderr[-500:]},
        )
    if not proc.stdout:
        raise AudioDecodeError(empty_message)
    return proc.stdout


def _resample_pcm16(
    pcm: np.ndarray,
    source_sample_rate: int,
    target_sample_rate: int,
) -> np.ndarray:
    if source_sample_rate <= 0:
        raise AudioDecodeError(f"invalid source sample rate: {source_sample_rate}")
    if target_sample_rate <= 0:
        raise AudioDecodeError(f"invalid target sample rate: {target_sample_rate}")
    if source_sample_rate == target_sample_rate or pcm.size == 0:
        return pcm.astype(np.int16, copy=False)

    _require_ffmpeg("PCM resampling requires ffmpeg")
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "-ac",
        "1",
        "-ar",
        str(source_sample_rate),
        "-i",
        "pipe:0",
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "-ac",
        "1",
        "-ar",
        str(target_sample_rate),
        "pipe:1",
    ]
    stdout = _run_ffmpeg(
        cmd,
        pcm.astype(np.int16, copy=False).tobytes(),
        timeout_message="ffmpeg audio resample timed out",
        failure_message="ffmpeg failed to resample audio",
        empty_message="resampled audio is empty",
    )
    return np.frombuffer(stdout, dtype=np.int16)


def encode_wav(pcm_int16: np.ndarray, sample_rate: int) -> bytes:
    """int16 单声道 PCM → WAV 字节流。"""
    if pcm_int16.dtype != np.int16:
        raise ValueError(f"expected int16, got {pcm_int16.dtype}")

    pcm_bytes = pcm_int16.tobytes()
    n_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * n_channels * bits_per_sample // 8
    block_align = n_channels * bits_per_sample // 8
    data_size = len(pcm_bytes)
    file_size = 36 + data_size

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        file_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        n_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header + pcm_bytes


def encode_pcm(pcm_int16: np.ndarray) -> bytes:
    """raw PCM int16 单声道。"""
    if pcm_int16.dtype != np.int16:
        raise ValueError(f"expected int16, got {pcm_int16.dtype}")
    return pcm_int16.tobytes()


def encode_audio(pcm_int16: np.ndarray, sample_rate: int, fmt: str) -> tuple[bytes, str]:
    """统一编码入口。返回 (bytes, content_type)。"""
    fmt = fmt.lower()
    if fmt == "wav":
        return encode_wav(pcm_int16, sample_rate), "audio/wav"
    if fmt == "pcm":
        return encode_pcm(pcm_int16), "audio/pcm"
    if fmt in ("mp3", "opus"):
        raise NotImplementedError(f"{fmt} encoding not implemented yet")
    raise ValueError(f"unknown audio format: {fmt}")
