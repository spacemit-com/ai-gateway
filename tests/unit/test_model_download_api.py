"""下载状态与错误分类：LLM 等四域（sqlite 状态）、ASR/TTS/VAD/Vision（内存任务表）、错误码清单。"""

from __future__ import annotations

import asyncio
import io
import re
import sqlite3
import tarfile
from pathlib import Path

import httpx
import pytest

from spacemit_ai_gateway.app.settings import (
    AsrConfig,
    DownloadConfig,
    LlmConfig,
    LlmStorageConfig,
    TtsConfig,
    VadConfig,
)
from spacemit_ai_gateway.common import downloader
from spacemit_ai_gateway.common.base_service import BaseModelService
from spacemit_ai_gateway.common.downloader import DownloadError, part_path
from spacemit_ai_gateway.common.enums import ModelStatus
from spacemit_ai_gateway.common.error_catalog import CATALOG
from spacemit_ai_gateway.common.errors import (
    DownloadNotSupported,
    ModelAlreadyDownloaded,
    ModelDownloading,
    ModelNotDownloaded,
    ModelUnknown,
)
from spacemit_ai_gateway.common.proxy_response import passthrough_response
from spacemit_ai_gateway.common.sessions import SessionStore

from .test_downloader import BASE, _payload


def _tar(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# LLM / Embed / Rerank / VLM 共用的 BaseModelService
# ---------------------------------------------------------------------------

class _Adapter:
    def __init__(self):
        self.running = True

    def is_running(self):
        return self.running

    async def warmup(self):
        pass


class _Backend:
    def __init__(self):
        self._remote_adapters = {}
        self.adapters = {}

    def is_model_running(self, model):
        return model in self.adapters and self.adapters[model].is_running()

    def get_adapter(self, model):
        return self.adapters.get(model)

    async def start_model(self, model, path, args):
        self.adapters[model] = _Adapter()

    async def stop_model(self, model):
        self.adapters.pop(model, None)

    async def shutdown(self):
        self.adapters.clear()


class _Svc(BaseModelService[_Backend, LlmConfig]):
    @property
    def adapter(self):
        return None

    def _get_backend_impl(self):
        return self._backends["fake"]


def _svc(tmp_path: Path, models: list[dict]) -> _Svc:
    cfg = LlmConfig(
        storage=LlmStorageConfig(
            base_dir=str(tmp_path / "state"),
            models_dir=str(tmp_path / "models"),
            db_path=str(tmp_path / "db.sqlite"),
        ),
        models=models,
    )
    return _Svc({"fake": _Backend()}, "fake", cfg, DownloadConfig(reserve_bytes=0))


async def _finish(svc: _Svc, model: str) -> None:
    task = svc._download_tasks.get(model)
    if task is not None:
        await task


async def test_failed_download_keeps_error_visible(server, tmp_path):
    url = server.add("llm/m.gguf", _payload())
    server.status["/model_zoo/llm/m.gguf"] = 404
    svc = _svc(tmp_path, [{"id": "m", "url": url}])
    await svc.initialize()
    try:
        await svc.download("m")
        await _finish(svc, "m")
        for _ in range(2):  # 以前第一次查询就被重置成 available
            st = await svc.get_download_progress("m")
            assert st["status"] == ModelStatus.ERROR
            assert st["error_code"] == "remote_http_error"
            assert st["retriable"] is False
        rows = {r["id"]: r for r in await svc.list_models()}
        assert rows["m"]["status"] == ModelStatus.ERROR
        assert rows["m"]["error_code"] == "remote_http_error"
    finally:
        await svc.shutdown()


async def test_download_reports_bytes_and_checksum(server, tmp_path):
    url = server.add("llm/ok.gguf", _payload())
    svc = _svc(tmp_path, [{"id": "ok", "url": url}])
    await svc.initialize()
    try:
        await svc.download("ok")
        await _finish(svc, "ok")
        st = await svc.get_download_progress("ok")
        assert st["status"] == ModelStatus.DOWNLOADED
        assert st["progress"] == 1.0
        assert st["downloaded_bytes"] == st["total_bytes"] == len(_payload())
        assert st["checksum"] == "verified"
        assert st["error_code"] is None
        with pytest.raises(ModelAlreadyDownloaded) as ei:
            await svc.download("ok")
        assert ei.value.code == "already_downloaded"
    finally:
        await svc.shutdown()


async def test_vlm_archive_extracted_atomically_and_removed(server, tmp_path):
    url = server.add("vlm/v.tar.gz", _tar({"model.gguf": b"g" * 100, "mmproj.gguf": b"p" * 10}))
    svc = _svc(tmp_path, [{"id": "v", "url": url, "local_dir": "v"}])
    await svc.initialize()
    try:
        await svc.download("v")
        await _finish(svc, "v")
        st = await svc.get_download_progress("v")
        assert st["status"] == ModelStatus.DOWNLOADED
        assert (tmp_path / "models" / "v" / "model.gguf").exists()
        assert not (tmp_path / "models" / "v.tar.gz").exists()
    finally:
        await svc.shutdown()


async def test_corrupt_vlm_archive_is_error_not_downloaded(server, tmp_path):
    url = server.add("vlm/bad.tar.gz", b"not-a-gzip" * 100)
    svc = _svc(tmp_path, [{"id": "bad", "url": url, "local_dir": "bad"}])
    await svc.initialize()
    try:
        await svc.download("bad")
        await _finish(svc, "bad")
        st = await svc.get_download_progress("bad")
        assert st["status"] == ModelStatus.ERROR  # 以前会显示 downloaded + 空目录
        assert st["error_code"] == "extract_failed"
        assert not (tmp_path / "models" / "bad").exists()
    finally:
        await svc.shutdown()


async def test_empty_leftover_vlm_dir_is_not_downloaded(server, tmp_path):
    (tmp_path / "models" / "old").mkdir(parents=True)  # 旧版本解压失败留下的空目录
    url = server.add("vlm/old.tar.gz", _tar({"m.gguf": b"g"}))
    svc = _svc(tmp_path, [{"id": "old", "url": url, "local_dir": "old"}])
    await svc.initialize()
    try:
        st = await svc.get_download_progress("old")
        assert st["status"] == ModelStatus.AVAILABLE
    finally:
        await svc.shutdown()


async def test_interrupted_registered_download_is_resumable_after_restart(server, tmp_path):
    url = server.add("llm/r.gguf", _payload())
    server.truncate_once.add("/model_zoo/llm/r.gguf")
    svc = _svc(tmp_path, [{"id": "preset", "url": server.add("llm/p.gguf", b"p")}])
    await svc.initialize()
    await svc.register("r", source_type="local_url", url=url)
    await svc.download("r")
    await _finish(svc, "r")
    assert (await svc.get_download_progress("r"))["error_code"] == "network_error"
    await svc._set_status("r", ModelStatus.DOWNLOADING)  # 模拟进程在下载中途退出
    await svc.shutdown()

    svc2 = _svc(tmp_path, [{"id": "preset", "url": server.add("llm/p.gguf", b"p")}])
    await svc2.initialize()
    try:
        st = await svc2.get_download_progress("r")
        assert st["status"] == ModelStatus.AVAILABLE  # 以前会一直卡在 downloading
        assert st["resumable"] is True
        await svc2.download("r")
        await _finish(svc2, "r")
        st = await svc2.get_download_progress("r")
        assert st["status"] == ModelStatus.DOWNLOADED
        assert server.ranges() == [f"bytes={len(_payload()) // 2}-"]
    finally:
        await svc2.shutdown()


async def test_user_cancel_discards_but_shutdown_keeps_partial(server, tmp_path, monkeypatch):
    url = server.add("llm/c.gguf", _payload())
    gate = asyncio.Event()
    original = downloader._write_chunk

    def slow(fh, hasher, chunk):
        original(fh, hasher, chunk)
        gate.set()
        import time
        time.sleep(0.05)

    monkeypatch.setattr(downloader, "_write_chunk", slow)
    monkeypatch.setattr(downloader, "_CHUNK_SIZE", 1024)
    svc = _svc(tmp_path, [{"id": "c", "url": url}])
    await svc.initialize()
    dest = tmp_path / "models" / "c.gguf"

    await svc.download("c")
    await asyncio.wait_for(gate.wait(), 5)
    await svc.cancel_download("c")
    st = await svc.get_download_progress("c")
    assert st["status"] == ModelStatus.AVAILABLE and st["resumable"] is False
    assert not part_path(dest).exists()

    gate.clear()
    await svc.download("c")
    await asyncio.wait_for(gate.wait(), 5)
    await svc.shutdown()  # 进程退出：保留 .part 供续传
    assert part_path(dest).exists()


async def test_cancel_waiting_model_keeps_other_models_partial(server, tmp_path, monkeypatch):
    # 两个模型指向同一个文件：取消等锁的 b，不能删掉 a 正在写的 .part
    url = server.add("llm/shared.gguf", _payload())
    gate = asyncio.Event()
    original = downloader._write_chunk

    def slow(fh, hasher, chunk):
        original(fh, hasher, chunk)
        gate.set()
        import time
        time.sleep(0.01)

    monkeypatch.setattr(downloader, "_write_chunk", slow)
    monkeypatch.setattr(downloader, "_CHUNK_SIZE", 4096)
    svc = _svc(tmp_path, [{"id": "a", "url": url}, {"id": "b", "url": url}])
    await svc.initialize()
    try:
        await svc.download("a")
        await asyncio.wait_for(gate.wait(), 5)
        await svc.download("b")
        await asyncio.sleep(0.05)  # b 在等文件锁
        await svc.cancel_download("b")
        assert part_path(tmp_path / "models" / "shared.gguf").exists()
        await _finish(svc, "a")
        st = await svc.get_download_progress("a")
        assert st["status"] == ModelStatus.DOWNLOADED and st["checksum"] == "verified", st
    finally:
        await svc.shutdown()


async def test_unexpected_download_failure_has_one_classification(server, tmp_path, monkeypatch):
    """下载流程外的异常（如解压前建临时目录时磁盘满）：下载状态与故障记录给出同一个错误码。"""
    import errno

    from spacemit_ai_gateway.common import base_service, error_log

    log = error_log.ErrorLog()
    monkeypatch.setattr(error_log, "_store", log)
    url = server.add("vlm/v.tar.gz", _tar({"model.gguf": b"g" * 100}))
    svc = _svc(tmp_path, [{"id": "v", "url": url, "local_dir": "v"}])
    svc.domain = "vlm"

    async def disk_full(*a, **kw):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(base_service, "run_extract", disk_full)
    await svc.initialize()
    try:
        await svc.download("v")
        await _finish(svc, "v")
        st = await svc.get_download_progress("v")
        rec = (await log.query())[0]
        assert st["error_code"] == rec["code"] == "disk_insufficient"
        assert st["retriable"] is rec["retriable"] is False
    finally:
        await svc.shutdown()


async def test_load_errors_carry_codes(server, tmp_path, monkeypatch):
    url = server.add("llm/l.gguf", _payload())
    svc = _svc(tmp_path, [{"id": "l", "url": url}])
    await svc.initialize()
    try:
        with pytest.raises(ModelNotDownloaded) as ei:
            await svc.load("l")
        assert ei.value.code == "model_not_downloaded" and ei.value.status_code == 400

        gate = asyncio.Event()
        release = asyncio.Event()
        original = downloader._stream_body

        async def blocked(*a, **kw):
            gate.set()
            await release.wait()
            return await original(*a, **kw)

        monkeypatch.setattr(downloader, "_stream_body", blocked)
        await svc.download("l")
        await asyncio.wait_for(gate.wait(), 5)
        with pytest.raises(ModelDownloading) as ei:  # 以前报的是"文件不存在"
            await svc.load("l")
        assert ei.value.code == "model_downloading" and ei.value.retriable
        release.set()
        await _finish(svc, "l")
    finally:
        await svc.shutdown()


async def test_crashed_backend_is_reaped_and_restarted(server, tmp_path):
    url = server.add("llm/x.gguf", _payload())
    svc = _svc(tmp_path, [{"id": "x", "url": url}])
    await svc.initialize()
    try:
        await svc.download("x")
        await _finish(svc, "x")
        await svc.load("x")
        backend = svc._get_backend_impl()
        old = backend.adapters["x"]
        old.running = False  # 推理进程退出
        await svc.load("x")
        assert backend.adapters["x"] is not old
    finally:
        await svc.shutdown()


class _CrashingStreamBackend(_Backend):
    """流式响应先给出一段正常输出，随后推理进程崩溃、连接断开。"""

    async def proxy_for(self, model_id, source_type, path, body, headers, stream=False):
        async def chunks():
            yield b'data: {"choices":[{"index":0,"delta":{"content":"Hi"}}]}\n\n'
            raise httpx.RemoteProtocolError("peer closed connection without sending complete message body")

        resp = httpx.Response(200, content=chunks(), headers={"content-type": "text/event-stream"})
        return httpx.AsyncClient(), resp


class _ChatSvc(_Svc):
    async def get_current_ctx_size(self):
        return None


async def test_stream_crash_midway_ends_with_classified_error_frame(server, tmp_path):
    import json

    from fastapi import FastAPI

    from spacemit_ai_gateway.domains.llm import api as llm_api
    from spacemit_ai_gateway.domains.vlm import api as vlm_api

    url = server.add("llm/s.gguf", _payload())
    svc = _svc(tmp_path, [{"id": "s", "url": url}])
    svc.__class__ = _ChatSvc
    svc._backends["fake"] = _CrashingStreamBackend()
    await svc.initialize()
    app = FastAPI()
    app.include_router(llm_api.router, prefix="/v1/llm")
    app.include_router(llm_api.compat_router)
    app.include_router(vlm_api.router, prefix="/v1/vlm")
    app.state.llm_service = app.state.vlm_service = svc
    try:
        await svc.download("s")
        await _finish(svc, "s")
        await svc.load("s")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            req = {"model": "s", "stream": True, "messages": [{"role": "user", "content": "hi"}]}

            for path in ("/v1/llm/chat/completions", "/v1/vlm/chat/completions"):
                r = await c.post(path, json=req)
                frames = [f for f in r.text.split("\n\n") if f.strip()]
                assert "Hi" in frames[0]  # 崩溃前的输出照常透传
                err = json.loads(frames[-1].removeprefix("data: "))["error"]
                assert err["code"] == "backend_crashed" and err["retriable"] is True, path
                assert "log_tail" in err["details"] and err["details"]["log_path"].endswith("s.log")

            r = await c.post("/v1/messages", json=req)
            event, data = r.text.strip().split("\n\n")[-1].split("\n")
            assert event == "event: error"
            assert json.loads(data.removeprefix("data: "))["error"]["code"] == "backend_crashed"

            r = await c.post("/v1/llm/api/chat", json=req)
            last = json.loads(r.text.strip().splitlines()[-1])
            assert last["code"] == "backend_crashed" and last["done"] is True
            assert '"done_reason": "stop"' not in r.text  # 不能再报正常结束

        remote = svc._transport_error("s", "remote", httpx.ReadError("reset"), midstream=True)
        assert remote.code == "upstream_error" and remote.retriable is True
    finally:
        await svc.shutdown()


async def test_old_database_is_migrated(tmp_path):
    db = tmp_path / "db.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE models (id TEXT PRIMARY KEY, source_type TEXT NOT NULL DEFAULT 'local_url',"
        " url TEXT, local_path TEXT, api_base_url TEXT, api_key TEXT,"
        " status TEXT NOT NULL DEFAULT 'available', is_preset INTEGER NOT NULL DEFAULT 0,"
        " download_progress REAL DEFAULT 0)"
    )
    conn.commit()
    conn.close()
    svc = _svc(tmp_path, [{"id": "a", "url": f"{BASE}/llm/a.gguf"}])
    await svc.initialize()
    try:
        st = await svc.get_download_progress("a")
        assert st["status"] == ModelStatus.AVAILABLE and st["error_code"] is None
    finally:
        await svc.shutdown()


