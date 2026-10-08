"""错误码清单与模型故障查询接口。"""

from typing import Optional

from fastapi import APIRouter, Query

from ..common.error_catalog import CATALOG, NOTES
from ..common.error_log import query_faults

router = APIRouter(tags=["Errors"])


@router.get("/v1/errors", summary="错误码清单：阶段、触发条件、是否可重试、建议处理")
async def list_error_codes() -> dict:
    return {"errors": CATALOG, "notes": NOTES}


@router.get("/v1/errors/recent", summary="最近的模型故障（下载/加载/推理），可按域、模型、时间过滤，新的在前")
async def recent_errors(
    domain: Optional[str] = Query(None, description="asr / tts / vad / vision / llm / embed / rerank / vlm"),
    model: Optional[str] = Query(None, description="模型 ID"),
    since: Optional[float] = Query(None, description="只返回该 Unix 时间戳之后的记录（用于增量拉取）"),
    limit: int = Query(100, ge=1, le=2000),
) -> dict:
    return {"errors": await query_faults(domain=domain, model=model, since=since, limit=limit)}
