import logging

from ...app.settings import LlmConfig
from ...common.base_service import BaseModelService
from .adapters.base import LlmBackend
from .adapters.llm_backend import LlmBackendImpl

logger = logging.getLogger(__name__)


class LLMService(BaseModelService[LlmBackend, LlmConfig]):
    """LLM 服务，继承自 BaseModelService。"""

    @property
    def adapter(self):
        """当前活跃模型的 LlamaAdapter，供 api.py 只读访问。"""
        if self._current_model and self._current_source_type != "remote":
            return self._get_backend_impl().get_adapter(self._current_model)
        return None

    async def get_current_ctx_size(self) -> int | None:
        """返回当前模型的 --ctx-size 参数值，用于 Ollama API 的 num_ctx 校验。"""
        adapter = self.adapter
        if not adapter:
            return None
        # 从 default_args 中提取 --ctx-size
        args = self.settings.default_args
        try:
            idx = args.index("--ctx-size")
            if idx + 1 < len(args):
                return int(args[idx + 1])
        except (ValueError, IndexError):
            pass
        return None

    def _get_backend_impl(self) -> LlmBackendImpl:
        """返回具体的 Backend 实现。"""
        return self._backends[self._default]  # type: ignore[return-value]
