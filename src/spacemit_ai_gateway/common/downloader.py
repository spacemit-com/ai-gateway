"""模型下载核心：所有域共用。

一次下载的流程：
1. HEAD 探测大小 / ETag（跟随重定向，但拒绝 https→http 降级）
2. 读取 <url>.md5（没有则只校验大小）
3. 磁盘预检：剩余空间 >= 待下载字节 + 解压估算 + 预留
4. 写入 <dest>.gwpart；已有 .gwpart 且 URL/ETag/大小未变时用 Range 续传
5. 校验大小与 md5，通过后原子 rename 为 <dest>

压缩包解压先解到临时目录，成功后再替换/合并到目标位置，失败不留半成品。
所有失败都抛 DownloadError，code 取自 common/error_catalog.py。
"""

from __future__ import annotations

import asyncio
import errno
import hashlib
import json
import logging
import os
import shutil
import ssl
import tarfile
import time
import uuid
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Optional

import httpx

from ..app.settings import DownloadConfig
from .error_catalog import is_retriable
from .error_log import mark_fault, record_fault
from .errors import (
    DomainError,
    DownloadInProgress,
    DownloadNotSupported,
    ModelAlreadyDownloaded,
    ModelUnknown,
    NoActiveDownload,
)

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024
_PROGRESS_INTERVAL_S = 0.5
_USER_AGENT = "spacemit-ai-gateway/0.1"

ProgressCallback = Callable[[int, Optional[int]], Awaitable[None]]

# 下载失败对应的 HTTP 状态码（仅在错误作为接口响应返回时使用）
_STATUS_BY_CODE = {
    "disk_insufficient": 507,
    "permission_denied": 500,
    "io_error": 500,
    "extract_failed": 500,
}


class DownloadError(DomainError):
    """下载失败；code 见 error_catalog 的 download 阶段。"""

    code = "download_failed"
    status_code = 502

    def __init__(self, code: str, message: str, *, details: dict | None = None):
        super().__init__(
            message,
            retriable=is_retriable(code),
            details=details,
            code=code,
            status_code=_STATUS_BY_CODE.get(code, 502),
        )


@dataclass
class FetchResult:
    path: Path
    size: int
    checksum: str  # "verified" | "unavailable"
    resumed_from: int = 0


@dataclass
class _Probe:
    url: str
    total: Optional[int]
    etag: Optional[str]


def make_client(config: DownloadConfig) -> httpx.AsyncClient:
    """测试里会 monkeypatch 这里注入 MockTransport。"""
    timeout = httpx.Timeout(
        connect=config.connect_timeout_s,
        read=config.read_timeout_s,
        write=config.read_timeout_s,
        pool=config.connect_timeout_s,
    )
    return httpx.AsyncClient(
        verify=config.tls_verify,
        follow_redirects=False,
        timeout=timeout,
        headers={"User-Agent": _USER_AGENT, "Accept-Encoding": "identity"},
    )


# ---------------------------------------------------------------------------
# 单文件下载
# ---------------------------------------------------------------------------

_path_locks: dict[str, asyncio.Lock] = {}


def _path_lock(path: Path) -> asyncio.Lock:
    # 多个模型共用同一个文件（如 matcha 声码器、yolov8n）时串行化，避免同写一个 .gwpart
    key = str(path)
    lock = _path_locks.get(key)
    if lock is None:
        lock = _path_locks[key] = asyncio.Lock()
    return lock


def part_path(dest: Path) -> Path:
    # 不用 .part：spacemit-ailab 用 wget 往 <dest>.part 下载同一批模型，同名会互相删改
    return dest.with_name(dest.name + ".gwpart")


def _meta_path(dest: Path) -> Path:
    return dest.with_name(dest.name + ".part.json")


def discard_partial(dest: Path) -> None:
    for p in (part_path(dest), _meta_path(dest)):
        p.unlink(missing_ok=True)


