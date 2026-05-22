"""Backend selection helpers for configurable domain allow-lists."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeVar

T = TypeVar("T")


def resolve_allowed_backends(
    configured: Sequence[str] | None,
    default: str,
    registry: Mapping[str, T],
    loaded: Mapping[str, object] | None = None,
) -> list[str]:
    """Return configured backends that can actually be used.

    ``loaded`` keeps unit-test and preconstructed backend injection working while
    production lazy services normally rely on ``registry`` only.
    """

    available = set(registry)
    if loaded:
        available.update(loaded)

    if configured:
        allowed = [name for name in configured if name in available]
    else:
        allowed = [default] if default in available else []

    if loaded and default in loaded and default not in allowed:
        allowed.insert(0, default)

    if allowed:
        return allowed
    if default in available:
        return [default]
    if registry:
        return [next(iter(registry))]
    if loaded:
        return [next(iter(loaded))]
    return []


def select_default_backend(
    configured_default: str,
    configured_backends: Sequence[str] | None,
    registry: Mapping[str, T],
) -> str:
    allowed = resolve_allowed_backends(configured_backends, configured_default, registry)
    if not allowed:
        raise ValueError("no backend registered")
    if configured_default in allowed:
        return configured_default
    return allowed[0]
