from typing import Literal

from pydantic import BaseModel, model_validator


class RegisterRequest(BaseModel):
    model: str | None = None
    source_type: Literal["remote", "local_url", "local_path"]
    # remote
    api_base_url: str | None = None
    api_key: str | None = None
    # local_url
    url: str | None = None
    # local_path
    local_path: str | None = None

    @model_validator(mode="after")
    def _check_fields(self) -> "RegisterRequest":
        if self.source_type == "remote":
            if not self.api_base_url:
                raise ValueError("api_base_url is required for remote models")
        elif self.source_type == "local_url":
            if not self.url:
                raise ValueError("url is required for local_url models")
        elif self.source_type == "local_path":
            if not self.local_path:
                raise ValueError("local_path is required for local_path models")
        return self


class DeregisterRequest(BaseModel):
    model: str


class LoadRequest(BaseModel):
    model: str
    extra_args: list[str] = []


class UnloadRequest(BaseModel):
    model: str


class SwitchRequest(BaseModel):
    model: str


class ModelInfo(BaseModel):
    id: str
    source_type: str
    url: str | None = None
    local_path: str | None = None
    api_base_url: str | None = None
    status: str
    is_preset: bool
    download_progress: float = 0
