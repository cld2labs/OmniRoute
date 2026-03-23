from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Mapping


MAX_EMBEDDING_TEXT_CHARS = 4000
_WHITESPACE_RE = re.compile(r'\s+')


def _collapse_whitespace(value: Any) -> str:
    return _WHITESPACE_RE.sub(' ', str(value or '')).strip()


def _get_incident_value(incident: Mapping[str, Any] | Any, field_name: str) -> Any:
    if isinstance(incident, Mapping):
        return incident.get(field_name)
    return getattr(incident, field_name, None)


def _serialize_occurred_at(incident: Mapping[str, Any] | Any) -> str:
    raw_value = _get_incident_value(incident, 'occurred_at')
    if isinstance(raw_value, datetime):
        return raw_value.isoformat()
    return _collapse_whitespace(raw_value)


def build_incident_embedding_text(
    incident: Mapping[str, Any] | Any,
    route_name: str | None,
    trip_context: str | None,
) -> str:
    route_value = _collapse_whitespace(route_name) or 'unknown'
    trip_value = _collapse_whitespace(trip_context) or 'unknown'
    incident_type = _collapse_whitespace(_get_incident_value(incident, 'incident_type'))
    occurred_at = _serialize_occurred_at(incident)
    summary = _collapse_whitespace(_get_incident_value(incident, 'summary'))
    details = _collapse_whitespace(_get_incident_value(incident, 'details'))

    lines = [
        f'Route: {route_value}',
        f'Trip: {trip_value}',
        f'Type: {incident_type}',
        f'OccurredAt: {occurred_at}',
        f'Summary: {summary}',
    ]
    if details:
        lines.append(f'Details: {details}')

    text = '\n'.join(lines).strip()
    if len(text) <= MAX_EMBEDDING_TEXT_CHARS:
        return text
    return text[:MAX_EMBEDDING_TEXT_CHARS].rstrip()
