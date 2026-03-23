from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ...models.schemas import IntentFilters, ValidatedQueryIntent
from .internal_plan import InternalQueryPlan, build_internal_plan


@dataclass(slots=True)
class ChainedQuerySpec:
    key: str
    primary_agent: str
    delegated_agent: str
    root_intent: ValidatedQueryIntent
    root_plan: InternalQueryPlan
    delegated_template_intent: ValidatedQueryIntent

    @property
    def execution_mode(self) -> str:
        return 'sql_plus_vector' if self.delegated_agent == 'insights' else 'sql_only'

    @property
    def active_agents(self) -> list[str]:
        return ['planner', self.primary_agent, self.delegated_agent]

    @property
    def handoffs(self) -> list[str]:
        final_step = 'grounded_route_delay_causes' if self.key == 'delayed_routes_with_causes' else 'grounded_route_delay_reservations'
        return [
            f'planner -> {self.primary_agent}',
            f'{self.primary_agent} -> {self.delegated_agent}',
            f'{self.delegated_agent} -> {final_step}',
        ]

    @property
    def task_descriptions(self) -> list[str]:
        if self.key == 'delayed_routes_with_causes':
            return [
                'planner routes delayed-route explanation request to operations',
                'operations identifies delayed routes from grounded trip data',
                'operations delegates route-level cause lookups to insights',
            ]
        return [
            'planner routes route-delay reservation request to operations',
            'operations verifies delayed route status from grounded trip data',
            'operations delegates route reservation counting to reservations',
        ]

    @property
    def available_tools(self) -> list[str]:
        tools = ['operations:sql_db_query', f'{self.delegated_agent}:sql_db_query']
        if self.delegated_agent == 'insights':
            tools.append('insights:incident_vector_search')
        return tools

    def delegated_intent_for_row(self, row: dict[str, Any]) -> ValidatedQueryIntent | None:
        route_name = row.get('route_name') or self.root_intent.filters.route_name
        route_id = row.get('route_id') or self.root_intent.filters.route_id
        if self.key == 'delayed_routes_with_causes':
            if not route_name and route_id is None:
                return None
            return self.delegated_template_intent.model_copy(
                deep=True,
                update={
                    'filters': self.delegated_template_intent.filters.model_copy(
                        update={
                            'route_name': route_name,
                            'route_id': route_id,
                        }
                    )
                },
            )
        if self.key == 'route_delay_and_reservation_count':
            return self.delegated_template_intent
        return None

    def delegated_query_for_row(self, row: dict[str, Any]) -> str:
        route_name = row.get('route_name') or self.root_intent.filters.route_name or 'the selected route'
        if self.key == 'delayed_routes_with_causes':
            return f'why is {route_name} delayed?'
        return f'how many reservations do we have for {route_name}?'

    def root_query_text(self) -> str:
        route_name = self.root_intent.filters.route_name or 'the selected route'
        if self.key == 'delayed_routes_with_causes':
            return 'which routes are delayed?'
        return f'is {route_name} delayed?'


def detect_chained_query(query_text: str, intent: ValidatedQueryIntent) -> ChainedQuerySpec | None:
    normalized = query_text.strip().lower()

    if _looks_like_delayed_routes_with_causes(normalized):
        root_intent = ValidatedQueryIntent(
            entity='routes',
            operation='list',
            intent_family='route_status_list',
            filters=intent.filters.model_copy(
                update={
                    'status': 'delayed',
                    'incident_type': None,
                }
            ),
            limit=min(intent.limit, 20),
            resolution_notes=['Chained use case: operations lists delayed routes before insights explains each route.'],
        )
        delegated_intent = ValidatedQueryIntent(
            entity='incidents',
            operation='explain',
            intent_family='route_delay_explanation',
            filters=IntentFilters(
                date_from=intent.filters.date_from,
                date_to=intent.filters.date_to,
                incident_type=intent.filters.incident_type,
                limit=2,
            ),
            limit=2,
            resolution_notes=['Chained use case: insights explains delay causes for routes produced by operations.'],
        )
        return ChainedQuerySpec(
            key='delayed_routes_with_causes',
            primary_agent='operations',
            delegated_agent='insights',
            root_intent=root_intent,
            root_plan=build_internal_plan('operations', root_intent),
            delegated_template_intent=delegated_intent,
        )

    if _looks_like_route_delay_and_reservation_count(normalized, intent):
        filters = intent.filters.model_copy(
            update={
                'status': 'delayed',
                'incident_type': None,
            }
        )
        root_intent = ValidatedQueryIntent(
            entity='trips',
            operation='count',
            intent_family='route_delay_check',
            filters=filters.model_copy(update={'date_from': None, 'date_to': None, 'relative_time_window': None}),
            metric='boolean_check',
            limit=1,
            resolution_notes=['Chained use case: operations verifies route delay before reservations counts bookings.'],
        )
        delegated_intent = ValidatedQueryIntent(
            entity='reservations',
            operation='count',
            filters=IntentFilters(
                route_id=intent.filters.route_id,
                route_name=intent.filters.route_name,
                date_from=intent.filters.date_from,
                date_to=intent.filters.date_to,
                limit=1,
            ),
            limit=1,
            resolution_notes=['Chained use case: reservations counts bookings for the delayed route scope.'],
        )
        return ChainedQuerySpec(
            key='route_delay_and_reservation_count',
            primary_agent='operations',
            delegated_agent='reservations',
            root_intent=root_intent,
            root_plan=build_internal_plan('operations', root_intent),
            delegated_template_intent=delegated_intent,
        )

    return None


