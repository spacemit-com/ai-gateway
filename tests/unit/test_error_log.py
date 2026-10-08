"""模型故障记录：SQLite 持久化、只记模型故障、各域出口记录一次、GET /v1/errors/recent。"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from spacemit_ai_gateway.common import error_log
from spacemit_ai_gateway.common.downloader import DownloadError
from spacemit_ai_gateway.common.error_log import ErrorLog, mark_fault, record_fault
from spacemit_ai_gateway.common.errors import DomainError, ModelLoadFailed
from spacemit_ai_gateway.gateway import error_codes
from spacemit_ai_gateway.gateway.errors import setup_exception_handlers

from .test_downloader import _payload
from .test_model_download_api import (  # noqa: F401  server 是 fixture
    SENSEVOICE_FILES,
    _asr_service,
    _Backend,
    _ChatSvc,
    _CrashingStreamBackend,
    _finish,
    _svc,
    _tar,
    server,
)


@pytest.fixture
def store(monkeypatch):
    """每个用例一个独立的内存记录（不落盘）。"""
    log = ErrorLog()
    monkeypatch.setattr(error_log, "_store", log)
    return log


def _entry(i: int, domain: str = "llm", model: str = "m") -> dict:
    return {"ts": 1000.0 + i, "domain": domain, "model": model, "code": "load_oom", "phase": "load",
            "message": f"e{i}", "retriable": False, "details": {"i": i}}


# ---------------------------------------------------------------------------
# 存储
# ---------------------------------------------------------------------------

async def test_records_survive_reopen(tmp_path):
    path = tmp_path / "state" / "errors.sqlite"
    log = ErrorLog()
    log.open(path)
    for i, (domain, model) in enumerate([("llm", "a"), ("asr", "sensevoice"), ("llm", "b")]):
        await log.add(_entry(i, domain, model))
    log.close()

    log = ErrorLog()  # 模拟 gateway 重启
    log.open(path)
    rows = await log.query()
    assert [r["model"] for r in rows] == ["b", "sensevoice", "a"]  # 新的在前
    assert rows[0]["details"] == {"i": 2} and rows[0]["retriable"] is False and rows[0]["time"]
    assert [r["model"] for r in await log.query(domain="llm")] == ["b", "a"]
    assert [r["model"] for r in await log.query(model="sensevoice")] == ["sensevoice"]
    assert [r["model"] for r in await log.query(since=1001.0)] == ["b"]
    assert len(await log.query(limit=1)) == 1
    log.close()


async def test_keeps_only_latest_rows(tmp_path):
    log = ErrorLog(max_rows=5)
    log.open(tmp_path / "errors.sqlite")
    for i in range(8):
        await log.add(_entry(i))
    rows = await log.query(limit=100)
    assert [r["message"] for r in rows] == ["e7", "e6", "e5", "e4", "e3"]
    log.close()


async def test_unwritable_path_falls_back_to_memory(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    log = ErrorLog()
    log.open(blocker / "errors.sqlite")  # 父目录是文件，打不开
    await log.add(_entry(0))
    assert [r["message"] for r in await log.query()] == ["e0"]


# ---------------------------------------------------------------------------
# 记录规则
# ---------------------------------------------------------------------------

async def test_only_tagged_model_faults_are_recorded_once(store):
    await record_fault(ModelLoadFailed("oom", code="load_oom"))  # 没标记模型
    await record_fault(mark_fault(DomainError("bad", code="validation_error"), "llm", "m"))  # 调用方参数错误
    for code in ("cancelled", "model_not_downloaded", "model_downloading", "model_not_loaded"):
        await record_fault(mark_fault(DomainError(code, code=code), "llm", "m"))
    assert await store.query() == []

    exc = mark_fault(ModelLoadFailed("cannot allocate", code="load_oom", details={"log_tail": ["x"]}), "llm", "m")
    mark_fault(exc, "vlm", "other")  # 已有标记不覆盖
    await record_fault(exc)
    await record_fault(exc)  # 同一个异常经过多个出口只记一次
    await record_fault(mark_fault(RuntimeError("boom"), "asr", "sensevoice"))
    rows = await store.query()
    assert [(r["domain"], r["model"], r["code"], r["phase"]) for r in rows] == [
        ("asr", "sensevoice", "internal_error", "inference"),
        ("llm", "m", "load_oom", "load"),
    ]
    assert rows[1]["details"] == {"log_tail": ["x"]}


# ---------------------------------------------------------------------------
# LLM 等四域（BaseModelService）
# ---------------------------------------------------------------------------

class _OomBackend(_Backend):
    async def start_model(self, model, path, args):
        raise ModelLoadFailed("llama-server exited: failed to allocate buffer", code="load_oom")


def _app(**services) -> FastAPI:
    from spacemit_ai_gateway.domains.llm import api as llm_api

    app = FastAPI()
    setup_exception_handlers(app)
    app.include_router(llm_api.router, prefix="/v1/llm")
    app.include_router(error_codes.router)
    for name, svc in services.items():
        setattr(app.state, name, svc)
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_llm_load_stream_and_download_faults(server, tmp_path, store):
    ok = server.add("llm/s.gguf", _payload())
    missing = server.add("llm/gone.gguf", _payload())
    server.status["/model_zoo/llm/gone.gguf"] = 404
    svc = _svc(tmp_path, [{"id": "s", "url": ok}, {"id": "gone", "url": missing}])
    svc.__class__ = _ChatSvc
    svc.domain = "llm"
    svc._backends["fake"] = _OomBackend()
    await svc.initialize()
    try:
        await svc.download("s")
        await _finish(svc, "s")
        await svc.download("gone")
        await _finish(svc, "gone")
        async with _client(_app(llm_service=svc)) as c:
            r = await c.post("/v1/llm/models/load", json={"model": "s"})
            assert r.status_code == 503 and r.json()["error"] == "load_oom"

            svc._backends["fake"] = _CrashingStreamBackend()
            await svc.load("s")
            req = {"model": "s", "stream": True, "messages": [{"role": "user", "content": "hi"}]}
            r = await c.post("/v1/llm/chat/completions", json=req)
            assert "backend_crashed" in r.text

            r = await c.post("/v1/llm/models/load", json={"model": "nope"})  # 未知模型不算故障
            r = await c.get("/v1/errors/recent", params={"domain": "llm"})
            got = [(e["model"], e["code"], e["phase"]) for e in r.json()["errors"]]
            assert got == [("s", "backend_crashed", "inference"), ("s", "load_oom", "load"),
                           ("gone", "remote_http_error", "download")]
            r = await c.get("/v1/errors/recent", params={"model": "gone"})
            assert [e["code"] for e in r.json()["errors"]] == ["remote_http_error"]
            assert (await c.get("/v1/errors/recent", params={"limit": 0})).status_code == 422
    finally:
        await svc.shutdown()


# ---------------------------------------------------------------------------
# ASR / TTS / VAD（DownloadTracker + 各自的服务）
# ---------------------------------------------------------------------------

async def test_asr_download_failure_recorded_once(server, tmp_path, store, monkeypatch):
    from spacemit_ai_gateway.domains.asr import service as asr_service_module

    url = server.add("asr/sensevoice.tar.gz", _tar(SENSEVOICE_FILES))
    server.status["/model_zoo/asr/sensevoice.tar.gz"] = 503
    monkeypatch.setattr(asr_service_module, "sdk_installed", lambda name: True)
    svc = _asr_service(tmp_path, url)
    with pytest.raises(DownloadError) as ei:
        await svc.load_model("sensevoice")
    await record_fault(ei.value)  # HTTP 出口再记一次也不会重复
    rows = await store.query()
    assert [(r["domain"], r["model"], r["code"]) for r in rows] == [("asr", "sensevoice", "remote_http_error")]


async def test_asr_inference_error_tagged_with_model(store):
    from spacemit_ai_gateway.domains.asr.schemas import RecognizeParams
    from spacemit_ai_gateway.domains.asr.service import AsrService

    class Broken:
        async def recognize(self, **kw):
            raise RuntimeError("onnxruntime: invalid state")

    svc = AsrService.__new__(AsrService)
    svc._default = "sensevoice"
    svc._stats = {"total_errors": 0}
    svc._effective_enable_emotion = lambda *a: False

    async def ensure(model=None):
        return Broken()

    svc._ensure_backend = ensure
    with pytest.raises(RuntimeError) as ei:
        await svc.recognize(b"\0" * 320, RecognizeParams())
    await record_fault(ei.value)
    rows = await store.query()
    assert [(r["domain"], r["model"], r["code"]) for r in rows] == [("asr", "sensevoice", "internal_error")]


# ---------------------------------------------------------------------------
# Vision
# ---------------------------------------------------------------------------

async def test_vision_load_and_inference_faults(store, monkeypatch):
    import threading

    from spacemit_ai_gateway.domains.vision import api as vision_api
    from spacemit_ai_gateway.domains.vision.schemas import ModelLoadResponse
    from spacemit_ai_gateway.domains.vision.service import _inference_failed

    class Registry:
        _lock = threading.Lock()
        _models: dict = {}

        def load_model(self, model_id, **kw):
            return ModelLoadResponse(loaded=False, model_id=model_id,
                                     engine_state={"status": "error", "error_message": "create failed: bad onnx"})

    monkeypatch.setattr(vision_api, "_registry", Registry())
    app = FastAPI()
    setup_exception_handlers(app)
    app.include_router(vision_api.app.router)
    async with _client(app) as c:
        r = await c.post("/v1/vision/models/load", json={"model_id": "yolov8n", "config_path": "/x.yaml"})
        assert r.status_code == 200 and r.json()["data"]["loaded"] is False

    exc = _inference_failed("yolov8n", "inference failed")
    assert exc.error == "inference_failed" and exc.retriable is True
    await record_fault(exc)
    rows = await store.query()
    assert [(r["model"], r["code"], r["phase"], r["message"]) for r in rows] == [
        ("yolov8n", "inference_failed", "inference", "inference failed"),
        ("yolov8n", "load_failed", "load", "create failed: bad onnx"),
    ]
