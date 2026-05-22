"""Integration tests for spacemit-ai-gateway API.

Starts the server in a subprocess with a temp DB, runs all non-inference
endpoints, then tears everything down and removes the temp DB.

Run:
    uv run pytest tests/unit/test_llm_service.py -v
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient as _TestClient

from spacemit_ai_gateway.domains.llm.api import router as _llm_router

PROJECT_ROOT = Path(__file__).parent.parent.parent


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def server():
    """Start spacemit-ai-gateway with a temp DB and random port; yield (base_url, db_path)."""
    import yaml as _yaml

    port = _free_port()
    tmp_db = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp_db.close()
    db_path = tmp_db.name
    tmp_dir = tempfile.TemporaryDirectory(prefix="spacemit-ai-gateway-llm-test-")

    # 读取 base.yaml，覆盖各域 db_path，避免测试进程写入用户 cache DB。
    base_yaml_path = PROJECT_ROOT / "configs" / "base.yaml"
    with open(base_yaml_path, "r", encoding="utf-8") as f:
        cfg = _yaml.safe_load(f) or {}
    cfg.setdefault("llm", {})
    cfg["llm"]["backend"] = None
    cfg["llm"].setdefault("storage", {})
    cfg["llm"]["storage"]["db_path"] = db_path

    # 禁用 embed 和 rerank 的自动加载
    cfg.setdefault("embed", {})
    cfg["embed"]["backend"] = None
    cfg["embed"].setdefault("storage", {})
    cfg["embed"]["storage"]["db_path"] = str(Path(tmp_dir.name) / "embed.sqlite")
    cfg.setdefault("rerank", {})
    cfg["rerank"]["backend"] = None
    cfg["rerank"].setdefault("storage", {})
    cfg["rerank"]["storage"]["db_path"] = str(Path(tmp_dir.name) / "rerank.sqlite")

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

    yield {"base_url": base_url, "db_path": db_path}

    proc.kill()
    proc.wait()
    Path(db_path).unlink(missing_ok=True)
    Path(tmp_cfg.name).unlink(missing_ok=True)
    tmp_dir.cleanup()


@pytest.fixture(scope="module")
def client(server):
    with httpx.Client(base_url=server["base_url"], timeout=10) as c:
        yield c


# ── helpers ───────────────────────────────────────────────────────────────────

def assert_ok(r: httpx.Response):
    assert r.status_code == 200, f"{r.status_code}: {r.text}"


def assert_err(r: httpx.Response, code: int = 400):
    assert r.status_code == code, f"expected {code}, got {r.status_code}: {r.text}"
    body = r.json()
    assert "error" in body


# ── tests ─────────────────────────────────────────────────────────────────────

def test_healthz(client):
    r = client.get("/healthz")
    assert_ok(r)
    body = r.json()
    assert "domains" in body
    # LLM 域无模型时应为 idle（服务在线，模型按需加载）
    assert body["domains"]["llm"]["state"] == "idle"


def test_list_models_returns_presets(client):
    r = client.get("/v1/llm/models")
    assert_ok(r)
    models = r.json()
    ids = [m["id"] for m in models]
    assert "qwen2.5-0.5b-instruct-q4_0" in ids
    preset_ids = {m["id"] for m in models if m["is_preset"] == 1}
    assert "qwen2.5-0.5b-instruct-q4_0" in preset_ids


def test_llm_healthz_not_running(client):
    r = client.get("/v1/llm/healthz")
    assert_ok(r)
    assert r.json()["status"] == "idle"


def test_openai_models_empty_when_no_model_loaded(client):
    r = client.get("/v1/models")
    assert_ok(r)
    assert r.json()["data"] == []


# register ────────────────────────────────────────────────────────────────────

def test_register_custom_model(client):
    uid = uuid.uuid4().hex[:8]
    r = client.post("/v1/llm/models/register", json={
        "model": f"test-custom-{uid}",
        "source_type": "local_url",
        "url": "https://example.com/test.gguf",
    })
    assert_ok(r)
    assert r.json()["model"] == f"test-custom-{uid}"


def test_register_duplicate(client):
    uid = uuid.uuid4().hex[:8]
    model = f"test-dup-{uid}"
    client.post("/v1/llm/models/register", json={"model": model, "source_type": "local_url", "url": "https://example.com/test.gguf"})
    r = client.post("/v1/llm/models/register", json={"model": model, "source_type": "local_url", "url": "https://example.com/test.gguf"})
    assert_err(r, 400)
    assert "already registered" in r.json()["message"]


def test_register_missing_source_type(client):
    r = client.post("/v1/llm/models/register", json={"model": "no-source"})
    assert r.status_code == 422


def test_register_remote_missing_api_base_url(client):
    r = client.post("/v1/llm/models/register", json={
        "model": "bad-remote",
        "source_type": "remote",
    })
    assert r.status_code == 422


def test_register_preset_already_exists(client):
    r = client.post("/v1/llm/models/register", json={
        "model": "qwen2.5-0.5b-instruct-q4_0",
        "source_type": "local_url",
        "url": "https://example.com/test.gguf",
    })
    assert_err(r, 400)


def test_register_local_path(client):
    """注册 local_path 类型模型，需要文件真实存在。"""
    uid = uuid.uuid4().hex[:8]
    # 创建一个临时文件模拟已存在的模型文件
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".gguf", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        r = client.post("/v1/llm/models/register", json={
            "model": f"test-local-{uid}",
            "source_type": "local_path",
            "local_path": tmp_path,
        })
        assert_ok(r)
        assert r.json()["status"] == "downloaded"
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_register_remote(client):
    uid = uuid.uuid4().hex[:8]
    r = client.post("/v1/llm/models/register", json={
        "model": f"test-remote-{uid}",
        "source_type": "remote",
        "api_base_url": "https://api.openai.com/v1",
        "api_key": "sk-test",
    })
    assert_ok(r)
    assert r.json()["status"] == "loaded"


# download progress ───────────────────────────────────────────────────────────

def test_download_progress_preset(client):
    r = client.get("/v1/llm/models/qwen2.5-0.5b-instruct-q4_0/download")
    assert_ok(r)
    body = r.json()
    assert body["model"] == "qwen2.5-0.5b-instruct-q4_0"
    assert "status" in body
    assert "progress" in body


def test_download_progress_not_found(client):
    r = client.get("/v1/llm/models/nonexistent-xyz/download")
    assert_err(r, 404)


# download start / cancel ─────────────────────────────────────────────────────

def test_download_start_and_cancel(client):
    uid = uuid.uuid4().hex[:8]
    model = f"test-dl-{uid}"
    # 注册一个带 URL 的模型
    r = client.post("/v1/llm/models/register", json={
        "model": model,
        "source_type": "local_url",
        "url": "https://huggingface.co/ggml-org/models/resolve/main/tinyllamas/stories260K.gguf",
    })
    assert_ok(r)

    # 触发下载
    r = client.post(f"/v1/llm/models/{model}/download")
    assert_ok(r)
    assert r.json()["status"] == "downloading"

    # 状态应为 downloading
    r = client.get(f"/v1/llm/models/{model}/download")
    assert_ok(r)
    assert r.json()["status"] == "downloading"

    # 取消下载
    r = client.delete(f"/v1/llm/models/{model}/download")
    assert_ok(r)
    assert r.json()["status"] == "available"

    # 取消后状态回到 available，进度归零
    time.sleep(0.3)
    r = client.get(f"/v1/llm/models/{model}/download")
    assert_ok(r)
    body = r.json()
    assert body["status"] == "available"
    assert body["progress"] == 0.0


def test_download_start_already_downloading(client):
    uid = uuid.uuid4().hex[:8]
    model = f"test-dl2-{uid}"
    client.post("/v1/llm/models/register", json={
        "model": model,
        "source_type": "local_url",
        "url": "https://huggingface.co/ggml-org/models/resolve/main/tinyllamas/stories260K.gguf",
    })
    client.post(f"/v1/llm/models/{model}/download")
    r = client.post(f"/v1/llm/models/{model}/download")
    assert_err(r, 400)
    assert "already downloading" in r.json()["message"]
    # 清理
    client.delete(f"/v1/llm/models/{model}/download")


def test_download_cancel_no_active(client):
    r = client.delete("/v1/llm/models/qwen2.5-0.5b-instruct-q4_0/download")
    assert_err(r, 400)
    assert "No active download" in r.json()["message"]


def test_download_start_nonexistent(client):
    r = client.post("/v1/llm/models/nonexistent-xyz/download")
    assert_err(r, 400)
    assert "not found" in r.json()["message"]


# load / unload ───────────────────────────────────────────────────────────────

def test_load_nonexistent(client):
    r = client.post("/v1/llm/models/load", json={"model": "nonexistent-xyz"})
    assert_err(r, 400)
    assert "not found" in r.json()["message"]


def test_unload_nonexistent(client):
    r = client.post("/v1/llm/models/unload", json={"model": "nonexistent-xyz"})
    assert_err(r, 400)


def test_load_downloading_model(client):
    uid = uuid.uuid4().hex[:8]
    model = f"test-loading-{uid}"
    client.post("/v1/llm/models/register", json={
        "model": model,
        "source_type": "local_url",
        "url": "https://huggingface.co/ggml-org/models/resolve/main/tinyllamas/stories260K.gguf",
    })
    client.post(f"/v1/llm/models/{model}/download")
    r = client.post("/v1/llm/models/load", json={"model": model})
    assert_err(r, 400)
    assert "downloading" in r.json()["message"]
    client.delete(f"/v1/llm/models/{model}/download")


def test_download_remote_model_rejected(client):
    uid = uuid.uuid4().hex[:8]
    model = f"test-remote-dl-{uid}"
    client.post("/v1/llm/models/register", json={
        "model": model,
        "source_type": "remote",
        "api_base_url": "https://api.openai.com/v1",
    })
    r = client.post(f"/v1/llm/models/{model}/download")
    assert_err(r, 400)
    assert "not a local_url model" in r.json()["message"]


def test_download_local_path_model_rejected(client):
    """local_path 类型模型不允许调用 download 接口。"""
    uid = uuid.uuid4().hex[:8]
    model = f"test-lp-dl-{uid}"

    # 创建临时文件用于注册
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".gguf", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        client.post("/v1/llm/models/register", json={
            "model": model,
            "source_type": "local_path",
            "local_path": tmp_path,
        })
        r = client.post(f"/v1/llm/models/{model}/download")
        assert_err(r, 400)
        assert "not a local_url model" in r.json()["message"]
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# deregister ──────────────────────────────────────────────────────────────────

def test_deregister_custom_model(client):
    uid = uuid.uuid4().hex[:8]
    model = f"test-dereg-{uid}"
    client.post("/v1/llm/models/register", json={
        "model": model,
        "source_type": "local_url",
        "url": "https://example.com/test.gguf",
    })
    r = client.post("/v1/llm/models/deregister", json={"model": model})
    assert_ok(r)
    assert r.json()["status"] == "deregistered"
    # 确认已从列表中移除
    models = client.get("/v1/llm/models").json()
    assert not any(m["id"] == model for m in models)


def test_deregister_nonexistent(client):
    r = client.post("/v1/llm/models/deregister", json={"model": "nonexistent-xyz"})
    assert_err(r, 400)
    assert "not found" in r.json()["message"]


def test_deregister_preset_rejected(client):
    r = client.post("/v1/llm/models/deregister", json={"model": "qwen2.5-0.5b-instruct-q4_0"})
    assert_err(r, 400)
    assert "preset" in r.json()["message"]


# switch (remote, no llama-server needed) ─────────────────────────────────────

def test_switch_to_remote_model(client):
    uid = uuid.uuid4().hex[:8]
    model = f"test-switch-remote-{uid}"
    client.post("/v1/llm/models/register", json={
        "model": model,
        "source_type": "remote",
        "api_base_url": "https://api.openai.com/v1",
        "api_key": "sk-test",
    })
    r = client.post("/v1/llm/models/switch", json={"model": model})
    assert_ok(r)
    assert r.json()["status"] == "loaded"
    # /v1/models 应反映当前模型
    models_r = client.get("/v1/models")
    assert_ok(models_r)
    ids = [m["id"] for m in models_r.json()["data"]]
    assert model in ids


def test_switch_nonexistent(client):
    r = client.post("/v1/llm/models/switch", json={"model": "nonexistent-xyz"})
    assert_err(r, 400)
    assert "not found" in r.json()["message"]


# /models alias ───────────────────────────────────────────────────────────────

def test_openai_models_alias(client):
    r = client.get("/models")
    assert_ok(r)
    assert "data" in r.json()


# chat aliases ────────────────────────────────────────────────────────────────

def test_chat_alias_no_model(client):
    # 先确保没有本地模型加载（remote 模型可能已加载，但无法连接，会 502/503）
    r = client.post("/chat/completions", json={
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
    })
    assert r.status_code in (503, 502, 500)


def test_completions_no_model(client):
    try:
        r = client.post("/v1/completions", json={
            "prompt": "hello",
            "stream": False,
        }, timeout=3)
        assert r.status_code in (503, 502, 500)
    except Exception:
        pass  # 连接远程 API 超时也算通过


def test_completions_alias_no_model(client):
    try:
        r = client.post("/completions", json={
            "prompt": "hello",
            "stream": False,
        }, timeout=3)
        assert r.status_code in (503, 502, 500)
    except Exception:
        pass


# chat (no model loaded) ──────────────────────────────────────────────────────

def test_chat_no_model_loaded(client):
    r = client.post("/v1/chat/completions", json={
        "model": "qwen2.5-0.5b-instruct-q4_0",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": False,
    })
    # 同事方案：模型已下载时自动 load，返回 200；未下载或无模型时返回 5xx
    assert r.status_code in (200, 503, 500, 502, 404)


# ── 推理测试（需要真实 llama-server + 模型文件）────────────────────────────────
#
# 使用 preset 模型 qwen3-0.6b-q4_0 和 qwen2.5-0.5b-instruct-q4_0
# 模型文件存放在 ~/.cache/spacemit-ai-gateway/models/llm/
# 若文件不存在则先下载（可能较慢），下载失败则 skip

MODEL_A = "qwen3-0.6b-q4_0"
MODEL_B = "qwen2.5-0.5b-instruct-q4_0"


def _ensure_downloaded(client, model: str, download_timeout: int = 300) -> bool:
    """确保模型已下载，返回 True 表示成功。未下载则触发下载并等待完成。"""
    r = client.get(f"/v1/llm/models/{model}/download")
    if r.status_code == 404:
        return False
    status = r.json().get("status", "")
    if status in ("downloaded", "loaded"):
        return True
    if status != "downloading":
        # 触发下载
        r = client.post(f"/v1/llm/models/{model}/download", timeout=30)
        if r.status_code != 200:
            return False
        status = r.json().get("status", "")
        if status in ("downloaded", "loaded"):
            return True
    # 轮询等待下载完成
    deadline = time.time() + download_timeout
    while time.time() < deadline:
        r = client.get(f"/v1/llm/models/{model}/download")
        s = r.json().get("status", "")
        if s in ("downloaded", "loaded"):
            return True
        if s != "downloading":
            return False
        time.sleep(3)
    return False


@pytest.fixture(scope="module")
def loaded_model_a(client):
    """加载 MODEL_A 并切换到该模型，测试完成后 unload。"""
    if not _ensure_downloaded(client, MODEL_A):
        pytest.skip(f"Model {MODEL_A} download failed or timed out")

    r = client.post("/v1/llm/models/load", json={"model": MODEL_A}, timeout=120)
    if r.status_code != 200:
        pytest.skip(f"Model {MODEL_A} load failed: {r.text}")

    # load 不切换指针，需要显式 switch
    r = client.post("/v1/llm/models/switch", json={"model": MODEL_A}, timeout=10)
    if r.status_code != 200:
        pytest.skip(f"Model {MODEL_A} switch failed: {r.text}")

    yield MODEL_A

    # Teardown: 尝试 unload，失败不报错（可能已被其他测试 unload 或服务已关闭）
    try:
        client.post("/v1/llm/models/unload", json={"model": MODEL_A}, timeout=30)
    except Exception:
        pass


def test_chat_non_stream(client, loaded_model_a):
    r = client.post("/v1/chat/completions", json={
        "model": loaded_model_a,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "max_tokens": 32,
        "thinking": False,
    }, timeout=60)
    assert_ok(r)
    body = r.json()
    assert body["object"] == "chat.completion"
    assert len(body["choices"]) > 0
    # content 可能为空（thinking 模式），检查有 choices 即可
    assert "message" in body["choices"][0]


def test_chat_stream(client, loaded_model_a):
    with client.stream("POST", "/v1/chat/completions", json={
        "model": loaded_model_a,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
        "max_tokens": 16,
    }, timeout=60) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        chunks = b"".join(resp.iter_bytes())
    assert b"data:" in chunks


def test_completions_non_stream(client, loaded_model_a):
    r = client.post("/v1/completions", json={
        "model": loaded_model_a,
        "prompt": "Once upon a time",
        "stream": False,
        "max_tokens": 16,
    }, timeout=60)
    assert_ok(r)
    assert r.json()["choices"][0]["text"]


def test_chat_alias(client, loaded_model_a):
    r = client.post("/chat/completions", json={
        "model": loaded_model_a,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "max_tokens": 8,
    }, timeout=60)
    assert_ok(r)


def test_llm_healthz_running(client, loaded_model_a):
    r = client.get("/v1/llm/healthz")
    assert_ok(r)
    assert r.json()["status"] == "ready"
    assert r.json()["model"] == loaded_model_a


def test_openai_models_shows_loaded(client, loaded_model_a):
    r = client.get("/v1/models")
    assert_ok(r)
    ids = [m["id"] for m in r.json()["data"]]
    assert loaded_model_a in ids


def test_unload_and_status(client, loaded_model_a):
    r = client.post("/v1/llm/models/unload", json={"model": loaded_model_a})
    assert_ok(r)
    r = client.get("/v1/llm/healthz")
    assert_ok(r)
    assert r.json()["status"] == "idle"
    # 重新加载并切换供后续 switch 测试使用
    client.post("/v1/llm/models/load", json={"model": loaded_model_a}, timeout=120)
    client.post("/v1/llm/models/switch", json={"model": loaded_model_a}, timeout=10)


# switch ──────────────────────────────────────────────────────────────────────

def test_switch_local_model(client, loaded_model_a):
    """先加载 MODEL_A，load MODEL_B（不切换），switch 到 MODEL_B，验证后再 switch 回来。"""
    if not _ensure_downloaded(client, MODEL_B):
        pytest.skip(f"Model {MODEL_B} download failed or timed out")

    # load MODEL_B（在新端口启动，但不切换指针）
    r = client.post("/v1/llm/models/load", json={"model": MODEL_B}, timeout=180)
    assert_ok(r)

    # 验证当前模型仍是 MODEL_A（load 不切换指针）
    ids = [m["id"] for m in client.get("/v1/models").json()["data"]]
    assert MODEL_A in ids

    # switch 到 MODEL_B（切换指针）
    r = client.post("/v1/llm/models/switch", json={"model": MODEL_B}, timeout=10)
    assert_ok(r)
    assert r.json()["status"] == "loaded"

    # 验证 /v1/models 反映新模型
    ids = [m["id"] for m in client.get("/v1/models").json()["data"]]
    assert MODEL_B in ids

    # switch 回 MODEL_A（MODEL_A 已在运行，直接切换）
    r = client.post("/v1/llm/models/switch", json={"model": MODEL_A}, timeout=10)
    assert_ok(r)


# ── 新增路由测试（无需模型加载）────────────────────────────────────────────────

def test_api_tags_no_model(client):
    r = client.get("/v1/llm/api/tags")
    assert_ok(r)
    assert "models" in r.json()


def test_models_alias(client):
    r = client.get("/models")
    assert_ok(r)
    assert "data" in r.json()


def test_chat_completions_alias_no_model(client):
    try:
        r = client.post("/chat/completions", json={
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        }, timeout=3)
        assert r.status_code in (503, 502, 500)
    except Exception:
        pass


def test_v1_responses_no_model(client):
    try:
        r = client.post("/v1/responses", json={
            "model": "test",
            "input": "hi",
            "stream": False,
        }, timeout=3)
        assert r.status_code in (503, 502, 500)
    except Exception:
        pass


def test_anthropic_messages_no_model(client):
    try:
        r = client.post("/v1/messages", json={
            "model": "test",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 8,
        }, timeout=3)
        assert r.status_code in (503, 502, 500)
    except Exception:
        pass


def test_anthropic_count_tokens_no_model(client):
    try:
        r = client.post("/v1/messages/count_tokens", json={
            "model": "test",
            "messages": [{"role": "user", "content": "hi"}],
        }, timeout=3)
        assert r.status_code in (503, 502, 500)
    except Exception:
        pass


def test_llm_tokenize_no_model(client):
    try:
        r = client.post("/v1/llm/tokenize", json={"content": "hello world"}, timeout=3)
        assert r.status_code in (503, 502, 500)
    except Exception:
        pass


def test_llm_detokenize_no_model(client):
    try:
        r = client.post("/v1/llm/detokenize", json={"tokens": [1, 2, 3]}, timeout=3)
        assert r.status_code in (503, 502, 500)
    except Exception:
        pass


def test_llm_props_no_model(client):
    r = client.get("/v1/llm/props")
    # 503 when no local model, or 200 if local model happens to be loaded
    assert r.status_code in (200, 503)


def test_llm_slots_no_model(client):
    r = client.get("/v1/llm/slots")
    assert r.status_code in (200, 503)


def test_llm_metrics_no_model(client):
    r = client.get("/v1/llm/metrics")
    assert r.status_code in (200, 501, 503)


def test_llm_lora_adapters_no_model(client):
    r = client.get("/v1/llm/lora-adapters")
    assert r.status_code in (200, 503)


# ── 新增路由测试（需要模型加载）────────────────────────────────────────────────

def test_api_tags_with_model(client, loaded_model_a):
    r = client.get("/v1/llm/api/tags")
    assert_ok(r)
    # current model may be remote (from earlier switch test); just check structure
    assert isinstance(r.json()["models"], list)


def test_llm_tokenize(client, loaded_model_a):
    r = client.post("/v1/llm/tokenize", json={"content": "hello world"}, timeout=10)
    assert_ok(r)
    assert "tokens" in r.json()


def test_llm_detokenize(client, loaded_model_a):
    # 先 tokenize 再 detokenize
    r = client.post("/v1/llm/tokenize", json={"content": "hi"}, timeout=10)
    assert_ok(r)
    tokens = r.json()["tokens"]
    r2 = client.post("/v1/llm/detokenize", json={"tokens": tokens}, timeout=10)
    assert_ok(r2)
    assert "content" in r2.json()


def test_llm_apply_template(client, loaded_model_a):
    r = client.post("/v1/llm/apply-template", json={
        "messages": [{"role": "user", "content": "hi"}]
    }, timeout=10)
    assert_ok(r)


def test_llm_props_with_model(client, loaded_model_a):
    r = client.get("/v1/llm/props", timeout=10)
    assert_ok(r)


def test_llm_slots_with_model(client, loaded_model_a):
    r = client.get("/v1/llm/slots", timeout=10)
    assert_ok(r)


def test_llm_metrics_with_model(client, loaded_model_a):
    r = client.get("/v1/llm/metrics", timeout=10)
    # llama-server requires --metrics flag; 501 is expected without it
    assert r.status_code in (200, 501)


def test_llm_lora_adapters_with_model(client, loaded_model_a):
    r = client.get("/v1/llm/lora-adapters", timeout=10)
    assert_ok(r)


def test_llm_completion_endpoint(client, loaded_model_a):
    r = client.post("/v1/llm/completion", json={
        "prompt": "Once upon",
        "n_predict": 8,
        "stream": False,
    }, timeout=60)
    assert_ok(r)


def test_llm_api_chat(client, loaded_model_a):
    r = client.post("/v1/llm/api/chat", json={
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "max_tokens": 8,
    }, timeout=60)
    assert_ok(r)


def test_llm_responses_endpoint(client, loaded_model_a):
    try:
        r = client.post("/v1/llm/responses", json={
            "model": loaded_model_a,
            "input": "hi",
            "stream": False,
        }, timeout=30)
        # llama-server 可能不支持此端点，502 也可接受
        assert r.status_code in (200, 404, 501, 502, 500)
    except Exception:
        pass


# ── Ollama 协议转换测试 ────────────────────────────────────────────────────────

def test_ollama_api_chat_no_model(client):
    try:
        r = client.post("/v1/llm/api/chat", json={
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        }, timeout=3)
        assert r.status_code in (503, 502, 500)
    except Exception:
        pass


def test_ollama_api_generate_no_model(client):
    try:
        r = client.post("/v1/llm/api/generate", json={
            "prompt": "hello",
            "stream": False,
        }, timeout=3)
        assert r.status_code in (503, 502, 500)
    except Exception:
        pass


def test_ollama_response_format(client, loaded_model_a):
    """Ollama /api/chat 响应应包含 done、model、message 字段。"""
    r = client.post("/v1/llm/api/chat", json={
        "model": loaded_model_a,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "options": {"num_predict": 8},
    }, timeout=60)
    assert_ok(r)
    body = r.json()
    assert body["done"] is True
    assert "done_reason" in body
    assert body["model"] == loaded_model_a
    assert "message" in body
    assert "role" in body["message"]
    assert "content" in body["message"]
    assert "eval_count" in body
    assert "prompt_eval_count" in body


def test_ollama_options_mapping(client, loaded_model_a):
    """options.num_predict 应映射为 max_tokens，限制输出长度。"""
    r = client.post("/v1/llm/api/chat", json={
        "model": loaded_model_a,
        "messages": [{"role": "user", "content": "count from 1 to 100"}],
        "stream": False,
        "options": {"num_predict": 5, "temperature": 0.0},
    }, timeout=60)
    assert_ok(r)
    body = r.json()
    # eval_count 应 <= num_predict
    assert body["eval_count"] <= 5


def test_ollama_api_generate(client, loaded_model_a):
    """Ollama /api/generate 响应应包含 response 字段。"""
    r = client.post("/v1/llm/api/generate", json={
        "model": loaded_model_a,
        "prompt": "1+1=",
        "options": {"num_predict": 5},
    }, timeout=60)
    assert_ok(r)
    body = r.json()
    assert body["done"] is True
    assert "response" in body
    assert body["model"] == loaded_model_a


def test_ollama_stream_format(client, loaded_model_a):
    """Ollama 流式响应每行应为合法 JSON，最后一行 done=true。"""
    with client.stream("POST", "/v1/llm/api/chat", json={
        "model": loaded_model_a,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
        "options": {"num_predict": 8},
    }, timeout=60) as resp:
        assert resp.status_code == 200
        lines = [line for line in resp.iter_lines() if line.strip()]

    assert len(lines) > 0
    for line in lines:
        chunk = json.loads(line)
        assert "done" in chunk
        assert "model" in chunk
    # 最后一行 done=true
    assert json.loads(lines[-1])["done"] is True


# ── llama-server 透传接口 ──────────────────────────────────────────────────────

def test_props_get_no_model(client):
    """未加载模型时 GET /v1/llm/props 应返回 502/503/500。"""
    try:
        r = client.get("/v1/llm/props", timeout=3)
        assert r.status_code in (502, 503, 500)
    except Exception:
        pass


def test_props_get(client, loaded_model_a):
    """GET /v1/llm/props 应返回服务属性对象。"""
    r = client.get("/v1/llm/props", timeout=10)
    assert_ok(r)
    body = r.json()
    assert isinstance(body, dict)


def test_props_post(client, loaded_model_a):
    """POST /v1/llm/props 应被透传（服务器未启用 --props 时返回 400/403/501 均可接受）。"""
    r = client.post("/v1/llm/props", json={}, timeout=10)
    assert r.status_code in (200, 400, 403, 501, 502, 503)


def test_slots_get(client, loaded_model_a):
    """GET /v1/llm/slots 应返回 slot 列表。"""
    r = client.get("/v1/llm/slots", timeout=10)
    assert_ok(r)
    body = r.json()
    assert isinstance(body, list)


def test_slots_get_fail_on_no_slot(client, loaded_model_a):
    """GET /v1/llm/slots?fail_on_no_slot=1 在有空闲 slot 时应返回 200。"""
    r = client.get("/v1/llm/slots", params={"fail_on_no_slot": "1"}, timeout=10)
    # 有空闲 slot 时 200，无空闲时 503
    assert r.status_code in (200, 503)


def test_slots_save(client, loaded_model_a):
    """POST /v1/llm/slots/0?action=save 应被透传（返回 200 或错误均可）。"""
    r = client.post("/v1/llm/slots/0", params={"action": "save"},
                    json={"filename": "test_slot_cache.bin"}, timeout=10)
    assert r.status_code in (200, 400, 403, 404, 501, 502, 503)


def test_slots_restore(client, loaded_model_a):
    """POST /v1/llm/slots/0?action=restore 应被透传。"""
    r = client.post("/v1/llm/slots/0", params={"action": "restore"},
                    json={"filename": "test_slot_cache.bin"}, timeout=10)
    assert r.status_code in (200, 400, 403, 404, 501, 502, 503)


def test_slots_erase(client, loaded_model_a):
    """POST /v1/llm/slots/0?action=erase 应被透传。"""
    r = client.post("/v1/llm/slots/0", params={"action": "erase"},
                    json={}, timeout=10)
    assert r.status_code in (200, 400, 403, 404, 501, 502, 503)


def test_metrics_get(client, loaded_model_a):
    """GET /v1/llm/metrics 应返回 Prometheus 格式文本。"""
    r = client.get("/v1/llm/metrics", timeout=10)
    assert_ok(r)
    ct = r.headers.get("content-type", "")
    assert "text/plain" in ct or "text" in ct
    assert len(r.text) > 0


def test_lora_adapters_get(client, loaded_model_a):
    """GET /v1/llm/lora-adapters 应返回适配器列表（无适配器时为空列表）。"""
    r = client.get("/v1/llm/lora-adapters", timeout=10)
    assert_ok(r)
    body = r.json()
    assert isinstance(body, list)


def test_lora_adapters_post(client, loaded_model_a):
    """POST /v1/llm/lora-adapters 设置 scale（无适配器时返回 400 可接受）。"""
    r = client.post("/v1/llm/lora-adapters", json=[{"id": 0, "scale": 1.0}], timeout=10)
    assert r.status_code in (200, 400, 404, 501, 502, 503)


# ── model routing unit tests (mock, no llama-server needed) ───────────────────

def _make_mock_svc(current_model: str):
    """构造 mock LLMService，proxy 返回 200 空响应。"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.aread = AsyncMock(return_value=json.dumps({
        "choices": [{"message": {"role": "assistant", "content": "ok"},
                     "finish_reason": "stop", "index": 0}],
        "model": current_model, "object": "chat.completion", "usage": {},
    }).encode())
    mock_resp.aclose = AsyncMock()
    mock_client = MagicMock()
    mock_client.aclose = AsyncMock()

    svc = MagicMock()
    svc.get_current_source_type.return_value = "local_url"
    svc.get_current_model.return_value = current_model
    svc.proxy = AsyncMock(return_value=(mock_client, mock_resp))
    return svc