def partial_size(dest: Path) -> int:
    try:
        return part_path(dest).stat().st_size
    except OSError:
        return 0


async def fetch_file(
    url: str,
    dest: Path,
    *,
    config: DownloadConfig,
    on_progress: Optional[ProgressCallback] = None,
    extract_ratio: float = 0.0,
    discard_on_cancel: Optional[Callable[[], bool]] = None,
) -> FetchResult:
    """下载 url 到 dest；支持续传、md5/大小校验、磁盘预检。失败抛 DownloadError。

    取消（CancelledError）时默认保留 .gwpart 以便续传；discard_on_cancel() 为真（用户取消）时删除。
    删除在文件锁内进行：等锁时被取消的任务不会删掉别的任务正在写的 .gwpart（共用文件，如 matcha 声码器）。
    """
    dest = Path(dest)
    async with _path_lock(dest):
        try:
            return await _fetch_locked(url, dest, config, on_progress, extract_ratio)
        except asyncio.CancelledError:
            if discard_on_cancel is not None and discard_on_cancel():
                discard_partial(dest)
            raise
        except DownloadError as exc:
            _to_download_error(exc, url)
            raise
        except Exception as exc:
            raise _to_download_error(exc, url) from exc


async def _fetch_locked(
    url: str,
    dest: Path,
    config: DownloadConfig,
    on_progress: Optional[ProgressCallback],
    extract_ratio: float,
) -> FetchResult:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = part_path(dest)
    meta_file = _meta_path(dest)

    async with make_client(config) as client:
        probe = await _probe(client, url, config)
        expected_md5 = await _fetch_md5(client, url, config) if config.verify_md5 else None

        offset = _usable_partial(part, meta_file, url, probe)
        need = (probe.total - offset) if probe.total is not None else 0
        need += int((probe.total or 0) * extract_ratio)
        _check_disk(dest.parent, need, config.reserve_bytes)

        meta_file.write_text(
            json.dumps({"url": url, "etag": probe.etag, "total": probe.total}),
            encoding="utf-8",
        )

        hasher = _Digest()
        if offset:
            await asyncio.to_thread(_hash_file, part, hasher)
            logger.info("resuming %s from %d bytes", dest.name, offset)

        offset = await _stream_body(
            client, probe, part, offset, hasher, config, on_progress
        )

    size = part.stat().st_size
    if probe.total is not None and size != probe.total:
        if size > probe.total:
            discard_partial(dest)
            raise DownloadError(
                "size_mismatch",
                f"downloaded {size} bytes, expected {probe.total}: {url}",
                details={"expected_bytes": probe.total, "actual_bytes": size},
            )
        # 连接提前断开：保留 .gwpart，下次续传
        raise DownloadError(
            "network_error",
            f"connection closed early at {size}/{probe.total} bytes: {url}",
            details={"downloaded_bytes": size, "total_bytes": probe.total},
        )
    if size == 0:
        discard_partial(dest)
        raise DownloadError("size_mismatch", f"downloaded empty file: {url}")

    checksum = "unavailable"
    if expected_md5:
        actual = hasher.h.hexdigest()
        if actual != expected_md5:
            discard_partial(dest)
            raise DownloadError(
                "checksum_mismatch",
                f"md5 mismatch for {dest.name}: expected {expected_md5}, got {actual}",
                details={"expected_md5": expected_md5, "actual_md5": actual},
            )
        checksum = "verified"

    os.replace(part, dest)
    meta_file.unlink(missing_ok=True)
    logger.info("downloaded %s (%d bytes, checksum %s)", dest, size, checksum)
    return FetchResult(path=dest, size=size, checksum=checksum, resumed_from=offset)


