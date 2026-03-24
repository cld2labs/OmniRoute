from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from api.config import Settings, get_settings
from api.models.schemas import AdminQueryRequest, ValidatedQueryIntent
from api.services.planner import PlannerDecision, QueryPlanner
from api.services.query_understanding.chained_queries import ChainedQuerySpec
from api.services.query_understanding.internal_plan import InternalQueryPlan, build_internal_plan
from sqlalchemy.ext.asyncio import AsyncSession

from .tools import AgentToolExecutionResult, build_specialist_toolbox

try:
    from crewai import Agent, Crew, Process, Task
except ImportError:  # pragma: no cover - optional local dependency
    Agent = Crew = Process = Task = None  # type: ignore[assignment]

try:
    from crewai.tools import tool as crewai_tool
except ImportError:  # pragma: no cover - optional local dependency
    crewai_tool = None  # type: ignore[assignment]


def is_crewai_available(settings: Settings | None = None) -> bool:
    current_settings = settings or get_settings()
    return bool(getattr(current_settings, 'crewai_enabled', True) and Agent is not None and Crew is not None and Task is not None)


@dataclass(slots=True)
class CrewAIOrchestrationResult:
    planner_decision: PlannerDecision
    plan: InternalQueryPlan
    active_agents: list[str] = field(default_factory=list)
    task_descriptions: list[str] = field(default_factory=list)
    handoffs: list[str] = field(default_factory=list)
    available_tools: list[str] = field(default_factory=list)
    backend: str = 'deterministic'
    crew: Any | None = None

    @property
    def assumptions(self) -> list[str]:
        assumptions = [f"Orchestration backend: {self.backend}."]
        if self.active_agents:
            assumptions.append(f"Active agents: {', '.join(self.active_agents)}.")
        if self.task_descriptions:
            assumptions.append(f"Planned handoffs: {' | '.join(self.task_descriptions)}.")
        if self.available_tools:
            assumptions.append(f"Available specialist tools: {', '.join(self.available_tools)}.")
        return assumptions


@dataclass(slots=True)
class CrewAIChainExecutionResult:
    root_rows: list[dict[str, Any]] = field(default_factory=list)
    delegated_results: list[dict[str, Any]] = field(default_factory=list)
    sql_records: list[dict[str, Any]] = field(default_factory=list)
    vector_records: list[dict[str, Any]] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    sql_queries: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    plan_steps: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str | None = None


