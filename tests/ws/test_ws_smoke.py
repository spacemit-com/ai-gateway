"""WebSocket 冒烟测试。

使用 FastAPI TestClient（同步上下文）跑 WS，因为 httpx.AsyncClient 不支持 WS。
目标：
- 三个 `/stream` 路径 connect 成功（校验路由注册）
- ASR/TTS 无 session_id 时 connect 后会收到 `{"type":"error"}` + 被 close
- VAD 无 session（设计无鉴权）直接能连 + 收到 `{"type":"ready"}`
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@pytest.fixture
def tclient():
    from spacemit_ai_gateway.app.main import app as real_app
    with TestClient(real_app) as c:
        yield c


def test_ws_asr_missing_session_errors(tclient):
    with tclient.websocket_connect("/v1/asr/stream") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "session" in msg["code"].lower() or "session" in msg["message"].lower()
        # 之后会被 server close
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_ws_tts_missing_session_errors(tclient):
    with tclient.websocket_connect("/v1/tts/stream") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_ws_vad_ready(tclient):
    with tclient.websocket_connect("/v1/vad/stream?sample_rate=16000") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "ready"
        # 主动结束
        ws.send_text(json.dumps({"type": "end"}))


def test_ws_asr_with_valid_session_ready(tclient):
    # 先 POST 签发 session
    r = tclient.post(
        "/v1/asr/stream/session",
        json={"sample_rate": 16000, "language": "zh"},
    )
    assert r.status_code == 200
    sid = r.json()["session_id"]

    with tclient.websocket_connect(
        f"/v1/asr/stream?session_id={sid}&language=zh&sample_rate=16000"
    ) as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"
        ws.send_text(json.dumps({"type": "end"}))
