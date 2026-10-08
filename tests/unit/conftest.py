"""unit 测试共用 fixture。"""

import httpx
import pytest

from spacemit_ai_gateway.common import downloader

from .test_downloader import FakeServer


@pytest.fixture
def server(monkeypatch):
    srv = FakeServer()
    monkeypatch.setattr(
        downloader, "make_client",
        lambda config: httpx.AsyncClient(transport=httpx.MockTransport(srv.handler)),
    )
    return srv