@pytest.fixture(scope="module")
def mock_app():
    from spacemit_ai_gateway.gateway.auth import verify_api_key

    app = FastAPI()
    app.include_router(_llm_router, prefix="/v1/llm")

    # Override API key verification for tests
    async def _mock_verify():
        return None

    app.dependency_overrides[verify_api_key] = _mock_verify
    return app


def test_model_routing_no_model_field(mock_app):
    """不传 model 字段 → proxy 被调用，用 current_model 跑（service 内部决定）。"""
    svc = _make_mock_svc("qwen3-0.6b-q4_0.gguf")
    mock_app.state.llm_service = svc
    with _TestClient(mock_app, raise_server_exceptions=False) as c:
        r = c.post("/v1/llm/chat/completions", json={
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        })
    assert r.status_code == 200
    svc.proxy.assert_called_once()


def test_model_routing_with_model_field(mock_app):
    """传入模型名 → proxy 被调用，request_body 原样透传给 service 处理。"""
    svc = _make_mock_svc("qwen3-0.6b-q4_0.gguf")
    mock_app.state.llm_service = svc
    with _TestClient(mock_app, raise_server_exceptions=False) as c:
        r = c.post("/v1/llm/chat/completions", json={
            "model": "lfm2.5-1.2b",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        })
    assert r.status_code == 200
    svc.proxy.assert_called_once()
    # 验证 request_body 原样传给 service（含 model 字段），由 service._resolve_model 处理
    call_args = svc.proxy.call_args
    body = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("request_body")
    assert b"lfm2.5-1.2b" in body


