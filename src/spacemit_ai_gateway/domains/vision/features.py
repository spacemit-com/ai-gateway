from __future__ import annotations

import math
from typing import List, Optional

from .adapters.native import NativeAdapter, ServiceError
from .models import ModelRegistry
from .schemas import ErrorCode, FeatureResponse, TimingInfo


def infer_embedding(
    adapter: NativeAdapter,
    registry: ModelRegistry,
    image_bytes: bytes,
    model_id: Optional[str] = None,
) -> FeatureResponse:
    managed, resolved_id = registry.get_instance(model_id)

    if managed.backend_instance is not None:
        try:
            img_bgr = adapter.bytes_to_bgr(image_bytes)
            vector = adapter.infer_embedding(managed.backend_instance, img_bgr)
            if vector is None:
                raise ServiceError(500, ErrorCode.MODEL_RUNTIME_ERROR, "embedding inference failed")
            timing = None
            if managed.timing_enabled:
                timing = adapter.get_last_timing(managed.backend_instance)
            return FeatureResponse(model_id=resolved_id, embedding=vector, timing=timing)
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError(500, ErrorCode.MODEL_RUNTIME_ERROR, f"native embedding error: {exc}") from exc

    # mock
    vector = adapter.mock_embedding(image_bytes)
    timing = adapter.mock_timing(image_bytes, purpose="embedding")
    return FeatureResponse(
        model_id=resolved_id,
        embedding=vector,
        timing=TimingInfo(embedding_ms=timing.infer_ms, infer_ms=timing.infer_ms),
    )


def compute_similarity(
    adapter: NativeAdapter,
    registry: ModelRegistry,
    image_bytes_a: bytes,
    image_bytes_b: Optional[bytes] = None,
    vector_b: Optional[List[float]] = None,
    model_id: Optional[str] = None,
) -> FeatureResponse:
    managed, resolved_id = registry.get_instance(model_id)

    # 获取 embedding_a
    resp_a = infer_embedding(adapter, registry, image_bytes_a, model_id)
    emb_a = resp_a.embedding
    if emb_a is None:
        raise ServiceError(500, ErrorCode.MODEL_RUNTIME_ERROR, "failed to compute embedding for file")

    # 获取 embedding_b
    if vector_b is not None:
        emb_b = vector_b
    elif image_bytes_b is not None:
        resp_b = infer_embedding(adapter, registry, image_bytes_b, model_id)
        emb_b = resp_b.embedding
        if emb_b is None:
            raise ServiceError(500, ErrorCode.MODEL_RUNTIME_ERROR, "failed to compute embedding for file_b")
    else:
        raise ServiceError(400, ErrorCode.INVALID_ARGUMENT, "similarity requires file_b or vector_b")

    if len(emb_a) != len(emb_b):
        raise ServiceError(400, ErrorCode.INVALID_ARGUMENT, "embedding dimensions must match")

    dot = sum(a * b for a, b in zip(emb_a, emb_b))
    na = math.sqrt(sum(a * a for a in emb_a))
    nb = math.sqrt(sum(b * b for b in emb_b))
    similarity = dot / (na * nb) if na > 0 and nb > 0 else 0.0

    return FeatureResponse(model_id=resolved_id, similarity=round(similarity, 6))
