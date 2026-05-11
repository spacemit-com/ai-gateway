"""系统资源监控 + AI 调用事件端点。"""

from __future__ import annotations

import time

import psutil
from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/api", tags=["System"])

psutil.cpu_percent(interval=None, percpu=True)


@router.get("/stats")
async def system_stats():
    cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
    cpu = sum(cpu_per_core) / len(cpu_per_core) if cpu_per_core else 0.0
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    dio = psutil.disk_io_counters()
    return {
        "timestamp": time.time(),
        "cpu_percent": cpu,
        "cpu_per_core": cpu_per_core,
        "memory": {
            "used_bytes": mem.used,
            "total_bytes": mem.total,
            "percent": mem.percent,
        },
        "disk": {
            "used_bytes": disk.used,
            "total_bytes": disk.total,
            "percent": disk.percent,
        },
        "network": {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
        },
        "disk_io": {
            "read_bytes": dio.read_bytes if dio else 0,
            "write_bytes": dio.write_bytes if dio else 0,
        },
    }


@router.get("/events")
async def get_events(
    request: Request,
    since: float = Query(default=0, description="Unix timestamp"),
):
    store = request.app.state.event_store
    return store.since(since)
