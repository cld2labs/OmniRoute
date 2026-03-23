from __future__ import annotations

import json
import logging
from datetime import datetime, time, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db_session
from ..models.schemas import (
    AdminQueryRequest,
    AgentResponse,
    CsvUploadResponse,
    DashboardMetrics,
    DashboardOverviewResponse,
    DataSeedRequest,
    IncidentCreateRequest,
    IncidentCreateResponse,
    IncidentListResponse,
    IncidentRecord,
    ReservationListResponse,
    ReservationRecord,
    RouteListResponse,
    RouteRecord,
    SimulationConfigPayload,
    SimulationControlRequest,
    SimulationStatusResponse,
    TripListResponse,
    TripRecord,
)
from ..models.tables import Incident, Reservation, Route, Trip
from ..services.data_engine import (
    get_engine_status,
    seed_data,
    start_simulation,
    stop_simulation,
    tick_simulation,
    update_simulation_config,
)
from ..services.ingest import ingest_incidents_csv, ingest_ops_csv, ingest_reservations_csv
from ..services.embeddings.jobs import enqueue_incident_embedding_job
from ..services.query_service import AdminQueryService

router = APIRouter(prefix='/admin', tags=['admin'])
query_service = AdminQueryService()
logger = logging.getLogger('omniroute.api')


@router.get('/dashboard/overview', response_model=DashboardOverviewResponse)
async def get_dashboard_overview(db_session: AsyncSession = Depends(get_db_session)) -> DashboardOverviewResponse:
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today_start + timedelta(days=1)

    active_routes = await db_session.scalar(select(func.count(Route.id)).where(Route.is_active.is_(True)))
    trips_in_progress = await db_session.scalar(select(func.count(Trip.id)).where(Trip.status.in_(('boarding', 'in_transit', 'delayed'))))
    delayed_trips = await db_session.scalar(select(func.count(Trip.id)).where(Trip.status == 'delayed'))
    cancelled_trips = await db_session.scalar(select(func.count(Trip.id)).where(Trip.status == 'cancelled'))
    active_incidents = await db_session.scalar(select(func.count(Incident.id)).where(Incident.occurred_at >= today_start))
    reservations_today = await db_session.scalar(
        select(func.count(Reservation.id)).where(Reservation.created_at >= today_start, Reservation.created_at < tomorrow)
    )

    capacity_total = await db_session.scalar(select(func.coalesce(func.sum(Trip.capacity_total), 0)))
    seats_available = await db_session.scalar(select(func.coalesce(func.sum(Trip.seats_available), 0)))
    utilization = 0.0
    if capacity_total:
        utilization = round((float(capacity_total) - float(seats_available or 0)) / float(capacity_total), 4)

    status_rows = (
        await db_session.execute(select(Trip.status, func.count(Trip.id)).group_by(Trip.status).order_by(Trip.status.asc()))
    ).all()
    incidents = (
        await db_session.execute(
            select(
                Incident.id.label('incident_id'),
                Incident.route_id,
                Incident.trip_id,
                Incident.incident_type,
                Incident.occurred_at,
                Incident.summary,
            )
            .order_by(Incident.occurred_at.desc())
            .limit(5)
        )
    ).mappings().all()

    engine_status = await get_engine_status(db_session)
    return DashboardOverviewResponse(
        metrics=DashboardMetrics(
            active_routes=int(active_routes or 0),
            trips_in_progress=int(trips_in_progress or 0),
            delayed_trips=int(delayed_trips or 0),
            cancelled_trips=int(cancelled_trips or 0),
            active_incidents=int(active_incidents or 0),
            reservations_today=int(reservations_today or 0),
            seat_utilization_pct=utilization,
        ),
        status_breakdown={status: count for status, count in status_rows},
        recent_incidents=[dict(row) for row in incidents],
        simulation=engine_status['engine'],
    )