async def _stream_body(
    client: httpx.AsyncClient,
    probe: _Probe,
    part: Path,
    offset: int,
    hasher: "_Digest",
    config: DownloadConfig,
    on_progress: Optional[ProgressCallback],
) -> int:
    """GET 正文写入 .gwpart，返回最初生效的续传偏移。"""
    if probe.total is not None and offset == probe.total:
        return offset  # .gwpart 已完整，只差校验

    headers = {}
    if offset:
        headers["Range"] = f"bytes={offset}-"
        if probe.etag and not probe.etag.startswith("W/"):
            headers["If-Range"] = probe.etag

    resp = await _send(client, "GET", probe.url, config, headers=headers, stream=True)
    try:
        if resp.status_code == 416 and offset:
            # 服务端认为范围无效：放弃续传，从头下载
            await resp.aclose()
            part.unlink(missing_ok=True)
            hasher.reset()
            return await _stream_body(client, probe, part, 0, hasher, config, on_progress)
        _raise_for_status(resp, probe.url)

        if offset and resp.status_code == 206 and not _range_starts_at(resp, offset):
            raise DownloadError("network_error", f"unexpected Content-Range for {probe.url}")
        if offset and resp.status_code != 206:
            # 服务端忽略 Range 或文件已变化：返回的是完整内容，从头写
            logger.info("server ignored Range for %s, restarting download", probe.url)
            offset = 0
            hasher.reset()

        downloaded = offset
        last_report = 0.0
        mode = "ab" if offset else "wb"
        with open(part, mode) as fh:
            async for chunk in resp.aiter_bytes(_CHUNK_SIZE):
                await asyncio.to_thread(_write_chunk, fh, hasher, chunk)
                downloaded += len(chunk)
                now = time.monotonic()
                if on_progress and now - last_report >= _PROGRESS_INTERVAL_S:
                    last_report = now
                    await on_progress(downloaded, probe.total)
            await asyncio.to_thread(_flush, fh)
        if on_progress:
            await on_progress(downloaded, probe.total)
        return offset
    finally:
        await resp.aclose()


class _Digest:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.h = hashlib.md5(usedforsecurity=False)


def _write_chunk(fh, hasher: _Digest, chunk: bytes) -> None:
    fh.write(chunk)
    hasher.h.update(chunk)


def _flush(fh) -> None:
    fh.flush()
    os.fsync(fh.fileno())


def _hash_file(path: Path, hasher: _Digest) -> None:
    with open(path, "rb") as fh:
        while chunk := fh.read(_CHUNK_SIZE):
            hasher.h.update(chunk)


def _range_starts_at(resp: httpx.Response, offset: int) -> bool:
    content_range = resp.headers.get("content-range", "")
    # 形如 "bytes 100-199/200"
    try:
        start = int(content_range.split()[1].split("-")[0])
    except (IndexError, ValueError):
        return False
    return start == offset


def _usable_partial(part: Path, meta_file: Path, url: str, probe: _Probe) -> int:
    """已有 .gwpart 能否续传：URL、ETag、总大小都没变才续。"""
    if not part.exists():
        meta_file.unlink(missing_ok=True)
        return 0
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = None
    size = part.stat().st_size
    if (
        not meta
        or meta.get("url") != url
        or meta.get("etag") != probe.etag
        or meta.get("total") != probe.total
        or (probe.total is not None and size > probe.total)
    ):
        part.unlink(missing_ok=True)
        meta_file.unlink(missing_ok=True)
        return 0
    return size


def _check_disk(directory: Path, need: int, reserve: int) -> None:
    free = shutil.disk_usage(directory).free
    if free < need + reserve:
        raise DownloadError(
            "disk_insufficient",
            f"not enough disk space in {directory}: need {_fmt(need)} + reserve "
            f"{_fmt(reserve)}, free {_fmt(free)}",
            details={"required_bytes": need, "reserve_bytes": reserve, "free_bytes": free},
        )


def _fmt(n: int) -> str:
    value = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}GiB"


# ---------------------------------------------------------------------------
# HTTP：重定向策略、探测、md5
# ---------------------------------------------------------------------------

