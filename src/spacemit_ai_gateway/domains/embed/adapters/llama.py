import asyncio
import logging
import subprocess
from pathlib import Path

import httpx

from ....common.port_pool import port_pool
from ....common.args_utils import merge_and_dedup_args

logger = logging.getLogger(__name__)


class LlamaEmbedAdapter:
    """llama-server --embedding 适配器（参考 LlamaAdapter）。"""

    def __init__(self, host: str = "127.0.0.1", default_args: list[str] | None = None):
        self.host = host
        self.port = port_pool.acquire()
        self.default_args = default_args or []
        self._process: subprocess.Popen | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self, model_path: Path, extra_args: list[str] | None = None) -> None:
        if self._process and self._process.poll() is None:
            logger.warning("llama-server --embedding already running, stopping first")
            self.stop()

        # 基础命令（硬编码，不可覆盖）
        cmd = [
            "llama-server",
            "-m", str(model_path),
            "--port", str(self.port),
            "--host", self.host,
            "--embedding",  # 必须启用 embedding 模式
        ]

        # 合并并去重参数：配置 default_args + 用户 extra_args
        # 注意：去重时会移除 default_args 中的 --embedding（如果存在）
        merged_args = merge_and_dedup_args(
            default_args=self.default_args,
            user_args=extra_args,
        )

        # 过滤掉已在 cmd 中的参数（避免重复 --embedding）
        filtered_args = [arg for arg in merged_args if arg not in cmd]
        cmd.extend(filtered_args)

        logger.info("Starting llama-server --embedding: %s", " ".join(cmd))
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def stop(self) -> None:
        if self._process and self._process.poll() is None:
            logger.info("Stopping llama-server --embedding (pid=%d)", self._process.pid)
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
        self._process = None
        port_pool.release(self.port)

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    async def health_check(self, timeout: float = 60.0, interval: float = 1.0) -> bool:
        deadline = asyncio.get_event_loop().time() + timeout
        async with httpx.AsyncClient() as client:
            while asyncio.get_event_loop().time() < deadline:
                if not self.is_running():
                    return False
                try:
                    resp = await client.get(f"{self.base_url}/health", timeout=2.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("status") in ("ok", "loading model"):
                            if data.get("status") == "ok":
                                return True
                except (httpx.RequestError, Exception):
                    pass
                await asyncio.sleep(interval)
        return False

    async def warmup(self) -> None:
        """发一次最小 embedding 请求，触发模型权重加载进内存。"""
        if not self.is_running():
            return
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                await client.post(
                    f"{self.base_url}/v1/embeddings",
                    json={"input": "warmup"},
                )
            logger.info("[warmup] llama-server --embedding:%d ready", self.port)
        except Exception as e:
            logger.warning("[warmup] llama-server --embedding:%d failed: %s", self.port, e)

    async def proxy(self, path: str, request_body: bytes, headers: dict, stream: bool = False):
        """透传请求到 llama-server，返回 httpx 响应（调用方负责关闭）。"""
        url = f"{self.base_url}{path}"
        client = httpx.AsyncClient(timeout=None)
        req = client.build_request("POST", url, content=request_body, headers=headers)
        response = await client.send(req, stream=stream)
        return client, response
