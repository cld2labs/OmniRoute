from __future__ import annotations

from datetime import datetime
from typing import Any

from ...models.schemas import ValidatedQueryIntent
from .internal_plan import InternalQueryPlan


def _limited_data_message() -> str:
    return 'I’m not able to answer that confidently with the current operational data. Try narrowing it by route, trip, date, or status.'


def synthesize_response(
    *,
    intent: ValidatedQueryIntent,
    plan: InternalQueryPlan,
    block_results: dict[str, list[dict[str, Any]]],
    vector_records: list[dict[str, Any]],
) -> tuple[str, str]:
    sql_total = sum(len(rows) for rows in block_results.values())
    if sql_total == 0 and not (plan.response_mode == 'incident_explanation' and vector_records):
        return _limited_data_message(), 'low'

    if plan.response_mode == 'route_list':
        answer = _route_list_answer(block_results)
    elif plan.response_mode == 'trip_list':
        answer = _trip_list_answer(block_results, intent)
    elif plan.response_mode == 'reservation_list':
        answer = _reservation_list_answer(block_results)
    elif plan.response_mode == 'reservation_compare':
        answer = _reservation_compare_answer(block_results)
    elif plan.response_mode == 'incident_compare':
        answer = _incident_compare_answer(block_results)
    elif plan.response_mode == 'incident_explanation':
        answer = _incident_explanation_answer(intent, block_results, vector_records)
    elif plan.response_mode == 'count':
        answer = _count_answer(intent, block_results)
    else:
        answer = f"Found {sql_total} records matching the request."

    confidence = 'high' if sql_total else 'medium' if vector_records else 'low'
    return answer, confidence


def _route_list_answer(block_results: dict[str, list[dict[str, Any]]]) -> str:
    rows = block_results.get('generated_sql') or []
    if not rows:
        return 'No routes matched the requested filters.'
    if len(rows) == 1:
        row = rows[0]
        route_name = row.get('route_name') or row.get('id') or 'the requested route'
        delayed_trip_count = row.get('delayed_trip_count')
        next_departure = _format_time(row.get('next_departure_time')) if row.get('next_departure_time') else None
        if delayed_trip_count is not None:
            if next_departure:
                return f'I found 1 delayed route: {route_name}. It has {delayed_trip_count} delayed trips, and the next matching departure is {next_departure}.'
            return f'I found 1 delayed route: {route_name}. It has {delayed_trip_count} delayed trips.'
        if row.get('origin_name') and row.get('destination_name'):
            if next_departure:
                return f"I found 1 route from {row['origin_name']} to {row['destination_name']}: {route_name}. Next departure is {next_departure}."
            return f"I found 1 route from {row['origin_name']} to {row['destination_name']}: {route_name}."
        return f'I found 1 route in scope: {route_name}.'
    first = rows[0]
    first_name = first.get('route_name') or first.get('id') or 'the first route'
    delayed_trip_count = first.get('delayed_trip_count')
    next_departure = _format_time(first.get('next_departure_time')) if first.get('next_departure_time') else None
    if delayed_trip_count is not None:
        if next_departure:
            return (
                f'I found {len(rows)} delayed routes. The first result is {first_name}, '
                f'with {delayed_trip_count} delayed trips and next matching departure at {next_departure}.'
            )
        return f'I found {len(rows)} delayed routes. The first result is {first_name}, with {delayed_trip_count} delayed trips.'
    if next_departure:
        return f'I found {len(rows)} routes. The first result is {first_name}, with next departure at {next_departure}.'
    return f'I found {len(rows)} routes. The first result is {first_name}.'


def _trip_list_answer(block_results: dict[str, list[dict[str, Any]]], intent: ValidatedQueryIntent) -> str:
    rows = block_results.get('generated_sql') or []
    if not rows:
        return 'No trips matched the requested filters.'
    route_label = intent.filters.route_name or rows[0].get('route_name') or 'the selected route'
    return f"I found {len(rows)} trips for {route_label}."


def _reservation_list_answer(block_results: dict[str, list[dict[str, Any]]]) -> str:
    rows = block_results.get('generated_sql') or []
    if not rows:
        return 'No reservations matched the requested filters.'
    return f"I found {len(rows)} reservations in scope."


def _reservation_compare_answer(block_results: dict[str, list[dict[str, Any]]]) -> str:
    rows = block_results.get('generated_sql') or []
    if not rows:
        return 'No reservation activity matched the requested filters.'
    leader = rows[0]
    count_value = next((leader[key] for key in leader if 'count' in key), len(rows))
    return (
        f"Compared reservation activity across {len(rows)} routes. "
        f"{leader.get('route_name', 'The top route')} has the highest activity with {count_value} reservations."
    )


def _incident_compare_answer(block_results: dict[str, list[dict[str, Any]]]) -> str:
    rows = block_results.get('generated_sql') or []
    if not rows:
        return 'No incident aggregates matched the requested filters.'
    leader = rows[0]
    count_value = next((leader[key] for key in leader if 'count' in key), len(rows))
    return f"{leader.get('route_name', 'The top route')} has the most incidents at {count_value}."


def _incident_explanation_answer(
    intent: ValidatedQueryIntent,
    block_results: dict[str, list[dict[str, Any]]],
    vector_records: list[dict[str, Any]],
) -> str:
    rows = block_results.get('generated_sql') or []
    route_label = intent.filters.route_name or 'the selected route'

    parts: list[str] = []
    if rows:
        first = rows[0]
        route_label = first.get('route_name') or route_label
        incident_count = len(rows)
        if first.get('incident_type'):
            parts.append(
                f'I found {incident_count} structured incident records tied to {route_label}. '
                f"The leading visible incident type is {first.get('incident_type')}."
            )
        else:
            parts.append(f'I found {incident_count} structured records tied to {route_label}.')
    if vector_records:
        parts.append(f"Similar incident narratives also point to '{vector_records[0]['summary']}' as related context.")
    return ' '.join(parts) if parts else _limited_data_message()


def _count_answer(intent: ValidatedQueryIntent, block_results: dict[str, list[dict[str, Any]]]) -> str:
    first_rows = block_results.get('generated_sql') or next(iter(block_results.values()), [])
    if not first_rows:
        return _limited_data_message()
    row = first_rows[0]
    count_value = next((value for key, value in row.items() if key.endswith('_count') or key == 'count'), None)
    if count_value is None:
        count_value = 0
    if intent.metric == 'boolean_check':
        subject = _boolean_subject(intent)
        if count_value:
            return f"Yes. I found {count_value} matching {subject}."
        return f'No. I did not find matching {subject}.'
    return f"There are {count_value} {intent.entity} matching the current filters."


def _boolean_subject(intent: ValidatedQueryIntent) -> str:
    if intent.entity == 'trips' and intent.filters.route_name and intent.filters.status:
        return f"{intent.filters.status} trips for {intent.filters.route_name}"
    if intent.entity == 'incidents' and intent.filters.route_name:
        return f"incidents for {intent.filters.route_name}"
    if intent.entity == 'reservations':
        return 'reservations in the requested scope'
    return f'{intent.entity} in the requested scope'


def _format_time(value: Any) -> str:
    if value is None:
        return 'not scheduled'
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M')
    return str(value)
