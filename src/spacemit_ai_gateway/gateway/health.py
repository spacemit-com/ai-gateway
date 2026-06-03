"""全局健康检查（聚合各域状态）。"""

from fastapi import APIRouter, Request

from ..common.ready_state import BackendReadyState
from ..domains.llm import service as llm_service

try:
    from ..domains.vision import api as vision_api
except ImportError:
    vision_api = None  # type: ignore[assignment]

router = APIRouter()

_LAZY_READY_STATES = {BackendReadyState.IDLE.value, "uninitialized", "unloaded"}


@router.get("/healthz", tags=["Health"])
async def healthz(request: Request):
    domains: dict[str, dict] = {}
    overall_ready = True

    for name, attr in [("asr", "asr_service"), ("tts", "tts_service"), ("vad", "vad_service")]:
        svc = getattr(request.app.state, attr, None)
        if svc is None:
            domains[name] = {"ready": False, "state": "uninitialized"}
            overall_ready = False
            continue
        info = await svc.healthz()
        domains[name] = info
        if (
            not info.get("ready", False)
            and info.get("state") not in _LAZY_READY_STATES
        ):
            overall_ready = False

    # LLM 域：idle 是正常初始状态，不影响 overall
    llm_svc = getattr(request.app.state, "llm_service", None)
    if llm_svc is not None:
        llm_info = await llm_svc.healthz()
    else:
        llm_info = llm_service.healthz()
    domains["llm"] = llm_info

    # VLM 域：视觉语言模型
    vlm_svc = getattr(request.app.state, "vlm_service", None)
    if vlm_svc is not None:
        domains["vlm"] = await vlm_svc.healthz()
    else:
        domains["vlm"] = {"ready": False, "state": "uninitialized"}
    vlm_info = domains["vlm"]
    if (
        not vlm_info.get("ready", False)
        and vlm_info.get("state") not in _LAZY_READY_STATES
    ):
        overall_ready = False

    # vision 当前为独立域实现（自管理 registry/service），从 vision 模块读取健康摘要。
    if vision_api is not None:
        vision_info = vision_api.domain_health_summary()
    else:
        vision_info = {"ready": False, "state": "uninitialized"}
    domains["vision"] = vision_info
    if (
        not vision_info.get("ready", False)
        and vision_info.get("state") not in _LAZY_READY_STATES
    ):
        overall_ready = False

    return {
        "status": "ok" if overall_ready else "degraded",
        "domains": domains,
    }