# ---------------------------------------------------------------------------
# ASR / TTS / VAD：内存任务表 + 加载前下载
# ---------------------------------------------------------------------------

def _asr_service(tmp_path, url):
    from spacemit_ai_gateway.domains.asr.service import AsrService

    cfg = AsrConfig(
        model_dir=str(tmp_path / "asr" / "sensevoice"),
        models=[{"id": "sensevoice", "url": url, "archive_subdir": "sensevoice"}],
        backends=["sensevoice", "qwen3-asr"],
    )
    return AsrService({}, "sensevoice", SessionStore(ttl_seconds=60, namespace="asr-test"), config=cfg,
                      download_config=DownloadConfig(reserve_bytes=0))


SENSEVOICE_FILES = {
    "sensevoice/model_quant_optimized.onnx": b"m" * 64,
    "sensevoice/tokens.txt": b"t",
    "sensevoice/am.mvn": b"a",
    "sensevoice/sensevoice_decoder_model.onnx": b"d" * 64,
}


async def test_asr_download_api_flow(server, tmp_path):
    url = server.add("asr/sensevoice.tar.gz", _tar(SENSEVOICE_FILES))
    svc = _asr_service(tmp_path, url)
    assert svc.downloads.status("sensevoice")["status"] == "available"
    assert {m.id: m.downloaded for m in svc.get_models()}["sensevoice"] is False
    await svc.downloads.start("sensevoice")
    await svc.downloads.ensure("sensevoice")
    st = svc.downloads.status("sensevoice")
    assert st["status"] == "downloaded" and st["checksum"] == "verified"
    assert (tmp_path / "asr" / "sensevoice" / "tokens.txt").exists()
    models = {m.id: m.downloaded for m in svc.get_models()}
    assert models == {"sensevoice": True, "qwen3-asr": None}
    with pytest.raises(DownloadNotSupported):
        svc.downloads.status("qwen3-asr")
    with pytest.raises(ModelUnknown):
        svc.downloads.status("whisper")


