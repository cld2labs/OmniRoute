from __future__ import annotations

from dataclasses import dataclass, field

from ..models.schemas import AdminQueryRequest, StructuredIntent, ValidatedQueryIntent


@dataclass(slots=True)
class PlannerDecision:
    selected_agent: str
    query_class: str
    execution_mode: str
    tool_hints: list[str] = field(default_factory=list)


class QueryPlanner:
    def decide(self, payload: AdminQueryRequest, extracted_filters: dict[str, object]) -> PlannerDecision:
        query = payload.query.lower()
        incident_required = bool(extracted_filters.get('incident_type')) or any(
            token in query for token in ('incident', 'incidents', 'why', 'cause', 'explain', 'similar', 'pattern')
        )
        reservation_required = self._has_any(
            query,
            ('reservation', 'reservations', 'booking', 'bookings', 'book', 'cancellation', 'cancelled', 'refunded', 'utilization'),
        ) or extracted_filters.get('reservation_id') is not None
        operations_required = self._has_any(
            query,
            ('route', 'routes', 'trip', 'trips', 'delay', 'delayed', 'status', 'seat', 'capacity', 'active route'),
        ) or extracted_filters.get('trip_id') is not None
        insights_required = self._has_any(
            query,
            ('incident', 'incidents', 'why', 'cause', 'explain', 'similar', 'pattern', 'unstable', 'trend'),
        ) or incident_required

        matches = {
            'reservations': reservation_required,
            'insights': insights_required,
            'operations': operations_required,
        }
        active = [name for name, matched in matches.items() if matched]
        query_class = active[0] if len(active) == 1 else 'mixed' if active else 'operations'

        if query_class == 'mixed':
            if reservation_required and not incident_required:
                selected_agent = 'reservations'
            elif insights_required:
                selected_agent = 'insights'
            else:
                selected_agent = 'operations'
        else:
            selected_agent = query_class

        tool_hints = ['sql']
        if incident_required:
            tool_hints.append('vector')

        execution_mode = 'sql_plus_vector' if 'vector' in tool_hints and incident_required else 'sql_only'
        return PlannerDecision(
            selected_agent=selected_agent,
            query_class=query_class,
            execution_mode=execution_mode,
            tool_hints=tool_hints,
        )

    def finalize(self, initial: PlannerDecision, intent: StructuredIntent | ValidatedQueryIntent) -> PlannerDecision:
        if intent.entity == 'reservations':
            selected_agent = 'reservations'
        elif intent.entity == 'incidents' or intent.operation == 'explain':
            selected_agent = 'insights'
        else:
            selected_agent = 'operations'

        query_class = selected_agent
        tool_hints = ['sql']
        if selected_agent == 'insights' and intent.operation == 'explain':
            tool_hints.append('vector')
        execution_mode = 'sql_plus_vector' if 'vector' in tool_hints else 'sql_only'
        return PlannerDecision(
            selected_agent=selected_agent,
            query_class=query_class,
            execution_mode=execution_mode,
            tool_hints=tool_hints,
        )

    @staticmethod
    def _has_any(query: str, tokens: tuple[str, ...]) -> bool:
        return any(token in query for token in tokens)
