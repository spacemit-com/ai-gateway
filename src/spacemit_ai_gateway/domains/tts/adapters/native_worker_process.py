"""Child process entrypoint for native spacemit_tts engines."""

from __future__ import annotations

import base64
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

# Keep the original stdout pipe for the protocol, then redirect fd=1 to stderr
# before importing native code. C/C++ stdout logs must not corrupt frames.
_PROTOCOL_OUT = os.fdopen(os.dup(sys.stdout.fileno()), "wb", buffering=0)
os.dup2(sys.stderr.fileno(), sys.stdout.fileno())


def _read_frame() -> dict[str, Any] | None:
    line = sys.stdin.buffer.readline()
    if not line:
        return None
    size = int(line.strip())
    body = sys.stdin.buffer.read(size)
    if len(body) != size:
        raise EOFError("incomplete frame")
    return json.loads(body.decode("utf-8"))


def _write_frame(payload: dict[str, Any]) -> None:
    data = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    _PROTOCOL_OUT.write(str(len(data)).encode("ascii") + b"\n" + data)
    _PROTOCOL_OUT.flush()


def _set_model_dir(engine_config, model_dir: str | None) -> None:
    if not model_dir:
        return
    model_dir_text = str(Path(model_dir).expanduser())
    if hasattr(engine_config, "model_dir"):
        engine_config.model_dir = model_dir_text
        return
    native_config = getattr(engine_config, "_config", None)
    if native_config is not None and hasattr(native_config, "model_dir"):
        native_config.model_dir = model_dir_text


class WorkerState:
    def __init__(self):
        self.config = None
        self.engine = None
        self.sample_rate = 0

    def init(self, params: dict[str, Any]) -> dict[str, Any]:
        from ....app.settings import TtsConfig
        import spacemit_tts

        config = TtsConfig(**params["config"])
        engine_config = spacemit_tts.Config.preset(config.backend)
        _set_model_dir(engine_config, config.model_dir)
        if config.sample_rate is not None:
            engine_config.sample_rate = config.sample_rate
        engine_config.speed = config.speed
        self.engine = spacemit_tts.Engine(engine_config)
        self.config = config
        self.sample_rate = int(engine_config.sample_rate)
        return {
            "backend": config.backend,
            "sample_rate": self.sample_rate,
        }

    def warmup(self, params: dict[str, Any]) -> dict[str, Any]:
        raw = self._require_engine().synthesize(params.get("text") or "hello")
        self._check_result(raw, "warmup")
        return {}

    def synthesize(self, params: dict[str, Any]) -> dict[str, Any]:
        import numpy as np

        raw = self._require_engine().synthesize(params["text"])
        self._check_result(raw, "synthesize")
        audio = np.asarray(raw.audio_int16, dtype=np.int16)
        return self._audio_payload(
            audio,
            sample_rate=int(raw.sample_rate),
            duration_ms=float(raw.duration_ms),
            processing_ms=float(raw.processing_time_ms),
            rtf=float(raw.rtf),
        )

    def stream(self, params: dict[str, Any], request_id: int) -> dict[str, Any]:
        import numpy as np
        import spacemit_tts

        stats = {"duration_ms": 0.0, "rtf": 0.0}
        errors: list[str] = []
        outer = self

        class _Bridge(spacemit_tts.TtsCallback):
            def on_event(self, result) -> None:
                try:
                    audio = np.asarray(result.get_audio_int16(), dtype=np.int16)
                    duration_ms = float(result.get_duration_ms() or 0.0)
                    rtf = float(result.get_rtf() or 0.0)
                except Exception as exc:
                    errors.append(f"tts on_event decode failed: {exc}")
                    return

                stats["duration_ms"] += duration_ms
                stats["rtf"] = rtf
                _write_frame({
                    "id": request_id,
                    "ok": True,
                    "event": "audio",
                    "result": outer._audio_payload(
                        audio,
                        sample_rate=outer.sample_rate,
                        duration_ms=duration_ms,
                        processing_ms=duration_ms * rtf,
                        rtf=rtf,
                    ),
                })

            def on_error(self, message: str) -> None:
                errors.append(str(message) if message else "tts error")

        self._require_engine().synthesize_streaming(params["text"], _Bridge())
        if errors:
            raise RuntimeError(errors[0])
        return stats

    def update_lexicon(self, params: dict[str, Any]) -> dict[str, Any]:
        engine = self._require_engine()
        updater = getattr(engine, "update_lexicon", None)
        if updater is not None:
            updater(params.get("entries") or [])
        return {}

    def shutdown(self, params: dict[str, Any]) -> dict[str, Any]:
        engine = self.engine
        self.engine = None
        if engine is not None:
            for method in ("shutdown", "close"):
                closer = getattr(engine, method, None)
                if closer is not None:
                    closer()
                    break
        return {}

    def _require_engine(self):
        if self.engine is None:
            raise RuntimeError("TTS engine is not initialized")
        return self.engine

    def _audio_payload(
        self,
        audio,
        *,
        sample_rate: int,
        duration_ms: float,
        processing_ms: float,
        rtf: float,
    ) -> dict[str, Any]:
        return {
            "audio_b64": base64.b64encode(audio.tobytes()).decode("ascii"),
            "sample_rate": int(sample_rate),
            "duration_ms": float(duration_ms),
            "processing_ms": float(processing_ms),
            "rtf": float(rtf),
        }

    @staticmethod
    def _check_result(raw, action: str) -> None:
        if not raw.is_success:
            raise RuntimeError(
                f"{action} failed: {getattr(raw, 'message', 'unknown error')}"
            )


def main() -> int:
    state = WorkerState()
    while True:
        request = _read_frame()
        if request is None:
            return 0
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        try:
            if method == "stream":
                result = state.stream(params, int(request_id))
                _write_frame({
                    "id": request_id,
                    "ok": True,
                    "event": "done",
                    "result": result,
                })
                continue

            handler = getattr(state, str(method))
            result = handler(params)
            _write_frame({"id": request_id, "ok": True, "result": result})
            if method == "shutdown":
                return 0
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            _write_frame({"id": request_id, "ok": False, "error": str(exc)})


if __name__ == "__main__":
    raise SystemExit(main())
