from __future__ import annotations

import logging
from inspect import isawaitable
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..embeddings.client import embeddings_enabled
from ..embeddings.jobs import enqueue_incident_embedding_job
from .parsing import MissingColumnsError, read_csv_bytes, read_csv_columns
from .upserts import (
    resolve_route_id_by_name,
    resolve_trip_id_by_route_and_departure,
    upsert_incident,
    upsert_reservation,
    upsert_route,
    upsert_route_stops,
    upsert_trip,
)
from .validators import IngestValidationError, validate_incident_row, validate_ops_row, validate_reservation_row


logger = logging.getLogger('omniroute.api.ingest')

MAX_ERROR_ITEMS = 50
OPS_REQUIRED_COLUMNS = {
    'route_name',
    'origin_name',
    'destination_name',
    'base_price_cents',
    'stops_json',
    'departure_time',
    'arrival_time',
    'capacity_total',
    'seats_available',
    'status',
    'delay_minutes',
}
RESERVATIONS_REQUIRED_COLUMNS = {
    'reservation_external_id',
    'route_name',
    'departure_time',
    'customer_name',
    'email',
    'phone_number',
    'seats_booked',
    'status',
    'amount_paid_cents',
}
INCIDENTS_REQUIRED_COLUMNS = {
    'incident_external_id',
    'route_name',
    'incident_type',
    'occurred_at',
    'summary',
}


async def enqueue_embedding_job(incident_id: str) -> None:
    result = enqueue_incident_embedding_job(incident_id)
    if isawaitable(result):
        await result


async def _invoke_enqueue_embedding_job(incident_id: str) -> None:
    maybe_awaitable = enqueue_embedding_job(incident_id)
    if isawaitable(maybe_awaitable):
        await maybe_awaitable


def _missing_required_columns(file_bytes: bytes, required: set[str]) -> list[str]:
    columns = set(read_csv_columns(file_bytes))
    missing = sorted(required - columns)
    return missing


def _empty_summary(rows_total: int) -> dict[str, Any]:
    return {
        'ok': True,
        'rows_total': rows_total,
        'rows_processed': 0,
        'rows_failed': 0,
        'errors': [],
    }


def _append_error(summary: dict[str, Any], *, row_number: int, code: str, message: str) -> None:
    summary['rows_failed'] += 1
    if len(summary['errors']) < MAX_ERROR_ITEMS:
        summary['errors'].append({'row': row_number, 'code': code, 'message': message})


def _ensure_required_columns(file_bytes: bytes, required_columns: set[str]) -> None:
    missing = _missing_required_columns(file_bytes, required_columns)
    if missing:
        raise MissingColumnsError(missing)


async def ingest_ops_csv(file_bytes: bytes, db_session: AsyncSession) -> dict[str, Any]:
    _ensure_required_columns(file_bytes, OPS_REQUIRED_COLUMNS)
    rows = read_csv_bytes(file_bytes)
    summary = _empty_summary(len(rows))

    file_tx = await db_session.begin()
    try:
        for index, row in enumerate(rows, start=2):
            try:
                row_input = validate_ops_row(row)
            except IngestValidationError as exc:
                _append_error(summary, row_number=index, code=exc.code, message=str(exc))
                continue

            row_tx = await db_session.begin_nested()
            try:
                route_id = await upsert_route(
                    db_session,
                    route_name=row_input.route_name,
                    origin_name=row_input.origin_name,
                    destination_name=row_input.destination_name,
                    base_price_cents=row_input.base_price_cents,
                )
                await upsert_route_stops(db_session, route_id=route_id, stops=row_input.stops)
                await upsert_trip(
                    db_session,
                    route_id=route_id,
                    departure_time=row_input.departure_time,
                    arrival_time=row_input.arrival_time,
                    capacity_total=row_input.capacity_total,
                    seats_available=row_input.seats_available,
                    status=row_input.status,
                    delay_minutes=row_input.delay_minutes,
                )
            except Exception:
                await row_tx.rollback()
                _append_error(
                    summary,
                    row_number=index,
                    code='UPSERT_ERROR',
                    message='Failed to upsert ops row.',
                )
                continue

            await row_tx.commit()
            summary['rows_processed'] += 1

        if summary['rows_processed'] > 0:
            await file_tx.commit()
        else:
            await file_tx.rollback()
        return summary
    except Exception:
        await file_tx.rollback()
        raise


