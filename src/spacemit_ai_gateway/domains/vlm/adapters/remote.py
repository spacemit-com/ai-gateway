import httpx


class RemoteAdapter:
    def __init__(self, api_base_url: str, api_key: str = ""):
        self.api_base_url = api_base_url.rstrip("/")
        self.api_key = api_key

    async def proxy(self, path: str, request_body: bytes, headers: dict, stream: bool = False):
        """Forward requests to a remote OpenAI-compatible VLM endpoint."""
        url = f"{self.api_base_url}{path}"
        merged_headers = dict(headers)
        if self.api_key:
            merged_headers["Authorization"] = f"Bearer {self.api_key}"
        client = httpx.AsyncClient(timeout=None)
        req = client.build_request("POST", url, content=request_body, headers=merged_headers)
        response = await client.send(req, stream=stream)
        return client, response