async def _send(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    config: DownloadConfig,
    *,
    headers: dict | None = None,
    stream: bool = False,
) -> httpx.Response:
    """手动跟随重定向：允许换域名（如 CDN），但不允许从 https 降级到 http。"""
    current = httpx.URL(url)
    for _ in range(config.max_redirects + 1):
        request = client.build_request(method, current, headers=headers)
        resp = await client.send(request, stream=stream)
        if not resp.is_redirect:
            return resp
        location = resp.headers.get("location", "")
        await resp.aclose()
        target = current.join(location)
        if current.scheme == "https" and target.scheme != "https":
            raise DownloadError(
                "redirect_blocked",
                f"refused redirect from {current} to {target} (https downgrade)",
                details={"from": str(current), "to": str(target)},
            )
        current = target
    raise DownloadError("redirect_blocked", f"too many redirects for {url}")


async def _probe(client: httpx.AsyncClient, url: str, config: DownloadConfig) -> _Probe:
    resp = await _send(client, "HEAD", url, config)
    if resp.status_code in (405, 501):
        return _Probe(url=url, total=None, etag=None)  # 服务端不支持 HEAD
    _raise_for_status(resp, url)
    total = resp.headers.get("content-length")
    return _Probe(
        url=str(resp.url),
        total=int(total) if total and total.isdigit() else None,
        etag=resp.headers.get("etag"),
    )


async def _fetch_md5(client: httpx.AsyncClient, url: str, config: DownloadConfig) -> Optional[str]:
    resp = await _send(client, "GET", url + ".md5", config)
    if resp.status_code in (403, 404):
        return None
    _raise_for_status(resp, url + ".md5")
    # md5sum 格式："<hex>  ./name" 或 "<hex>  name"
    token = resp.text.strip().split()[0].lower() if resp.text.strip() else ""
    if len(token) == 32 and all(c in "0123456789abcdef" for c in token):
        return token
    logger.warning("ignore malformed md5 file for %s: %r", url, resp.text[:80])
    return None


def _raise_for_status(resp: httpx.Response, url: str) -> None:
    if resp.status_code < 400:
        return
    code = resp.status_code
    raise DownloadError(
        "remote_http_error",
        f"HTTP {code} from {url}",
        details={"http_status": code, "retriable": code >= 500 or code == 429},
    )


def _to_download_error(exc: BaseException, url: str) -> DownloadError:
    if isinstance(exc, DownloadError):
        if exc.code == "remote_http_error" and isinstance(exc.details, dict):
            # 5xx / 429 可重试，4xx 不可重试
            exc.retriable = bool(exc.details.get("retriable"))
        return exc
    if isinstance(exc, httpx.ConnectError) and _is_tls_error(exc):
        return DownloadError("tls_error", f"TLS verification failed for {url}: {exc}")
    if isinstance(exc, httpx.TimeoutException):
        return DownloadError("network_error", f"timeout while downloading {url}: {exc!r}")
    if isinstance(exc, httpx.TransportError):
        return DownloadError("network_error", f"network error while downloading {url}: {exc!r}")
    if isinstance(exc, PermissionError):
        return DownloadError("permission_denied", f"permission denied: {exc}")
    if isinstance(exc, OSError) and exc.errno in (errno.ENOSPC, errno.EDQUOT):
        return DownloadError("disk_insufficient", f"disk full while downloading {url}: {exc}")
    if isinstance(exc, OSError):
        return DownloadError("io_error", f"I/O error while downloading {url}: {exc}")
    return DownloadError("io_error", f"unexpected error while downloading {url}: {exc!r}")


def _is_tls_error(exc: BaseException) -> bool:
    seen = set()
    cur: Optional[BaseException] = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, ssl.SSLError) or "CERTIFICATE_VERIFY_FAILED" in str(cur):
            return True
        cur = cur.__cause__ or cur.__context__
    return False


