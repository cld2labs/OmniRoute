from __future__ import annotations

import re

INTENT_PATTERNS = [
    ('why_route_delayed', [
        r'why\b.{0,30}\broute\b',
        r'what caused.{0,30}\broute\b',
        r'reason.{0,30}\broute.{0,30}\bdelay',
        r'why.{0,30}\bdelayed\b.{0,30}\broute\b',
    ]),
    ('why_trip_delayed', [
        r'why\b.{0,30}\btrip\b',
        r'what caused.{0,30}\btrip\b',
        r'reason.{0,30}\btrip.{0,30}\bdelay',
    ]),
    ('routes_delayed_count', [
        r'how many\b.{0,30}\broutes?\b.{0,30}\b(delayed|late)\b',
        r'how many\b.{0,30}\b(delayed|late)\b.{0,30}\broutes?\b',
        r'(count|number of|total)\b.{0,30}\broutes?\b.{0,30}\b(delayed|late)\b',
        r'(count|number of|total)\b.{0,30}\b(delayed|late)\b.{0,30}\broutes?\b',
    ]),
    ('routes_delayed', [
        r'(show|list|which|get|find)\b.{0,20}\b(delayed|late)\b.{0,20}\broutes?\b',
        r'\broutes?\b.{0,20}\b(delayed|late|have delays|with delays)\b',
        r'\bdelayed\b.{0,20}\broutes?\b',
    ]),
    ('route_delayed_trips', [
        r'\bdelayed\b.{0,30}\btrips?\b.{0,30}\broute\b',
        r'\btrips?\b.{0,30}\bdelayed\b.{0,30}\broute\b',
        r'(show|list|which)\b.{0,20}\btrips?\b.{0,30}\bdelayed\b',
    ]),
    ('route_operational_summary', [
        r'\boperational\b.{0,20}\b(status|summary|overview)\b',
        r'\b(status|summary|overview)\b.{0,20}\b(all|every)\b.{0,20}\broutes?\b',
        r'\broute.{0,20}(dashboard|overview|summary)\b',
    ]),
]


def classify_intent(query: str) -> str | None:
    normalized = query.strip().lower()
    for intent, patterns in INTENT_PATTERNS:
        if any(re.search(pattern, normalized, re.IGNORECASE) for pattern in patterns):
            return intent
    return None
