"""LangSmith tracing helpers. No Streamlit dependency."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from typing import Any

from atrium.config import TRACING_FLAG_VARS

DEFAULT_ENDPOINT = "https://api.smith.langchain.com"


def tracing_project() -> str | None:
    return os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT")


def tracing_enabled() -> bool:
    has_key = bool(os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY"))
    flag_on = any(os.getenv(name, "").lower() == "true" for name in TRACING_FLAG_VARS)
    return has_key and flag_on


def refresh_env_cache() -> None:
    """langsmith memoises env lookups; clear them after ``apply_env``."""

    try:
        from langsmith.utils import get_env_var

        get_env_var.cache_clear()
    except Exception:  # pragma: no cover - defensive
        pass


@contextlib.contextmanager
def trace(project: str | None = None) -> Iterator[Any]:
    """Force tracing for the wrapped block and yield the tracer (or ``None``).

    A failed trace upload never propagates out of here.
    """

    if not tracing_enabled():
        yield None
        return
    from langchain_core.tracers.context import tracing_v2_enabled

    with tracing_v2_enabled(project_name=project or tracing_project()) as tracer:
        yield tracer


def check_connection() -> tuple[bool, str]:
    """Ping the LangSmith API with the configured key. Returns ``(ok, message)``."""

    try:
        from langsmith import Client

        client = Client()
        list(client.list_projects(limit=1))  # forces an authenticated request
    except Exception as exc:  # noqa: BLE001 - report whatever the API said
        return False, f"LangSmith rechazó la conexión: {exc}"

    endpoint = os.getenv("LANGSMITH_ENDPOINT", DEFAULT_ENDPOINT)
    message = f"Conecta OK ({endpoint})"
    project = tracing_project()
    if project:
        with contextlib.suppress(Exception):
            if not client.has_project(project_name=project):
                message += (
                    f" — el proyecto '{project}' todavía no existe (se crea con el primer trace)"
                )
    return True, message
