"""Unit tests for Embed service.

Run:
    uv run pytest tests/unit/test_embed_service.py -v
"""

import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx
import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def server():
    """Start spacemit-ai-gateway with a temp DB and random port; yield base_url; kill and clean up."""
    import yaml as _yaml

    port = _free_port()
    tmp_db = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp_db.close()
    db_path = tmp_db.name

    # 读取 base.yaml，覆盖 embed.backend=null 和 embed.storage.db_path，避免自动加载模型
    # 同时禁用 llm.backend，避免 /v1/models 返回 LLM 模型
    base_yaml_path = PROJECT_ROOT / "configs" / "base.yaml"
    with open(base_yaml_path, "r", encoding="utf-8") as f:
        cfg = _yaml.safe_load(f) or {}
    cfg.setdefault("embed", {})
    cfg["embed"]["backend"] = None
    cfg["embed"].setdefault("storage", {})
    cfg["embed"]["storage"]["db_path"] = db_path
    cfg.setdefault("llm", {})
    cfg["llm"]["backend"] = None

    tmp_cfg = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    )
    _yaml.dump(cfg, tmp_cfg)
    tmp_cfg.close()

    env = os.environ.copy()
    env["SPACEMIT_AI_GATEWAY_CONFIG"] = tmp_cfg.name

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn",
         "spacemit_ai_gateway.app.main:app",
         "--host", "0.0.0.0", "--port", str(port)],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    base_url = f"http://localhost:{port}"
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            r = httpx.get(f"{base_url}/healthz", timeout=1)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.3)
    else:
        proc.kill()
        raise RuntimeError("Server did not start in time")

    yield base_url

    proc.kill()
    proc.wait()
    Path(db_path).unlink(missing_ok=True)
    Path(tmp_cfg.name).unlink(missing_ok=True)


@pytest.fixture(scope="module")
def client(server):
    with httpx.Client(base_url=server, timeout=10) as c:
        yield c


# ── helpers ───────────────────────────────────────────────────────────────────

def assert_ok(r: httpx.Response):
    assert r.status_code == 200, f"{r.status_code}: {r.text}"


def assert_err(r: httpx.Response, code: int = 400):
    assert r.status_code == code, f"expected {code}, got {r.status_code}: {r.text}"
    body = r.json()
    assert "error" in body or "detail" in body


# ── tests ─────────────────────────────────────────────────────────────────────

def test_list_models_returns_presets(client):
    r = client.get("/v1/embed/models")
    assert_ok(r)
    models = r.json()
    ids = [m["id"] for m in models]
    assert "bge-small-zh-v1.5-q4_k_m" in ids
    preset_ids = {m["id"] for m in models if m["is_preset"] == 1}
    assert "bge-small-zh-v1.5-q4_k_m" in preset_ids


def test_embed_healthz_not_running(client):
    r = client.get("/v1/embed/healthz")
    assert_ok(r)
    assert r.json()["status"] == "failed"


def test_openai_models_empty_when_no_model_loaded(client):
    r = client.get("/v1/models")
    assert_ok(r)
    # embed 的 compat_router 也注册了 /v1/models，但只返回当前加载的模型
    # 无模型时应为空
    assert r.json()["data"] == []


# register ────────────────────────────────────────────────────────────────────

def test_register_custom_model(client):
    uid = uuid.uuid4().hex[:8]
    r = client.post("/v1/embed/models/register", json={
        "model": f"test-custom-{uid}",
        "source_type": "local_url",
        "url": "https://example.com/test.gguf",
    })
    assert_ok(r)
    assert r.json()["model"] == f"test-custom-{uid}"


def test_register_duplicate(client):
    uid = uuid.uuid4().hex[:8]
    model = f"test-dup-{uid}"
    client.post("/v1/embed/models/register", json={"model": model, "source_type": "local_url", "url": "https://example.com/test.gguf"})
    r = client.post("/v1/embed/models/register", json={"model": model, "source_type": "local_url", "url": "https://example.com/test.gguf"})
    assert_err(r, 400)
    assert "already registered" in r.json()["message"]


def test_register_remote(client):
    uid = uuid.uuid4().hex[:8]
    r = client.post("/v1/embed/models/register", json={
        "model": f"test-remote-{uid}",
        "source_type": "remote",
        "api_base_url": "https://api.openai.com/v1",
        "api_key": "sk-test",
    })
    assert_ok(r)
    assert r.json()["status"] == "loaded"


# download progress ───────────────────────────────────────────────────────────

def test_download_progress_preset(client):
    r = client.get("/v1/embed/models/bge-small-zh-v1.5-q4_k_m/download")
    assert_ok(r)
    body = r.json()
    assert body["model"] == "bge-small-zh-v1.5-q4_k_m"
    assert "status" in body
    assert "progress" in body


def test_download_progress_not_found(client):
    r = client.get("/v1/embed/models/nonexistent-xyz/download")
    assert_err(r, 404)


# deregister ──────────────────────────────────────────────────────────────────

def test_deregister_custom_model(client):
    uid = uuid.uuid4().hex[:8]
    model = f"test-dereg-{uid}"
    client.post("/v1/embed/models/register", json={
        "model": model,
        "source_type": "local_url",
        "url": "https://example.com/test.gguf",
    })
    r = client.post("/v1/embed/models/deregister", json={"model": model})
    assert_ok(r)
    assert r.json()["status"] == "deregistered"


def test_deregister_nonexistent(client):
    r = client.post("/v1/embed/models/deregister", json={"model": "nonexistent-xyz"})
    assert_err(r, 400)


def test_deregister_preset_rejected(client):
    r = client.post("/v1/embed/models/deregister", json={"model": "bge-small-zh-v1.5-q4_k_m"})
    assert_err(r, 400)
    assert "preset" in r.json()["message"].lower()
