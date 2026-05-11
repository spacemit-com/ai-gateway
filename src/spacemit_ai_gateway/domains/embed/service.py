import logging

from ...app.settings import EmbedConfig
from ...common.base_service import BaseModelService
from .adapters.base import EmbedBackend
from .adapters.embed_backend import EmbedBackendImpl

logger = logging.getLogger(__name__)


class EmbedService(BaseModelService[EmbedBackend, EmbedConfig]):
    """Embed 服务，继承自 BaseModelService。"""

    @property
    def adapter(self):
        """当前活跃模型的 LlamaEmbedAdapter，供 api.py 只读访问。"""
        if self._current_model and self._current_source_type != "remote":
            return self._get_backend_impl().get_adapter(self._current_model)
        return None

    def _get_backend_impl(self) -> EmbedBackendImpl:
        """返回具体的 Backend 实现。"""
        return self._backends[self._default]  # type: ignore[return-value]
