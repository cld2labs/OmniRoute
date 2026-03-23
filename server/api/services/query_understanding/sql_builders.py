from __future__ import annotations

from typing import Any


def build_sql_for_intent_family(filters: dict[str, Any], intent_context: dict[str, Any] | None) -> str | None:
    family = (intent_context or {}).get('intent_family')
    if family == 'route_delay_check':
        return _build_route_delay_check_sql(filters)
    if family == 'route_delay_explanation':
        return _build_route_delay_explanation_sql(filters)
    if family == 'reservation_count_in_range':
        return _build_reservation_count_in_range_sql(filters)
    if family == 'reservation_list_in_range':
        return _build_reservation_list_in_range_sql(filters)
    if family == 'route_status_list':
        return _build_route_status_list_sql(filters)
    return None


def _inclusive_day_upper_bound(param_name: str) -> str:
    return f"CAST(%({param_name})s AS date) + INTERVAL '1 day'"


def _sql_limit(filters: dict[str, Any], default: int = 20) -> str:
    limit = filters.get('limit')
    return '%(limit)s' if limit is not None else str(default)


def _route_scope_predicate(filters: dict[str, Any], *, route_alias: str = 'r') -> str:
    if filters.get('route_id') is not None:
        return f'{route_alias}.id = %(route_id)s'
    if filters.get('route_name') is not None:
        return f'{route_alias}.route_name = %(route_name)s'
    if filters.get('origin') is not None:
        return f'{route_alias}.origin_name = %(origin)s'
    if filters.get('destination') is not None:
        return f'{route_alias}.destination_name = %(destination)s'
    raise ValueError('Deterministic route-scoped SQL requires a normalized route, origin, or destination filter.')


def _build_route_delay_check_sql(filters: dict[str, Any]) -> str:
    if any(filters.get(key) is not None for key in ('route_id', 'route_name', 'origin', 'destination')):
        route_predicate = _route_scope_predicate(filters)
        return (
            'SELECT COUNT(*) AS delayed_trip_count '
            'FROM trips t '
            'JOIN routes r ON r.id = t.route_id '
            f'WHERE {route_predicate} '
            'AND r.is_active = true '
            'AND t.status = %(status)s '
            ';'
        )
    return (
        'SELECT COUNT(DISTINCT t.route_id) AS delayed_route_count '
        'FROM trips t '
        'JOIN routes r ON r.id = t.route_id '
        'WHERE r.is_active = true '
        'AND t.status = %(status)s '
        ';'
    )


def _build_route_delay_explanation_sql(filters: dict[str, Any]) -> str:
    if any(filters.get(key) is not None for key in ('route_id', 'route_name', 'origin', 'destination')):
        route_predicate = _route_scope_predicate(filters)
        return (
            'SELECT i.id AS incident_id, i.route_id, i.trip_id, r.route_name, i.incident_type, i.occurred_at, '
            'i.summary, i.details, i.proof_url, t.delay_minutes '
            'FROM incidents i '
            'LEFT JOIN trips t ON t.id = i.trip_id '
            'LEFT JOIN routes r ON r.id = COALESCE(i.route_id, t.route_id) '
            f'WHERE {route_predicate} '
            "AND i.occurred_at >= %(date_from)s "
            f'AND i.occurred_at < {_inclusive_day_upper_bound("date_to")} '
            'ORDER BY i.occurred_at DESC '
            f'LIMIT {_sql_limit(filters)};'
        )
    return (
        'SELECT i.id AS incident_id, i.route_id, i.trip_id, r.route_name, i.incident_type, i.occurred_at, '
        'i.summary, i.details, i.proof_url, t.delay_minutes '
        'FROM incidents i '
        'LEFT JOIN trips t ON t.id = i.trip_id '
        'LEFT JOIN routes r ON r.id = COALESCE(i.route_id, t.route_id) '
        'WHERE EXISTS ('
        'SELECT 1 FROM trips t2 '
        'WHERE t2.route_id = COALESCE(i.route_id, t.route_id) '
        'AND t2.status = %(status)s '
        "AND t2.departure_time >= %(date_from)s "
        f'AND t2.departure_time < {_inclusive_day_upper_bound("date_to")} '
        ') '
        "AND i.occurred_at >= %(date_from)s "
        f'AND i.occurred_at < {_inclusive_day_upper_bound("date_to")} '
        'ORDER BY i.occurred_at DESC '
        f'LIMIT {_sql_limit(filters)};'
    )


def _build_reservation_count_in_range_sql(filters: dict[str, Any]) -> str:
    del filters
    return (
        'SELECT COUNT(*) AS reservation_count '
        'FROM reservations r '
        "WHERE r.created_at >= %(date_from)s "
        f'AND r.created_at < {_inclusive_day_upper_bound("date_to")};'
    )


def _build_reservation_list_in_range_sql(filters: dict[str, Any]) -> str:
    del filters
    return (
        'SELECT r.id AS reservation_id, r.trip_id, r.customer_name, r.email, r.phone_number, '
        'r.seats_booked, r.amount_paid_cents, r.status, r.created_at, r.updated_at '
        'FROM reservations r '
        "WHERE r.created_at >= %(date_from)s "
        f'AND r.created_at < {_inclusive_day_upper_bound("date_to")} '
        'ORDER BY r.created_at DESC '
        f'LIMIT {_sql_limit(filters)};'
    )


def _build_route_status_list_sql(filters: dict[str, Any]) -> str:
    status = filters.get('status')
    if status == 'active':
        return (
            'SELECT r.id AS route_id, r.route_name, r.origin_name, r.destination_name, r.base_price_cents, '
            'MIN(t.departure_time) AS next_departure_time '
            'FROM routes r '
            'LEFT JOIN trips t ON t.route_id = r.id AND t.departure_time >= CURRENT_TIMESTAMP '
            'WHERE r.is_active = true '
            'GROUP BY r.id, r.route_name, r.origin_name, r.destination_name, r.base_price_cents '
            'ORDER BY r.route_name '
            f'LIMIT {_sql_limit(filters)};'
        )
    if status in {'delayed', 'completed'}:
        status_count_alias = 'delayed_trip_count' if status == 'delayed' else 'completed_trip_count'
        return (
            'SELECT r.id AS route_id, r.route_name, r.origin_name, r.destination_name, r.base_price_cents, '
            f'COUNT(t.id) AS {status_count_alias}, '
            'MIN(CASE WHEN t.departure_time >= CURRENT_TIMESTAMP THEN t.departure_time END) AS next_departure_time '
            'FROM routes r '
            'JOIN trips t ON t.route_id = r.id '
            'WHERE r.is_active = true '
            'AND t.status = %(status)s '
            'GROUP BY r.id, r.route_name, r.origin_name, r.destination_name, r.base_price_cents '
            'ORDER BY r.route_name '
            f'LIMIT {_sql_limit(filters)};'
        )
    raise ValueError('Deterministic route status listing requires a supported route status filter.')
