"""Backend 就绪状态枚举。

用于 healthz 汇报 backend 生命周期：
- INITIALIZING: 构造函数里（极短暂）
- WARMING_UP: 构造成功，正在预热模型/建立连接
- READY: 可以正常服务
- DEGRADED: SDK 不可用或 Engine 初始化失败，降级为 mock
- FAILED: 彻底不可用（预留，当前未使用）
"""

from enum import Enum


class BackendReadyState(str, Enum):
    INITIALIZING = "initializing"
    WARMING_UP = "warming_up"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"

    @property
    def is_serving(self) -> bool:
        return self in (BackendReadyState.READY, BackendReadyState.DEGRADED)