async def test_asr_load_reports_download_error_instead_of_mock(server, tmp_path, monkeypatch):
    from spacemit_ai_gateway.domains.asr import service as asr_service_module

    url = server.add("asr/sensevoice.tar.gz", _tar(SENSEVOICE_FILES))
    server.status["/model_zoo/asr/sensevoice.tar.gz"] = 503
    monkeypatch.setattr(asr_service_module, "sdk_installed", lambda name: True)
    svc = _asr_service(tmp_path, url)
    with pytest.raises(DownloadError) as ei:
        await svc.load_model("sensevoice")
    assert ei.value.code == "remote_http_error" and ei.value.retriable is True
    assert svc._backends == {}
    assert svc.downloads.status("sensevoice")["error_code"] == "remote_http_error"


def test_tts_assets_cover_matcha_and_kokoro(monkeypatch, tmp_path):
    from spacemit_ai_gateway.domains.tts.adapters import kokoro, matcha

    cfg = TtsConfig(model_dir=str(tmp_path / "tts"))
    zh = matcha.model_assets("matcha_zh", cfg)
    vocoder, archive = zh.artifacts
    assert vocoder.path == tmp_path / "tts" / "vocos-22khz-univ.q.onnx"
    assert archive.archive and "vocos-22khz-univ.q.onnx" not in archive.required
    assert "matcha-icefall-zh-baker/lexicon.txt" in archive.required

    # model_zoo 源码中的 Kokoro preset（archive 上的 tar.gz）
    monkeypatch.setattr(kokoro, "_preset_location",
                        lambda: ("~/.cache/models/tts/kokoro-tts", "kokoro-v1.0-en"))
    ko = kokoro.model_assets(cfg)
    (art,) = ko.artifacts
    assert art.url.endswith("/tts/kokoro/kokoro-v1.0-en.tar.gz")
    assert art.path == Path("~/.cache/models/tts/kokoro-tts").expanduser()
    assert "kokoro-v1.0-en/voices/af_heart.bin" in art.required

    # 已发布的 spacemit-tts 1.0.4 preset 是 kokoro-v1.0.q（从 HuggingFace 下载），交给 SDK 自己下载
    monkeypatch.setattr(kokoro, "_preset_location",
                        lambda: ("~/.cache/models/tts/kokoro-tts", "kokoro-v1.0.q"))
    assert kokoro.model_assets(cfg) is None


