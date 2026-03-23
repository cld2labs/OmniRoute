from __future__ import annotations

from dataclasses import dataclass, field

from ...models.schemas import ValidatedQueryIntent


@dataclass(slots=True)
class SQLBlockRequest:
    name: str
    description: str


@dataclass(slots=True)
class InternalQueryPlan:
    selected_agent: str
    entity: str
    operation: str
    response_mode: str
    requires_vector: bool = False
    sql_blocks: list[SQLBlockRequest] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    @property
    def plan_steps(self) -> list[str]:
        steps = [f"sql:{block.name}" for block in self.sql_blocks]
        if self.requires_vector:
            steps.append('vector:incident_narratives')
        steps.append(f"synthesis:{self.response_mode}")
        return steps


def build_internal_plan(selected_agent: str, intent: ValidatedQueryIntent) -> InternalQueryPlan:
    key = (intent.entity, intent.operation)
    if key == ('routes', 'list'):
        return InternalQueryPlan(
            selected_agent=selected_agent,
            entity='routes',
            operation='list',
            response_mode='route_list',
            sql_blocks=[SQLBlockRequest('generated_sql', 'List routes with route-level filters.')],
        )
    if key == ('routes', 'count'):
        return InternalQueryPlan(
            selected_agent=selected_agent,
            entity='routes',
            operation='count',
            response_mode='count',
            sql_blocks=[SQLBlockRequest('generated_sql', 'Count routes in scope.')],
        )
    if key == ('trips', 'list'):
        return InternalQueryPlan(
            selected_agent=selected_agent,
            entity='trips',
            operation='list',
            response_mode='trip_list',
            sql_blocks=[SQLBlockRequest('generated_sql', 'List trips in scope.')],
        )
    if key == ('trips', 'count'):
        return InternalQueryPlan(
            selected_agent=selected_agent,
            entity='trips',
            operation='count',
            response_mode='count',
            sql_blocks=[SQLBlockRequest('generated_sql', 'Count trips in scope.')],
        )
    if key == ('reservations', 'count'):
        return InternalQueryPlan(
            selected_agent=selected_agent,
            entity='reservations',
            operation='count',
            response_mode='count',
            sql_blocks=[SQLBlockRequest('generated_sql', 'Count reservations in scope.')],
        )
    if key == ('reservations', 'list'):
        return InternalQueryPlan(
            selected_agent=selected_agent,
            entity='reservations',
            operation='list',
            response_mode='reservation_list',
            sql_blocks=[SQLBlockRequest('generated_sql', 'List reservations in scope.')],
        )
    if key == ('reservations', 'compare') or (intent.entity == 'reservations' and intent.operation == 'aggregate'):
        return InternalQueryPlan(
            selected_agent=selected_agent,
            entity='reservations',
            operation=intent.operation,
            response_mode='reservation_compare',
            sql_blocks=[SQLBlockRequest('generated_sql', 'Compare reservation activity by route.')],
        )
    if key == ('incidents', 'explain'):
        return InternalQueryPlan(
            selected_agent=selected_agent,
            entity='incidents',
            operation='explain',
            response_mode='incident_explanation',
            requires_vector=True,
            sql_blocks=[SQLBlockRequest('generated_sql', 'List structured incident evidence for the explanation.')],
        )
    if intent.entity == 'incidents' and intent.group_by == 'route':
        return InternalQueryPlan(
            selected_agent=selected_agent,
            entity='incidents',
            operation=intent.operation,
            response_mode='incident_compare',
            sql_blocks=[SQLBlockRequest('generated_sql', 'Aggregate incidents by route.')],
        )
    if key == ('incidents', 'count'):
        return InternalQueryPlan(
            selected_agent=selected_agent,
            entity='incidents',
            operation='count',
            response_mode='count',
            sql_blocks=[SQLBlockRequest('generated_sql', 'Count incidents in scope.')],
        )
    return InternalQueryPlan(
        selected_agent=selected_agent,
        entity=intent.entity,
        operation=intent.operation,
        response_mode='generic_list',
        requires_vector=False,
        sql_blocks=[SQLBlockRequest('generated_sql', 'List records in scope.')],
    )
