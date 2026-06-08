from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PACKAGES = {
    "spacemit-ai-gateway",
    "spacemit-asr",
    "spacemit-tts",
    "spacemit-vad",
    "spacemit-audio",
    "spacemit-vision",
}


def _project_version() -> str:
    text = (ROOT / "pyproject.toml").read_text()
    match = re.search(r"^version = \"([^\"]+)\"", text, re.MULTILINE)
    assert match is not None
    return match.group(1)


def _runtime_pins() -> dict[str, str]:
    pins = {}
    for line in (ROOT / "requirements-runtime.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        assert "==" in line, f"runtime dependency must be exact-pinned: {line}"
        name, version = line.split("==", 1)
        assert name not in pins, f"duplicate runtime dependency: {name}"
        assert version, f"missing version for runtime dependency: {name}"
        pins[name] = version
    return pins


def test_gateway_runtime_pin_matches_project_version() -> None:
    assert _runtime_pins()["spacemit-ai-gateway"] == _project_version()


def test_spacemit_runtime_wheels_are_exact_pinned() -> None:
    pins = _runtime_pins()
    assert set(pins) == RUNTIME_PACKAGES