def test_vad_assets_follow_sdk_layout(tmp_path):
    from spacemit_ai_gateway.domains.vad.adapters import silero

    default = silero.model_assets(VadConfig())
    assert default.artifacts[0].path == Path("~/.cache/models/vad/silero/silero_vad.onnx").expanduser()
    custom = silero.model_assets(VadConfig(model_dir=str(tmp_path / "vad")))
    assert custom.artifacts[0].path == tmp_path / "vad" / "silero_vad.onnx"


async def test_matcha_failure_with_sdk_installed_raises_instead_of_mock(monkeypatch, tmp_path):
    from spacemit_ai_gateway.common.errors import ModelLoadFailed
    from spacemit_ai_gateway.domains.tts.adapters import matcha

    stops = []

    class FailingWorker:
        def __init__(self, config):
            pass

        async def start(self):
            raise RuntimeError("engine boom")

        async def stop(self, *, kill=False):
            stops.append(kill)

    monkeypatch.setattr(matcha, "_ensure_model_assets", lambda *a, **kw: None)
    monkeypatch.setattr(matcha, "NativeTtsWorker", FailingWorker)
    monkeypatch.setattr(matcha, "sdk_installed", lambda name: True)
    backend = matcha.MatchaBackend(TtsConfig(backend="matcha_zh_en", model_dir=str(tmp_path)))
    with pytest.raises(ModelLoadFailed) as ei:
        await backend.warmup()
    assert ei.value.code == "load_failed"
    assert backend._mock is True and backend._worker is None and stops == [True]


