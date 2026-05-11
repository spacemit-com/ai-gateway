"""音频编解码 helper。

- decode_audio: 字节流 → int16 numpy 数组 + 采样率
  支持 WAV/PCM（最小依赖）；其它格式抛 NotImplementedError 让 adapter 自己处理。
- encode_wav: int16 PCM + sample_rate → WAV 字节流（服务端最常用响应格式）
- encode_pcm / encode_mp3 / encode_opus: 占位，真正需要时在 adapter 层按需引入 ffmpeg/soundfile
"""

from __future__ import annotations

import io
import struct
import wave
from typing import Optional

import numpy as np


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
