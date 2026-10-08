"""llama-server 子进程：输出落盘、启动失败分类。

LLM / Embed / Rerank / VLM 四域共用。进程 stdout+stderr 写到
<storage.base_dir>/logs/<model>.log（单文件上限 10 MiB，滚动保留一份 .log.1），
启动失败时根据退出码和日志尾部给出 load_* 错误码。
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
from collections import deque
from pathlib import Path
from typing import Any, Optional

from .errors import DomainError, ModelLoadFailed

logger = logging.getLogger(__name__)

_LOG_MAX_BYTES = 10 * 1024 * 1024
_TAIL_LINES = 40
_SIGKILL = -9

# 先判断内存不足：llama.cpp 内存分配失败后也会打印 "failed to load model"。
# 不能只匹配 "failed to allocate"：K3 上每次启动都会打印
# "CPU_RISCV64_SPACEMIT: failed to allocate init_barrier from shared mem, falling back to heap"
_OOM_PATTERNS = (
    "failed to allocate buffer",
    "failed to allocate cpu buffer",
    "out of memory",
    "cannot allocate memory",
    "unable to allocate",
    "std::bad_alloc",
    "insufficient memory",
)
_INVALID_ARGS_PATTERNS = (
    "invalid argument",
    "unknown argument",
    "error while handling argument",
    "unrecognized option",
)
_INVALID_MODEL_PATTERNS = (
    "unknown model architecture",
    "invalid magic",
    "failed to read magic",
    "gguf_init_from_file",
    "error loading model",
    "failed to load model",
    "unsupported model",
    "wrong shape",
    "not within the file bounds",
    "no gguf file found",
)


def process_log_path(config: Any, model_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", model_id)
    return Path(config.storage.base_dir).expanduser() / "logs" / f"{safe}.log"


def spawn_logged(cmd: list[str], log_path: Optional[Path]) -> subprocess.Popen:
    """启动子进程，输出写入 log_path（每次启动前把旧日志滚动为 .log.1）。"""
    if log_path is None:
        return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        os.replace(log_path, log_path.with_name(log_path.name + ".1"))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    thread = threading.Thread(
        target=_pump, args=(proc.stdout, log_path), name=f"llama-log-{log_path.stem}", daemon=True
    )
    thread.start()
    proc._log_thread = thread  # type: ignore[attr-defined]
    return proc


def _pump(stream, log_path: Path) -> None:
    written = 0
    fh = open(log_path, "ab")
    try:
        for line in iter(stream.readline, b""):
            if written + len(line) > _LOG_MAX_BYTES:
                fh.close()
                os.replace(log_path, log_path.with_name(log_path.name + ".1"))
                fh = open(log_path, "wb")
                written = 0
            fh.write(line)
            fh.flush()
            written += len(line)
    except Exception:  # 日志写失败不能影响推理进程
        logger.warning("stop writing llama-server log %s", log_path, exc_info=True)
        for _ in iter(stream.readline, b""):
            pass
    finally:
        fh.close()


def read_log_tail(log_path: Path, lines: int = _TAIL_LINES) -> list[str]:
    try:
        with open(log_path, "rb") as fh:
            tail = deque(fh, maxlen=lines)
    except OSError:
        return []
    return [line.decode("utf-8", errors="replace").rstrip() for line in tail]


def adapter_returncode(adapter: Any) -> Optional[int]:
    proc = getattr(adapter, "_process", None)
    return proc.poll() if proc is not None else None


def _wait_log_flushed(proc: Any) -> None:
    thread = getattr(proc, "_log_thread", None)
    if thread is not None:
        thread.join(timeout=2.0)


def classify_start_failure(
    model_id: str, returncode: Optional[int], tail: list[str], log_path: Optional[Path] = None
) -> ModelLoadFailed:
    # "falling back" 表示已自行恢复的告警，不参与分类
    text = "\n".join(line for line in tail if "falling back" not in line).lower()
    if returncode is None:
        code, reason = "load_timeout", "not ready within the startup timeout"
    elif returncode == _SIGKILL:
        code, reason = "load_oom", "process was killed (SIGKILL), most likely by the OOM killer"
    elif any(p in text for p in _OOM_PATTERNS):
        code, reason = "load_oom", "out of memory while loading the model"
    elif any(p in text for p in _INVALID_ARGS_PATTERNS):
        code, reason = "load_invalid_args", "llama-server rejected the arguments"
    elif any(p in text for p in _INVALID_MODEL_PATTERNS):
        code, reason = "load_invalid_model", "model file is invalid or not supported"
    else:
        code, reason = "load_failed", f"process exited with code {returncode}"
    return ModelLoadFailed(
        f"llama-server failed to start for model '{model_id}': {reason}",
        code=code,
        retriable=code in ("load_timeout", "load_failed"),
        details={
            "returncode": returncode,
            "log_tail": tail[-20:],
            "log_path": str(log_path) if log_path else None,
        },
    )


async def start_and_wait(
    adapter: Any,
    model_id: str,
    model_path: Path,
    extra_args: list[str],
    config: Any,
    timeout: float = 120.0,
) -> None:
    """启动 adapter 并等待就绪；失败时停止进程、释放端口并抛分类后的 ModelLoadFailed。"""
    log_path = process_log_path(config, model_id)
    try:
        adapter.start(model_path, extra_args=extra_args, log_path=log_path)
    except FileNotFoundError as exc:
        adapter.stop()
        raise ModelLoadFailed(
            f"llama-server executable not found: {exc}", code="backend_missing"
        ) from exc
    except DomainError:
        adapter.stop()
        raise
    except Exception as exc:
        adapter.stop()
        raise ModelLoadFailed(
            f"failed to start llama-server for model '{model_id}': {exc}",
            code="load_invalid_model",
        ) from exc

    if await adapter.health_check(timeout=timeout):
        return
    returncode = adapter_returncode(adapter)
    proc = getattr(adapter, "_process", None)
    adapter.stop()
    _wait_log_flushed(proc)
    error = classify_start_failure(model_id, returncode, read_log_tail(log_path), log_path)
    logger.error("%s; last log lines:\n%s", error.message, "\n".join(error.details["log_tail"]))
    raise error