async def ingest_reservations_csv(file_bytes: bytes, db_session: AsyncSession) -> dict[str, Any]:
    _ensure_required_columns(file_bytes, RESERVATIONS_REQUIRED_COLUMNS)
    rows = read_csv_bytes(file_bytes)
    summary = _empty_summary(len(rows))

    file_tx = await db_session.begin()
    try:
        for index, row in enumerate(rows, start=2):
            try:
                row_input = validate_reservation_row(row)
            except IngestValidationError as exc:
                _append_error(summary, row_number=index, code=exc.code, message=str(exc))
                continue

            row_tx = await db_session.begin_nested()
            try:
                trip_id = await resolve_trip_id_by_route_and_departure(
                    db_session,
                    route_name=row_input.route_name,
                    departure_time=row_input.departure_time,
                )
                if trip_id is None:
                    raise IngestValidationError(
                        'No trip found for route_name + departure_time.',
                        code='LOOKUP_ERROR',
                    )
                await upsert_reservation(db_session, trip_id=trip_id, reservation=row_input)
            except IngestValidationError as exc:
                await row_tx.rollback()
                _append_error(summary, row_number=index, code=exc.code, message=str(exc))
                continue
            except Exception:
                await row_tx.rollback()
                _append_error(
                    summary,
                    row_number=index,
                    code='UPSERT_ERROR',
                    message='Failed to upsert reservation row.',
                )
                continue

            await row_tx.commit()
            summary['rows_processed'] += 1

        if summary['rows_processed'] > 0:
            await file_tx.commit()
        else:
            await file_tx.rollback()
        return summary
    except Exception:
        await file_tx.rollback()
        raise


async def ingest_incidents_csv(file_bytes: bytes, db_session: AsyncSession) -> dict[str, Any]:
    _ensure_required_columns(file_bytes, INCIDENTS_REQUIRED_COLUMNS)
    rows = read_csv_bytes(file_bytes)
    summary = _empty_summary(len(rows))
    incident_ids_to_enqueue: list[UUID] = []

    file_tx = await db_session.begin()
    try:
        for index, row in enumerate(rows, start=2):
            try:
                row_input = validate_incident_row(row)
            except IngestValidationError as exc:
                _append_error(summary, row_number=index, code=exc.code, message=str(exc))
                continue

            row_tx = await db_session.begin_nested()
            try:
                route_id = await resolve_route_id_by_name(db_session, row_input.route_name)
                if route_id is None:
                    raise IngestValidationError('No route found for route_name.', code='LOOKUP_ERROR')

                trip_id: UUID | None = None
                if row_input.departure_time is not None:
                    trip_id = await resolve_trip_id_by_route_and_departure(
                        db_session,
                        route_name=row_input.route_name,
                        departure_time=row_input.departure_time,
                    )
                    if trip_id is None:
                        raise IngestValidationError(
                            'No trip found for route_name + departure_time.',
                            code='LOOKUP_ERROR',
                        )

                incident_id = await upsert_incident(
                    db_session,
                    route_id=route_id,
                    trip_id=trip_id,
                    incident=row_input,
                )
                incident_ids_to_enqueue.append(incident_id)
            except IngestValidationError as exc:
                await row_tx.rollback()
                _append_error(summary, row_number=index, code=exc.code, message=str(exc))
                continue
            except Exception:
                await row_tx.rollback()
                _append_error(
                    summary,
                    row_number=index,
                    code='UPSERT_ERROR',
                    message='Failed to upsert incident row.',
                )
                continue

            await row_tx.commit()
            summary['rows_processed'] += 1

        if summary['rows_processed'] > 0:
            await file_tx.commit()
            if embeddings_enabled():
                for incident_id in incident_ids_to_enqueue:
                    await _invoke_enqueue_embedding_job(str(incident_id))
            else:
                logger.info('incident_embedding_enqueue_skipped reason=disabled')
        else:
            await file_tx.rollback()
        return summary
    except Exception:
        await file_tx.rollback()
        raise
