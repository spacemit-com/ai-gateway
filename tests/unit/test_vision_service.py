from __future__ import annotations

from spacemit_ai_gateway.domains.vision.service import VisionService


def test_build_segments_uses_label_fallback() -> None:
    segments = VisionService._build_segments(
        [{"label": 2, "score": 0.9, "mask": "m"}],
        labels=["person", "bicycle", "car"],
    )

    assert segments[0]["class_id"] == 2
    assert segments[0]["label_name"] == "car"
    assert segments[0]["score"] == 0.9


def test_build_segments_keeps_native_label_name() -> None:
    segments = VisionService._build_segments(
        [{"class_idx": 5, "class_name": "bus", "confidence": 0.7}],
        labels=["person"],
    )

    assert segments[0]["class_id"] == 5
    assert segments[0]["label_name"] == "bus"
    assert segments[0]["score"] == 0.7


def test_build_segments_missing_class_does_not_default_to_person() -> None:
    segments = VisionService._build_segments([{"score": 0.4}], labels=["person"])

    assert segments[0]["class_id"] == -1
    assert segments[0].get("label_name") != "person"
