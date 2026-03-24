from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Callable

from ..config import Settings, get_settings

try:
    import langsmith as _langsmith
    from langsmith.wrappers import wrap_openai as _wrap_openai
except ImportError:  # pragma: no cover - optional dependency
    _langsmith = None
    _wrap_openai = None


def is_langsmith_enabled(settings: Settings | None = None) -> bool:
    current_settings = settings or get_settings()
    return bool(current_settings.langsmith_tracing and current_settings.langsmith_api_key and _langsmith is not None)


def traceable(*args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    if _langsmith is None:
        return lambda func: func
    return _langsmith.traceable(*args, **kwargs)


def wrap_openai_client(client: Any, settings: Settings | None = None) -> Any:
    if not is_langsmith_enabled(settings) or _wrap_openai is None:
        return client
    return _wrap_openai(client)


@asynccontextmanager
async def chat_trace(
    *,
    name: str,
    inputs: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    settings: Settings | None = None,
):
    current_settings = settings or get_settings()
    if not is_langsmith_enabled(current_settings) or _langsmith is None:
        yield
        return

    client = _langsmith.Client(
        api_key=current_settings.langsmith_api_key,
        api_url=current_settings.langsmith_endpoint,
    )
    extra: dict[str, Any] = {
        'project_name': current_settings.langsmith_project,
        'metadata': metadata or {},
        'tags': tags or [],
        'client': client,
    }
    with _langsmith.tracing_context(
        enabled=True,
        project_name=current_settings.langsmith_project,
        client=client,
    ):
        traced = _langsmith.trace(
            name=name,
            run_type='chain',
            inputs=inputs,
            **extra,
        )
        with traced:
            yield