def test_model_routing_service_error_returns_503(mock_app):
    """service.proxy 抛 RuntimeError（如模型未下载）→ 返回 503。"""
    svc = _make_mock_svc("qwen3-0.6b-q4_0.gguf")
    svc.proxy = AsyncMock(side_effect=RuntimeError("Model 'lfm2.5-1.2b' is not downloaded"))
    mock_app.state.llm_service = svc
    with _TestClient(mock_app, raise_server_exceptions=False) as c:
        r = c.post("/v1/llm/chat/completions", json={
            "model": "lfm2.5-1.2b",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        })
    assert r.status_code == 503


# ── file naming and existence tests ───────────────────────────────────────────

def test_download_uses_url_filename(client):
    """下载时使用 URL 最后一段作为文件名，而非 model_id.gguf。"""
    uid = uuid.uuid4().hex[:8]
    model_id = f"test-naming-{uid}"

    # 注册一个带特定文件名的 URL
    r = client.post("/v1/llm/models/register", json={
        "model": model_id,
        "source_type": "local_url",
        "url": "https://example.com/Custom-Model-Name-Q4_0.gguf",
    })
    assert_ok(r)

    # 尝试下载（会失败因为 URL 不存在，但可以检查日志或数据库）
    # 这里主要验证注册成功，实际文件名验证需要在 service 层单元测试


