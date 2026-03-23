from __future__ import annotations

import json
import re
import sys
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .query_understanding.schema_context import get_agent_schema_context
from .query_understanding.sql_builders import build_sql_for_intent_family
from .query_understanding.intent_classifier import classify_intent
from .query_understanding.intent_contracts import CANONICAL_SQL, INTENT_TO_CANONICAL
from .query_understanding.sql_generator import generate_sql
from .query_understanding.sql_semantics import validate_sql_matches_filters
from .query_understanding.sql_validator import validate_generated_sql


class SQLTool:
    def __init__(self, db_session: AsyncSession, llm_client: Any, agent: str):
        self.db = db_session
        self.llm = llm_client
        self.agent = agent

    async def run(
        self,
        query: str,
        filters: dict[str, Any],
        *,
        intent_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            normalized_filters = {key: value for key, value in filters.items() if value is not None}
            normalized_filters['limit'] = min(int(normalized_filters.get('limit', 200)), 200)

            deterministic_sql = build_sql_for_intent_family(normalized_filters, intent_context)
            if deterministic_sql is not None:
                clean_sql = await validate_generated_sql(deterministic_sql.strip(), self.db, normalized_filters)
                sql_source = 'intent_family'
                canonical = False
            else:
                canonical_intent = classify_intent(query)
                if canonical_intent:
                    canonical_sql = CANONICAL_SQL[INTENT_TO_CANONICAL[canonical_intent]].strip()
                    clarification = self._canonical_clarification(canonical_intent, normalized_filters)
                    if clarification is not None:
                        return {
                            'rows': [],
                            'row_count': 0,
                            'truncated': False,
                            'needs_clarification': True,
                            'clarification_question': clarification,
                            'canonical': True,
                        }
                    clean_sql = await validate_generated_sql(canonical_sql, self.db, normalized_filters)
                    sql_source = 'canonical'
                    canonical = True
                else:
                    schema_context = get_agent_schema_context(self.agent)
                    error: str | None = None
                    raw_payload: dict[str, Any] | None = None
                    clean_sql = ''
                    for attempt in range(2):
                        raw_payload = await generate_sql(
                            query,
                            self.agent,
                            normalized_filters,
                            self.llm,
                            schema_context,
                            intent_context=intent_context,
                            error_feedback=error if attempt == 1 else None,
                        )
                        if raw_payload.get('needs_clarification'):
                            return {
                                'rows': [],
                                'row_count': 0,
                                'truncated': False,
                                'needs_clarification': True,
                                'clarification_question': raw_payload.get('clarification_question'),
                                'ambiguity_reason': raw_payload.get('ambiguity_reason'),
                                'canonical': False,
                            }
                        try:
                            clean_sql = await validate_generated_sql(raw_payload['sql'], self.db, normalized_filters)
                            break
                        except ValueError as exc:
                            error = str(exc)
                            if attempt == 1:
                                return {
                                    'rows': [],
                                    'row_count': 0,
                                    'truncated': False,
                                    'error': f'SQL generation failed after retry: {error}',
                                    'canonical': False,
                                }
                    sql_source = 'llm'
                    canonical = False

            validate_sql_matches_filters(
                clean_sql,
                normalized_filters,
                entity=(intent_context or {}).get('entity'),
                operation=(intent_context or {}).get('operation'),
            )
            clean_sql = self._normalize_date_interval_expressions(clean_sql)
            executable_sql = self._to_sqlalchemy_text_sql(clean_sql)
            print(
                json.dumps(
                    {
                        'event': 'generated_sql',
                        'service': 'api',
                        'agent': self.agent,
                        'sql_source': sql_source,
                        'canonical': canonical,
                        'query': query,
                        'sql': clean_sql,
                    }
                ),
                file=sys.stdout,
                flush=True,
            )
            result = await self.db.execute(text(executable_sql), normalized_filters)
            rows = [dict(row) for row in result.mappings().fetchmany(200)]
            return {
                'rows': rows,
                'row_count': len(rows),
                'truncated': len(rows) == 200,
                'sql_used': clean_sql,
                'canonical': canonical,
            }
        except Exception as exc:
            print(
                json.dumps(
                    {
                        'event': 'generated_sql_error',
                        'service': 'api',
                        'agent': self.agent,
                        'query': query,
                        'sql': locals().get('clean_sql'),
                        'sql_executable': locals().get('executable_sql'),
                        'error': str(exc),
                    }
                ),
                file=sys.stdout,
                flush=True,
            )
            return {
                'rows': [],
                'row_count': 0,
                'truncated': False,
                'error': str(exc),
                'sql_used': locals().get('clean_sql'),
                'canonical': locals().get('canonical', False),
            }

    @staticmethod
    def _to_sqlalchemy_text_sql(sql: str) -> str:
        return re.sub(r'%\(([a-zA-Z_][a-zA-Z0-9_]*)\)s', r':\1', sql)

    @staticmethod
    def _normalize_date_interval_expressions(sql: str) -> str:
        sql = re.sub(
            r'%\((date_(?:from|to))\)s\s*\+\s*INTERVAL\s*\'1 day\'',
            r'CAST(%(\1)s AS date) + INTERVAL \'1 day\'',
            sql,
            flags=re.IGNORECASE,
        )
        return re.sub(
            r':(date_(?:from|to))\s*\+\s*INTERVAL\s*\'1 day\'',
            r'CAST(:\1 AS date) + INTERVAL \'1 day\'',
            sql,
            flags=re.IGNORECASE,
        )

    @staticmethod
    def _canonical_clarification(intent: str, filters: dict[str, Any]) -> str | None:
        if intent in {'route_delayed_trips', 'why_route_delayed'} and not filters.get('route_name'):
            return 'Which route are you asking about?'
        if intent == 'why_trip_delayed' and not filters.get('trip_id'):
            return 'Which trip are you asking about?'
        return None
