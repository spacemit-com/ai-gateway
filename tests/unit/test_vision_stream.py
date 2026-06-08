from __future__ import annotations

from spacemit_ai_gateway.domains.vision.models import ManagedModel
from spacemit_ai_gateway.domains.vision.schemas import ModelInfo
from spacemit_ai_gateway.domains.vision.stream import StreamSessionManager


class _FakeAdapter:
    def __init__(self) -> None:
        self.infer_kwargs = None

    def bytes_to_bgr(self, image_bytes: bytes) -> bytes:
        return image_bytes

    def infer_image(self, instance, img_bgr, **kwargs):
        self.infer_kwargs = kwargs
        return True, [{"bbox": [1, 2, 3, 4], "score": 0.9, "label": 0}]

    def _as_mapping(self, raw):
        return raw


class _FakeRegistry:
    def __init__(self) -> None:
        self.managed = ManagedModel(
            info=ModelInfo(model_id="yolov8n", capabilities=["detect"], status="ready"),
            backend_instance=object(),
        )

    def get_instance(self, model_id=None):
        return self.managed, model_id or "yolov8n"


def test_stream_session_accepts_thresholds_and_passes_them_to_infer() -> None:
    adapter = _FakeAdapter()
    manager = StreamSessionManager(adapter, _FakeRegistry())

    session = manager.create_session(model_id="yolov8n", conf=0.31, iou=0.52)
    result = manager.process_frame(session, b"fake-image")

    assert result.detections
    assert adapter.infer_kwargs == {"conf": 0.31, "iou": 0.52}


def test_update_session_thresholds_keeps_missing_values_unchanged() -> None:
    manager = StreamSessionManager(_FakeAdapter(), _FakeRegistry())
    session = manager.create_session(model_id="yolov8n", conf=0.25, iou=0.45)

    manager.update_session_thresholds(session, conf=0.4, iou=None)

    assert session.conf == 0.4
    assert session.iou == 0.45
