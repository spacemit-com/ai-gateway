from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from .adapters.native import NativeAdapter, ServiceError
from .models import ModelRegistry
from .schemas import (
    DetectionItem,
    ClassifyItem,
    EmotionItem,
    ErrorCode,
    InferenceResponse,
    InferenceResults,
    PoseItem,
    PoseKeypoint,
)


VALID_TASKS = {"detect", "classify", "pose", "segment", "emotion"}


class VisionService:
    """核心业务编排层：组合 ModelRegistry + NativeAdapter。"""

    def __init__(self, adapter: NativeAdapter, registry: ModelRegistry) -> None:
        self.adapter = adapter
        self.registry = registry

    def resolve_image_bytes(
        self,
        file_bytes: Optional[bytes] = None,
        image_base64: Optional[str] = None,
        image_url: Optional[str] = None,
        handle: Optional[str] = None,
    ) -> bytes:
        # file 和 handle 二选一
        sources = sum(1 for s in (file_bytes, image_base64, image_url, handle) if s)
        if sources == 0:
            raise ServiceError(
                400,
                ErrorCode.INVALID_IMAGE_INPUT,
                "one of file/handle/image_base64/image_url is required",
            )
        if file_bytes and handle:
            raise ServiceError(400, ErrorCode.INVALID_ARGUMENT, "file and handle are mutually exclusive")

        if file_bytes:
            return file_bytes
        if image_base64:
            return self.adapter.decode_base64_image(image_base64)
        if image_url:
            return self.adapter.load_url_bytes(image_url)
        if handle:
            return self._resolve_handle(handle)
        raise ServiceError(400, ErrorCode.INVALID_IMAGE_INPUT, "one of file/handle/image_base64/image_url is required")

    @staticmethod
    def _resolve_handle(handle: str) -> bytes:
        """从对象存储句柄或本地路径加载图像。"""
        import os
        # 本地路径
        if os.path.isfile(handle):
            with open(handle, "rb") as f:
                return f.read()
        # 可扩展：对接 S3/OSS 等对象存储
        raise ServiceError(400, ErrorCode.INVALID_IMAGE_INPUT, f"handle not resolvable: {handle}")

    def infer(
        self,
        tasks: List[str],
        image_bytes: bytes,
        model_id: Optional[str] = None,
        render: bool = False,
        render_mode: Optional[str] = None,
        conf: Optional[float] = None,
        iou: Optional[float] = None,
    ) -> InferenceResponse:
        if not tasks:
            raise ServiceError(400, ErrorCode.INVALID_ARGUMENT, "tasks[] is required and must not be empty")
        unknown = set(tasks) - VALID_TASKS
        if unknown:
            raise ServiceError(
                400,
                ErrorCode.INVALID_ARGUMENT,
                f"unsupported tasks: {sorted(unknown)}. valid: {sorted(VALID_TASKS)}",
            )

        managed, resolved_id = self.registry.get_instance(model_id)

        if managed.backend_instance is not None:
            resp = self._infer_native(managed, resolved_id, tasks, image_bytes, conf=conf, iou=iou)
        else:
            resp = self._infer_mock(resolved_id, tasks, image_bytes)

        if render:
            rendered_url = self._render(managed, image_bytes, render_mode)
            resp.rendered_image_url = rendered_url

        return resp

    def _render(self, managed, image_bytes: bytes, render_mode: Optional[str] = None) -> str:
        """服务端渲染叠框图，返回产物路径。"""
        import os
        import time

        artifact_dir = "/tmp/vision_render"
        os.makedirs(artifact_dir, exist_ok=True)
        filename = f"infer_{int(time.time() * 1000)}.jpg"
        filepath = os.path.join(artifact_dir, filename)

        if managed.backend_instance is not None:
            try:
                if hasattr(managed.backend_instance, "supports_draw") and managed.backend_instance.supports_draw():
                    import cv2
                    img_bgr = self.adapter.bytes_to_bgr(image_bytes)
                    result = managed.backend_instance.draw(img_bgr)
                    if isinstance(result, tuple) and len(result) == 2:
                        _, drawn_img = result
                        cv2.imwrite(filepath, drawn_img)
                        return f"/artifacts/vision/render/{filename}"
            except Exception:
                pass

        # fallback: 保存原图
        with open(filepath, "wb") as f:
            f.write(image_bytes)
        return f"/artifacts/vision/render/{filename}"

    def _infer_native(
        self,
        managed,
        resolved_id: str,
        tasks: List[str],
        image_bytes: bytes,
        conf: Optional[float] = None,
        iou: Optional[float] = None,
    ) -> InferenceResponse:
        try:
            img_bgr = self.adapter.bytes_to_bgr(image_bytes)
            ok, raw_results = self.adapter.infer_image(
                managed.backend_instance, img_bgr, conf=conf, iou=iou,
            )
            if not ok:
                raise ServiceError(500, ErrorCode.MODEL_RUNTIME_ERROR, "inference failed")

            results = InferenceResults()
            raw_items = self._extract_raw_items(raw_results)
            labels = managed.labels

            for task in tasks:
                if task == "detect":
                    results.detect = self._build_detections(raw_items, labels)
                elif task == "classify":
                    results.classify = self._build_classifications(raw_items, labels)
                elif task == "emotion":
                    results.emotion = self._build_emotions(raw_items, labels)
                elif task == "pose":
                    results.pose = self._build_poses(raw_items)
                elif task == "segment":
                    results.segment = self._build_segments(raw_items, labels)

            timing = None
            if managed.timing_enabled:
                timing = self.adapter.get_last_timing(managed.backend_instance)

            return InferenceResponse(model_id=resolved_id, results=results, timing=timing)
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError(500, ErrorCode.MODEL_RUNTIME_ERROR, f"native inference error: {exc}") from exc

    def _infer_mock(self, resolved_id: str, tasks: List[str], image_bytes: bytes) -> InferenceResponse:
        digest_int = int(hashlib.sha256(image_bytes).hexdigest()[:8], 16)
        labels_pool = ["person", "car", "fire", "smoke", "face"]
        results = InferenceResults()

        for task in tasks:
            if task == "detect":
                label_idx = digest_int % len(labels_pool)
                score = round(0.5 + ((digest_int % 5000) / 10000.0), 4)
                x1 = float((digest_int % 120) + 10)
                y1 = float((digest_int % 90) + 8)
                results.detect = [
                    DetectionItem(x1=x1, y1=y1, x2=x1 + 180.0, y2=y1 + 260.0, score=score,
                                  label=label_idx, label_name=labels_pool[label_idx])
                ]
            elif task == "classify":
                mock_class_names = ["tench", "goldfish", "tiger shark", "hammerhead", "electric ray",
                                    "stingray", "cock", "hen", "ostrich", "brambling"]
                cls_idx = digest_int % 10
                results.classify = [
                    ClassifyItem(
                        label=cls_idx,
                        label_name=mock_class_names[cls_idx],
                        score=round(0.7 + (digest_int % 300) / 1000.0, 4),
                    )
                ]
            elif task == "emotion":
                emotions = ["happy", "sad", "angry", "neutral", "surprise"]
                results.emotion = [EmotionItem(label=emotions[digest_int % len(emotions)], score=0.85)]
            elif task == "pose":
                kps = [
                    PoseKeypoint(x=float(50 + (digest_int % 100)), y=float(30 + (digest_int % 80)), visibility=0.9)
                    for _ in range(17)
                ]
                results.pose = [PoseItem(keypoints=kps, score=0.88)]
            elif task == "segment":
                results.segment = [{"mask_rle": "mock", "area": 12345, "class_id": digest_int % 5}]

        timing = self.adapter.mock_timing(image_bytes, purpose="infer")
        return InferenceResponse(model_id=resolved_id, results=results, timing=timing)

    def _extract_raw_items(self, raw_results) -> List[Dict[str, Any]]:
        if raw_results is None:
            return []
        if not isinstance(raw_results, (list, tuple)):
            raw_results = [raw_results]
        items = []
        for raw in raw_results:
            m = self.adapter._as_mapping(raw)
            if m:
                if {"x1", "y1", "x2", "y2"}.issubset(m.keys()) and "bbox" not in m:
                    m["bbox"] = [m["x1"], m["y1"], m["x2"], m["y2"]]
                items.append(m)
        return items

    @staticmethod
    def _build_detections(items: List[Dict[str, Any]], labels: Optional[List[str]] = None) -> List[DetectionItem]:
        result = []
        for m in items:
            bbox = m.get("bbox", [0, 0, 0, 0])
            label_idx = int(m.get("class_id", m.get("class_idx", m.get("label", 0))))
            label_name = m.get("label_name") or m.get("class_name")
            if not label_name and labels and 0 <= label_idx < len(labels):
                label_name = labels[label_idx]
            result.append(DetectionItem(
                x1=float(bbox[0]) if len(bbox) > 0 else 0,
                y1=float(bbox[1]) if len(bbox) > 1 else 0,
                x2=float(bbox[2]) if len(bbox) > 2 else 0,
                y2=float(bbox[3]) if len(bbox) > 3 else 0,
                score=float(m.get("score", m.get("confidence", 0))),
                label=label_idx,
                label_name=label_name,
                track_id=int(m.get("track_id", -1)),
            ))
        return result

    @staticmethod
    def _build_classifications(items: List[Dict[str, Any]], labels: Optional[List[str]] = None) -> List[ClassifyItem]:
        result = []
        for m in items:
            label_idx = int(m.get("class_id", m.get("class_idx", m.get("label", 0))))
            label_name = m.get("label_name") or m.get("class_name")
            if not label_name and labels and 0 <= label_idx < len(labels):
                label_name = labels[label_idx]
            result.append(ClassifyItem(
                label=label_idx,
                label_name=label_name,
                score=float(m.get("score", m.get("confidence", 0))),
            ))
        return result

    @staticmethod
    def _build_emotions(items: List[Dict[str, Any]], labels: Optional[List[str]] = None) -> List[EmotionItem]:
        result = []
        for m in items:
            label_str = str(m.get("label", m.get("class_name", "unknown")))
            # If label is numeric and we have labels list, map it
            if label_str.isdigit() and labels:
                label_idx = int(label_str)
                if 0 <= label_idx < len(labels):
                    label_str = labels[label_idx]
            result.append(EmotionItem(
                label=label_str,
                score=float(m.get("score", m.get("confidence", 0))),
            ))
        return result

    @staticmethod
    def _build_poses(items: List[Dict[str, Any]]) -> List[PoseItem]:
        result = []
        for m in items:
            raw_kps = (
                m.get("keypoints")
                or m.get("landmarks")
                or m.get("kpts")
                or m.get("pose")
                or []
            )
            keypoints = VisionService._normalize_keypoints(raw_kps)
            result.append(PoseItem(
                keypoints=keypoints,
                score=float(m.get("score", m.get("confidence", 0))),
            ))
        return result

    @staticmethod
    def _normalize_keypoints(raw_kps: Any) -> List[PoseKeypoint]:
        keypoints: List[PoseKeypoint] = []
        if not raw_kps:
            return keypoints

        # 扁平数组: [x, y, vis, x, y, vis, ...]
        if isinstance(raw_kps, (list, tuple)) and raw_kps and not isinstance(raw_kps[0], dict):
            # 兼容对象数组（如 pybind 包装对象）
            if hasattr(raw_kps[0], "x") and hasattr(raw_kps[0], "y"):
                for kp in raw_kps:
                    keypoints.append(PoseKeypoint(
                        x=float(getattr(kp, "x", 0)),
                        y=float(getattr(kp, "y", 0)),
                        visibility=float(getattr(kp, "visibility", 1.0)),
                    ))
                return keypoints

            for i in range(0, len(raw_kps) - 2, 3):
                keypoints.append(PoseKeypoint(
                    x=float(raw_kps[i]),
                    y=float(raw_kps[i + 1]),
                    visibility=float(raw_kps[i + 2]),
                ))
            return keypoints

        for kp in raw_kps:
            if isinstance(kp, dict):
                keypoints.append(PoseKeypoint(
                    x=float(kp.get("x", 0)),
                    y=float(kp.get("y", 0)),
                    visibility=float(kp.get("visibility", 1.0)),
                ))
            elif hasattr(kp, "x") and hasattr(kp, "y"):
                keypoints.append(PoseKeypoint(
                    x=float(getattr(kp, "x", 0)),
                    y=float(getattr(kp, "y", 0)),
                    visibility=float(getattr(kp, "visibility", 1.0)),
                ))
        return keypoints

    @staticmethod
    def _build_segments(items: List[Dict[str, Any]], labels: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        result = []
        for m in items:
            seg: Dict[str, Any] = {}
            if "mask" in m:
                mask = m["mask"]
                try:
                    import numpy as np
                    if isinstance(mask, np.ndarray):
                        seg["mask"] = {
                            "shape": list(mask.shape),
                            "dtype": str(mask.dtype),
                            "nonzero": int(np.count_nonzero(mask)),
                        }
                        # Extract contour polygons from binary mask for frontend rendering
                        if "contour" not in m:
                            try:
                                import cv2
                                mask_u8 = (mask > 0).astype(np.uint8) * 255
                                contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                                polys = []
                                for c in contours:
                                    if len(c) >= 3:
                                        polys.append(c.reshape(-1, 2).tolist())
                                if polys:
                                    seg["contour"] = polys
                            except Exception:
                                pass
                    else:
                        seg["mask"] = mask
                except Exception:
                    seg["mask"] = str(mask)
            if "contour" in m:
                seg["contour"] = m["contour"]
            if "area" in m:
                seg["area"] = m["area"]
            label_idx, label_name = VisionService._resolve_item_label(m, labels, default=-1)
            seg["class_id"] = label_idx
            if label_name:
                seg["label_name"] = label_name
            seg["score"] = float(m.get("score", m.get("confidence", 0)))
            result.append(seg)
        return result

    @staticmethod
    def _resolve_item_label(
        item: Dict[str, Any],
        labels: Optional[List[str]] = None,
        *,
        default: int = 0,
    ) -> tuple[int, Optional[str]]:
        raw_label = None
        for key in ("class_id", "class_idx", "label"):
            value = item.get(key)
            if value is not None:
                raw_label = value
                break

        label_name = item.get("label_name") or item.get("class_name")
        label_idx = default

        if raw_label is not None:
            try:
                label_idx = int(raw_label)
            except (TypeError, ValueError):
                raw_label_name = str(raw_label)
                if not label_name:
                    label_name = raw_label_name
                if labels:
                    try:
                        label_idx = labels.index(raw_label_name)
                    except ValueError:
                        label_idx = default

        if not label_name and labels and 0 <= label_idx < len(labels):
            label_name = labels[label_idx]

        return label_idx, label_name