@router.get('/routes', response_model=RouteListResponse)
async def list_routes(
    active: bool | None = Query(default=None),
    db_session: AsyncSession = Depends(get_db_session),
) -> RouteListResponse:
    stmt = select(Route).order_by(Route.route_name.asc())
    if active is not None:
        stmt = stmt.where(Route.is_active.is_(active))
    rows = (await db_session.execute(stmt)).scalars().all()
    return RouteListResponse(
        routes=[
            RouteRecord(
                route_id=row.id,
                route_name=row.route_name,
                origin_name=row.origin_name,
                destination_name=row.destination_name,
                base_price_cents=row.base_price_cents,
                popularity_score=row.popularity_score,
                is_active=row.is_active,
            )
            for row in rows
        ]
    )


@router.get('/trips', response_model=TripListResponse)
async def list_trips(
    route_id: UUID | None = None,
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    db_session: AsyncSession = Depends(get_db_session),
) -> TripListResponse:
    stmt = (
        select(
            Trip.id.label('trip_id'),
            Trip.route_id,
            Route.route_name,
            Trip.departure_time,
            Trip.arrival_time,
            Trip.capacity_total,
            Trip.seats_available,
            Trip.status,
            Trip.delay_minutes,
            Trip.last_simulated_at,
        )
        .join(Route, Route.id == Trip.route_id)
        .order_by(Trip.departure_time.asc())
        .limit(limit)
    )
    if route_id is not None:
        stmt = stmt.where(Trip.route_id == route_id)
    if status:
        stmt = stmt.where(Trip.status == status)
    if date_from is not None:
        stmt = stmt.where(Trip.departure_time >= date_from)
    if date_to is not None:
        stmt = stmt.where(Trip.departure_time <= date_to)

    rows = (await db_session.execute(stmt)).mappings().all()
    return TripListResponse(trips=[TripRecord(**dict(row)) for row in rows])


