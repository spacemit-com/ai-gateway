"""ASR service 单元测试。"""

from __future__ import annotations

import pytest

from spacemit_ai_gateway.common.errors import InvalidSessionError
from spacemit_ai_gateway.domains.asr.schemas import RecognizeParams, StreamSessionRequest


async def test_recognize_returns_text(asr_service):
    resp = await asr_service.recognize(
        b"\x00" * 16000,
        RecognizeParams(language="zh", sample_rate=16000),
    )
    assert resp.text == "fake transcription"
    assert resp.duration_ms > 0
    assert len(resp.sentences) == 1


async def test_create_stream_session_and_open(asr_service):
    ss = await asr_service.create_stream_session(
        StreamSessionRequest(sample_rate=16000, language="zh")
    )
    assert ss.session_id
    # open 时 pop 后就不复存在
    stream = await asr_service.open_stream(
        session_id=ss.session_id, language="zh", sample_rate=16000, partial=True
    )
    assert stream is not None


async def test_open_stream_without_session_raises(asr_service):
    with pytest.raises(InvalidSessionError):
        await asr_service.open_stream(
            session_id=None, language="zh", sample_rate=16000, partial=True
        )


async def test_open_stream_with_bad_session_raises(asr_service):
    with pytest.raises(InvalidSessionError):
        await asr_service.open_stream(
            session_id="nonexistent", language="zh", sample_rate=16000, partial=True
        )


async def test_healthz_ready(asr_service):
    h = await asr_service.healthz()
    assert h["ready"] is True
    assert h["backend"] == "fake-asr"
