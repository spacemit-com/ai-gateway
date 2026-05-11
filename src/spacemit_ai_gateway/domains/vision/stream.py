from __future__ import annotations

import asyncio
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .adapters.native import NativeAdapter, ServiceError
from .models import ManagedModel, ModelRegistry
from .schemas import (
    ClassifyItem,
    DetectionItem,
    EmotionItem,
    ErrorCode,
    PoseItem,
    PoseKeypoint,
    StreamDeleteResponse,
    StreamFrameResult,
    TimingInfo,
)


@dataclass
class StreamSession:
    stream_id: str
    model_id: str
    managed: ManagedModel
    fps_limit: int = 30
    priority: int = 0
    expires_at: float = 0.0
    created_at: float = field(default_factory=time.time)
    frame_count: int = 0
    cancelled: asyncio.Event = field(default_factory=asyncio.Event)


class StreamSessionManager:
    """管理流式推理会话的生命周期。"""

    DEFAULT_EXPIRE_SECONDS = 300
    MAX_SESSIONS = 16

    def __init__(self, adapter: NativeAdapter, registry: ModelRegistry) -> None:
        self._lock = threading.RLock()
        self._sessions: Dict[str, StreamSession] = {}
        self._adapter = adapter
        self._registry = registry

    def create_session(
        self,
        model_id: Optional[str] = None,
        model_group: Optional[str] = None,
        fps_limit: Optional[int] = None,
        priority: Optional[int] = None,
    ) -> StreamSession:
        """从 WS start signal 或内部调用创建会话，返回 StreamSession。"""
        with self._lock:
            if len(self._sessions) >= self.MAX_SESSIONS:
                raise ServiceError(429, ErrorCode.TOO_MANY_REQUESTS, "too many active stream sessions")

        managed, resolved_id = self._registry.get_instance(model_id)
        fps = min(fps_limit or 30, 60)
        stream_id = f"vision_stream_{uuid.uuid4().hex[:12]}"

        session = StreamSession(
            stream_id=stream_id,
            model_id=resolved_id,
            managed=managed,
            fps_limit=fps,
            priority=priority or 0,
            expires_at=time.time() + self.DEFAULT_EXPIRE_SECONDS,
        )

        with self._lock:
            self._sessions[stream_id] = session

        return session

    def build_ready_event(self, session: StreamSession, model_group: Optional[str] = None) -> dict:
        return {
            "event": "ready",
            "stream_id": session.stream_id,
            "params": {
                "model_group": model_group or session.model_id,
                "fps_limit": session.fps_limit,
                "priority": "normal" if session.priority == 0 else str(session.priority),
            },
        }

    def get_session(self, stream_id: str) -> StreamSession:
        with self._lock:
            session = self._sessions.get(stream_id)
            if session is None:
                raise ServiceError(404, ErrorCode.SERVICE_NOT_FOUND, f"stream session not found: {stream_id}")
            if time.time() > session.expires_at:
                del self._sessions[stream_id]
                raise ServiceError(410, ErrorCode.SERVICE_NOT_FOUND, f"stream session expired: {stream_id}")
            return session

    def delete_session(self, stream_id: str) -> StreamDeleteResponse:
        with self._lock:
            session = self._sessions.pop(stream_id, None)
            if session is None:
                raise ServiceError(404, ErrorCode.SERVICE_NOT_FOUND, f"stream session not found: {stream_id}")
            session.cancelled.set()
        return StreamDeleteResponse(released=True, stream_id=stream_id)

    def cancel_sessions_for_model(self, model_id: str) -> int:
        cancelled = 0
        with self._lock:
            to_remove = [sid for sid, s in self._sessions.items() if s.model_id == model_id]
            for sid in to_remove:
                self._sessions.pop(sid).cancelled.set()
                cancelled += 1
        return cancelled

    def process_frame(
        self, session: StreamSession, image_bytes: bytes, timestamp_ms: Optional[int] = None,
    ) -> StreamFrameResult:
        """对单帧图像执行推理，返回检测/跟踪结果。"""
        session.frame_count += 1

        if session.managed.backend_instance is not None:
            return self._process_native(session, image_bytes, timestamp_ms)

        return self._process_mock(session, image_bytes, timestamp_ms)

    def _process_native(
        self, session: StreamSession, image_bytes: bytes, timestamp_ms: Optional[int],
    ) -> StreamFrameResult:
        try:
            img_bgr = self._adapter.bytes_to_bgr(image_bytes)
            ok, raw_results = self._adapter.infer_image(session.managed.backend_instance, img_bgr)
            if not ok:
                raise ServiceError(500, ErrorCode.MODEL_RUNTIME_ERROR, "stream frame inference failed")

            raw_items = self._extract_raw_items(raw_results)
            caps = session.managed.info.capabilities if session.managed.info else []
            labels = session.managed.labels

            detections = self._build_detections(raw_items, labels) if "detect" in caps or "track" in caps else []
            pose = self._build_poses(raw_items) if "pose" in caps else None
            emotion = self._build_emotions(raw_items, labels) if "emotion" in caps else None
            classify = self._build_classifications(raw_items, labels) if "classify" in caps else None

            timing = None
            if session.managed.timing_enabled:
                timing = self._adapter.get_last_timing(session.managed.backend_instance)

            return StreamFrameResult(
                stream_id=session.stream_id,
                timestamp_ms=timestamp_ms or int(time.time() * 1000),
                detections=detections,
                pose=pose,
                emotion=emotion,
                classify=classify,
                timing=timing,
            )
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError(500, ErrorCode.MODEL_RUNTIME_ERROR, f"stream frame error: {exc}") from exc

    def _process_mock(
        self, session: StreamSession, image_bytes: bytes, timestamp_ms: Optional[int],
    ) -> StreamFrameResult:
        import hashlib
        digest_int = int(hashlib.sha256(image_bytes).hexdigest()[:8], 16)
        score = round(0.5 + ((digest_int % 5000) / 10000.0), 4)
        x1 = float((digest_int % 120) + 10)
        y1 = float((digest_int % 90) + 8)
        detections = [
            DetectionItem(
                x1=x1, y1=y1, x2=x1 + 180.0, y2=y1 + 260.0,
                score=score, label=0, track_id=session.frame_count % 10,
            )
        ]
        timing = self._adapter.mock_timing(image_bytes, purpose="stream")
        return StreamFrameResult(
            stream_id=session.stream_id,
            timestamp_ms=timestamp_ms or int(time.time() * 1000),
            detections=detections,
            timing=TimingInfo(detect_ms=timing.preprocess_ms, track_ms=timing.postprocess_ms, infer_ms=timing.infer_ms),
        )

    def _extract_raw_items(self, raw_results: Any) -> List[Dict]:
        if raw_results is None:
            return []
        if not isinstance(raw_results, (list, tuple)):
            raw_results = [raw_results]
        items = []
        for raw in raw_results:
            m = self._adapter._as_mapping(raw)
            if m:
                if {"x1", "y1", "x2", "y2"}.issubset(m.keys()) and "bbox" not in m:
                    m["bbox"] = [m["x1"], m["y1"], m["x2"], m["y2"]]
                items.append(m)
        return items

    @staticmethod
    def _build_detections(items: List[Dict], labels: Optional[List[str]] = None) -> List[DetectionItem]:
        result = []
        for m in items:
            bbox = m.get("bbox", [0, 0, 0, 0])
            if not bbox or len(bbox) < 4:
                continue
            label_idx = int(m.get("class_id", m.get("class_idx", m.get("label", 0))))
            label_name = m.get("class_name")
            if not label_name and labels and 0 <= label_idx < len(labels):
                label_name = labels[label_idx]
            result.append(DetectionItem(
                x1=float(bbox[0]), y1=float(bbox[1]),
                x2=float(bbox[2]), y2=float(bbox[3]),
                score=float(m.get("score", m.get("confidence", 0))),
                label=label_idx, label_name=label_name,
                track_id=int(m.get("track_id", -1)),
            ))
        return result

    @staticmethod
    def _build_poses(items: List[Dict]) -> List[PoseItem]:
        result = []
        for m in items:
            raw_kps = m.get("keypoints") or m.get("landmarks") or m.get("kpts") or m.get("pose") or []
            keypoints: List[PoseKeypoint] = []
            if raw_kps:
                if isinstance(raw_kps[0], dict):
                    keypoints = [PoseKeypoint(x=float(k.get("x", 0)), y=float(k.get("y", 0)),
                                              visibility=float(k.get("visibility", 1.0))) for k in raw_kps]
                elif hasattr(raw_kps[0], "x"):
                    keypoints = [PoseKeypoint(x=float(k.x), y=float(k.y),
                                              visibility=float(getattr(k, "visibility", 1.0))) for k in raw_kps]
                else:
                    for i in range(0, len(raw_kps) - 2, 3):
                        keypoints.append(PoseKeypoint(x=float(raw_kps[i]), y=float(raw_kps[i+1]),
                                                      visibility=float(raw_kps[i+2])))
            result.append(PoseItem(keypoints=keypoints, score=float(m.get("score", m.get("confidence", 0)))))
        return result

    @staticmethod
    def _build_emotions(items: List[Dict], labels: Optional[List[str]] = None) -> List[EmotionItem]:
        result = []
        for m in items:
            label_str = str(m.get("label", m.get("class_name", "unknown")))
            if label_str.isdigit() and labels:
                idx = int(label_str)
                if 0 <= idx < len(labels):
                    label_str = labels[idx]
            result.append(EmotionItem(label=label_str, score=float(m.get("score", m.get("confidence", 0)))))
        return result

    @staticmethod
    def _build_classifications(items: List[Dict], labels: Optional[List[str]] = None) -> List[ClassifyItem]:
        result = []
        for m in items:
            label_idx = int(m.get("class_id", m.get("class_idx", m.get("label", 0))))
            label_name = m.get("class_name")
            if not label_name and labels and 0 <= label_idx < len(labels):
                label_name = labels[label_idx]
            result.append(ClassifyItem(label=label_idx, label_name=label_name,
                                       score=float(m.get("score", m.get("confidence", 0)))))
        return result
