"""common/llama_process.py：子进程日志落盘、启动失败分类。"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from spacemit_ai_gateway.common import llama_process
from spacemit_ai_gateway.common.errors import ModelLoadFailed
from spacemit_ai_gateway.common.llama_process import (
    classify_start_failure,
    read_log_tail,
    spawn_logged,
    start_and_wait,
)


@pytest.mark.parametrize(
    "returncode,log,code",
    [
        (None, "", "load_timeout"),
        (-9, "", "load_oom"),
        (1, "ggml_backend_cpu_buffer_type_alloc_buffer: failed to allocate buffer of size 9 GiB\n"
            "llama_model_load: error loading model: unable to allocate CPU buffer", "load_oom"),
        (1, "error: invalid argument: --bogus", "load_invalid_args"),
        (1, "llama_model_loader: unknown model architecture: 'foo'", "load_invalid_model"),
        (1, "gguf_init_from_file_impl: invalid magic characters: 'abcd', expected 'GGUF'", "load_invalid_model"),
        (2, "something else", "load_failed"),
    ],
)
def test_classify_start_failure(returncode, log, code):
    err = classify_start_failure("m", returncode, log.splitlines())
    assert err.code == code
    assert err.retriable is (code in ("load_timeout", "load_failed"))
    assert err.details["returncode"] == returncode


# K3 上 llama-server（llama.cpp-tools-spacemit 0.1.7）的真实输出；每次启动都有 SpacemiT 的 shared mem 告警
_K3_PREAMBLE = [
    "CPU_RISCV64_SPACEMIT: alloc_chunk: open(/dev/tcm_sync_mem) failed, errno=2",
    "CPU_RISCV64_SPACEMIT: failed to allocate init_barrier from shared mem, falling back to heap",
]


@pytest.mark.parametrize(
    "lines,code",
    [
        (["0.00.009.359 E gguf_init_from_reader: invalid magic characters: 'NOTA', expected 'GGUF'",
          "0.00.009.806 E srv    load_model: failed to load model, '/x/invalid.gguf'",
          "0.00.010.839 E srv  llama_server: exiting due to model loading error"], "load_invalid_model"),
        (["error: invalid argument: --no-such-flag"], "load_invalid_args"),
        (["0.08.601.674 E alloc_tensor_range: failed to allocate CPU buffer of size 458752000000",
          "0.08.626.057 E llama_init_from_model: failed to initialize the context: "
          "failed to allocate buffer for kv cache"], "load_oom"),
    ],
)
def test_classify_real_k3_logs(lines, code):
    assert classify_start_failure("m", 1, _K3_PREAMBLE + lines).code == code


def test_spawn_logged_captures_output_and_rotates(tmp_path):
    log = tmp_path / "logs" / "m.log"
    script = "import sys; print('hello'); print('boom', file=sys.stderr); sys.exit(3)"
    proc = spawn_logged([sys.executable, "-u", "-c", script], log)
    assert proc.wait(10) == 3
    proc._log_thread.join(5)
    assert read_log_tail(log) == ["hello", "boom"]

    proc = spawn_logged([sys.executable, "-c", "print('second')"], log)
    proc.wait(10)
    proc._log_thread.join(5)
    assert read_log_tail(log) == ["second"]
    assert read_log_tail(log.with_name("m.log.1")) == ["hello", "boom"]


class _FakeAdapter:
    def __init__(self, *, start_exc=None, exit_code=None, log_lines=()):
        self.start_exc = start_exc
        self.exit_code = exit_code
        self.log_lines = log_lines
        self.stopped = False
        self._process = None

    def start(self, model_path, extra_args=None, log_path=None):
        if self.start_exc:
            raise self.start_exc
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(self.log_lines))
        self._process = SimpleNamespace(poll=lambda: self.exit_code)

    async def health_check(self, timeout):
        return False

    def stop(self):
        self.stopped = True
        self._process = None


def _config(tmp_path):
    return SimpleNamespace(storage=SimpleNamespace(base_dir=str(tmp_path)))


async def test_missing_binary_is_backend_missing(tmp_path):
    adapter = _FakeAdapter(start_exc=FileNotFoundError("llama-server"))
    with pytest.raises(ModelLoadFailed) as ei:
        await start_and_wait(adapter, "m", Path("x.gguf"), [], _config(tmp_path))
    assert ei.value.code == "backend_missing" and adapter.stopped


async def test_exit_during_start_is_classified_with_log_tail(tmp_path):
    adapter = _FakeAdapter(exit_code=1, log_lines=["load", "error: invalid argument: --nope"])
    with pytest.raises(ModelLoadFailed) as ei:
        await start_and_wait(adapter, "m", Path("x.gguf"), [], _config(tmp_path))
    assert ei.value.code == "load_invalid_args"
    assert ei.value.details["log_tail"][-1] == "error: invalid argument: --nope"
    assert ei.value.details["log_path"] == str(tmp_path / "logs" / "m.log")
    assert adapter.stopped


async def test_still_running_at_deadline_is_timeout(tmp_path):
    adapter = _FakeAdapter(exit_code=None)
    with pytest.raises(ModelLoadFailed) as ei:
        await start_and_wait(adapter, "m", Path("x.gguf"), [], _config(tmp_path), timeout=0)
    assert ei.value.code == "load_timeout" and ei.value.retriable


def test_log_path_sanitizes_model_id(tmp_path):
    path = llama_process.process_log_path(_config(tmp_path), "org/Model:1")
    assert path == tmp_path / "logs" / "org_Model_1.log"
