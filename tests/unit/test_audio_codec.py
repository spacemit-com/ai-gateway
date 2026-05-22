from __future__ import annotations

import io
import wave

import numpy as np
import pytest

from spacemit_ai_gateway.common import audio_codec
from spacemit_ai_gateway.common.audio_codec import (
    AudioDecodeError,
    normalize_audio_for_inference,
)


def _wav_bytes(pcm: np.ndarray, sample_rate: int, channels: int = 1) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.astype(np.int16).tobytes())
    return buf.getvalue()


def test_normalize_raw_pcm16_defaults_to_target_rate():
    pcm = np.arange(1600, dtype=np.int16)

    normalized = normalize_audio_for_inference(pcm.tobytes(), target_sample_rate=16000)

    assert normalized.sample_rate == 16000
    assert normalized.source_sample_rate == 16000
    assert normalized.source_format == "raw"
    assert normalized.pcm == pcm.tobytes()


def test_normalize_raw_pcm16_resamples_explicit_input_rate():
    pcm = np.arange(4800, dtype=np.int16)

    normalized = normalize_audio_for_inference(
        pcm.tobytes(),
        input_sample_rate=48000,
        target_sample_rate=16000,
    )

    assert normalized.sample_rate == 16000
    assert normalized.source_sample_rate == 48000
    assert normalized.source_format == "raw"
    assert len(normalized.pcm) == 1600 * 2


def test_normalize_wav_downmixes_and_resamples():
    frames = 4800
    left = np.arange(frames, dtype=np.int16)
    right = np.zeros(frames, dtype=np.int16)
    stereo = np.column_stack([left, right]).reshape(-1)

    normalized = normalize_audio_for_inference(
        _wav_bytes(stereo, sample_rate=48000, channels=2),
        input_sample_rate=0,
        target_sample_rate=16000,
        filename="input.wav",
        content_type="audio/wav",
    )

    assert normalized.sample_rate == 16000
    assert normalized.source_sample_rate == 48000
    assert normalized.source_format == "wav"
    assert len(normalized.pcm) == 1600 * 2


def test_normalize_compressed_audio_requires_ffmpeg(monkeypatch):
    monkeypatch.setattr(audio_codec.shutil, "which", lambda _: None)

    with pytest.raises(AudioDecodeError, match="requires ffmpeg"):
        normalize_audio_for_inference(
            b"ID3\x04\x00\x00\x00\x00\x00\x00",
            filename="input.mp3",
            content_type="audio/mpeg",
        )


def test_normalize_raw_pcm16_resample_requires_ffmpeg(monkeypatch):
    monkeypatch.setattr(audio_codec.shutil, "which", lambda _: None)

    with pytest.raises(AudioDecodeError, match="resampling requires ffmpeg"):
        normalize_audio_for_inference(
            np.arange(4800, dtype=np.int16).tobytes(),
            input_sample_rate=48000,
            target_sample_rate=16000,
        )


def test_normalize_rejects_invalid_raw_pcm16_size():
    with pytest.raises(AudioDecodeError, match="even number of bytes"):
        normalize_audio_for_inference(b"\x00", input_sample_rate=16000)
