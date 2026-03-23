from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.tables import Incident
from .client import get_embedding_client


MAX_VECTOR_TOP_K = 5


async def search_similar_incidents(
    query_text: str,
    db_session: AsyncSession,
    top_k: int = 5,
    route_id: UUID | None = None,
    trip_id: UUID | None = None,
    date_from: date | datetime | None = None,
    date_to: date | datetime | None = None,
    incident_type: str | None = None,
) -> list[dict]:
    normalized_query = str(query_text or '').strip()
    if not normalized_query:
        return []

    try:
        k = min(max(1, int(top_k)), MAX_VECTOR_TOP_K)
    except (TypeError, ValueError):
        k = MAX_VECTOR_TOP_K
    query_embedding = await get_embedding_client().embed_text(normalized_query)
    distance = Incident.embedding.cosine_distance(query_embedding)
    score = (1 - distance).label('score')

    stmt = (
        select(
            Incident.id.label('incident_id'),
            Incident.occurred_at.label('occurred_at'),
            Incident.summary.label('summary'),
            score,
        )
        .where(Incident.embedding.is_not(None))
    )

    if route_id is not None:
        stmt = stmt.where(Incident.route_id == route_id)
    if trip_id is not None:
        stmt = stmt.where(Incident.trip_id == trip_id)
    if date_from is not None:
        stmt = stmt.where(Incident.occurred_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(Incident.occurred_at <= date_to)
    if incident_type is not None:
        stmt = stmt.where(Incident.incident_type == incident_type)

    stmt = stmt.order_by(distance.asc()).limit(k)
    result = await db_session.execute(stmt)
    rows = result.mappings().all()

    matches: list[dict] = []
    for row in rows:
        matches.append(
            {
                'incident_id': str(row['incident_id']),
                'occurred_at': row['occurred_at'],
                'summary': row['summary'],
                'score': float(row['score']),
            }
        )
    return matches
