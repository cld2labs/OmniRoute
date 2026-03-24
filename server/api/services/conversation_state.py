from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

SESSION_TTL = timedelta(minutes=10)

conversation_store: dict[str, dict[str, Any]] = {}


def get_state(conversation_id: str | None) -> dict[str, Any] | None:
    if not conversation_id:
        return None
    cleanup_stale_sessions()
    return conversation_store.get(conversation_id)


def set_state(conversation_id: str, state: dict[str, Any]) -> dict[str, Any]:
    cleanup_stale_sessions()
    current = dict(state)
    current['created_at'] = current.get('created_at') or _now()
    current['updated_at'] = _now()
    conversation_store[conversation_id] = current
    return current


def clear_state(conversation_id: str | None) -> None:
    if not conversation_id:
        return
    conversation_store.pop(conversation_id, None)


def resolve_state(conversation_id: str | None) -> dict[str, Any] | None:
    state = get_state(conversation_id)
    if state is None:
        return None
    created_at = state.get('created_at')
    if isinstance(created_at, datetime) and _now() - created_at > SESSION_TTL:
        clear_state(conversation_id)
        return None
    return state


def cleanup_stale_sessions() -> None:
    cutoff = _now() - SESSION_TTL
    stale_ids = [
        conversation_id
        for conversation_id, state in conversation_store.items()
        if not isinstance(state.get('created_at'), datetime) or state['created_at'] < cutoff
    ]
    for conversation_id in stale_ids:
        conversation_store.pop(conversation_id, None)


def _now() -> datetime:
    return datetime.now(timezone.utc)
