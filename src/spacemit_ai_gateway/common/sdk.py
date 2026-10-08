"""SDK 可用性判断。"""

from __future__ import annotations

import importlib.util


def sdk_installed(module: str) -> bool:
    """SDK 是否已安装（不导入）。

    没装 SDK 的开发环境里 ASR/TTS/VAD 走 mock；装了 SDK 的设备上加载失败要如实报错，
    不能用 mock 的假结果冒充成功。
    """
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):  # sys.modules[module] is None 时 find_spec 抛 ValueError
        return False