def build_chained_answer(
    *,
    chain_spec: ChainedQuerySpec,
    root_rows: list[dict[str, Any]],
    delegated_results: list[dict[str, Any]],
) -> tuple[str, str]:
    if chain_spec.key == 'delayed_routes_with_causes':
        if not root_rows:
            return 'No delayed routes matched the requested filters.', 'low'

        route_count = len(root_rows)
        parts = [f'I found {route_count} delayed routes.']
        explained_route_names: list[str] = []
        for item in delegated_results[:2]:
            route_row = item['route_row']
            route_name = route_row.get('route_name') or route_row.get('route_id') or 'the route'
            explained_route_names.append(str(route_name))
            delayed_trip_count = route_row.get('delayed_trip_count')
            sql_rows = item['sql_rows']
            vector_rows = item['vector_rows']
            explanation_parts: list[str] = []
            if delayed_trip_count is not None:
                explanation_parts.append(f'{route_name} has {delayed_trip_count} delayed trips')
            else:
                explanation_parts.append(f'{route_name} is delayed')
            if sql_rows:
                lead = sql_rows[0]
                incident_type = lead.get('incident_type')
                summary = lead.get('summary')
                if incident_type and summary:
                    explanation_parts.append(f"latest structured cause signal is {incident_type}: {summary}")
                elif incident_type:
                    explanation_parts.append(f'latest structured cause signal is {incident_type}')
                elif summary:
                    explanation_parts.append(f'latest structured cause signal is {summary}')
            elif vector_rows:
                explanation_parts.append(f"related incident narrative suggests {vector_rows[0].get('summary', 'a similar prior disruption')}")
            else:
                explanation_parts.append('no recent incident explanation was found')
            parts.append('. '.join(explanation_parts) + '.')
        other_routes = [
            str(row.get('route_name') or row.get('route_id') or 'unknown route')
            for row in root_rows
            if str(row.get('route_name') or row.get('route_id') or 'unknown route') not in explained_route_names
        ]
        if other_routes:
            parts.append(f"Other delayed routes: {', '.join(other_routes)}.")
        confidence = 'high' if delegated_results else 'medium'
        return ' '.join(parts), confidence

    delayed_trip_count = 0
    if root_rows:
        delayed_trip_count = int(root_rows[0].get('delayed_trip_count') or 0)
    reservation_rows = delegated_results[0]['sql_rows'] if delegated_results else []
    reservation_count = 0
    if reservation_rows:
        first = reservation_rows[0]
        reservation_count = int(next((value for key, value in first.items() if key.endswith('_count') or key == 'count'), 0) or 0)
    route_name = chain_spec.root_intent.filters.route_name or 'the selected route'
    if delayed_trip_count:
        return (
            f'{route_name} is delayed with {delayed_trip_count} matching delayed trips. '
            f'It has {reservation_count} reservations matching the current filters.'
        ), 'high'
    return (
        f'{route_name} is not currently delayed based on grounded trip data. '
        f'It has {reservation_count} reservations matching the current filters.'
    ), 'medium'


def _looks_like_delayed_routes_with_causes(query_text: str) -> bool:
    has_why = any(token in query_text for token in ('why', 'cause', 'caused', 'reason'))
    has_delayed_routes = (
        ('route' in query_text and 'delayed' in query_text)
        or re.search(r'which\s+routes?', query_text) is not None
    )
    return has_why and has_delayed_routes


def _looks_like_route_delay_and_reservation_count(query_text: str, intent: ValidatedQueryIntent) -> bool:
    has_delay = 'delayed' in query_text or 'delay' in query_text
    has_reservations = any(token in query_text for token in ('reservation', 'reservations', 'booking', 'bookings'))
    wants_count = any(token in query_text for token in ('how many', 'count', 'number of', 'total'))
    has_route_scope = intent.filters.route_name is not None or intent.filters.route_id is not None
    return has_delay and has_reservations and wants_count and has_route_scope
