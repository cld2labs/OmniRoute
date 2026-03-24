from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.schemas import ValidatedQueryIntent
from api.services.embeddings.search import search_similar_incidents
from api.services.query_understanding.internal_plan import InternalQueryPlan
from api.services.sql_tool import SQLTool


@dataclass(slots=True)
class AgentToolExecutionResult:
    sql_records: list[dict[str, Any]] = field(default_factory=list)
    vector_records: list[dict[str, Any]] = field(default_factory=list)
    block_results: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    sql_queries: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str | None = None


class SpecialistToolbox:
    agent_name = 'operations'

    def __init__(self, llm_client: Any | None = None) -> None:
        self._llm_client = llm_client

    async def execute(
        self,
        *,
        query_text: str,
        intent: ValidatedQueryIntent,
        plan: InternalQueryPlan,
        db_session: AsyncSession,
    ) -> AgentToolExecutionResult:
        result = await self._run_sql_blocks(
            query_text=query_text,
            intent=intent,
            plan=plan,
            db_session=db_session,
        )
        result.assumptions.append(f'{self.agent_name} agent used tools: {", ".join(result.tool_calls)}.')
        return result

    async def _run_sql_blocks(
        self,
        *,
        query_text: str,
        intent: ValidatedQueryIntent,
        plan: InternalQueryPlan,
        db_session: AsyncSession,
    ) -> AgentToolExecutionResult:
        block_results: dict[str, list[dict[str, Any]]] = {}
        sql_records: list[dict[str, Any]] = []
        sql_queries: list[str] = []
        assumptions = list(intent.resolution_notes)
        errors: list[str] = []
        tool_calls: list[str] = ['sql_db_query']
        sql_tool = SQLTool(db_session=db_session, llm_client=self._llm_client, agent=plan.selected_agent)
        filters = intent.filters.model_dump(mode='python')
        filters['limit'] = min(intent.limit, 200)
        intent_context = {
            'entity': intent.entity,
            'operation': intent.operation,
            'intent_family': intent.intent_family,
            'metric': intent.metric,
            'group_by': intent.group_by,
            'sort_by': intent.sort_by,
            'sort_direction': intent.sort_direction,
            'selected_agent': plan.selected_agent,
        }

        for block in plan.sql_blocks:
            result = await sql_tool.run(query_text, filters, intent_context=intent_context)
            if result.get('needs_clarification'):
                return AgentToolExecutionResult(
                    assumptions=assumptions,
                    errors=errors,
                    tool_calls=tool_calls,
                    needs_clarification=True,
                    clarification_question=result.get('clarification_question'),
                )
            rows = result['rows']
            block_results[block.name] = rows
            sql_records.extend(rows)
            if result.get('sql_used'):
                sql_queries.append(result['sql_used'])
            if result.get('error'):
                errors.append(result['error'])
                assumptions.append(f"SQL issue for {block.name}: {result['error']}")

        return AgentToolExecutionResult(
            sql_records=sql_records,
            block_results=block_results,
            assumptions=assumptions,
            sql_queries=sql_queries,
            errors=errors,
            tool_calls=tool_calls,
        )


class OperationsToolbox(SpecialistToolbox):
    agent_name = 'operations'


class ReservationsToolbox(SpecialistToolbox):
    agent_name = 'reservations'


class InsightsToolbox(SpecialistToolbox):
    agent_name = 'insights'

    async def execute(
        self,
        *,
        query_text: str,
        intent: ValidatedQueryIntent,
        plan: InternalQueryPlan,
        db_session: AsyncSession,
    ) -> AgentToolExecutionResult:
        result = await self._run_sql_blocks(
            query_text=query_text,
            intent=intent,
            plan=plan,
            db_session=db_session,
        )
        if result.needs_clarification:
            return result

        if plan.requires_vector:
            result.tool_calls.append('incident_vector_search')
            result.vector_records = await search_similar_incidents(
                query_text,
                db_session=db_session,
                top_k=min(intent.limit, 5),
                route_id=intent.filters.route_id,
                trip_id=intent.filters.trip_id,
                date_from=intent.filters.date_from,
                date_to=intent.filters.date_to,
                incident_type=intent.filters.incident_type,
            )

        result.assumptions.append(f'{self.agent_name} agent used tools: {", ".join(result.tool_calls)}.')
        return result


def build_specialist_toolbox(selected_agent: str, *, llm_client: Any | None = None) -> SpecialistToolbox:
    if selected_agent == 'reservations':
        return ReservationsToolbox(llm_client=llm_client)
    if selected_agent == 'insights':
        return InsightsToolbox(llm_client=llm_client)
    return OperationsToolbox(llm_client=llm_client)