@router.get('/reservations', response_model=ReservationListResponse)
async def list_reservations(
    trip_id: UUID | None = None,
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    db_session: AsyncSession = Depends(get_db_session),
) -> ReservationListResponse:
    stmt = select(Reservation).order_by(Reservation.created_at.desc()).limit(limit)
    if trip_id is not None:
        stmt = stmt.where(Reservation.trip_id == trip_id)
    if status:
        stmt = stmt.where(Reservation.status == status)

    rows = (await db_session.execute(stmt)).scalars().all()
    return ReservationListResponse(
        reservations=[
            ReservationRecord(
                reservation_id=row.id,
                trip_id=row.trip_id,
                customer_name=row.customer_name,
                email=row.email,
                phone_number=row.phone_number,
                seats_booked=row.seats_booked,
                amount_paid_cents=row.amount_paid_cents,
                booking_channel=row.booking_channel,
                status=row.status,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]
    )


@router.get('/incidents', response_model=IncidentListResponse)
async def list_incidents(
    route_id: UUID | None = None,
    trip_id: UUID | None = None,
    incident_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    db_session: AsyncSession = Depends(get_db_session),
) -> IncidentListResponse:
    stmt = select(Incident).order_by(Incident.occurred_at.desc()).limit(limit)
    if route_id is not None:
        stmt = stmt.where(Incident.route_id == route_id)
    if trip_id is not None:
        stmt = stmt.where(Incident.trip_id == trip_id)
    if incident_type:
        stmt = stmt.where(Incident.incident_type == incident_type)
    if date_from is not None:
        stmt = stmt.where(Incident.occurred_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(Incident.occurred_at <= date_to)

    rows = (await db_session.execute(stmt)).scalars().all()
    return IncidentListResponse(
        incidents=[
            IncidentRecord(
                incident_id=row.id,
                route_id=row.route_id,
                trip_id=row.trip_id,
                incident_type=row.incident_type,
                delay_minutes=row.delay_minutes,
                severity=row.severity,
                source_type=row.source_type,
                occurred_at=row.occurred_at,
                summary=row.summary,
                details=row.details,
                proof_url=row.proof_url,
            )
            for row in rows
        ]
    )


@router.post('/incidents', response_model=IncidentCreateResponse)
async def create_incident(
    payload: IncidentCreateRequest,
    background_tasks: BackgroundTasks,
    db_session: AsyncSession = Depends(get_db_session),
) -> IncidentCreateResponse:
    resolved_route_id = payload.route_id
    trip: Trip | None = None

    if payload.trip_id is not None:
        trip = await db_session.get(Trip, payload.trip_id)
        if trip is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Trip not found.')
        if resolved_route_id is not None and trip.route_id != resolved_route_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Selected trip does not belong to the selected route.')
        resolved_route_id = trip.route_id

    incident = Incident(
        route_id=resolved_route_id,
        trip_id=payload.trip_id,
        incident_type=payload.incident_type,
        delay_minutes=payload.delay_minutes,
        severity=payload.severity,
        source_type=payload.source_type,
        occurred_at=payload.occurred_at,
        summary=payload.summary,
        details=payload.details,
        proof_url=payload.proof_url,
        embedding=None,
    )
    db_session.add(incident)

    if trip is not None and payload.delay_minutes is not None:
        trip.status = 'delayed'
        trip.delay_minutes = payload.delay_minutes
        trip.last_simulated_at = datetime.now(timezone.utc)

    await db_session.commit()
    await db_session.refresh(incident)
    background_tasks.add_task(enqueue_incident_embedding_job, str(incident.id))
    return IncidentCreateResponse(ok=True, incident_id=str(incident.id))


@router.post('/query', response_model=AgentResponse, response_model_exclude_none=True)
async def run_admin_query(
    payload: AdminQueryRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
) -> AgentResponse:
    response = await query_service.run(payload, db_session)
    sql_entries = [
        assumption.removeprefix('SQL used: ').strip()
        for assumption in (response.query_plan.assumptions if response.query_plan else [])
        if assumption.startswith('SQL used: ')
    ]
    if sql_entries:
        logger.info(
            json.dumps(
                {
                    'event': 'generated_sql',
                    'service': 'api',
                    'request_id': getattr(request.state, 'request_id', ''),
                    'route': request.url.path,
                    'selected_agent': response.query_plan.selected_agent if response.query_plan else None,
                    'query': payload.query,
                    'sql': sql_entries,
                }
            )
        )
    return response


@router.get('/simulation/status', response_model=SimulationStatusResponse)
async def simulation_status(db_session: AsyncSession = Depends(get_db_session)) -> SimulationStatusResponse:
    return SimulationStatusResponse(**(await get_engine_status(db_session)))


@router.post('/simulation/start')
async def simulation_start(
    payload: SimulationControlRequest,
    db_session: AsyncSession = Depends(get_db_session),
) -> dict:
    if payload.action != 'start':
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Use action=start for this endpoint.')
    return await start_simulation(db_session)


@router.post('/simulation/stop')
async def simulation_stop(
    payload: SimulationControlRequest,
    db_session: AsyncSession = Depends(get_db_session),
) -> dict:
    if payload.action != 'stop':
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Use action=stop for this endpoint.')
    return await stop_simulation(db_session)


@router.post('/simulation/tick')
async def simulation_tick(db_session: AsyncSession = Depends(get_db_session)) -> dict:
    return await tick_simulation(db_session)


@router.put('/simulation/config')
async def simulation_config(
    payload: SimulationConfigPayload,
    db_session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await update_simulation_config(db_session, payload)


@router.post('/data/seed')
async def data_seed(
    payload: DataSeedRequest,
    db_session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await seed_data(db_session, payload)


@router.post('/uploads/csv', response_model=CsvUploadResponse)
async def upload_csv(
    dataset: str = Query(..., pattern='^(ops|reservations|incidents)$'),
    file: UploadFile = File(...),
    db_session: AsyncSession = Depends(get_db_session),
) -> CsvUploadResponse:
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Uploaded file is empty.')

    if dataset == 'ops':
        summary = await ingest_ops_csv(file_bytes, db_session)
    elif dataset == 'reservations':
        summary = await ingest_reservations_csv(file_bytes, db_session)
    else:
        summary = await ingest_incidents_csv(file_bytes, db_session)

    return CsvUploadResponse(dataset=dataset, filename=file.filename or 'upload.csv', **summary)
