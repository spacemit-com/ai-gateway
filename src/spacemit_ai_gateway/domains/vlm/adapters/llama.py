"""VlmLlamaAdapter — starts llama-server for VLM models with vision support."""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from pathlib import Path

import httpx

from ....common.port_pool import port_pool
from ....common.args_utils import merge_and_dedup_args

logger = logging.getLogger(__name__)


class VlmLlamaAdapter:
    """Manages a llama-server process for VLM inference.

    Accepts a model directory path, reads config.json to locate the
    text model GGUF file and vision model paths, then builds and
    starts llama-server with VLM-specific arguments.
    """

    def __init__(self, host: str = "127.0.0.1", default_args: list[str] | None = None):
        self.host = host
        self.port = port_pool.acquire()
        self.default_args = default_args or []
        self._process: subprocess.Popen | None = None
        self._port_released = False

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self, model_path: Path, extra_args: list[str] | None = None) -> None:
        """Start llama-server for VLM inference.

        Args:
            model_path: Path to the model directory or GGUF file.
            extra_args: Additional arguments for llama-server.
        """
        if self._process and self._process.poll() is None:
            logger.warning("VLM llama-server already running, stopping first")
            self.stop()

        model_dir = None
        gguf_path = model_path

        if model_path.is_dir():
            model_dir = model_path
            gguf_path = self._find_gguf_file(model_path)
            if not gguf_path:
                raise RuntimeError(f"No GGUF file found in {model_path}")

        cmd = self._build_command(gguf_path, model_dir, extra_args)

        logger.info("Starting VLM llama-server: %s", " ".join(cmd))
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _find_gguf_file(self, model_dir: Path) -> Path | None:
        """Find the text model GGUF file in the model directory."""
        config_path = model_dir / "config.json"
        if config_path.exists():
            try:
                with open(config_path) as f:
                    config = json.load(f)
                text_path = config.get("text_model_path", "")
                if not text_path and isinstance(config.get("text_model"), dict):
                    text_path = config["text_model"].get("model_path", "")
                if text_path:
                    gguf = model_dir / text_path
                    if gguf.exists():
                        return gguf
            except Exception:
                pass

        for p in model_dir.rglob("*.gguf"):
            return p
        return None

    def _build_command(
        self,
        gguf_path: Path,
        model_dir: Path | None,
        extra_args: list[str] | None = None,
    ) -> list[str]:
        """Build the llama-server command with VLM-specific arguments."""
        cmd = [
            "llama-server",
            "-m", str(gguf_path),
            "--port", str(self.port),
            "--host", self.host,
        ]

        vlm_args: list[str] = []
        if model_dir:
            vlm_args = self._build_vlm_args_from_dir(model_dir)

        merged_args = merge_and_dedup_args(
            default_args=vlm_args + self.default_args,
            user_args=extra_args,
        )
        cmd.extend(merged_args)
        return cmd

    def _build_vlm_args_from_dir(self, model_dir: Path) -> list[str]:
        """Build VLM-specific arguments from model directory config.json."""
        args: list[str] = []
        config_path = model_dir / "config.json"
        config: dict = {}
        if config_path.exists():
            try:
                with open(config_path) as f:
                    config = json.load(f)
            except Exception:
                pass

        media_backend = config.get("media_backend", "smt")
        args.extend(["--vision-backend", media_backend])

        if media_backend in ("smt", "auto"):
            smt_dir = config.get("smt_config_dir", str(model_dir))
            args.extend(["--smt-config-dir", smt_dir])

        vision_paths = config.get("vision_model_paths", [])
        if isinstance(vision_paths, str):
            vision_paths = [vision_paths]
        for vp in vision_paths:
            if vp:
                full_path = str(model_dir / vp) if not Path(vp).is_absolute() else vp
                args.extend(["--mmproj", full_path])

        media_path = config.get("media_path", "")
        if media_path:
            args.extend(["--media-path", media_path])

        if config.get("no_warmup", True):
            args.append("--no-warmup")

        gen = config.get("generation", {})
        enable_thinking = gen.get("enable_thinking", False)
        if not enable_thinking:
            args.extend(["--reasoning", "off"])
        else:
            args.extend(["--reasoning", "on"])
            budget = gen.get("reasoning_budget", -1)
            if budget and budget > 0:
                args.extend(["--reasoning-budget", str(budget)])

        ngl = config.get("n_gpu_layers", config.get("ngl", 0))
        args.extend(["-ngl", str(ngl)])

        return args

    def stop(self) -> None:
        """Stop the llama-server process."""
        if self._process and self._process.poll() is None:
            logger.info("Stopping VLM llama-server (pid=%d)", self._process.pid)
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
        self._process = None
        if not self._port_released:
            port_pool.release(self.port)
            self._port_released = True

    def is_running(self) -> bool:
        """Check if the llama-server process is running."""
        return self._process is not None and self._process.poll() is None

    async def health_check(self, timeout: float = 120.0, interval: float = 1.0) -> bool:
        """Wait for the llama-server to become healthy."""
        deadline = asyncio.get_event_loop().time() + timeout
        async with httpx.AsyncClient() as client:
            while asyncio.get_event_loop().time() < deadline:
                if not self.is_running():
                    return False
                try:
                    resp = await client.get(f"{self.base_url}/health", timeout=2.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("status") == "ok":
                            return True
                except (httpx.RequestError, Exception):
                    pass
                await asyncio.sleep(interval)
        return False

    async def warmup(self) -> None:
        """Send a minimal inference request to trigger model weight loading."""
        if not self.is_running():
            return
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json={"messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
                )
            logger.info("[warmup] VLM llama-server:%d ready", self.port)
        except Exception as e:
            logger.warning("[warmup] VLM llama-server:%d failed: %s", self.port, e)

    async def proxy(self, path: str, request_body: bytes, headers: dict, stream: bool = False):
        """Proxy an HTTP request to the llama-server."""
        url = f"{self.base_url}{path}"
        client = httpx.AsyncClient(timeout=None)
        req = client.build_request("POST", url, content=request_body, headers=headers)
        response = await client.send(req, stream=stream)
        return client, response
