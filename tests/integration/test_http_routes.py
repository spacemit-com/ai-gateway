"""HTTP 路由烟测。Adapter 在 SDK 缺失时自动走 mock 模式。"""

from __future__ import annotations

import io
import wave


def _wav_silence(sample_rate: int = 48000, channels: int = 2, duration_ms: int = 100) -> bytes:
    frames = sample_rate * duration_ms // 1000
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00" * frames * channels * 2)
    return buf.getvalue()


async def test_root(client):
    r = await client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert "domains" in data


async def test_global_healthz(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "domains" in data
    for dom in ("asr", "tts", "vad"):
        assert dom in data["domains"]
        assert data["domains"][dom]["state"] == "idle"


async def test_openapi_paths(client):
    r = await client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    # HTTP 路径全部注册
    assert "/v1/asr/recognize" in paths
    assert "/v1/asr/stream/session" in paths
    assert "/v1/asr/models" in paths
    assert "/v1/tts/synthesize" in paths
    assert "/v1/tts/stream/session" in paths
    assert "/v1/vad/analyze" in paths
    assert "/v1/vad/segments" in paths


async def test_asr_models(client):
    r = await client.get("/v1/asr/models")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 1


async def test_asr_languages(client):
    r = await client.get("/v1/asr/languages")
    assert r.status_code == 200
    data = r.json()
    assert "languages" in data
    assert data["default"]


async def test_asr_recognize_mock(client):
    files = {"file": ("test.pcm", b"\x00" * 3200, "audio/wav")}
    r = await client.post("/v1/asr/recognize", files=files)
    assert r.status_code == 200
    data = r.json()
    assert "text" in data


async def test_asr_recognize_accepts_48k_stereo_wav(client):
    files = {"file": ("test.wav", _wav_silence(), "audio/wav")}
    r = await client.post("/v1/asr/recognize", files=files)
    assert r.status_code == 200
    data = r.json()
    assert "text" in data


async def test_asr_stream_session_create(client):
    r = await client.post(
        "/v1/asr/stream/session",
        json={"sample_rate": 16000, "language": "zh"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["session_id"]


async def test_tts_synthesize_mock(client):
    r = await client.post(
        "/v1/tts/synthesize",
        json={"text": "你好", "response_format": "wav"},
    )
    assert r.status_code == 200
    # 返回二进制音频（StreamingResponse 或 Response）
    assert len(r.content) > 0


async def test_tts_voices(client):
    r = await client.get("/v1/tts/voices")
    assert r.status_code == 200


async def test_tts_stream_session_create(client):
    r = await client.post(
        "/v1/tts/stream/session",
        json={"voice_id": "default", "response_format": "pcm"},
    )
    assert r.status_code == 200
    assert r.json()["session_id"]


async def test_vad_analyze_mock(client):
    files = {"file": ("test.pcm", b"\x00" * 3200, "audio/wav")}
    r = await client.post("/v1/vad/analyze", files=files)
    assert r.status_code == 200
    data = r.json()
    assert "is_speech" in data


async def test_vad_analyze_accepts_48k_stereo_wav(client):
    files = {"file": ("test.wav", _wav_silence(), "audio/wav")}
    r = await client.post("/v1/vad/analyze", files=files)
    assert r.status_code == 200
    data = r.json()
    assert "is_speech" in data


async def test_vad_segments_mock(client):
    files = {"file": ("test.pcm", b"\x00" * 3200, "audio/wav")}
    r = await client.post("/v1/vad/segments", files=files)
    assert r.status_code == 200
    data = r.json()
    assert "segments" in data


async def test_vad_params(client):
    r = await client.get("/v1/vad/params")
    assert r.status_code == 200


async def test_all_healthz(client):
    for domain in ("asr", "tts", "vad"):
        r = await client.get(f"/v1/{domain}/healthz")
        assert r.status_code == 200
        data = r.json()
        assert "state" in data
