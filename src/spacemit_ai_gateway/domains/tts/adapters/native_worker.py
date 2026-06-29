"""Subprocess-backed client for native spacemit_tts engines."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import itertools
import json
import logging
import sys
from typing import Any, AsyncIterator

import numpy as np

from ....app.settings import TtsConfig
from ....common.errors import TtsBackendUnavailable
from .base import TtsResult

logger = logging.getLogger(__name__)


class NativeTtsWorker:
    """Owns one native TTS engine in a child process.

    Native ONNX Runtime / EP allocations stay in the worker PID, so unloading the
    model can reclaim memory by terminating the process even when native release
    paths retain internal buffers.
    """

    def __init__(
        self,
        config: TtsConfig,
        *,
        startup_timeout_s: float = 300.0,
        request_timeout_s: float | None = None,
    ):
        self._config = config
        self._startup_timeout_s = startup_timeout_s
        self._request_timeout_s = request_timeout_s
        self._process: asyncio.subprocess.Process | None = None
        self._io_lock = asyncio.Lock()
        self._next_id = itertools.count(1)
        self._init_info: dict[str, Any] = {}

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def start(self) -> dict[str, Any]:
        if self.is_running:
            return self._init_info

        self._process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-u",
            "-m",
            "spacemit_ai_gateway.domains.tts.adapters.native_worker_process",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )
        try:
            self._init_info = await self._call(
                "init",
                {"config": self._config.model_dump(mode="json")},
                timeout_s=self._startup_timeout_s,
            )
            return self._init_info
        except Exception:
            await self.stop(kill=True)
            raise

    async def warmup(self, text: str) -> None:
        await self.start()
        await self._call(
            "warmup",
            {"text": text},
            timeout_s=self._startup_timeout_s,
        )

    async def synthesize(self, text: str) -> TtsResult:
        await self.start()
        payload = await self._call(
            "synthesize",
            {"text": text},
            timeout_s=self._request_timeout_s,
        )
        return self._result_from_payload(payload)

    async def stream_synthesize(self, text: str) -> AsyncIterator[dict[str, Any]]:
        """Yield audio and done events from native streaming synthesis."""
        await self.start()
        async with self._io_lock:
            if not self.is_running or self._process is None:
                raise TtsBackendUnavailable("native TTS worker is not running")
            request_id = next(self._next_id)
            await self._write_payload({
                "id": request_id,
                "method": "stream",
                "params": {"text": text},
            })
            try:
                while True:
                    response = await self._read_response(request_id)
                    if not response.get("ok", False):
                        raise TtsBackendUnavailable(
                            str(response.get("error") or "native TTS worker error")
                        )
                    event = response.get("event")
                    payload = dict(response.get("result") or {})
                    if event == "audio":
                        result = self._result_from_payload(payload)
                        yield {
                            "type": "audio",
                            "audio": result.audio,
                            "sample_rate": result.sample_rate,
                            "duration_ms": result.duration_ms,
                            "rtf": result.rtf,
                        }
                    elif event == "done":
                        yield {
                            "type": "done",
                            "duration_ms": float(payload.get("duration_ms", 0.0)),
                            "rtf": float(payload.get("rtf", 0.0)),
                        }
                        return
                    else:
                        await self._kill_process()
                        raise TtsBackendUnavailable(
                            f"native TTS worker returned unknown stream event: {event}"
                        )
            except asyncio.CancelledError:
                await self._kill_process()
                raise

    async def update_lexicon(self, entries: list[dict]) -> None:
        await self.start()
        await self._call("update_lexicon", {"entries": entries}, timeout_s=30.0)

    async def stop(self, *, kill: bool = False) -> None:
        proc = self._process
        if proc is None:
            return

        if proc.returncode is None and not kill:
            try:
                await self._call("shutdown", {}, timeout_s=5.0)
            except Exception:
                logger.debug("native TTS worker shutdown request failed", exc_info=True)

        if proc.returncode is None:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(proc.wait(), timeout=1.0)

        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()

        self._process = None
        self._init_info = {}

    async def _call(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout_s: float | None,
    ) -> dict[str, Any]:
        async with self._io_lock:
            if not self.is_running or self._process is None:
                raise TtsBackendUnavailable("native TTS worker is not running")
            request_id = next(self._next_id)
            task = asyncio.create_task(
                self._send_and_receive({
                    "id": request_id,
                    "method": method,
                    "params": params,
                })
            )
            try:
                if timeout_s is None:
                    return await asyncio.shield(task)
                return await asyncio.wait_for(asyncio.shield(task), timeout=timeout_s)
            except asyncio.TimeoutError as exc:
                task.cancel()
                await self._kill_process()
                with contextlib.suppress(Exception, asyncio.CancelledError):
                    await task
                raise TtsBackendUnavailable(
                    f"native TTS worker timed out during {method}"
                ) from exc
            except asyncio.CancelledError:
                with contextlib.suppress(Exception, asyncio.CancelledError):
                    await task
                raise

    async def _send_and_receive(self, payload: dict[str, Any]) -> dict[str, Any]:
        await self._write_payload(payload)
        response = await self._read_response(payload["id"])
        if not response.get("ok", False):
            raise TtsBackendUnavailable(str(response.get("error") or "native TTS worker error"))
        return dict(response.get("result") or {})

    async def _write_payload(self, payload: dict[str, Any]) -> None:
        assert self._process is not None
        assert self._process.stdin is not None

        data = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        self._process.stdin.write(str(len(data)).encode("ascii") + b"\n" + data)
        await self._process.stdin.drain()

    async def _read_response(self, expected_id: int) -> dict[str, Any]:
        assert self._process is not None
        assert self._process.stdout is not None

        line = await self._process.stdout.readline()
        if not line:
            await self._process.wait()
            raise TtsBackendUnavailable(
                f"native TTS worker exited with code {self._process.returncode}"
            )
        try:
            size = int(line.strip())
        except ValueError as exc:
            await self._kill_process()
            raise TtsBackendUnavailable("native TTS worker protocol desynchronized") from exc

        body = await self._process.stdout.readexactly(size)
        response = json.loads(body.decode("utf-8"))
        if response.get("id") != expected_id:
            await self._kill_process()
            raise TtsBackendUnavailable("native TTS worker returned mismatched response")
        return response

    @staticmethod
    def _result_from_payload(payload: dict[str, Any]) -> TtsResult:
        audio = np.frombuffer(
            base64.b64decode(payload["audio_b64"].encode("ascii")),
            dtype=np.int16,
        ).copy()
        return TtsResult(
            audio=audio,
            sample_rate=int(payload["sample_rate"]),
            duration_ms=float(payload.get("duration_ms", 0.0)),
            processing_ms=float(payload.get("processing_ms", 0.0)),
            rtf=float(payload.get("rtf", 0.0)),
        )

    async def _kill_process(self) -> None:
        proc = self._process
        if proc is None:
            return
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        self._process = None
        self._init_info = {}