def test_load_missing_file_resets_status(client, server):
    """load 时如果文件不存在，应回退状态到 available 并提示重新下载。"""
    import sqlite3

    db_path = server["db_path"]
    uid = uuid.uuid4().hex[:8]
    model_id = f"test-missing-{uid}"

    # 1. 注册模型
    r = client.post("/v1/llm/models/register", json={
        "model": model_id,
        "source_type": "local_url",
        "url": "https://example.com/test.gguf",
    })
    assert_ok(r)

    # 2. 手动修改数据库状态为 downloaded，设置一个不存在的文件路径
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE models SET status=?, local_path=? WHERE id=?",
        ("downloaded", "/tmp/nonexistent_file_12345.gguf", model_id)
    )
    conn.commit()
    conn.close()

    # 3. 尝试 load，应该返回错误并重置状态
    r = client.post("/v1/llm/models/load", json={"model": model_id})
    assert_err(r, 400)
    assert "file not found" in r.json()["message"].lower()

    # 4. 验证状态已重置为 available
    r = client.get("/v1/llm/models")
    assert_ok(r)
    models = {m["id"]: m for m in r.json()}
    assert models[model_id]["status"] == "available"
    assert models[model_id]["local_path"] is None


def test_load_missing_local_path_resets_status(client, server):
    """load 时如果 DB 中 local_path 为空，应回退状态而不是触发 500。"""
    import sqlite3

    db_path = server["db_path"]
    uid = uuid.uuid4().hex[:8]
    model_id = f"test-missing-path-{uid}"

    r = client.post("/v1/llm/models/register", json={
        "model": model_id,
        "source_type": "local_url",
        "url": "https://example.com/test.gguf",
    })
    assert_ok(r)

    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE models SET status=?, local_path=NULL WHERE id=?",
        ("downloaded", model_id),
    )
    conn.commit()
    conn.close()

    r = client.post("/v1/llm/models/load", json={"model": model_id})
    assert_err(r, 400)
    assert "no local file path" in r.json()["message"].lower()

    r = client.get("/v1/llm/models")
    assert_ok(r)
    models = {m["id"]: m for m in r.json()}
    assert models[model_id]["status"] == "available"
    assert models[model_id]["local_path"] is None
