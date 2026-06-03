from __future__ import annotations

import hashlib
import logging
import os
import threading
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen

import numpy as np
import yaml

from .adapters.native import NativeAdapter, ServiceError
from .schemas import (
    ErrorCode,
    ModelInfo,
    ModelLoadResponse,
    ModelSwitchResponse,
    ModelUnloadResponse,
    ModelsListResponse,
)

logger = logging.getLogger(__name__)


_BASE = "https://archive.spacemit.com/spacemit-ai/model_zoo/vision"

# model_id → 仓库内已知配置的映射，用于 model_id 快捷加载
KNOWN_MODELS: Dict[str, Dict[str, Any]] = {
    # YOLOv8 detect variants (n/s/m)
    "yolov8n": {
        "config": "configs/vision/yolov8n.yaml",
        "caps": ["detect"],
        "models": [{"url": f"{_BASE}/yolov8/yolov8n.q.onnx", "dest": "~/.cache/models/vision/yolov8/yolov8n.q.onnx"}],
    },
    "yolov8s": {
        "config": "configs/vision/yolov8s.yaml",
        "caps": ["detect"],
        "models": [{"url": f"{_BASE}/yolov8/yolov8s.q.onnx", "dest": "~/.cache/models/vision/yolov8/yolov8s.q.onnx"}],
    },
    "yolov8m": {
        "config": "configs/vision/yolov8m.yaml",
        "caps": ["detect"],
        "models": [{"url": f"{_BASE}/yolov8/yolov8m.q.onnx", "dest": "~/.cache/models/vision/yolov8/yolov8m.q.onnx"}],
    },
    "yolov11n": {
        "config": "configs/vision/yolov11n.yaml",
        "caps": ["detect"],
        "models": [{"url": f"{_BASE}/yolov11/yolo11n.q.onnx", "dest": "~/.cache/models/vision/yolov11/yolo11n.q.onnx"}],
    },
    "yolov11s": {
        "config": "configs/vision/yolov11s.yaml",
        "caps": ["detect"],
        "models": [{"url": f"{_BASE}/yolov11/yolo11s.q.onnx", "dest": "~/.cache/models/vision/yolov11/yolo11s.q.onnx"}],
    },
    "yolov11m": {
        "config": "configs/vision/yolov11m.yaml",
        "caps": ["detect"],
        "models": [{"url": f"{_BASE}/yolov11/yolo11m.q.onnx", "dest": "~/.cache/models/vision/yolov11/yolo11m.q.onnx"}],
    },
    "yolov5-face": {
        "config": "configs/vision/yolov5-face.yaml",
        "caps": ["detect"],
        "models": [
            {
                "url": f"{_BASE}/yolov5-face/yolov5n-face_cut.q.onnx",
                "dest": "~/.cache/models/vision/yolov5-face/yolov5n-face_cut.q.onnx",
            }
        ],
    },
    "yolov5-gesture": {
        "config": "configs/vision/yolov5_gesture.yaml",
        "caps": ["detect"],
        "models": [
            {
                "url": f"{_BASE}/yolov5/yolov5_gesture.q.onnx",
                "dest": "~/.cache/models/vision/yolov5/yolov5_gesture.q.onnx",
            }
        ],
    },
    # YOLOv8 pose variants (n/s/m)
    "yolov8n-pose": {
        "config": "configs/vision/yolov8n-pose.yaml",
        "caps": ["detect", "pose"],
        "models": [
            {
                "url": f"{_BASE}/yolov8_pose/yolov8n-pose.q.onnx",
                "dest": "~/.cache/models/vision/yolov8_pose/yolov8n-pose.q.onnx",
            }
        ],
    },
    "yolov8s-pose": {
        "config": "configs/vision/yolov8s-pose.yaml",
        "caps": ["detect", "pose"],
        "models": [
            {
                "url": f"{_BASE}/yolov8_pose/yolov8s-pose.q.onnx",
                "dest": "~/.cache/models/vision/yolov8_pose/yolov8s-pose.q.onnx",
            }
        ],
    },
    "yolov8m-pose": {
        "config": "configs/vision/yolov8m-pose.yaml",
        "caps": ["detect", "pose"],
        "models": [
            {
                "url": f"{_BASE}/yolov8_pose/yolov8m-pose.q.onnx",
                "dest": "~/.cache/models/vision/yolov8_pose/yolov8m-pose.q.onnx",
            }
        ],
    },
    # YOLOv8 seg variants (n/s/m)
    "yolov8n-seg": {
        "config": "configs/vision/yolov8n-seg.yaml",
        "caps": ["detect", "segment"],
        "models": [
            {
                "url": f"{_BASE}/yolov8_seg/yolov8n-seg.q.onnx",
                "dest": "~/.cache/models/vision/yolov8_seg/yolov8n-seg.q.onnx",
            }
        ],
    },
    "yolov8s-seg": {
        "config": "configs/vision/yolov8s-seg.yaml",
        "caps": ["detect", "segment"],
        "models": [
            {
                "url": f"{_BASE}/yolov8_seg/yolov8s-seg.q.onnx",
                "dest": "~/.cache/models/vision/yolov8_seg/yolov8s-seg.q.onnx",
            }
        ],
    },
    "yolov8m-seg": {
        "config": "configs/vision/yolov8m-seg.yaml",
        "caps": ["detect", "segment"],
        "models": [
            {
                "url": f"{_BASE}/yolov8_seg/yolov8m-seg.q.onnx",
                "dest": "~/.cache/models/vision/yolov8_seg/yolov8m-seg.q.onnx",
            }
        ],
    },
    "resnet50": {
        "config": "configs/vision/resnet50.yaml",
        "caps": ["classify"],
        "models": [{"url": f"{_BASE}/resnet/resnet50.q.onnx", "dest": "~/.cache/models/vision/resnet/resnet50.q.onnx"}],
    },
    "emotion": {
        "config": "configs/vision/emotion.yaml",
        "caps": ["classify", "emotion"],
        "models": [
            {
                "url": f"{_BASE}/resnet/emotion_resnet50_final.q.onnx",
                "dest": "~/.cache/models/vision/resnet/emotion_resnet50_final.q.onnx",
            }
        ],
    },
    "arcface": {
        "config": "configs/vision/arcface.yaml",
        "caps": ["embedding"],
        "models": [
            {
                "url": f"{_BASE}/arcface/arcface_mobilefacenet_cut.q.onnx",
                "dest": "~/.cache/models/vision/arcface/arcface_mobilefacenet_cut.q.onnx",
            }
        ],
    },
    "bytetrack": {
        "config": "configs/vision/bytetrack.yaml",
        "caps": ["detect", "track"],
        "models": [{"url": f"{_BASE}/yolov8/yolov8n.q.onnx", "dest": "~/.cache/models/vision/yolov8/yolov8n.q.onnx"}],
    },
    "ocsort": {
        "config": "configs/vision/ocsort.yaml",
        "caps": ["detect", "track"],
        "models": [
            {
                "url": f"{_BASE}/yolov8/yolov8n.q.onnx",
                "dest": "~/.cache/models/vision/ocsort/yolov8n.q.onnx",
            },
            {
                "url": f"{_BASE}/ocsort/ocsort_yoloxs_sim.fp32.onnx",
                "dest": "~/.cache/models/vision/ocsort/ocsort_yoloxs_sim.fp32.onnx",
            },
        ],
    },
}


