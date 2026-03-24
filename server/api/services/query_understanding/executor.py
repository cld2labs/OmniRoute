from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agents.tools import build_specialist_toolbox
from ...config import get_settings
from ...models.schemas import ValidatedQueryIntent
from ...observability import wrap_openai_client
from .internal_plan import InternalQueryPlan

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover
    AsyncOpenAI = None  # type: ignore[assignment]


@dataclass(slots=True)
class QueryExecutionResult:
    sql_records: list[dict[str, Any]] = field(default_factory=list)
    vector_records: list[dict[str, Any]] = field(default_factory=list)
    block_results: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    sql_queries: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str | None = None


class QueryUnderstandingExecutor:
    def __init__(self, llm_client: Any | None = None) -> None:
        self._llm_client = llm_client or self._build_llm_client()

    @property
    def llm_client(self) -> Any | None:
        return self._llm_client

    async def execute(
        self,
        *,
        query_text: str,
        intent: ValidatedQueryIntent,
        plan: InternalQueryPlan,
        db_session: AsyncSession,
    ) -> QueryExecutionResult:
        toolbox = build_specialist_toolbox(plan.selected_agent, llm_client=self._llm_client)
        result = await toolbox.execute(
            query_text=query_text,
            intent=intent,
            plan=plan,
            db_session=db_session,
        )

        return QueryExecutionResult(
            sql_records=result.sql_records,
            vector_records=result.vector_records,
            block_results=result.block_results,
            assumptions=result.assumptions,
            sql_queries=result.sql_queries,
            errors=result.errors,
            tool_calls=result.tool_calls,
            needs_clarification=result.needs_clarification,
            clarification_question=result.clarification_question,
        )

    @staticmethod
    def _build_llm_client() -> Any | None:
        if os.getenv('PYTEST_CURRENT_TEST'):
            return None
        settings = get_settings()
        if AsyncOpenAI is None or not settings.llm_api_key:
            return None
        return wrap_openai_client(
            AsyncOpenAI(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                timeout=float(settings.llm_timeout_seconds),
            ),
            settings,
        )
