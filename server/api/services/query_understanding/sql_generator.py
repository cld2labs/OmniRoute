from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from uuid import UUID

from ...config import get_settings


class SQLGenerationInsufficientDataError(ValueError):
    pass

AGENT_FEW_SHOTS = {
    'operations': """
"Which trips are delayed on Route Alpha?" ->
SELECT t.id, t.departure_time, t.delay_minutes, t.status FROM trips t JOIN routes r ON r.id = t.route_id WHERE r.route_name = %(route_name)s AND t.status = 'delayed' ORDER BY t.departure_time LIMIT 50;

"Show me routes from Los Angeles" ->
SELECT r.id AS route_id, r.route_name, r.origin_name, r.destination_name, r.base_price_cents, MIN(t.departure_time) AS next_departure_time FROM routes r LEFT JOIN trips t ON t.route_id = r.id AND t.departure_time >= CURRENT_TIMESTAMP WHERE r.origin_name = %(origin)s GROUP BY r.id, r.route_name, r.origin_name, r.destination_name, r.base_price_cents ORDER BY r.route_name LIMIT 20;

"Status breakdown for trips this week?" ->
SELECT t.status, COUNT(*) as count FROM trips t WHERE t.departure_time >= date_trunc('week', CURRENT_DATE) AND t.departure_time < date_trunc('week', CURRENT_DATE) + interval '7 days' GROUP BY t.status ORDER BY count DESC LIMIT 20;

"Routes with most delayed trips this month?" ->
SELECT r.route_name, COUNT(*) as delayed_count FROM trips t JOIN routes r ON r.id = t.route_id WHERE t.status = 'delayed' AND t.departure_time >= date_trunc('month', CURRENT_DATE) GROUP BY r.route_name ORDER BY delayed_count DESC LIMIT 20;
""".strip(),
    'reservations': """
"How many cancellations today?" ->
SELECT COUNT(*) as cancellations FROM reservations r WHERE r.status = 'cancelled' AND r.updated_at::date = CURRENT_DATE LIMIT 1;

"Seat utilization for Route B this week?" ->
SELECT r.route_name, SUM(t.capacity_total) as total_seats, SUM(t.capacity_total - t.seats_available) as booked_seats, ROUND(100.0 * SUM(t.capacity_total - t.seats_available) / NULLIF(SUM(t.capacity_total), 0), 2) as utilization_pct FROM trips t JOIN routes r ON r.id = t.route_id WHERE r.route_name = %(route_name)s AND t.departure_time >= date_trunc('week', CURRENT_DATE) GROUP BY r.route_name LIMIT 10;
""".strip(),
    'insights': """
"Why has Route A been delayed this week?" ->
SELECT i.id, i.incident_type, i.occurred_at, i.summary, t.delay_minutes FROM incidents i JOIN routes r ON r.id = i.route_id LEFT JOIN trips t ON t.id = i.trip_id WHERE r.route_name = %(route_name)s AND i.occurred_at >= date_trunc('week', CURRENT_DATE) ORDER BY i.occurred_at DESC LIMIT 20;

"Routes with weather incidents AND cancellations last week?" ->
SELECT r.route_name, COUNT(DISTINCT i.id) as weather_incidents, COUNT(DISTINCT CASE WHEN t.status = 'cancelled' THEN t.id END) as cancelled_trips FROM routes r JOIN incidents i ON i.route_id = r.id JOIN trips t ON t.route_id = r.id WHERE i.incident_type = 'weather' AND i.occurred_at >= CURRENT_DATE - interval '7 days' AND t.departure_time >= CURRENT_DATE - interval '7 days' GROUP BY r.route_name HAVING COUNT(DISTINCT i.id) > 0 AND COUNT(DISTINCT CASE WHEN t.status = 'cancelled' THEN t.id END) > 0 ORDER BY weather_incidents DESC LIMIT 20;
""".strip(),
}

SYSTEM_PROMPT_TEMPLATE = """
You are a PostgreSQL SQL generator for OmniRoute, an internal transportation operations platform.

{schema_context}

RULES:
- Return ONLY valid JSON matching the schema above. No markdown. No explanation. No preamble.
- Use only the tables and columns defined in the schema context. Never invent columns.
- Generate only SELECT statements. Never use DROP, DELETE, UPDATE, INSERT, TRUNCATE, ALTER, CREATE, GRANT, REVOKE.
- Never reference incidents.embedding in SQL - that column is for vector search only.
- Always include LIMIT (maximum 200).
- Use %(param_name)s placeholders for all user-supplied values.
- If the query is ambiguous or missing a required filter, set needs_clarification: true and write a specific clarification_question. Do not guess.
- If the question cannot be answered from the schema, set needs_clarification: true and explain in clarification_question.
- Temperature is 0. Be deterministic.
- Respect the validated target entity and operation exactly. Do not switch to another entity.
- If target entity is routes, start from routes unless the query is impossible without a simple FK join.
- If target entity is trips, start from trips.
- If target entity is reservations, start from reservations.
- If target entity is incidents, start from incidents.
- Use only the normalized filters that are provided. Do not reinterpret origin or destination as route_name.
- For route listing queries, include the next upcoming trip departure as next_departure_time when trips can be joined.

Response JSON schema:
{{
  "sql": "SELECT ... LIMIT 50",
  "needs_clarification": false,
  "clarification_question": null,
  "ambiguity_reason": null
}}

Available params: %(route_name)s %(trip_id)s %(reservation_id)s %(incident_id)s %(date_from)s %(date_to)s %(status)s %(incident_type)s %(limit)s

EXAMPLES:
{few_shot_examples}
""".strip()


