import httpx


class RemoteAdapter:
    """远程 API 适配器（参考 LLM）。"""

    def __init__(self, api_base_url: str, api_key: str = ""):
        self.api_base_url = api_base_url.rstrip("/")
        self.api_key = api_key

    async def proxy(self, path: str, request_body: bytes, headers: dict, stream: bool = False):
        """透传请求到远程 API。"""
        url = f"{self.api_base_url}{path}"
        client = httpx.AsyncClient(timeout=None)
        req_headers = dict(headers)
        if self.api_key:
            req_headers["Authorization"] = f"Bearer {self.api_key}"
        req = client.build_request("POST", url, content=request_body, headers=req_headers)
        response = await client.send(req, stream=stream)
        return client, response
