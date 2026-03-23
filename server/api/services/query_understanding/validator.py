from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.schemas import IntentFilters, StructuredIntent, ValidatedQueryIntent
from ...models.tables import Route
from .reference_resolver import RouteReferenceSnapshot, resolve_route_like_reference

ALLOWED_OPERATIONS = {
    'routes': {'list', 'count', 'compare', 'summarize', 'aggregate'},
    'trips': {'list', 'count', 'compare', 'summarize', 'aggregate'},
    'reservations': {'list', 'count', 'compare', 'summarize', 'aggregate'},
    'incidents': {'list', 'count', 'compare', 'summarize', 'aggregate', 'explain'},
}


@dataclass(slots=True)
class RouteReference(RouteReferenceSnapshot):
    route_id: Any
    route_name: str
    origin_name: str
    destination_name: str
    is_active: bool


class QueryIntentValidator:
    async def validate(
        self,
        intent: StructuredIntent,
        *,
        db_session: AsyncSession,
        previous_intent: ValidatedQueryIntent | None = None,
        today: date | None = None,
    ) -> ValidatedQueryIntent:
        today = today or date.today()
        if intent.entity == 'unknown' and previous_intent is not None:
            intent = intent.model_copy(update={'entity': previous_intent.entity, 'operation': previous_intent.operation})

        if intent.entity == 'unknown':
            return ValidatedQueryIntent(
                entity='routes',
                operation='list',
                filters=intent.filters,
                metric=intent.metric,
                group_by=intent.group_by,
                sort_by=intent.sort_by,
                sort_direction=intent.sort_direction,
                limit=intent.limit,
                needs_clarification=True,
                clarification_reason='unknown_entity',
                clarification_question='I need more information. Are you asking about routes, trips, reservations, or incidents?',
                clarification_options=['routes', 'trips', 'reservations', 'incidents'],
            )

        normalized = intent.model_copy(deep=True)
        filters = normalized.filters
        notes: list[str] = []

        self._normalize_operation(normalized)
        self._normalize_time_filters(normalized, today=today)
        self._normalize_status(normalized)
        self._normalize_intent_family(normalized, today=today, notes=notes)

        route_refs = await self._load_route_references(db_session)
        await self._normalize_route_references(normalized, route_refs, notes)
        self._normalize_location_references(normalized, route_refs)
        self._apply_previous_context(normalized, previous_intent)
        self._normalize_sort(normalized)

        clarification_question, clarification_options = self._clarification_for(normalized, route_refs)
        return ValidatedQueryIntent(
            entity=normalized.entity,  # type: ignore[arg-type]
            operation=normalized.operation,  # type: ignore[arg-type]
            intent_family=normalized.intent_family,
            filters=normalized.filters,
            metric=normalized.metric,
            group_by=normalized.group_by,
            sort_by=normalized.sort_by,
            sort_direction=normalized.sort_direction,
            limit=normalized.limit,
            needs_clarification=clarification_question is not None or normalized.needs_clarification,
            clarification_reason=normalized.clarification_reason,
            clarification_question=clarification_question,
            clarification_options=clarification_options,
            resolution_notes=notes,
        )

    def _normalize_time_filters(self, intent: StructuredIntent, *, today: date) -> None:
        filters = intent.filters
        if filters.date_from or filters.date_to:
            return
        if filters.relative_time_window == 'now' and intent.entity == 'reservations':
            filters.relative_time_window = None
            return
        mapping = {
            'today': (today, today),
            'now': (today, today),
            'this_week': (today - timedelta(days=today.weekday()), today),
            'last_week': (
                today - timedelta(days=today.weekday() + 7),
                today - timedelta(days=today.weekday() + 1),
            ),
            'this_month': (today.replace(day=1), today),
            'recently': (today - timedelta(days=7), today),
        }
        if filters.relative_time_window in mapping:
            filters.date_from, filters.date_to = mapping[filters.relative_time_window]

    def _normalize_status(self, intent: StructuredIntent) -> None:
        status = intent.filters.status
        if status is None:
            return
        if intent.entity == 'incidents' and status == 'delayed':
            intent.filters.incident_type = intent.filters.incident_type or 'delay'
            intent.filters.status = None

    def _normalize_operation(self, intent: StructuredIntent) -> None:
        if intent.operation not in ALLOWED_OPERATIONS[intent.entity]:
            if intent.entity == 'incidents' and intent.operation == 'list' and intent.metric == 'incidents':
                intent.operation = 'aggregate'
            elif intent.entity in {'routes', 'trips', 'reservations'} and intent.operation == 'explain':
                intent.entity = 'incidents'
            else:
                intent.operation = 'list'

        if intent.operation == 'compare' and intent.group_by is None:
            intent.group_by = 'route'
        if intent.operation == 'aggregate' and intent.sort_direction is None:
            intent.sort_direction = 'desc'
        if (
            intent.entity == 'routes'
            and intent.operation == 'count'
            and intent.filters.status in {'scheduled', 'boarding', 'in_transit', 'delayed', 'cancelled', 'completed'}
            and (intent.filters.route_id is not None or intent.filters.route_name is not None or intent.filters.origin is not None or intent.filters.destination is not None)
        ):
            intent.entity = 'trips'

    def _normalize_intent_family(self, intent: StructuredIntent, *, today: date, notes: list[str]) -> None:
        if intent.intent_family is None and intent.entity == 'reservations' and intent.filters.date_from is not None and intent.filters.date_to is not None:
            if intent.operation == 'count':
                intent.intent_family = 'reservation_count_in_range'
            elif intent.operation == 'list':
                intent.intent_family = 'reservation_list_in_range'

        if intent.intent_family == 'route_delay_check':
            intent.entity = 'trips'
            intent.operation = 'count'
            intent.metric = 'boolean_check'
            intent.filters.status = 'delayed'
            intent.filters.date_from = None
            intent.filters.date_to = None
            intent.filters.relative_time_window = None
            notes.append('Applied route_delay_check contract: delayed route means active routes with delayed trips, derived from trips with no implicit time window.')

        if intent.intent_family == 'route_delay_explanation':
            intent.entity = 'incidents'
            intent.operation = 'explain'
            intent.filters.status = 'delayed'
            intent.filters.incident_type = None
            if intent.filters.date_from is None and intent.filters.date_to is None and intent.filters.relative_time_window is None:
                intent.filters.relative_time_window = 'recently'
                self._normalize_time_filters(intent, today=today)
            notes.append('Applied route_delay_explanation contract: explain route delay using recent incidents for the route or related trips, not only delay-typed incidents.')

        if intent.intent_family == 'reservation_count_in_range':
            intent.entity = 'reservations'
            intent.operation = 'count'
            notes.append('Applied reservation_count_in_range contract: count reservations by created_at over an inclusive whole-day date range.')

        if intent.intent_family == 'reservation_list_in_range':
            intent.entity = 'reservations'
            intent.operation = 'list'
            notes.append('Applied reservation_list_in_range contract: list reservations by created_at over an inclusive whole-day date range.')

        if intent.intent_family == 'route_status_list':
            status = intent.filters.status
            if status == 'active':
                intent.entity = 'routes'
                intent.operation = 'list'
                notes.append('Applied route_status_list contract: active routes means routes where is_active is true.')
            elif status in {'delayed', 'completed'}:
                intent.entity = 'routes'
                intent.operation = 'list'
                notes.append(
                    f"Applied route_status_list contract: '{status}' routes means active routes having at least one trip with status '{status}', derived from trips rather than a route-level status column."
                )

    async def _load_route_references(self, db_session: AsyncSession) -> list[RouteReference]:
        rows = (
            await db_session.execute(
                select(
                    Route.id.label('route_id'),
                    Route.route_name,
                    Route.origin_name,
                    Route.destination_name,
                    Route.is_active,
                ).order_by(Route.route_name.asc())
            )
        ).mappings().all()
        return [RouteReference(**row) for row in rows]

    async def _normalize_route_references(
        self,
        intent: StructuredIntent,
        route_refs: list[RouteReference],
        notes: list[str],
    ) -> None:
        filters = intent.filters
        if filters.route_id is not None:
            for ref in route_refs:
                if ref.route_id == filters.route_id:
                    filters.route_name = ref.route_name
                    return

        if not filters.route_name:
            return

        resolution = resolve_route_like_reference(filters.route_name, route_refs)
        if resolution.route_id is not None:
            filters.route_id = resolution.route_id
            filters.route_name = resolution.route_name
            notes.extend(resolution.notes)
            return
        if resolution.origin is not None:
            filters.origin = resolution.origin
            filters.route_name = None
            notes.extend(resolution.notes)
            return
        if resolution.destination is not None:
            filters.destination = resolution.destination
            filters.route_name = None
            notes.extend(resolution.notes)
            return
        if resolution.clarification is not None:
            intent.needs_clarification = True
            intent.clarification_reason = resolution.clarification.reason
            return
        if filters.route_name:
            intent.needs_clarification = True
            intent.clarification_reason = 'unknown_route_reference'

    def _normalize_location_references(self, intent: StructuredIntent, route_refs: list[RouteReference]) -> None:
        filters = intent.filters
        if filters.origin:
            matches = sorted({ref.origin_name for ref in route_refs if ref.origin_name.lower() == filters.origin.lower()})
            if len(matches) == 1:
                filters.origin = matches[0]
            elif not matches:
                partial = sorted({ref.origin_name for ref in route_refs if filters.origin.lower() in ref.origin_name.lower()})
                if len(partial) == 1:
                    filters.origin = partial[0]
                elif len(partial) > 1:
                    intent.needs_clarification = True
                    intent.clarification_reason = 'ambiguous_origin'

        if filters.destination:
            matches = sorted({ref.destination_name for ref in route_refs if ref.destination_name.lower() == filters.destination.lower()})
            if len(matches) == 1:
                filters.destination = matches[0]
            elif not matches:
                partial = sorted({ref.destination_name for ref in route_refs if filters.destination.lower() in ref.destination_name.lower()})
                if len(partial) == 1:
                    filters.destination = partial[0]
                elif len(partial) > 1:
                    intent.needs_clarification = True
                    intent.clarification_reason = 'ambiguous_destination'

    def _apply_previous_context(self, intent: StructuredIntent, previous_intent: ValidatedQueryIntent | None) -> None:
        if previous_intent is None:
            return
        if intent.filters.route_id is None and intent.filters.route_name is None and previous_intent.filters.route_id is not None:
            if intent.entity in {previous_intent.entity, 'incidents'}:
                intent.filters.route_id = previous_intent.filters.route_id
                intent.filters.route_name = previous_intent.filters.route_name

    def _normalize_sort(self, intent: StructuredIntent) -> None:
        if intent.sort_by is None:
            intent.sort_by = intent.filters.sort_by
        if intent.sort_direction is None:
            intent.sort_direction = intent.filters.sort_direction
        if intent.sort_direction is None and intent.operation in {'compare', 'aggregate'}:
            intent.sort_direction = 'desc'

    def _clarification_for(
        self,
        intent: StructuredIntent,
        route_refs: list[RouteReference],
    ) -> tuple[str | None, list[str]]:
        reason = intent.clarification_reason
        if reason == 'ambiguous_route_reference':
            options = [ref.route_name for ref in route_refs[:5]]
            return 'I found multiple routes matching that reference. Which route did you mean?', options
        if reason == 'ambiguous_route_location_reference':
            label = intent.filters.route_name or intent.filters.origin or intent.filters.destination or 'that location'
            return (
                f"I couldn't deterministically map '{label}' to a route. Do you mean a route name, routes originating there, or routes arriving there?",
                ['route_name', 'origin', 'destination'],
            )
        if reason == 'unknown_route_reference':
            label = intent.filters.route_name or 'that route reference'
            return f"I couldn't resolve '{label}' to a known route. Do you mean a route name, origin city, or destination city?", []
        if reason == 'ambiguous_origin':
            return 'I found multiple possible origin matches. Which origin city did you mean?', []
        if reason == 'ambiguous_destination':
            return 'I found multiple possible destination matches. Which destination city did you mean?', []

        if intent.needs_clarification and intent.clarification_reason == 'broad_unfiltered_list':
            if intent.entity == 'routes':
                return 'That route request is broad. Do you want active, delayed, completed, or all routes?', ['active', 'delayed', 'completed', 'all']
            if intent.entity == 'trips':
                return 'That trip request is broad. Do you want delayed trips, active trips, or trips for a specific route?', ['delayed', 'active', 'specific_route']

        if intent.operation == 'explain' and not (intent.filters.route_id or intent.filters.route_name or intent.filters.trip_id):
            intent.needs_clarification = True
            intent.clarification_reason = 'missing_scope_for_explanation'
            return 'What route or trip do you want explained?', []

        return None, []
