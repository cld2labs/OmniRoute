from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import SessionLocal
from ...models.tables import Incident, Route, Trip
from .builder import build_incident_embedding_text
from .client import embeddings_enabled, get_embedding_client


logger = logging.getLogger('omniroute.api.embeddings.jobs')


async def enqueue_incident_embedding_job(incident_id: str) -> None:
    if not embeddings_enabled():
        logger.info('incident_embedding_enqueue_skipped incident_id=%s reason=disabled', incident_id)
        return

    # TODO: Replace local asyncio task scheduling with a real queue producer.
    logger.info('incident_embedding_enqueue_stub incident_id=%s', incident_id)
    asyncio.create_task(_process_with_fresh_session(incident_id))


async def _process_with_fresh_session(incident_id: str) -> None:
    async with SessionLocal() as session:
        await process_incident_embedding_job(incident_id, session)


async def _resolve_route_name(db_session: AsyncSession, route_id: UUID | None) -> str:
    if route_id is None:
        return 'unknown'
    result = await db_session.execute(select(Route.route_name).where(Route.id == route_id))
    route_name = result.scalar_one_or_none()
    return str(route_name or 'unknown')


async def _resolve_trip_context(db_session: AsyncSession, incident: Incident) -> str:
    if incident.trip_id is None:
        return 'unknown'

    result = await db_session.execute(
        select(Trip.id, Trip.departure_time).where(Trip.id == incident.trip_id)
    )
    row = result.one_or_none()
    if row is None:
        return str(incident.trip_id)
    if row.departure_time is not None:
        return row.departure_time.isoformat()
    return str(row.id)


async def process_incident_embedding_job(incident_id: str, db_session: AsyncSession) -> None:
    latency_start = perf_counter()
    provider = 'unknown'
    model = 'unknown'

    try:
        incident_uuid = UUID(str(incident_id))
    except ValueError:
        logger.warning(
            'incident_embedding_processed incident_id=%s provider=%s model=%s latency_ms=%d success=false',
            incident_id,
            provider,
            model,
            int((perf_counter() - latency_start) * 1000),
        )
        return

    try:
        embedding_client = get_embedding_client()
        provider = embedding_client.config.provider
        model = embedding_client.config.model

        result = await db_session.execute(select(Incident).where(Incident.id == incident_uuid))
        incident = result.scalar_one_or_none()
        if incident is None:
            logger.warning(
                'incident_embedding_processed incident_id=%s provider=%s model=%s latency_ms=%d success=false',
                incident_id,
                provider,
                model,
                int((perf_counter() - latency_start) * 1000),
            )
            return

        route_name = await _resolve_route_name(db_session, incident.route_id)
        trip_context = await _resolve_trip_context(db_session, incident)
        embedding_text = build_incident_embedding_text(incident, route_name, trip_context)
        embedding_vector = await embedding_client.embed_text(embedding_text)

        incident.embedding = embedding_vector
        # TODO: Add embedding_hash and embedding_status tracking columns in a future migration.
        await db_session.commit()
        logger.info(
            'incident_embedding_processed incident_id=%s provider=%s model=%s latency_ms=%d success=true',
            incident_id,
            provider,
            model,
            int((perf_counter() - latency_start) * 1000),
        )
    except Exception:
        await db_session.rollback()
        logger.exception(
            'incident_embedding_processed incident_id=%s provider=%s model=%s latency_ms=%d success=false',
            incident_id,
            provider,
            model,
            int((perf_counter() - latency_start) * 1000),
        )
