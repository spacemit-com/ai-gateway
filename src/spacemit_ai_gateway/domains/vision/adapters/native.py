from __future__ import annotations

import base64
import hashlib
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import URLError
from urllib.request import Request, urlopen

import cv2
import numpy as np

from ..schemas import ErrorCode, TimingInfo


class ServiceError(Exception):
    def __init__(self, http_status: int, code: ErrorCode, message: str):
        self.http_status = http_status
        self.code = int(code)
        self.message = message
        super().__init__(message)


class NativeAdapter:
    """封装 VisionServiceNative C++ bindings，提供统一推理接口。"""

    def __init__(self) -> None:
        self._native_available = False
        self._VisionServiceNative = None
        self._VisionServiceStatus = None
        self._VisionServiceTimingOptions = None
        self._last_create_error: Optional[str] = None
        self._load_native_bindings()

    def _load_native_bindings(self) -> None:
        """Try wheel bindings first, then source-tree bindings fallback."""
        # 1) Prefer packaged wheel import path.
        try:
            from spacemit_vision import (  # type: ignore
                VisionServiceNative,
                VisionServiceStatus,
                VisionServiceTimingOptions,
                extension_import_error,
            )
            self._VisionServiceNative = VisionServiceNative
            self._VisionServiceStatus = VisionServiceStatus
            self._VisionServiceTimingOptions = VisionServiceTimingOptions
            self._native_available = True
            ext_err = extension_import_error()
            if ext_err is not None:
                self._last_create_error = str(ext_err)
            return
        except Exception as exc:
            wheel_error = exc

        # 2) Fallback to source-tree import path.
        # .../src/spacemit_ai_gateway/domains/vision/adapters/native.py -> repo root is parents[5]
        repo_src = (Path(__file__).resolve().parents[5] / "src").resolve()
        if str(repo_src) not in sys.path:
            sys.path.insert(0, str(repo_src))
        try:
            from core.python.vision_service_native import (  # type: ignore
                VisionServiceNative,
                VisionServiceStatus,
                VisionServiceTimingOptions,
                extension_import_error,
            )
            self._VisionServiceNative = VisionServiceNative
            self._VisionServiceStatus = VisionServiceStatus
            self._VisionServiceTimingOptions = VisionServiceTimingOptions
            self._native_available = True
            ext_err = extension_import_error()
            if ext_err is not None:
                self._last_create_error = str(ext_err)
            return
        except Exception as exc:
            self._native_available = False
            self._last_create_error = (
                f"wheel import failed: {wheel_error}; source import failed: {exc}"
            )

    @property
    def native_available(self) -> bool:
        return self._native_available

    @property
    def last_create_error(self) -> Optional[str]:
        return self._last_create_error

    def create_instance(
        self, config_path: str, model_path_override: str = "", lazy_load: bool = False
    ) -> Optional[Any]:
        if not self._native_available or self._VisionServiceNative is None:
            self._last_create_error = "native bindings are unavailable"
            return None
        try:
            instance = self._VisionServiceNative.create(config_path, model_path_override, lazy_load)
            self._last_create_error = None
            return instance
        except Exception as exc:
            self._last_create_error = str(exc) or exc.__class__.__name__
            return None

    def release_instance(self, instance: Optional[Any]) -> bool:
        """Release native instance resources safely.

        Returns True if released (or nothing to release), False when release fails.
        """
        if instance is None:
            return True
        release_fn = getattr(instance, "release", None)
        if not callable(release_fn):
            return True
        try:
            release_fn()
            return True
        except Exception:
            return False

    # ── Image utils ─────────────────────────────────────────────────

    @staticmethod
    def decode_base64_image(value: str) -> bytes:
        text = value.strip()
        if "," in text and text.lower().startswith("data:"):
            text = text.split(",", 1)[1]
        try:
            return base64.b64decode(text, validate=True)
        except Exception as exc:
            raise ServiceError(400, ErrorCode.INVALID_IMAGE_INPUT, "invalid image_base64") from exc

    @staticmethod
    def load_url_bytes(image_url: str) -> bytes:
        try:
            req = Request(image_url, headers={"User-Agent": "vision-openapi/1.0"})
            with urlopen(req, timeout=5) as resp:
                return resp.read()
        except URLError as exc:
            raise ServiceError(400, ErrorCode.INVALID_IMAGE_INPUT, f"failed to fetch image_url: {exc}") from exc

    @staticmethod
    def bytes_to_bgr(image_bytes: bytes) -> np.ndarray:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ServiceError(400, ErrorCode.INVALID_IMAGE_INPUT, "failed to decode image")
        return np.ascontiguousarray(img, dtype=np.uint8)

    @staticmethod
    def bgr_to_jpeg_base64(img_bgr: np.ndarray) -> str:
        success, buffer = cv2.imencode(".jpg", img_bgr)
        if not success:
            raise ServiceError(500, ErrorCode.INTERNAL_ERROR, "failed to encode image to jpeg")
        return base64.b64encode(buffer).decode("utf-8")

    # ── Native inference ────────────────────────────────────────────

    def infer_image(
        self,
        instance: Any,
        img_bgr: np.ndarray,
        conf: Optional[float] = None,
        iou: Optional[float] = None,
    ) -> Tuple[bool, Any]:
        conf_val = float(conf) if conf is not None and conf > 0 else -1.0
        iou_val = float(iou) if iou is not None and iou > 0 else -1.0
        try:
            status, results = instance.infer_image(img_bgr, conf=conf_val, iou=iou_val)
        except TypeError:
            # Older binding without conf/iou kwargs
            status, results = instance.infer_image(img_bgr)
        ok = status == self._VisionServiceStatus.OK
        return ok, results

    def infer_embedding(self, instance: Any, img_bgr: np.ndarray) -> Optional[List[float]]:
        result = instance.infer_embedding(img_bgr)
        # 兼容两种绑定返回：
        # 1) 直接返回 embedding 向量
        # 2) 返回 (status, embedding)
        if isinstance(result, tuple) and len(result) == 2:
            status, vector = result
            if self._VisionServiceStatus is not None and status != self._VisionServiceStatus.OK:
                return None
            return self._to_float_list(vector)
        return self._to_float_list(result)

    def infer_sequence(
        self, instance: Any, pts: np.ndarray, width: int, height: int
    ) -> Tuple[bool, Any]:
        status, result = instance.infer_sequence(pts, width, height)
        ok = status == self._VisionServiceStatus.OK
        return ok, result

    def get_last_timing(self, instance: Any) -> TimingInfo:
        native_timing = instance.get_last_timing()
        m = self._as_mapping(native_timing)
        return TimingInfo(
            preprocess_ms=self._to_nonzero_float(m.get("preprocess_ms")),
            model_infer_ms=self._to_nonzero_float(m.get("model_infer_ms")),
            postprocess_ms=self._to_nonzero_float(m.get("postprocess_ms")),
            detect_ms=self._to_nonzero_float(m.get("detect_ms")),
            track_ms=self._to_nonzero_float(m.get("track_ms")),
            embedding_ms=self._to_nonzero_float(m.get("embedding_ms")),
            sequence_ms=self._to_nonzero_float(m.get("sequence_ms")),
            draw_ms=self._to_nonzero_float(m.get("draw_ms")),
            infer_ms=self._to_nonzero_float(m.get("infer_ms")),
        )

    def set_timing_options(self, instance: Any, enabled: bool, print_to_stdout: bool) -> None:
        if self._VisionServiceTimingOptions is None:
            return
        opts = self._VisionServiceTimingOptions()
        opts.enabled = enabled
        opts.print_to_stdout = print_to_stdout
        instance.set_timing_options(opts)

    # ── Mock helpers ────────────────────────────────────────────────

    @staticmethod
    def mock_timing(seed_bytes: bytes, purpose: str = "infer") -> TimingInfo:
        digest = hashlib.sha256(seed_bytes + purpose.encode("utf-8")).digest()
        base = 1.0 + digest[0] / 128.0
        return TimingInfo(
            preprocess_ms=round(base * 0.8, 3),
            model_infer_ms=round(base * 4.1, 3),
            postprocess_ms=round(base * 1.3, 3),
            infer_ms=round(base * 6.2, 3),
        )

    @staticmethod
    def mock_embedding(image_bytes: bytes, dim: int = 512) -> List[float]:
        digest = hashlib.sha256(image_bytes).digest()
        vec = [((digest[i % len(digest)] / 255.0) * 2.0 - 1.0) for i in range(dim)]
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    # ── Mapping helpers ─────────────────────────────────────────────

    @classmethod
    def _as_mapping(cls, value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        if value is None:
            return {}
        if hasattr(value, "__dict__"):
            return dict(vars(value))
        keys = [
            "label", "label_name", "class_name", "class_id", "class_idx", "score", "confidence",
            "bbox", "box", "x1", "y1", "x2", "y2", "track_id", "mask", "keypoints",
            "preprocess_ms", "model_infer_ms", "postprocess_ms", "detect_ms",
            "track_ms", "embedding_ms", "sequence_ms", "draw_ms", "infer_ms",
        ]
        mapped: Dict[str, Any] = {}
        for k in keys:
            v = cls._read_obj_field(value, k)
            if v is not None:
                mapped[k] = v
        return mapped

    @staticmethod
    def _read_obj_field(obj: Any, name: str) -> Any:
        if not hasattr(obj, name):
            return None
        val = getattr(obj, name)
        if callable(val):
            try:
                return val()
            except Exception:
                return None
        return val

    @staticmethod
    def _to_float_list(value: Any) -> Optional[List[float]]:
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            try:
                return [float(x) for x in value]
            except Exception:
                return None
        return None

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _to_nonzero_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            v = float(value)
            return v if v != 0.0 else None
        except Exception:
            return None

    @staticmethod
    def _to_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default
