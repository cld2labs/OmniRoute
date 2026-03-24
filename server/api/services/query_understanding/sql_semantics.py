from __future__ import annotations

import re
from typing import Any


def validate_sql_matches_filters(
    sql: str,
    filters: dict[str, Any],
    *,
    entity: str | None = None,
    operation: str | None = None,
) -> None:
    sql_lower = sql.lower()
    _validate_target_entity(sql_lower, entity=entity, operation=operation)
    if filters.get('origin'):
        if 'origin_name' not in sql_lower:
            raise ValueError("Generated SQL does not honor the normalized origin filter.")
        if _uses_route_name_placeholder(sql_lower):
            raise ValueError("Generated SQL used route_name where origin_name was required.")
    if filters.get('destination'):
        if 'destination_name' not in sql_lower:
            raise ValueError("Generated SQL does not honor the normalized destination filter.")
        if _uses_route_name_placeholder(sql_lower):
            raise ValueError("Generated SQL used route_name where destination_name was required.")


def _uses_route_name_placeholder(sql_lower: str) -> bool:
    return re.search(r'route_name\s*=\s*(%\(|:)?route_name', sql_lower) is not None


def _validate_target_entity(sql_lower: str, *, entity: str | None, operation: str | None) -> None:
    del operation
    if entity is None:
        return

    table_pattern = {
        'routes': r'\bfrom\s+routes\b',
        'trips': r'\bfrom\s+trips\b',
        'reservations': r'\bfrom\s+reservations\b',
        'incidents': r'\bfrom\s+incidents\b',
    }.get(entity)
    if table_pattern is None:
        return
    if re.search(table_pattern, sql_lower) is None:
        raise ValueError(f"Generated SQL did not target the validated entity '{entity}'.")
