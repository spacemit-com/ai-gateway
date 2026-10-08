"""common/downloader.py：续传、校验、磁盘预检、重定向、解压、下载任务表。"""

from __future__ import annotations

import asyncio
import hashlib
import io
import ssl
import tarfile
from collections import namedtuple
from pathlib import Path

import httpx
import pytest

from spacemit_ai_gateway.app.settings import DownloadConfig
from spacemit_ai_gateway.common import downloader
from spacemit_ai_gateway.common.downloader import (
    Artifact,
    DownloadError,
    DownloadTracker,
    ModelAssets,
    extract_archive,
    fetch_file,
    part_path,
)

BASE = "https://archive.example.com/model_zoo"


class FakeServer:
    """最小文件服务器：HEAD / GET / Range / <url>.md5 / 重定向。"""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.md5: dict[str, str] = {}
        self.redirects: dict[str, str] = {}
        self.truncate_once: set[str] = set()
        self.ignore_range = False
        self.status: dict[str, int] = {}
        self.etag_salt = ""
        self.requests: list[tuple[str, str, dict]] = []

    def add(self, name: str, data: bytes, *, md5: bool = True) -> str:
        path = f"/model_zoo/{name}"
        self.files[path] = data
        if md5:
            self.md5[path] = hashlib.md5(data).hexdigest()
        return f"{BASE}/{name}"

    def handler(self, request: httpx.Request) -> httpx.Response:
        url, path = str(request.url), request.url.path
        self.requests.append((request.method, url, dict(request.headers)))
        if url in self.redirects:
            return httpx.Response(302, headers={"location": self.redirects[url]})
        if path in self.status:
            return httpx.Response(self.status[path])
        if path.endswith(".md5"):
            base = path[: -len(".md5")]
            if base in self.md5:
                return httpx.Response(200, text=f"{self.md5[base]}  ./{base.rsplit('/', 1)[-1]}\n")
            return httpx.Response(404, text="<html>404</html>")
        data = self.files.get(path)
        if data is None:
            return httpx.Response(404)
        etag = f'"{len(data):x}{self.etag_salt}"'
        headers = {"content-length": str(len(data)), "etag": etag, "accept-ranges": "bytes"}
        if request.method == "HEAD":
            return httpx.Response(200, headers=headers)
        rng = request.headers.get("range")
        if rng and not self.ignore_range:
            if request.headers.get("if-range") not in (None, etag):
                return httpx.Response(200, headers=headers, content=data)
            start = int(rng.split("=")[1].split("-")[0])
            if start >= len(data):
                return httpx.Response(416)
            body = data[start:]
            return httpx.Response(
                206,
                headers={
                    "content-length": str(len(body)),
                    "content-range": f"bytes {start}-{len(data) - 1}/{len(data)}",
                    "etag": etag,
                },
                content=body,
            )
        if path in self.truncate_once:
            self.truncate_once.discard(path)
            return httpx.Response(200, headers=headers, content=data[: len(data) // 2])
        return httpx.Response(200, headers=headers, content=data)

    def ranges(self) -> list[str]:
        return [h.get("range") for m, _u, h in self.requests if m == "GET" and h.get("range")]


@pytest.fixture
def server(monkeypatch):
    srv = FakeServer()

    def make_client(config):
        return httpx.AsyncClient(transport=httpx.MockTransport(srv.handler), follow_redirects=False)

    monkeypatch.setattr(downloader, "make_client", make_client)
    return srv


@pytest.fixture
def cfg():
    return DownloadConfig(reserve_bytes=0)


def _payload(n: int = 300_000) -> bytes:
    return bytes(i % 251 for i in range(n))


# ---- fetch_file ----

async def test_fetch_verifies_md5_and_renames(server, cfg, tmp_path):
    url = server.add("llm/a.gguf", _payload())
    result = await fetch_file(url, tmp_path / "a.gguf", config=cfg)
    assert result.checksum == "verified"
    assert (tmp_path / "a.gguf").read_bytes() == _payload()
    assert not part_path(tmp_path / "a.gguf").exists()


async def test_fetch_without_md5_checks_size_only(server, cfg, tmp_path):
    url = server.add("llm/b.gguf", _payload(), md5=False)
    result = await fetch_file(url, tmp_path / "b.gguf", config=cfg)
    assert result.checksum == "unavailable"
    assert result.size == len(_payload())


async def test_fetch_md5_mismatch_discards_file(server, cfg, tmp_path):
    url = server.add("llm/c.gguf", _payload())
    server.md5["/model_zoo/llm/c.gguf"] = "0" * 32
    with pytest.raises(DownloadError) as ei:
        await fetch_file(url, tmp_path / "c.gguf", config=cfg)
    assert ei.value.code == "checksum_mismatch"
    assert ei.value.retriable is True
    assert not (tmp_path / "c.gguf").exists()
    assert not part_path(tmp_path / "c.gguf").exists()


async def test_truncated_download_resumes_with_range(server, cfg, tmp_path):
    url = server.add("vlm/d.tar.gz", _payload())
    server.truncate_once.add("/model_zoo/vlm/d.tar.gz")
    dest = tmp_path / "d.tar.gz"
    with pytest.raises(DownloadError) as ei:
        await fetch_file(url, dest, config=cfg)
    assert ei.value.code == "network_error" and ei.value.retriable
    assert part_path(dest).stat().st_size == len(_payload()) // 2

    result = await fetch_file(url, dest, config=cfg)
    assert result.resumed_from == len(_payload()) // 2
    assert server.ranges() == [f"bytes={len(_payload()) // 2}-"]
    assert result.checksum == "verified"
    assert dest.read_bytes() == _payload()


async def test_resume_restarts_when_remote_file_changed(server, cfg, tmp_path):
    url = server.add("llm/e.gguf", _payload())
    server.truncate_once.add("/model_zoo/llm/e.gguf")
    dest = tmp_path / "e.gguf"
    with pytest.raises(DownloadError):
        await fetch_file(url, dest, config=cfg)
    server.etag_salt = "-v2"  # 服务器上的文件被替换
    result = await fetch_file(url, dest, config=cfg)
    assert result.resumed_from == 0
    assert server.ranges() == []
    assert dest.read_bytes() == _payload()


async def test_server_ignoring_range_restarts_cleanly(server, cfg, tmp_path):
    url = server.add("llm/f.gguf", _payload())
    server.truncate_once.add("/model_zoo/llm/f.gguf")
    dest = tmp_path / "f.gguf"
    with pytest.raises(DownloadError):
        await fetch_file(url, dest, config=cfg)
    server.ignore_range = True
    result = await fetch_file(url, dest, config=cfg)
    assert result.checksum == "verified"
    assert dest.read_bytes() == _payload()


async def test_disk_precheck_rejects_before_writing(server, tmp_path, monkeypatch):
    url = server.add("llm/g.gguf", _payload())
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(downloader.shutil, "disk_usage", lambda p: Usage(10**9, 0, 100_000))
    with pytest.raises(DownloadError) as ei:
        await fetch_file(url, tmp_path / "g.gguf", config=DownloadConfig(reserve_bytes=0))
    assert ei.value.code == "disk_insufficient"
    assert ei.value.details["free_bytes"] == 100_000
    assert not part_path(tmp_path / "g.gguf").exists()
    assert [m for m, *_ in server.requests if m == "GET" and not _[0].endswith(".md5")] == []


async def test_disk_precheck_counts_reserve_and_extract_ratio(server, tmp_path, monkeypatch):
    url = server.add("vlm/h.tar.gz", _payload(1000))
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(downloader.shutil, "disk_usage", lambda p: Usage(10**9, 0, 2500))
    with pytest.raises(DownloadError) as ei:
        await fetch_file(url, tmp_path / "h.tar.gz", config=DownloadConfig(reserve_bytes=600), extract_ratio=1.0)
    assert ei.value.details["required_bytes"] == 2000


async def test_https_downgrade_redirect_blocked(server, cfg, tmp_path):
    url = server.add("llm/i.gguf", _payload())
    server.redirects[url] = "http://evil.example.com/i.gguf"
    with pytest.raises(DownloadError) as ei:
        await fetch_file(url, tmp_path / "i.gguf", config=cfg)
    assert ei.value.code == "redirect_blocked"


async def test_https_redirect_to_other_host_allowed(server, cfg, tmp_path):
    server.add("llm/j.gguf", _payload())
    src = "https://mirror.example.com/j.gguf"
    server.redirects[src] = f"{BASE}/llm/j.gguf"
    server.redirects[src + ".md5"] = f"{BASE}/llm/j.gguf.md5"
    result = await fetch_file(src, tmp_path / "j.gguf", config=cfg)
    assert result.checksum == "verified"


@pytest.mark.parametrize("status,retriable", [(404, False), (503, True)])
async def test_remote_http_error_retriable_by_status(server, cfg, tmp_path, status, retriable):
    url = server.add("llm/k.gguf", _payload())
    server.status["/model_zoo/llm/k.gguf"] = status
    with pytest.raises(DownloadError) as ei:
        await fetch_file(url, tmp_path / "k.gguf", config=cfg)
    assert ei.value.code == "remote_http_error"
    assert ei.value.retriable is retriable


async def test_tls_failure_classified(monkeypatch, cfg, tmp_path):
    def handler(request):
        try:
            raise ssl.SSLCertVerificationError("certificate has expired")
        except ssl.SSLError as exc:
            raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate has expired") from exc

    monkeypatch.setattr(
        downloader, "make_client",
        lambda c: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(DownloadError) as ei:
        await fetch_file(f"{BASE}/x.gguf", tmp_path / "x.gguf", config=cfg)
    assert ei.value.code == "tls_error"


async def test_connect_failure_is_network_error(monkeypatch, cfg, tmp_path):
    def handler(request):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(
        downloader, "make_client",
        lambda c: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(DownloadError) as ei:
        await fetch_file(f"{BASE}/x.gguf", tmp_path / "x.gguf", config=cfg)
    assert ei.value.code == "network_error" and ei.value.retriable


# ---- extract_archive ----

def _tar_bytes(files: dict[str, bytes], links: dict[str, str] | None = None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        for name, target in (links or {}).items():
            info = tarfile.TarInfo(name)
            info.type = tarfile.SYMTYPE
            info.linkname = target
            tf.addfile(info)
    return buf.getvalue()


def test_extract_replace_is_atomic(tmp_path):
    archive = tmp_path / "m.tar.gz"
    archive.write_bytes(_tar_bytes({"model.gguf": b"x" * 10, "config.json": b"{}"}))
    target = tmp_path / "models" / "m"
    target.mkdir(parents=True)
    (target / "stale.txt").write_text("old")
    extract_archive(archive, target, replace=True)
    assert sorted(p.name for p in target.iterdir()) == ["config.json", "model.gguf"]
    assert [p.name for p in target.parent.iterdir()] == ["m"]


def test_extract_corrupt_archive_leaves_no_target(tmp_path):
    archive = tmp_path / "bad.tar.gz"
    archive.write_bytes(b"not-a-gzip" * 100)
    target = tmp_path / "models" / "bad"
    with pytest.raises(DownloadError) as ei:
        extract_archive(archive, target, replace=True)
    assert ei.value.code == "extract_failed"
    assert not target.exists()
    assert list((tmp_path / "models").iterdir()) == []


def test_extract_rejects_escaping_symlink(tmp_path):
    archive = tmp_path / "evil.tar.gz"
    archive.write_bytes(_tar_bytes({}, links={"escape": "/etc"}))
    target = tmp_path / "models" / "evil"
    with pytest.raises(DownloadError) as ei:
        extract_archive(archive, target, replace=True)
    assert ei.value.code == "extract_failed"
    assert not target.exists()


def test_extract_merge_flattens_subdir(tmp_path):
    archive = tmp_path / "s.tar.gz"
    archive.write_bytes(_tar_bytes({"sensevoice/model.onnx": b"m", "sensevoice/tokens.txt": b"t"}))
    target = tmp_path / "asr" / "sensevoice"
    target.mkdir(parents=True)
    (target / "keep.txt").write_text("k")
    extract_archive(archive, target, subdir="sensevoice")
    assert sorted(p.name for p in target.iterdir()) == ["keep.txt", "model.onnx", "tokens.txt"]


# ---- DownloadTracker ----

def _tracker(server, tmp_path, cfg):
    file_url = server.add("vad/silero_vad.onnx", b"onnx" * 1000)
    tar_url = server.add("asr/pack.tar.gz", _tar_bytes({"pack/model.onnx": b"m" * 100, "pack/tokens.txt": b"t"}))
    models = {
        "silero": ModelAssets("silero", [Artifact(file_url, tmp_path / "vad" / "silero_vad.onnx")]),
        "pack": ModelAssets("pack", [Artifact(
            tar_url, tmp_path / "asr" / "pack", archive=True, archive_subdir="pack",
            required=("model.onnx", "tokens.txt"),
        )]),
    }
    return DownloadTracker("test", models.get, lambda: [*models, "remote-only"], cfg)


async def test_tracker_download_and_status(server, cfg, tmp_path):
    tracker = _tracker(server, tmp_path, cfg)
    assert tracker.status("pack")["status"] == "available"
    await tracker.start("pack")
    await tracker.ensure("pack")
    st = tracker.status("pack")
    assert st["status"] == "downloaded" and st["progress"] == 1.0
    assert st["checksum"] == "verified"
    assert (tmp_path / "asr" / "pack" / "model.onnx").exists()
    assert not (tmp_path / "asr" / "pack.tar.gz").exists()  # 解压后删除压缩包


async def test_tracker_error_stays_visible(server, cfg, tmp_path):
    tracker = _tracker(server, tmp_path, cfg)
    server.status["/model_zoo/vad/silero_vad.onnx"] = 404
    with pytest.raises(DownloadError) as ei:
        await tracker.ensure("silero")
    assert ei.value.code == "remote_http_error"
    st = tracker.status("silero")
    assert st["status"] == "error"
    assert st["error_code"] == "remote_http_error"
    assert st["retriable"] is False


async def test_tracker_cancel_discards_partial(server, cfg, tmp_path, monkeypatch):
    tracker = _tracker(server, tmp_path, cfg)
    gate = asyncio.Event()
    original = downloader._write_chunk

    def slow_write(fh, hasher, chunk):
        original(fh, hasher, chunk)
        gate.set()
        import time
        time.sleep(0.2)

    monkeypatch.setattr(downloader, "_write_chunk", slow_write)
    monkeypatch.setattr(downloader, "_CHUNK_SIZE", 64)
    await tracker.start("silero")
    await asyncio.wait_for(gate.wait(), 5)
    st = await tracker.cancel("silero")
    assert st["status"] == "available"
    assert not part_path(tmp_path / "vad" / "silero_vad.onnx").exists()


async def test_cancel_waiting_model_keeps_other_models_partial(server, cfg, tmp_path, monkeypatch):
    # matcha_zh / matcha_en 共用声码器：取消等锁的 b，不能删掉 a 正在写的 .part
    url = server.add("tts/vocoder.onnx", _payload())
    shared = Artifact(url, tmp_path / "tts" / "vocoder.onnx")
    tracker = DownloadTracker("tts", lambda m: ModelAssets(m, [shared]), lambda: ["a", "b"], cfg)
    gate = asyncio.Event()
    original = downloader._write_chunk

    def slow_write(fh, hasher, chunk):
        original(fh, hasher, chunk)
        gate.set()
        import time
        time.sleep(0.01)

    monkeypatch.setattr(downloader, "_write_chunk", slow_write)
    monkeypatch.setattr(downloader, "_CHUNK_SIZE", 4096)
    await tracker.start("a")
    await asyncio.wait_for(gate.wait(), 5)
    await tracker.start("b")
    await asyncio.sleep(0.05)  # b 在等文件锁
    await tracker.cancel("b")
    assert part_path(shared.path).exists()

    while tracker.status("a")["status"] == "downloading":
        await asyncio.sleep(0.02)
    st = tracker.status("a")
    assert st["status"] == "downloaded" and st["checksum"] == "verified", st
    assert shared.path.read_bytes() == _payload()


async def test_tracker_rejects_unknown_and_unsupported(server, cfg, tmp_path):
    from spacemit_ai_gateway.common.errors import DownloadNotSupported, ModelUnknown

    tracker = _tracker(server, tmp_path, cfg)
    with pytest.raises(DownloadNotSupported):
        tracker.status("remote-only")
    with pytest.raises(ModelUnknown):
        await tracker.start("nope")
