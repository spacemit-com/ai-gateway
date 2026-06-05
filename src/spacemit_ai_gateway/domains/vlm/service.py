import logging

from ...app.settings import VlmConfig
from ...common.base_service import BaseModelService
from .adapters.base import VlmBackend
from .adapters.vlm_backend import VlmBackendImpl

logger = logging.getLogger(__name__)


class VlmService(BaseModelService[VlmBackend, VlmConfig]):
    """VLM service using the shared model lifecycle and proxy path."""

    @property
    def adapter(self):
        """Current active model's VlmLlamaAdapter, for api.py read-only access."""
        if self._current_model and self._current_source_type != "remote":
            return self._get_backend_impl().get_adapter(self._current_model)
        return None

    def _get_backend_impl(self) -> VlmBackendImpl:
        return self._backends[self._default]  # type: ignore[return-value]