# ---------------------------------------------------------------------------
# 接口层
# ---------------------------------------------------------------------------

async def test_routes_expose_download_and_error_catalog(client):
    r = await client.get("/v1/errors")
    assert r.status_code == 200
    codes = {e["code"] for e in r.json()["errors"]}
    assert {"disk_insufficient", "checksum_mismatch", "load_oom", "backend_crashed"} <= codes

    r = await client.get("/v1/asr/models/whisper/download")
    assert r.status_code == 404 and r.json()["error"] == "model_unknown"

    paths = (await client.get("/openapi.json")).json()["paths"]
    for domain in ("asr", "tts", "vad", "llm", "embed", "rerank"):
        assert f"/v1/{domain}/models/{{model}}/download" in paths
    assert "/v1/vision/models/{model_id}/download" in paths


def test_every_raised_code_is_in_catalog():
    src = Path(__file__).resolve().parents[2] / "src" / "spacemit_ai_gateway"
    text = "\n".join(
        (src / rel).read_text(encoding="utf-8")
        for rel in ("common/downloader.py", "common/llama_process.py",
                    "common/base_service.py", "common/proxy_response.py")
    )
    errors = (src / "common/errors.py").read_text(encoding="utf-8")
    text += errors[errors.index("# 模型下载 / 加载"):]  # 本次新增的错误类
    raised = set(re.findall(r'DownloadError\(\s*"([a-z_]+)"', text))
    raised |= set(re.findall(r'code(?:\s*=\s*|, reason = )"([a-z_]+)"', text))
    raised -= {"domain_error", "download_failed"}
    catalog = {e["code"] for e in CATALOG}
    assert raised - catalog == set()