class CrewAIQueryOrchestrator:
    def __init__(self, planner: QueryPlanner | None = None, settings: Settings | None = None) -> None:
        self._planner = planner or QueryPlanner()
        self._settings = settings or get_settings()

    async def orchestrate(
        self,
        *,
        payload: AdminQueryRequest,
        intent: ValidatedQueryIntent,
        initial_decision: PlannerDecision,
        chain_spec: ChainedQuerySpec | None = None,
    ) -> CrewAIOrchestrationResult:
        if chain_spec is not None:
            planner_decision = PlannerDecision(
                selected_agent=chain_spec.primary_agent,
                query_class='mixed',
                execution_mode=chain_spec.execution_mode,
                tool_hints=['sql', 'delegate'] + (['vector'] if chain_spec.delegated_agent == 'insights' else []),
            )
            if not is_crewai_available(self._settings):
                return CrewAIOrchestrationResult(
                    planner_decision=planner_decision,
                    plan=chain_spec.root_plan,
                    active_agents=chain_spec.active_agents,
                    task_descriptions=chain_spec.task_descriptions,
                    handoffs=chain_spec.handoffs,
                    available_tools=chain_spec.available_tools,
                )

            crew = self._build_chained_crew(payload=payload, chain_spec=chain_spec)
            return CrewAIOrchestrationResult(
                planner_decision=planner_decision,
                plan=chain_spec.root_plan,
                active_agents=chain_spec.active_agents,
                task_descriptions=chain_spec.task_descriptions,
                handoffs=chain_spec.handoffs,
                available_tools=chain_spec.available_tools,
                backend='crewai',
                crew=crew,
            )

        planner_decision = self._planner.finalize(initial_decision, intent)
        plan = build_internal_plan(planner_decision.selected_agent, intent)
        active_agents = ['planner', planner_decision.selected_agent]
        available_tools = self._tool_names_for_agent(planner_decision.selected_agent)
        task_descriptions = [
            f"planner routes {intent.entity}/{intent.operation} to {planner_decision.selected_agent}",
            f"{planner_decision.selected_agent} executes {plan.response_mode}",
        ]
        handoffs = [
            f"planner -> {planner_decision.selected_agent}",
            f"{planner_decision.selected_agent} -> grounded_{plan.response_mode}",
        ]

        if not is_crewai_available(self._settings):
            return CrewAIOrchestrationResult(
                planner_decision=planner_decision,
                plan=plan,
                active_agents=active_agents,
                task_descriptions=task_descriptions,
                handoffs=handoffs,
                available_tools=available_tools,
            )

        crew = self._build_crew(payload=payload, intent=intent, planner_decision=planner_decision, plan=plan)
        return CrewAIOrchestrationResult(
            planner_decision=planner_decision,
            plan=plan,
            active_agents=active_agents,
            task_descriptions=task_descriptions,
            handoffs=handoffs,
            available_tools=available_tools,
            backend='crewai',
            crew=crew,
        )

    async def execute_chained(
        self,
        *,
        payload: AdminQueryRequest,
        chain_spec: ChainedQuerySpec,
        db_session: AsyncSession,
        llm_client: Any | None = None,
    ) -> CrewAIChainExecutionResult | None:
        if not is_crewai_available(self._settings):
            return None

        loop = asyncio.get_running_loop()
        state_lock = threading.Lock()
        shared_state: dict[str, Any] = {
            'root_rows': [],
            'delegated_results': [],
            'sql_records': [],
            'vector_records': [],
            'assumptions': [],
            'sql_queries': [],
            'tool_calls': [],
            'plan_steps': list(chain_spec.root_plan.plan_steps),
            'needs_clarification': False,
            'clarification_question': None,
        }

        def _run_on_loop(coro: Any) -> Any:
            return asyncio.run_coroutine_threadsafe(coro, loop).result()

        async def _execute_specialist(
            *,
            selected_agent: str,
            query_text: str,
            intent: ValidatedQueryIntent,
        ) -> tuple[InternalQueryPlan, AgentToolExecutionResult]:
            plan = build_internal_plan(selected_agent, intent)
            toolbox = build_specialist_toolbox(selected_agent, llm_client=llm_client)
            result = await toolbox.execute(
                query_text=query_text,
                intent=intent,
                plan=plan,
                db_session=db_session,
            )
            return plan, result

        def _merge_execution(plan: InternalQueryPlan, result: AgentToolExecutionResult) -> dict[str, Any]:
            payload_data = {
                'sql_rows': result.block_results.get('generated_sql') or [],
                'vector_rows': result.vector_records,
                'tool_calls': result.tool_calls,
                'sql_queries': result.sql_queries,
                'assumptions': result.assumptions,
                'plan_steps': plan.plan_steps,
                'needs_clarification': result.needs_clarification,
                'clarification_question': result.clarification_question,
            }
            return payload_data

        def _execute_root_tool() -> str:
            plan, result = _run_on_loop(
                _execute_specialist(
                    selected_agent=chain_spec.primary_agent,
                    query_text=chain_spec.root_query_text(),
                    intent=chain_spec.root_intent,
                )
            )
            payload_data = _merge_execution(plan, result)
            with state_lock:
                shared_state['root_rows'] = payload_data['sql_rows']
                shared_state['sql_records'].extend(result.sql_records)
                shared_state['vector_records'].extend(result.vector_records)
                shared_state['tool_calls'].extend(result.tool_calls)
                shared_state['sql_queries'].extend(result.sql_queries)
                shared_state['assumptions'].extend(result.assumptions)
                shared_state['plan_steps'] = list(plan.plan_steps)
                shared_state['needs_clarification'] = result.needs_clarification
                shared_state['clarification_question'] = result.clarification_question
            return json.dumps(
                {
                    'routes_found': len(payload_data['sql_rows']),
                    'needs_clarification': payload_data['needs_clarification'],
                },
                ensure_ascii=True,
            )

        def _execute_delegated_tool() -> str:
            with state_lock:
                root_rows = list(shared_state['root_rows'])
                if shared_state['needs_clarification']:
                    return json.dumps({'delegated_items': 0, 'skipped': 'clarification_required'}, ensure_ascii=True)

            delegated_rows = root_rows[:3] if chain_spec.key == 'delayed_routes_with_causes' else [root_rows[0] if root_rows else {}]
            summaries: list[dict[str, Any]] = []
            for row in delegated_rows:
                delegated_intent = chain_spec.delegated_intent_for_row(row)
                if delegated_intent is None:
                    continue
                delegated_query = chain_spec.delegated_query_for_row(row)
                plan, result = _run_on_loop(
                    _execute_specialist(
                        selected_agent=chain_spec.delegated_agent,
                        query_text=delegated_query,
                        intent=delegated_intent,
                    )
                )
                payload_data = _merge_execution(plan, result)
                summaries.append(
                    {
                        'route_row': row,
                        'sql_rows': payload_data['sql_rows'],
                        'vector_rows': payload_data['vector_rows'],
                    }
                )
                with state_lock:
                    shared_state['delegated_results'].append(summaries[-1])
                    shared_state['sql_records'].extend(result.sql_records)
                    shared_state['vector_records'].extend(result.vector_records)
                    shared_state['tool_calls'].extend(result.tool_calls)
                    shared_state['sql_queries'].extend(result.sql_queries)
                    shared_state['assumptions'].extend(result.assumptions)
                    shared_state['plan_steps'].append(f'delegate:{chain_spec.delegated_agent}')
                    if result.needs_clarification and not shared_state['needs_clarification']:
                        shared_state['needs_clarification'] = True
                        shared_state['clarification_question'] = result.clarification_question

            return json.dumps({'delegated_items': len(summaries)}, ensure_ascii=True)

        planner_agent = Agent(
            role='Planner Agent',
            goal='Route each admin query to the correct specialist without changing the grounded execution rules.',
            backstory='Coordinates OmniRoute query handling and preserves SQL-first execution boundaries.',
            allow_delegation=True,
            tools=[self._build_handoff_contract_tool()],
            verbose=False,
        )
        primary_agent = self._build_specialist_agent(
            chain_spec.primary_agent,
            tools=[self._make_tool('primary_grounded_execution', 'Execute the grounded primary specialist step exactly once.', _execute_root_tool)],
            allow_delegation=True,
        )
        delegated_agent = self._build_specialist_agent(
            chain_spec.delegated_agent,
            tools=[self._make_tool('delegated_grounded_execution', 'Execute the bounded delegated specialist step exactly once.', _execute_delegated_tool)],
        )
        planner_task = Task(
            description=(
                'Confirm the bounded chain for this request.\n'
                f'User query: {payload.query}\n'
                f'Primary specialist: {chain_spec.primary_agent}\n'
                f'Delegated specialist: {chain_spec.delegated_agent}\n'
                'Do not answer the user.'
            ),
            expected_output='Short routing confirmation.',
            agent=planner_agent,
        )
        primary_task = Task(
            description=(
                'Use the primary_grounded_execution tool exactly once.\n'
                'Return a short note confirming the primary grounded step completed.\n'
                'Do not answer the user.'
            ),
            expected_output='Short note confirming the primary grounded step executed.',
            agent=primary_agent,
        )
        delegated_task = Task(
            description=(
                'Use the delegated_grounded_execution tool exactly once after the primary step.\n'
                'Return a short note confirming the delegated grounded step completed.\n'
                'Do not answer the user.'
            ),
            expected_output='Short note confirming the delegated grounded step executed.',
            agent=delegated_agent,
        )
        crew = Crew(
            agents=[planner_agent, primary_agent, delegated_agent],
            tasks=[planner_task, primary_task, delegated_task],
            process=Process.sequential if Process is not None else 'sequential',
            verbose=False,
        )

        try:
            await asyncio.to_thread(crew.kickoff)
        except Exception:
            return None

        with state_lock:
            if not shared_state['tool_calls'] and not shared_state['needs_clarification']:
                return None
            return CrewAIChainExecutionResult(
                root_rows=list(shared_state['root_rows']),
                delegated_results=list(shared_state['delegated_results']),
                sql_records=list(shared_state['sql_records']),
                vector_records=list(shared_state['vector_records']),
                assumptions=list(shared_state['assumptions']),
                sql_queries=list(shared_state['sql_queries']),
                tool_calls=list(shared_state['tool_calls']),
                plan_steps=list(shared_state['plan_steps']),
                needs_clarification=bool(shared_state['needs_clarification']),
                clarification_question=shared_state['clarification_question'],
            )

    def _build_crew(
        self,
        *,
        payload: AdminQueryRequest,
        intent: ValidatedQueryIntent,
        planner_decision: PlannerDecision,
        plan: InternalQueryPlan,
    ) -> Any:
        planner_tools = [self._build_handoff_contract_tool()]
        planner_agent = Agent(
            role='Planner Agent',
            goal='Route each admin query to the correct specialist without changing the grounded execution rules.',
            backstory='Coordinates OmniRoute query handling and preserves SQL-first execution boundaries.',
            allow_delegation=True,
            tools=planner_tools,
            verbose=False,
        )
        specialist_tools = self._build_specialist_tools(planner_decision.selected_agent)
        specialist_agent = self._build_specialist_agent(planner_decision.selected_agent, tools=specialist_tools)
        tasks = [
            Task(
                description=(
                    'Review the validated intent and confirm the specialist handoff.\n'
                    f'User query: {payload.query}\n'
                    f'Entity: {intent.entity}\n'
                    f'Operation: {intent.operation}\n'
                    f'Selected specialist: {planner_decision.selected_agent}\n'
                    'Do not answer the user. Produce only a short routing confirmation.'
                ),
                expected_output='Short routing confirmation naming the chosen specialist.',
                agent=planner_agent,
            ),
            Task(
                description=(
                    'A deterministic service will execute the query after this handoff.\n'
                    f'Prepare the execution brief for response mode {plan.response_mode}.\n'
                    f'Plan steps: {", ".join(plan.plan_steps)}\n'
                    'Do not invent data and do not answer the user directly.'
                ),
                expected_output='Short execution brief aligned with the selected response mode.',
                agent=specialist_agent,
            ),
        ]
        process = Process.sequential if Process is not None else 'sequential'
        return Crew(
            agents=[planner_agent, specialist_agent],
            tasks=tasks,
            process=process,
            verbose=False,
        )

    def _build_chained_crew(
        self,
        *,
        payload: AdminQueryRequest,
        chain_spec: ChainedQuerySpec,
    ) -> Any:
        planner_tools = [self._build_handoff_contract_tool()]
        planner_agent = Agent(
            role='Planner Agent',
            goal='Route each admin query to the correct specialist without changing the grounded execution rules.',
            backstory='Coordinates OmniRoute query handling and preserves SQL-first execution boundaries.',
            allow_delegation=True,
            tools=planner_tools,
            verbose=False,
        )
        primary_tools = self._build_specialist_tools(chain_spec.primary_agent)
        primary_agent = self._build_specialist_agent(chain_spec.primary_agent, tools=primary_tools, allow_delegation=True)
        delegated_tools = self._build_specialist_tools(chain_spec.delegated_agent)
        delegated_agent = self._build_specialist_agent(chain_spec.delegated_agent, tools=delegated_tools)
        tasks = [
            Task(
                description=(
                    'Review the validated intent and confirm the chained specialist handoff.\n'
                    f'User query: {payload.query}\n'
                    f'Primary specialist: {chain_spec.primary_agent}\n'
                    f'Delegated specialist: {chain_spec.delegated_agent}\n'
                    'Do not answer the user. Produce only a short routing confirmation.'
                ),
                expected_output='Short routing confirmation naming the primary and delegated specialist.',
                agent=planner_agent,
            ),
            Task(
                description=(
                    'Prepare the grounded primary execution brief.\n'
                    f'Primary plan steps: {", ".join(chain_spec.root_plan.plan_steps)}\n'
                    'Do not invent data and do not answer the user directly.'
                ),
                expected_output='Short execution brief for the primary specialist.',
                agent=primary_agent,
            ),
            Task(
                description=(
                    'Prepare the delegated execution brief for the follow-up specialist.\n'
                    f'Delegated specialist: {chain_spec.delegated_agent}\n'
                    'Do not invent data and do not answer the user directly.'
                ),
                expected_output='Short execution brief for the delegated specialist.',
                agent=delegated_agent,
            ),
        ]
        process = Process.sequential if Process is not None else 'sequential'
        return Crew(
            agents=[planner_agent, primary_agent, delegated_agent],
            tasks=tasks,
            process=process,
            verbose=False,
        )

    @staticmethod
    def _build_specialist_agent(agent_name: str, *, tools: list[Any], allow_delegation: bool = False) -> Any:
        role_map = {
            'operations': (
                'Operations Agent',
                'Handle grounded route and trip questions using structured SQL evidence.',
                'Specializes in routes, trips, delays, capacity, and operational status.',
            ),
            'reservations': (
                'Reservations Agent',
                'Handle reservation queries and booking flows using grounded reservation records.',
                'Specializes in reservations, bookings, cancellations, and utilization signals.',
            ),
            'insights': (
                'Insights Agent',
                'Handle incident explanations while keeping SQL as the source of truth and vector search scoped to narratives.',
                'Specializes in incident patterns, explanations, and similarity-backed narrative retrieval.',
            ),
        }
        role, goal, backstory = role_map.get(agent_name, role_map['operations'])
        return Agent(
            role=role,
            goal=goal,
            backstory=backstory,
            allow_delegation=allow_delegation,
            tools=tools,
            verbose=False,
        )

    @staticmethod
    def _tool_names_for_agent(agent_name: str) -> list[str]:
        toolbox = build_specialist_toolbox(agent_name)
        names = ['sql_db_query']
        if toolbox.agent_name == 'insights':
            names.append('incident_vector_search')
        return names

    def _build_specialist_tools(self, agent_name: str) -> list[Any]:
        tools = [self._make_tool('sql_db_query', 'Use validated SQL against operational data only.', lambda: 'Use SQLTool execution.')]
        if agent_name == 'insights':
            tools.append(
                self._make_tool(
                    'incident_vector_search',
                    'Search similar incident narratives only when the plan requires vector support.',
                    lambda: 'Use incident narrative vector retrieval only for incident explanations.',
                )
            )
        return tools

    def _build_handoff_contract_tool(self) -> Any:
        return self._make_tool(
            'specialist_handoff_contract',
            'Confirm the selected specialist and the grounded execution contract.',
            lambda: 'Planner must hand off to one primary specialist and may authorize one bounded delegated specialist while preserving SQL as the source of truth.',
        )

    @staticmethod
    def _make_tool(name: str, description: str, fn: Callable[[], str]) -> Any:
        if crewai_tool is None:
            return {'name': name, 'description': description}

        def _tool() -> str:
            return fn()

        _tool.__name__ = name
        _tool.__doc__ = description
        decorated = crewai_tool(name)(_tool)
        decorated.__doc__ = description
        decorated.description = description
        return decorated