# ---------------------------------------------------------------------------
# 解压
# ---------------------------------------------------------------------------

def extract_archive(
    archive: Path,
    target: Path,
    *,
    subdir: Optional[str] = None,
    replace: bool = False,
) -> None:
    """解压到临时目录，成功后替换（replace=True）或合并到 target。失败抛 DownloadError。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{target.name}.extracting-{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        _extract_to(archive, staging)
        source = staging
        if subdir and (staging / subdir).is_dir():
            source = staging / subdir
        if replace:
            old = None
            if target.exists():
                old = target.with_name(f".{target.name}.old-{uuid.uuid4().hex[:8]}")
                os.replace(target, old)
            os.replace(source, target)
            if old is not None:
                shutil.rmtree(old, ignore_errors=True)
        else:
            target.mkdir(parents=True, exist_ok=True)
            for entry in list(source.iterdir()):
                _merge_move(entry, target / entry.name)
    except DownloadError:
        raise
    except (tarfile.TarError, EOFError, zlib.error) as exc:
        raise DownloadError("extract_failed", f"failed to extract {archive.name}: {exc}") from exc
    except PermissionError as exc:
        raise DownloadError("permission_denied", f"permission denied while extracting: {exc}") from exc
    except OSError as exc:
        if exc.errno in (errno.ENOSPC, errno.EDQUOT):
            raise DownloadError("disk_insufficient", f"disk full while extracting {archive.name}") from exc
        raise DownloadError("extract_failed", f"failed to extract {archive.name}: {exc}") from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _extract_to(archive: Path, dest: Path) -> None:
    with tarfile.open(archive, "r:*") as tf:
        if hasattr(tarfile, "data_filter"):
            # 拒绝绝对路径、..、指向目录外的链接、设备文件
            tf.extractall(dest, filter="data")
            return
        root = dest.resolve()
        for member in tf.getmembers():
            path = (root / member.name).resolve()
            if path != root and root not in path.parents:
                raise DownloadError("extract_failed", f"unsafe path in archive: {member.name}")
            if member.issym() or member.islnk() or member.isdev():
                raise DownloadError("extract_failed", f"links/devices not allowed in archive: {member.name}")
        tf.extractall(dest)


def _merge_move(src: Path, dst: Path) -> None:
    if src.is_dir() and not src.is_symlink() and dst.is_dir() and not dst.is_symlink():
        for child in list(src.iterdir()):
            _merge_move(child, dst / child.name)
        return
    if dst.is_dir() and not dst.is_symlink():
        shutil.rmtree(dst)
    elif dst.exists() or dst.is_symlink():
        dst.unlink()
    os.replace(src, dst)


async def run_extract(archive: Path, target: Path, *, subdir: Optional[str] = None, replace: bool = False) -> None:
    """在线程里解压；被取消时等解压线程结束再抛出，避免残留临时目录。"""
    fut = asyncio.ensure_future(
        asyncio.to_thread(extract_archive, archive, target, subdir=subdir, replace=replace)
    )
    try:
        await asyncio.shield(fut)
    except asyncio.CancelledError:
        try:
            await fut
        except Exception:
            pass
        raise


# ---------------------------------------------------------------------------
# 模型级下载任务（ASR / TTS / VAD / Vision 使用；LLM 等四域的状态存在 sqlite，见 base_service）
# ---------------------------------------------------------------------------

def url_filename(url: str) -> str:
    return url.split("?")[0].rstrip("/").split("/")[-1]


@dataclass(frozen=True)
class Artifact:
    url: str
    path: Path  # 单文件：最终文件；压缩包：解压目标目录
    archive: bool = False
    archive_subdir: Optional[str] = None
    replace: bool = False
    required: tuple[str, ...] = ()  # 压缩包解压后必须存在的相对路径

    def ready(self) -> bool:
        if not self.archive:
            return _file_ready(self.path)
        if self.required:
            return all(_path_ready(self.path / rel) for rel in self.required)
        return self.path.is_dir() and any(self.path.iterdir())

    @property
    def download_path(self) -> Path:
        # 压缩包下载到目标目录旁边，解压成功后删除
        return self.path.parent / url_filename(self.url) if self.archive else self.path


@dataclass
class ModelAssets:
    model_id: str
    artifacts: list[Artifact]

    def ready(self) -> bool:
        return all(a.ready() for a in self.artifacts)

    def missing(self) -> list[Artifact]:
        return [a for a in self.artifacts if not a.ready()]


def _file_ready(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _path_ready(path: Path) -> bool:
    return path.is_dir() or _file_ready(path)


@dataclass
class _Job:
    status: str = "downloading"
    downloaded_bytes: int = 0
    total_bytes: Optional[int] = None
    checksum: Optional[str] = None
    error: Optional[DownloadError] = None
    user_cancelled: bool = False
    updated_at: float = field(default_factory=time.time)


AssetResolver = Callable[[str], Optional[ModelAssets]]


class DownloadTracker:
    """单个域的下载任务表（内存）。下载完成与否以文件为准，失败原因保存在内存里。"""

    def __init__(
        self,
        domain: str,
        resolver: AssetResolver,
        known_models: Callable[[], list[str]],
        config: Optional[DownloadConfig] = None,
    ):
        self._domain = domain
        self._resolver = resolver
        self._known_models = known_models
        self._config = config or DownloadConfig()
        self._jobs: dict[str, _Job] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    # ---- 查询 ----

    def supports(self, model_id: str) -> bool:
        return self._resolver(model_id) is not None

    def is_ready(self, model_id: str) -> bool:
        assets = self._resolver(model_id)
        return assets is not None and assets.ready()

    def _assets(self, model_id: str) -> ModelAssets:
        assets = self._resolver(model_id)
        if assets is not None:
            return assets
        if model_id in self._known_models():
            raise DownloadNotSupported(
                f"{self._domain} model '{model_id}' is not downloaded by the gateway"
            )
        raise ModelUnknown(
            f"{self._domain} model '{model_id}' not found",
            details={"available": self._known_models()},
        )

    def status(self, model_id: str) -> dict:
        assets = self._assets(model_id)
        job = self._jobs.get(model_id)
        running = model_id in self._tasks
        if running and job is not None:
            status = "downloading"
        elif assets.ready():
            status = "downloaded"
        elif job is not None and job.error is not None:
            status = "error"
        else:
            status = "available"
        downloaded = job.downloaded_bytes if job else 0
        total = job.total_bytes if job else None
        if status == "downloaded":
            progress = 1.0
        elif total:
            progress = min(downloaded / total, 1.0)
        else:
            progress = 0.0
        error = job.error if (job and status == "error") else None
        return {
            "model": model_id,
            "status": status,
            "progress": round(progress, 4),
            "downloaded_bytes": downloaded,
            "total_bytes": total,
            "checksum": job.checksum if job and status == "downloaded" else None,
            "error_code": error.code if error else None,
            "error_message": error.message if error else None,
            "retriable": error.retriable if error else None,
            "resumable": status != "downloading"
            and any(partial_size(a.download_path) > 0 for a in assets.missing()),
        }

    # ---- 操作 ----

    async def start(self, model_id: str) -> dict:
        assets = self._assets(model_id)
        if model_id in self._tasks:
            raise DownloadInProgress(f"{self._domain} model '{model_id}' is already downloading")
        if assets.ready():
            raise ModelAlreadyDownloaded(f"{self._domain} model '{model_id}' is already downloaded")
        self._spawn(model_id, assets)
        return self.status(model_id)

    async def cancel(self, model_id: str) -> dict:
        self._assets(model_id)
        task = self._tasks.get(model_id)
        if task is None:
            raise NoActiveDownload(f"No active download for {self._domain} model '{model_id}'")
        self._jobs[model_id].user_cancelled = True
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        return self.status(model_id)

    async def ensure(self, model_id: str) -> None:
        """加载前调用：已下载直接返回；否则下载（或等待进行中的下载）直到完成，失败抛 DownloadError。"""
        assets = self._resolver(model_id)
        if assets is None or assets.ready():
            return
        task = self._tasks.get(model_id) or self._spawn(model_id, assets)
        # shield：加载请求被客户端断开时不连带取消下载
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            current = asyncio.current_task()
            cancelling = getattr(current, "cancelling", lambda: 0)()
            if task.cancelled() and not cancelling:
                raise DownloadError("cancelled", f"{self._domain} model '{model_id}' download was cancelled")
            raise
        job = self._jobs.get(model_id)
        if job is not None and job.error is not None:
            raise job.error
        if not assets.ready():
            raise DownloadError("io_error", f"{self._domain} model '{model_id}' files missing after download")

    async def shutdown(self) -> None:
        for task in list(self._tasks.values()):
            task.cancel()
        for task in list(self._tasks.values()):
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    # ---- 执行 ----

    def _spawn(self, model_id: str, assets: ModelAssets) -> asyncio.Task:
        self._jobs[model_id] = _Job()
        task = asyncio.create_task(self._run(model_id, assets))
        self._tasks[model_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(model_id, None))
        return task

    async def _run(self, model_id: str, assets: ModelAssets) -> None:
        job = self._jobs[model_id]
        pending = assets.missing()
        checksums: list[str] = []
        completed = 0
        current: Optional[Artifact] = None
        try:
            for artifact in pending:
                current = artifact

                async def report(done: int, total: Optional[int], _base=completed) -> None:
                    job.downloaded_bytes = _base + done
                    job.total_bytes = (_base + total) if total is not None else None
                    job.updated_at = time.time()

                if artifact.ready():  # 共用文件可能已被其他任务下完
                    continue
                result = await fetch_file(
                    artifact.url,
                    artifact.download_path,
                    config=self._config,
                    on_progress=report,
                    extract_ratio=self._config.archive_extract_ratio if artifact.archive else 0.0,
                    discard_on_cancel=lambda: job.user_cancelled,
                )
                checksums.append(result.checksum)
                if artifact.archive:
                    await run_extract(
                        result.path,
                        artifact.path,
                        subdir=artifact.archive_subdir,
                        replace=artifact.replace,
                    )
                    result.path.unlink(missing_ok=True)
                    if not artifact.ready():
                        missing = [r for r in artifact.required if not _path_ready(artifact.path / r)]
                        raise DownloadError(
                            "extract_failed",
                            f"archive {url_filename(artifact.url)} did not provide: {', '.join(missing)}",
                        )
                completed += result.size
            job.status = "downloaded"
            job.checksum = "unavailable" if "unavailable" in checksums else ("verified" if checksums else None)
            job.downloaded_bytes = completed or job.downloaded_bytes
            job.total_bytes = job.downloaded_bytes
        except asyncio.CancelledError:
            if job.user_cancelled:
                job.downloaded_bytes = 0
            job.status = "available"
            logger.info("%s download cancelled: %s", self._domain, model_id)
            raise
        except DownloadError as exc:
            job.status = "error"
            job.error = exc
            logger.error("%s download failed for %s: [%s] %s", self._domain, model_id, exc.code, exc.message)
            # 加载时触发的下载失败会把同一个异常再抛给调用方，record_fault 按对象去重
            await record_fault(mark_fault(exc, self._domain, model_id))
        except Exception as exc:  # 兜底，避免任务异常无人接收
            job.status = "error"
            job.error = _to_download_error(exc, current.url if current else "")
            logger.exception("%s download crashed for %s", self._domain, model_id)
            await record_fault(mark_fault(job.error, self._domain, model_id))
        finally:
            job.updated_at = time.time()
