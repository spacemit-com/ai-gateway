"""全局空闲端口池，供各 adapter 申请/归还端口使用。"""
import logging
import socket
import threading

from ..app.settings import get_settings as _get_settings

logger = logging.getLogger(__name__)


def _is_port_free(port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(("", port))
            return True
        except OSError:
            return False


class PortPool:
    """线程安全的端口池。

    初始化时扫描 [start, end] 范围内所有空闲端口并入池。
    acquire() 取出一个端口，release(port) 归还。
    """

    def __init__(self, start: int = 8020, end: int = 8040):
        self._lock = threading.Lock()
        self._free: list[int] = [p for p in range(start, end + 1) if _is_port_free(p)]
        self._in_use: set[int] = set()
        logger.debug("PortPool initialized: %d ports available (%d-%d)", len(self._free), start, end)

    def acquire(self) -> int:
        """申请一个空闲端口，无可用端口时抛出 RuntimeError。"""
        with self._lock:
            while self._free:
                port = self._free.pop(0)
                if _is_port_free(port):
                    self._in_use.add(port)
                    logger.debug("PortPool: acquired port %d", port)
                    return port
                # 端口已被外部占用，跳过
                logger.debug("PortPool: port %d no longer free, skipping", port)
            raise RuntimeError("PortPool exhausted: no free ports available")

    def release(self, port: int) -> None:
        """归还端口回池。"""
        with self._lock:
            self._in_use.discard(port)
            if port not in self._free:
                self._free.append(port)
                self._free.sort()
            logger.debug("PortPool: released port %d", port)

    @property
    def available(self) -> int:
        with self._lock:
            return len(self._free)


_s = _get_settings()
port_pool = PortPool(
    start=_s.llm.port_pool.start,
    end=_s.llm.port_pool.end,
)