def _infer_capabilities_from_class(class_name: str) -> List[str]:
    """Infer model capabilities from a class string like 'deploy.yolov8_pose.YOLOv8PoseDetector'."""
    class_lower = class_name.lower()

    # Pose detection
    if "pose" in class_lower:
        return ["detect", "pose"]
    # Segmentation
    if "seg" in class_lower or "segment" in class_lower:
        return ["detect", "segment"]
    # Tracking
    if "track" in class_lower or "bytetrack" in class_lower or "ocsort" in class_lower:
        return ["detect", "track"]
    # Embedding/face recognition
    if "arcface" in class_lower or "embedding" in class_lower or "recogni" in class_lower:
        return ["embedding"]
    # Emotion classification
    if "emotion" in class_lower:
        return ["classify", "emotion"]
    # General classification
    if "classif" in class_lower or "resnet" in class_lower:
        return ["classify"]
    # Default: object detection
    return ["detect"]


def _infer_capabilities_from_yaml(yaml_path: str) -> List[str]:
    """Load a YAML config and infer capabilities from its class field."""
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        class_name = cfg.get("class", "")
        if class_name:
            return _infer_capabilities_from_class(class_name)
    except Exception:
        pass
    return ["detect"]


def _scan_config_directory(config_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Scan a config directory and return discovered models as {model_id: {config, caps}}."""
    discovered = {}
    if not config_dir.exists():
        return discovered

    for yaml_file in config_dir.glob("*.yaml"):
        model_id = yaml_file.stem
        # Skip if already in KNOWN_MODELS (explicit registration takes precedence)
        if model_id in KNOWN_MODELS:
            continue

        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            class_name = cfg.get("class", "")
            if not class_name:
                continue

            caps = _infer_capabilities_from_class(class_name)
            # Construct relative config path
            rel_path = f"configs/vision/{yaml_file.name}"
            discovered[model_id] = {"config": rel_path, "caps": caps}
        except Exception:
            continue

    return discovered


def _get_all_known_models() -> Dict[str, Dict[str, Any]]:
    """Return merged dict of KNOWN_MODELS + auto-discovered models from config dirs."""
    all_models = dict(KNOWN_MODELS)

    # Scan repo configs/vision/
    repo_config_dir = _repo_root() / "configs" / "vision"
    discovered_repo = _scan_config_directory(repo_config_dir)
    all_models.update(discovered_repo)

    # Scan package configs/vision/
    pkg_config_dir = _package_root() / "configs" / "vision"
    discovered_pkg = _scan_config_directory(pkg_config_dir)
    all_models.update(discovered_pkg)

    return all_models


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _package_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _cache_root() -> Path:
    return Path(os.getenv("XDG_CACHE_HOME", "~/.cache")).expanduser() / "spacemit-ai-gateway"


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _resolve_data_file_path(path_value: str, config_path: str) -> Optional[Path]:
    raw = Path(path_value).expanduser()
    if raw.is_absolute():
        return raw.resolve() if raw.exists() else None

    candidates = [
        (Path(config_path).resolve().parent / raw).resolve(),
        (Path.cwd() / raw).resolve(),
        (_repo_root() / raw).resolve(),
    ]

    parts = raw.parts
    if len(parts) >= 2 and parts[0] == "src" and parts[1] == "spacemit_ai_gateway":
        candidates.append((_package_root() / Path(*parts[2:])).resolve())
    elif parts and parts[0] == "spacemit_ai_gateway":
        candidates.append((_package_root() / Path(*parts[1:])).resolve())
    else:
        candidates.append((_package_root() / raw).resolve())

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _materialize_config_for_runtime(config_path: str) -> str:
    """Create a runtime YAML with package resource paths resolved to absolute files."""
    try:
        source_path = Path(config_path).resolve()
        with open(source_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        return config_path

    changed = False
    label_file = cfg.get("label_file_path")
    if isinstance(label_file, str) and label_file.strip():
        label_path = _resolve_data_file_path(label_file, config_path)
        if label_path and _is_relative_to(label_path, _package_root()):
            cfg["label_file_path"] = str(label_path)
            changed = True

    if not changed:
        return config_path

    digest = hashlib.sha256(
        f"{source_path}:{source_path.stat().st_mtime_ns}".encode("utf-8")
    ).hexdigest()[:16]
    try:
        output_dir = _cache_root() / "vision" / "configs"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{source_path.stem}-{digest}.yaml"
        content = yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False)
        if not output_path.exists() or output_path.read_text(encoding="utf-8") != content:
            output_path.write_text(content, encoding="utf-8")
        return str(output_path)
    except Exception:
        return config_path


def _load_labels(config_path: str) -> Optional[List[str]]:
    """Load label names from the label_file_path specified in a YAML config."""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        label_file = cfg.get("label_file_path")
        if not label_file:
            return None
        label_path = _resolve_data_file_path(label_file, config_path)
        if label_path is None or not label_path.exists():
            return None
        lines = label_path.read_text(encoding="utf-8").strip().splitlines()
        # Format: "n01440764 tench, Tinca tinca" or just "person"
        labels = []
        for line in lines:
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and parts[0].startswith("n"):
                # ImageNet format: synset_id label_name
                labels.append(parts[1].split(",")[0].strip())
            elif parts:
                labels.append(parts[-1].strip())
        return labels if labels else None
    except Exception:
        return None


def _resolve_config_path(config_path: str) -> str:
    """Resolve config path from cwd, source tree, or packaged defaults."""
    expanded = Path(config_path).expanduser()
    if expanded.is_absolute():
        return str(expanded)

    # Backward compatibility: accept legacy "config/vision/*" paths.
    candidates = [expanded]
    normalized = Path(str(expanded).replace("config/vision/", "configs/vision/", 1))
    if normalized != expanded:
        candidates.append(normalized)

    for relative_path in candidates:
        for base_dir in (Path.cwd(), _repo_root(), _package_root()):
            candidate = (base_dir / relative_path).resolve()
            if candidate.exists():
                return str(candidate)

    return str((_package_root() / normalized).resolve())


def _download_file(url: str, dest: str) -> None:
    """Download a file from url to dest, creating parent dirs as needed."""
    dest_path = Path(dest).expanduser()
    if dest_path.exists():
        return
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(dest_path) + ".tmp"
    print(f"[models] Downloading {dest_path.name} from {url} ...")
    req = Request(url, headers={"User-Agent": "vision-openapi/1.0"})
    written = 0
    with urlopen(req, timeout=300) as resp:
        expected = resp.headers.get("Content-Length")
        expected = int(expected) if expected else None
        with open(tmp, "wb") as f:
            while True:
                chunk = resp.read(1 << 20)  # 1MB
                if not chunk:
                    break
                f.write(chunk)
                written += len(chunk)
            f.flush()
            os.fsync(f.fileno())
    if expected and written != expected:
        os.unlink(tmp)
        raise RuntimeError(
            f"incomplete download: got {written} bytes, expected {expected}"
        )
    os.rename(tmp, str(dest_path))
    print(f"[models] Saved {dest_path} ({written} bytes)")


def _ensure_models_downloaded(model_id: str) -> None:
    """Download model files for a known model_id if they don't exist locally."""
    known = _get_all_known_models().get(model_id)
    if not known or "models" not in known:
        return
    for entry in known["models"]:
        try:
            _download_file(entry["url"], entry["dest"])
        except Exception as exc:
            raise ServiceError(
                500, ErrorCode.MODEL_RUNTIME_ERROR,
                f"failed to download model file for '{model_id}': {exc}",
            ) from exc


def _iter_onnx_paths(value: Any) -> List[str]:
    """Recursively collect *.onnx path strings from yaml values."""
    paths: List[str] = []
    if isinstance(value, str):
        if ".onnx" in value.lower():
            paths.append(value)
        return paths
    if isinstance(value, dict):
        for v in value.values():
            paths.extend(_iter_onnx_paths(v))
        return paths
    if isinstance(value, list):
        for v in value:
            paths.extend(_iter_onnx_paths(v))
        return paths
    return paths


def _download_model_path_if_missing(path_value: str, resolved_config: str) -> None:
    """Download one model path if it points to missing local cache file."""
    if not isinstance(path_value, str) or not path_value.strip():
        return

    model_path_obj = Path(path_value).expanduser()
    if model_path_obj.is_absolute():
        local_model_path = model_path_obj
    else:
        local_model_path = (Path(resolved_config).parent / model_path_obj).resolve()

    if local_model_path.exists():
        return

    # Expected cache layout: ~/.cache/models/vision/<subdir>/<file>.onnx
    parts = local_model_path.parts
    if "vision" not in parts:
        return
    vision_idx = parts.index("vision")
    remote_subpath = "/".join(parts[vision_idx + 1 :])
    if not remote_subpath:
        return

    _download_file(f"{_BASE}/{remote_subpath}", str(local_model_path))


def _ensure_model_from_config_downloaded(resolved_config: str, model_path_override: str = "") -> None:
    """Try downloading model files referenced by config and override path."""
    try:
        with open(resolved_config, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        return

    # Collect all onnx paths from config (model_path, secondary trackers, etc.).
    onnx_paths = _iter_onnx_paths(cfg)
    if model_path_override:
        onnx_paths.append(model_path_override)

    try:
        for p in onnx_paths:
            _download_model_path_if_missing(p, resolved_config)
    except Exception as exc:
        raise ServiceError(
            500,
            ErrorCode.MODEL_RUNTIME_ERROR,
            f"failed to download model referenced by config '{resolved_config}': {exc}",
        ) from exc


def _read_image_size_from_config(config_path: str) -> tuple[int, int]:
    """Read image_size from YAML; default 640x640 when missing."""
    width, height = 640, 640
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        size = cfg.get("image_size") or cfg.get("input_size")
        if isinstance(size, (list, tuple)) and len(size) >= 2:
            width, height = int(size[0]), int(size[1])
        elif isinstance(size, int):
            width = height = int(size)
    except Exception:
        pass
    return max(width, 1), max(height, 1)


def _warmup_uses_embedding(capabilities: List[str]) -> bool:
    """ArcFace 等只走 /feature → infer_embedding，不能用 infer_image 预热。"""
    return "embedding" in capabilities and not any(
        c in capabilities for c in ("detect", "classify", "pose", "segment", "track", "emotion")
    )


def _warmup_native_instance(
    adapter: NativeAdapter,
    instance: Any,
    config_path: str,
    capabilities: List[str],
    model_id: str = "",
) -> None:
    """按 config 的 image_size 构造合成 BGR，跑一轮与业务一致的推理预热。"""
    try:
        width, height = _read_image_size_from_config(config_path)
        img_bgr = np.zeros((height, width, 3), dtype=np.uint8)

        if _warmup_uses_embedding(capabilities):
            # similarity 会连续 infer_embedding 两次
            for _ in range(2):
                adapter.infer_embedding(instance, img_bgr)
            return

        adapter.infer_image(instance, img_bgr)
    except Exception:
        pass


@dataclass
class ManagedModel:
    info: ModelInfo
    config_path: str = ""
    model_path_override: str = ""
    backend_instance: Optional[Any] = None
    timing_enabled: bool = False
    timing_print_to_stdout: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    labels: Optional[List[str]] = field(default=None)


class ModelRegistry:
    """管理已加载模型列表、默认模型指针。"""

    def __init__(self, adapter: NativeAdapter) -> None:
        self._lock = threading.RLock()
        self._models: Dict[str, ManagedModel] = {}
        self._default_model_id: Optional[str] = None
        self._default_model_group: Optional[str] = None
        self._adapter = adapter

    @property
    def default_model_id(self) -> Optional[str]:
        with self._lock:
            return self._default_model_id

    def get_instance(self, model_id: Optional[str] = None) -> tuple[ManagedModel, str]:
        """获取指定或默认模型。返回 (ManagedModel, resolved_model_id)。"""
        with self._lock:
            mid = model_id or self._default_model_id
            if mid is None:
                raise ServiceError(400, ErrorCode.MODEL_NOT_FOUND, "no model loaded, call /models/load first")
            managed = self._models.get(mid)
            if managed is None:
                raise ServiceError(404, ErrorCode.MODEL_NOT_FOUND, f"model not found: {mid}")
            if managed.info.status == "error":
                reason = managed.info.error_message or "unknown error"
                raise ServiceError(503, ErrorCode.MODEL_NOT_READY, f"model load failed: {mid} — {reason}")
            if managed.info.status != "ready":
                raise ServiceError(
                    503,
                    ErrorCode.MODEL_NOT_READY,
                    f"model not ready: {mid} (status={managed.info.status})",
                )
            return managed, mid

    def list_models(self, tags: Optional[str] = None, backend: Optional[str] = None) -> ModelsListResponse:
        with self._lock:
            items: List[ModelInfo] = []
            loaded_ids: set = set()
            for m in self._models.values():
                if tags and tags not in m.info.capabilities:
                    continue
                if backend and m.info.backend != backend:
                    continue
                items.append(m.info)
                loaded_ids.add(m.info.model_id)
            # Include known but unloaded models (KNOWN_MODELS + auto-discovered)
            for mid, known in _get_all_known_models().items():
                if mid in loaded_ids:
                    continue
                caps = known.get("caps", [])
                if tags and tags not in caps:
                    continue
                items.append(ModelInfo(
                    model_id=mid,
                    config_path=known.get("config", ""),
                    capabilities=caps,
                    status="unloaded",
                ))
            return ModelsListResponse(data=items)

    def load_model(
        self,
        model_id: str,
        config_path: Optional[str] = None,
        model_path_override: str = "",
        lazy_load: bool = False,
    ) -> ModelLoadResponse:
        with self._lock:
            cached = self._models.get(model_id)
            if cached is not None and cached.info.status == "ready":
                cached_resp = ModelLoadResponse(
                    loaded=True,
                    model_id=model_id,
                    engine_state={
                        "backend": cached.info.backend,
                        "status": "ready",
                        "config_path": cached.config_path,
                    },
                )
                warmup_instance = cached.backend_instance
                warmup_config_path = cached.config_path
                warmup_caps = list(cached.info.capabilities)
            else:
                cached_resp = None
                warmup_instance = None
                warmup_config_path = ""
                warmup_caps = []

        if cached_resp is not None:
            if warmup_instance is not None:
                warmup_cfg = _materialize_config_for_runtime(warmup_config_path)
                with self._lock:
                    still = self._models.get(model_id)
                    if still is cached and still.backend_instance is warmup_instance:
                        _warmup_native_instance(
                            self._adapter,
                            warmup_instance,
                            warmup_cfg,
                            warmup_caps,
                            model_id=model_id,
                        )
            return cached_resp

        # 先释放其他已加载模型，腾出 AI cores
        self._release_other_models(model_id)

        # 解析 config_path：显式传入 > KNOWN_MODELS/已扫描的 yaml 查表
        all_known = _get_all_known_models()
        resolved_config = config_path or ""
        known = all_known.get(model_id)
        if not resolved_config and known:
            resolved_config = known["config"]
        if not resolved_config:
            raise ServiceError(
                400, ErrorCode.INVALID_ARGUMENT,
                f"config_path is required for unknown model_id '{model_id}'. "
                f"known models: {sorted(all_known.keys())}",
            )

        resolved_config = _resolve_config_path(resolved_config)
        runtime_config = _materialize_config_for_runtime(resolved_config)

        # capabilities 来源（优先级）：已注册 > 从 YAML 的 class 字段推断 > 默认 detect
        if known and known.get("caps"):
            capabilities = known["caps"]
        else:
            capabilities = _infer_capabilities_from_yaml(runtime_config)

        # 自动下载模型文件（如果不存在）
        _ensure_models_downloaded(model_id)
        _ensure_model_from_config_downloaded(runtime_config, model_path_override)

        # 调用 VisionServiceNative.create(config_path, model_path_override, lazy_load)
        instance = self._adapter.create_instance(runtime_config, model_path_override, lazy_load)
        if instance is not None:
            backend_name = "native"
            status = "ready"
            error_msg = None
        elif self._adapter.native_available:
            # native 可用但 create 失败
            backend_name = "native"
            status = "error"
            reason = self._adapter.last_create_error or "unknown error"
            error_msg = f"VisionServiceNative.create failed for config: {runtime_config}; reason: {reason}"
        else:
            # native 不可用，降级 mock
            backend_name = "mock"
            status = "ready"
            error_msg = None


        info = ModelInfo(
            model_id=model_id,
            config_path=resolved_config,
            capabilities=capabilities,
            defaults={"input_size": 640, "threshold": 0.25},
            status=status,
            backend=backend_name,
            error_message=error_msg,
        )
        # Load label names from config's label_file_path
        labels = _load_labels(runtime_config)

        managed = ManagedModel(
            info=info,
            config_path=resolved_config,
            model_path_override=model_path_override,
            backend_instance=instance,
            timing_enabled=True,
            timing_print_to_stdout=True,
            labels=labels,
        )

        if instance is not None:
            self._adapter.set_timing_options(instance, enabled=True, print_to_stdout=True)
            _warmup_native_instance(
                self._adapter, instance, runtime_config, capabilities, model_id=model_id
            )

        with self._lock:
            self._models[model_id] = managed
            if self._default_model_id is None and status == "ready":
                self._default_model_id = model_id

        engine_state = {"backend": backend_name, "status": status, "config_path": resolved_config}
        if error_msg:
            engine_state["error_message"] = error_msg

        return ModelLoadResponse(
            loaded=(status == "ready"),
            model_id=model_id,
            engine_state=engine_state,
        )

    def _release_other_models(self, keep_model_id: str) -> None:
        """Unload all loaded models except *keep_model_id* to free AI cores."""
        with self._lock:
            others = [(mid, m) for mid, m in self._models.items() if mid != keep_model_id]
        if others:
            logger.info("[load_model] releasing %d other model(s): %s",
                        len(others), [mid for mid, _ in others])
        else:
            logger.info("[load_model] no other models loaded, nothing to release")
        for mid, m in others:
            ok = self._adapter.release_instance(m.backend_instance)
            m.backend_instance = None
            logger.info("[load_model] released %s: %s", mid, ok)
            with self._lock:
                self._models.pop(mid, None)
                if self._default_model_id == mid:
                    self._default_model_id = None

    def unload_model(self, model_id: str) -> ModelUnloadResponse:
        with self._lock:
            managed = self._models.get(model_id)
            if managed is None:
                raise ServiceError(404, ErrorCode.MODEL_NOT_FOUND, f"model not found: {model_id}")
            instance = managed.backend_instance
            managed.backend_instance = None
            if not self._adapter.release_instance(instance):
                raise ServiceError(500, ErrorCode.INTERNAL_ERROR, f"failed to release model: {model_id}")
            del self._models[model_id]
            if self._default_model_id == model_id:
                self._default_model_id = next(iter(self._models), None)
        return ModelUnloadResponse(unloaded=True, model_id=model_id)

    def switch_model(
        self, model_id: Optional[str] = None, model_group: Optional[str] = None
    ) -> ModelSwitchResponse:
        with self._lock:
            if model_id:
                if model_id not in self._models:
                    raise ServiceError(404, ErrorCode.MODEL_NOT_FOUND, f"model not found: {model_id}")
                self._default_model_id = model_id
            if model_group:
                self._default_model_group = model_group
            return ModelSwitchResponse(
                switched=True,
                default_model_id=self._default_model_id,
                default_model_group=self._default_model_group,
                effective_scope="new_requests_only",
            )
