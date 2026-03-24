from __future__ import annotations

import re
from typing import Any

import sqlparse
from sqlalchemy import text

FORBIDDEN = [
    'drop',
    'delete',
    'update',
    'insert',
    'truncate',
    'alter',
    'create',
    'replace',
    'grant',
    'revoke',
    'pg_',
    'information_schema',
    'pg_catalog',
]


def strip_sql_fences(sql: str) -> str:
    return re.sub(r'```sql|```', '', sql, flags=re.IGNORECASE).strip()


def _to_sqlalchemy_text_sql(sql: str) -> str:
    return re.sub(r'%\(([a-zA-Z_][a-zA-Z0-9_]*)\)s', r':\1', sql)


def _is_scalar_count_query(sql: str) -> bool:
    normalized = re.sub(r'\s+', ' ', sql.strip().lower())
    if ' group by ' in normalized:
        return False
    return normalized.startswith('select count(') or normalized.startswith('select count(distinct')


async def validate_generated_sql(sql: str, db_session: Any, params: dict[str, Any] | None = None) -> str:
    if not sql or not sql.strip():
        raise ValueError('Empty SQL.')
    sql = strip_sql_fences(sql)
    parsed = sqlparse.parse(sql)
    if not parsed or len(parsed) != 1:
        raise ValueError('Expected exactly one SQL statement.')
    if parsed[0].get_type() != 'SELECT':
        raise ValueError(f"Only SELECT allowed. Got: {parsed[0].get_type()}")
    sql_lower = sql.lower()
    for kw in FORBIDDEN:
        if kw == 'pg_':
            matched = kw in sql_lower
        else:
            matched = re.search(rf'(?<![a-z0-9_]){re.escape(kw)}(?![a-z0-9_])', sql_lower) is not None
        if matched:
            raise ValueError(f'Forbidden keyword: {kw}')
    if 'limit' not in sql_lower and not _is_scalar_count_query(sql):
        raise ValueError('SQL must include LIMIT.')
    try:
        explain_sql = _to_sqlalchemy_text_sql(sql)
        execution = db_session.execute(text(f'EXPLAIN {explain_sql}'), params or {})
        if hasattr(execution, '__await__'):
            await execution
    except Exception as exc:
        raise ValueError(f'SQL failed dry-run: {exc}') from exc
    return sql
