from __future__ import annotations

import numpy as np

from .adapters.native import NativeAdapter, ServiceError
from .models import ModelRegistry
from .schemas import ErrorCode, SequenceRequest, SequenceResponse


SEQUENCE_CLASS_NAMES = ["normal", "fall_down", "sit_down", "stand_up"]


def infer_sequence(
    adapter: NativeAdapter,
    registry: ModelRegistry,
    req: SequenceRequest,
) -> SequenceResponse:
    managed, resolved_id = registry.get_instance(req.model_id)

    if not req.sequence_data:
        raise ServiceError(400, ErrorCode.INVALID_SEQUENCE_INPUT, "sequence_data is required")

    if managed.backend_instance is not None:
        try:
            pts = np.array(req.sequence_data, dtype=np.float32)
            pts = np.ascontiguousarray(pts)
            window = req.window_size or len(req.sequence_data)
            ok, result = adapter.infer_sequence(managed.backend_instance, pts, window, window)
            if not ok:
                raise ServiceError(500, ErrorCode.MODEL_RUNTIME_ERROR, "sequence inference failed")

            m = adapter._as_mapping(result)
            scores_raw = m.get("scores", [])
            scores = [float(s) for s in scores_raw] if scores_raw else [0.0] * len(SEQUENCE_CLASS_NAMES)
            top_idx = scores.index(max(scores)) if scores else 0
            top_label = SEQUENCE_CLASS_NAMES[top_idx] if top_idx < len(SEQUENCE_CLASS_NAMES) else "unknown"

            return SequenceResponse(
                model_id=resolved_id,
                scores=scores,
                top_label=top_label,
                labels=SEQUENCE_CLASS_NAMES,
            )
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError(500, ErrorCode.MODEL_RUNTIME_ERROR, f"native sequence error: {exc}") from exc

    # mock: 基于序列数据生成伪结果
    n = len(req.sequence_data)
    avg_val = sum(req.sequence_data) / n if n > 0 else 0.0
    scores = [0.0] * len(SEQUENCE_CLASS_NAMES)
    # 简单 mock：根据平均值分配分数
    fall_idx = 1
    normal_idx = 0
    if avg_val > 0.5:
        scores[fall_idx] = 0.85
        scores[normal_idx] = 0.15
    else:
        scores[normal_idx] = 0.80
        scores[fall_idx] = 0.10
        scores[2] = 0.05
        scores[3] = 0.05

    top_idx = scores.index(max(scores))
    return SequenceResponse(
        model_id=resolved_id,
        scores=[round(s, 4) for s in scores],
        top_label=SEQUENCE_CLASS_NAMES[top_idx],
        labels=SEQUENCE_CLASS_NAMES,
    )
