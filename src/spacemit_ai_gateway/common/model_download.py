"""Small helpers for downloading bundled model archives."""

from __future__ import annotations

import logging
import fcntl
import shutil
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_COPY_CHUNK_SIZE = 1024 * 1024
_USER_AGENT = "spacemit-ai-gateway/0.1"


class ModelDownloadError(RuntimeError):
    """Raised when a model cannot be downloaded or unpacked."""


def expand_path(path: str | Path) -> Path:
    return Path(path).expanduser()


def ensure_remote_file(path: str | Path, url: str, *, timeout_s: int = 60) -> None:
    target = expand_path(path)
    if _path_ready(target):
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    with _file_lock(target.parent / f".{target.name}.lock"):
        if _path_ready(target):
            return

        logger.info("model file missing, downloading %s to %s", url, target)
        with tempfile.NamedTemporaryFile(
            prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent), delete=False
        ) as tmp:
            tmp_path = Path(tmp.name)

        try:
            _download_url(url, tmp_path, timeout_s=timeout_s)
            tmp_path.replace(target)
        except Exception as exc:
            tmp_path.unlink(missing_ok=True)
            if isinstance(exc, ModelDownloadError):
                raise
            raise ModelDownloadError(f"failed to download {url}: {exc}") from exc


def ensure_archive_model(
    model_dir: str | Path,
    *,
    url: str,
    archive_name: str,
    required_paths: Sequence[str],
    archive_subdir: str | None = None,
    timeout_s: int = 60,
) -> None:
    target_dir = expand_path(model_dir)
    missing = _missing_paths(target_dir, required_paths)
    if not missing:
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    with _file_lock(target_dir.parent / f".{target_dir.name}.lock"):
        missing = _missing_paths(target_dir, required_paths)
        if not missing:
            return

        logger.info(
            "model files missing under %s (%s), downloading %s",
            target_dir,
            ", ".join(missing),
            url,
        )

        with tempfile.TemporaryDirectory(
            prefix=".model-download-", dir=str(target_dir.parent)
        ) as tmp_name:
            tmp_dir = Path(tmp_name)
            archive_path = tmp_dir / archive_name
            extract_dir = tmp_dir / "extract"
            extract_dir.mkdir()

            _download_url(url, archive_path, timeout_s=timeout_s)
            _safe_extract_tar(archive_path, extract_dir)

            source_dir = extract_dir
            if archive_subdir:
                subdir = extract_dir / archive_subdir
                if subdir.is_dir():
                    source_dir = subdir

            _copy_contents(source_dir, target_dir)

        missing_after = _missing_paths(target_dir, required_paths)
        if missing_after:
            raise ModelDownloadError(
                f"downloaded archive did not provide required files: {', '.join(missing_after)}"
            )


@contextmanager
def _file_lock(lock_path: Path) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _missing_paths(base_dir: Path, relative_paths: Sequence[str]) -> list[str]:
    return [path for path in relative_paths if not _path_ready(base_dir / path)]


def _path_ready(path: Path) -> bool:
    if path.is_dir():
        return True
    return path.is_file() and path.stat().st_size > 0


def _download_url(url: str, target_path: Path, *, timeout_s: int) -> None:
    request = Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(request, timeout=timeout_s) as response:
            status = getattr(response, "status", None)
            if status is not None and status >= 400:
                raise ModelDownloadError(f"HTTP {status} while downloading {url}")
            with target_path.open("wb") as output:
                shutil.copyfileobj(response, output, length=_COPY_CHUNK_SIZE)
    except Exception as exc:
        if isinstance(exc, ModelDownloadError):
            raise
        raise ModelDownloadError(f"failed to download {url}: {exc}") from exc

    if not _path_ready(target_path):
        raise ModelDownloadError(f"downloaded empty file from {url}")


def _safe_extract_tar(archive_path: Path, dest_dir: Path) -> None:
    dest_root = dest_dir.resolve()
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive.getmembers():
                target = (dest_root / member.name).resolve()
                if target != dest_root and dest_root not in target.parents:
                    raise ModelDownloadError(
                        f"unsafe path in model archive: {member.name}"
                    )
                if member.issym() or member.islnk():
                    raise ModelDownloadError(
                        f"links are not allowed in model archive: {member.name}"
                    )
            archive.extractall(dest_root)
    except tarfile.TarError as exc:
        raise ModelDownloadError(f"failed to extract {archive_path}: {exc}") from exc


def _copy_contents(source_dir: Path, target_dir: Path) -> None:
    for entry in source_dir.iterdir():
        target = target_dir / entry.name
        if entry.is_dir():
            shutil.copytree(entry, target, dirs_exist_ok=True)
        else:
            shutil.copy2(entry, target)