def _intent_family_guidance(intent_context: dict[str, Any] | None) -> str:
    family = (intent_context or {}).get('intent_family')
    if family == 'route_delay_check':
        return (
            'Intent family contract: route_delay_check.\n'
            '- Treat "route delayed" as delayed trips on active routes with no implicit time window.\n'
            '- Prefer COUNT(*) AS delayed_trip_count from trips joined to routes.\n'
            '- Use COUNT(DISTINCT t.route_id) AS delayed_route_count for global delayed-route counts.\n'
            '- Honor route_id or route_name if provided.\n'
            '- Do not query incidents for this family.\n'
        )
    if family == 'route_delay_explanation':
        return (
            'Intent family contract: route_delay_explanation.\n'
            '- Explain route delay using recent incidents tied to the route or its trips.\n'
            '- Prefer incidents joined to routes, with optional join to trips for delay context.\n'
            '- Do not require incident_type = delay unless it was explicitly provided after normalization.\n'
            '- Order by incident recency descending.\n'
        )
    if family == 'reservation_count_in_range':
        return (
            'Intent family contract: reservation_count_in_range.\n'
            '- Count reservations by reservations.created_at over the normalized date_from/date_to range.\n'
            '- Treat the date range as inclusive whole days.\n'
            '- Use created_at >= %(date_from)s AND created_at < CAST(%(date_to)s AS date) + INTERVAL \'1 day\'.\n'
            '- Prefer COUNT(*) AS reservation_count.\n'
        )
    if family == 'reservation_list_in_range':
        return (
            'Intent family contract: reservation_list_in_range.\n'
            '- List reservations by reservations.created_at over the normalized date_from/date_to range.\n'
            '- Treat the date range as inclusive whole days.\n'
            '- Use created_at >= %(date_from)s AND created_at < CAST(%(date_to)s AS date) + INTERVAL \'1 day\'.\n'
            '- Order by created_at descending.\n'
        )
    if family == 'route_status_list':
        return (
            'Intent family contract: route_status_list.\n'
            '- If status is active, list routes where routes.is_active = true.\n'
            '- If status is delayed or completed, list active routes having at least one trip with that trip status.\n'
            '- Treat route status here as a derived trip condition, not a route table fact.\n'
            '- Prefer including COUNT(t.id) for the matching trip status per route.\n'
            '- For route listings, include next_departure_time when trips can be joined.\n'
        )
    return ''


def _json_safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


async def generate_sql(
    natural_language_query: str,
    agent: str,
    filters: dict[str, Any],
    llm_client: Any,
    schema_context: str,
    *,
    intent_context: dict[str, Any] | None = None,
    error_feedback: str | None = None,
) -> dict[str, Any]:
    if llm_client is None:
        raise ValueError('LLM SQL generation is unavailable because no LLM client is configured.')

    settings = get_settings()
    few_shot_examples = AGENT_FEW_SHOTS.get(agent, AGENT_FEW_SHOTS['operations'])
    family_guidance = _intent_family_guidance(intent_context)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(schema_context=schema_context, few_shot_examples=few_shot_examples)
    if family_guidance:
        system_prompt = f'{system_prompt}\n\n{family_guidance}'.strip()
    user_prompt = (
        f'Agent: {agent}\n'
        f'Intent context: {json.dumps(_json_safe(intent_context or {}), sort_keys=True)}\n'
        f'Question: {natural_language_query}\n'
        f'Filters: {json.dumps(_json_safe(filters), sort_keys=True)}\n'
        'Generate the best single SQL query for this request.'
    )
    if error_feedback:
        user_prompt = (
            f'{user_prompt}\n'
            f'Previous attempt failed validation with this error: {error_feedback}\n'
            'Fix the SQL and return corrected JSON.'
        )
    response = await llm_client.responses.create(
        model=settings.llm_model,
        temperature=0,
        max_output_tokens=512,
        input=[
            {'role': 'system', 'content': [{'type': 'input_text', 'text': system_prompt}]},
            {'role': 'user', 'content': [{'type': 'input_text', 'text': user_prompt}]},
        ],
    )
    content = getattr(response, 'output_text', '') or ''
    payload = _parse_generation_payload(content)
    if payload['needs_clarification']:
        return payload
    if payload['sql'] is None:
        raise SQLGenerationInsufficientDataError('This question cannot be answered from the available operational data.')
    return payload


def _parse_generation_payload(content: str) -> dict[str, Any]:
    text = content.strip()
    if text == 'INSUFFICIENT_DATA':
        raise SQLGenerationInsufficientDataError('This question cannot be answered from the available operational data.')

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {
            'sql': text,
            'needs_clarification': False,
            'clarification_question': None,
            'ambiguity_reason': None,
        }

    return {
        'sql': parsed.get('sql'),
        'needs_clarification': bool(parsed.get('needs_clarification', False)),
        'clarification_question': parsed.get('clarification_question'),
        'ambiguity_reason': parsed.get('ambiguity_reason'),
    }
