from __future__ import annotations

import json
import logging
from typing import Any

from ...config import get_settings
from ...models.schemas import ValidatedQueryIntent
from .internal_plan import InternalQueryPlan

logger = logging.getLogger('omniroute.api')


class GroundedAnswerSynthesizer:
    def __init__(self, llm_client: Any | None = None) -> None:
        self._llm_client = llm_client

    async def synthesize(
        self,
        *,
        query_text: str,
        intent: ValidatedQueryIntent,
        plan: InternalQueryPlan,
        deterministic_answer: str,
        block_results: dict[str, list[dict[str, Any]]],
        vector_records: list[dict[str, Any]],
    ) -> str:
        if self._llm_client is None:
            return deterministic_answer

        sql_rows = block_results.get('generated_sql') or []
        if not sql_rows and not vector_records:
            return deterministic_answer

        settings = get_settings()
        sql_rows = sql_rows[:5]
        vector_records = vector_records[:3]

        system_prompt = (
            'You rewrite grounded transportation query results into a concise operator-facing answer. '
            'Use only the provided evidence. Do not invent facts, counts, causes, dates, or identifiers. '
            'If evidence is limited, say so plainly. Keep the answer to 2 short paragraphs maximum. '
            'Preserve concrete route_id, trip_id, reservation_id, or incident_id references when they are present in the evidence.'
        )
        user_prompt = (
            f'User query: {query_text}\n'
            f'Intent: {json.dumps(intent.model_dump(mode="json"), ensure_ascii=True)}\n'
            f'Plan: {json.dumps({"selected_agent": plan.selected_agent, "response_mode": plan.response_mode}, ensure_ascii=True)}\n'
            f'Deterministic fallback answer: {deterministic_answer}\n'
            f'SQL evidence rows: {json.dumps(sql_rows, default=str, ensure_ascii=True)}\n'
            f'Incident narrative evidence: {json.dumps(vector_records, default=str, ensure_ascii=True)}\n'
            'Rewrite the fallback answer into a natural response grounded only in this evidence.'
        )

        try:
            response = await self._llm_client.responses.create(  # type: ignore[union-attr]
                model=settings.llm_model,
                temperature=min(settings.llm_temperature, 0.2),
                input=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt},
                ],
            )
        except Exception:
            logger.exception('Grounded answer synthesis failed')
            return deterministic_answer

        content = (getattr(response, 'output_text', '') or '').strip()
        return content or deterministic_answer