def test_non_json_backend_error_is_classified():
    from spacemit_ai_gateway.common.errors import DomainError

    resp = httpx.Response(404, headers={"content-type": "text/html"})
    with pytest.raises(DomainError) as ei:
        passthrough_response(b"<html>not found</html>", resp)
    assert ei.value.code == "upstream_error" and ei.value.status_code == 502

    ok = passthrough_response(b'{"error": {"type": "exceed_context_size_error"}}', httpx.Response(400))
    assert ok.status_code == 400  # 引擎自己的 JSON 错误原样透传


def test_vlm_model_dir_descends_into_archive_top_level_dir(tmp_path):
    from spacemit_ai_gateway.domains.vlm.adapters.llama import resolve_model_dir

    # archive 上的 VLM tar.gz 自带顶层目录：fastvlm-mm-0.5b-q4_1/config.json
    outer = tmp_path / "fastvlm-mm-0.5b-q4_1"
    inner = outer / "fastvlm-mm-0.5b-q4_1"
    inner.mkdir(parents=True)
    (inner / "config.json").write_text("{}")
    assert resolve_model_dir(outer) == inner

    # 手动解压到 models/vlm/ 的扁平布局保持不变
    (outer / "config.json").write_text("{}")
    assert resolve_model_dir(outer) == outer
