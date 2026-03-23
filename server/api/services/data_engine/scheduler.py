from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import socket
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.schemas import DataSeedRequest, SimulationConfigPayload
from ...models.tables import Incident, Reservation, Route, SimulationConfig, SimulationJob, Trip
from .seed import seed_network
from .state import get_state, set_state, utcnow
from .tick import run_tick


def _engine_stale_after(tick_interval_seconds: int) -> timedelta:
    return timedelta(seconds=max(15, tick_interval_seconds * 2 + 5))


async def _get_or_create_config(session: AsyncSession) -> SimulationConfig:
    result = await session.execute(select(SimulationConfig).where(SimulationConfig.is_active.is_(True)))
    config = result.scalar_one_or_none()
    if config is not None:
        return config

    config = SimulationConfig(
        config_name='default',
        is_active=True,
        booking_rate_per_tick=Decimal('3.0'),
        cancellation_rate_per_tick=Decimal('0.8'),
        incident_rate_per_tick=Decimal('0.4'),
        delay_sensitivity=Decimal('1.0'),
        tick_interval_seconds=60,
    )
    session.add(config)
    await session.flush()
    return config


async def _record_job(session: AsyncSession, *, job_type: str, triggered_by: str, status: str = 'running') -> SimulationJob:
    job = SimulationJob(
        id=uuid4(),
        job_type=job_type,
        status=status,
        started_at=utcnow(),
        triggered_by=triggered_by,
        details_json={},
    )
    session.add(job)
    await session.flush()
    return job


async def _mark_job_failed(session: AsyncSession, job: SimulationJob, error_message: str) -> None:
    session.add(job)
    job.status = 'failed'
    job.finished_at = utcnow()
    job.error_message = error_message
    job.details_json = {'error': error_message}
    await session.commit()


async def seed_data(session: AsyncSession, payload: DataSeedRequest) -> dict:
    config = await _get_or_create_config(session)
    del config
    job = await _record_job(session, job_type='seed', triggered_by='manual')
    try:
        stats = await seed_network(session, route_count=payload.routes, days=payload.days)
        job.status = 'succeeded'
        job.finished_at = utcnow()
        job.details_json = stats
        await set_state(session, 'last_seed_run', {'at': job.finished_at.isoformat(), 'stats': stats})
        await session.commit()
        return stats
    except Exception as exc:
        await session.rollback()
        await _mark_job_failed(session, job, str(exc))
        raise


async def tick_simulation(
    session: AsyncSession,
    triggered_by: str = 'manual',
    *,
    enable_cascading_delays: bool = True,
) -> dict:
    config = await _get_or_create_config(session)
    job = await _record_job(session, job_type='tick', triggered_by=triggered_by)
    try:
        stats = await run_tick(
            session,
            booking_rate=float(config.booking_rate_per_tick),
            cancellation_rate=float(config.cancellation_rate_per_tick),
            incident_rate=float(config.incident_rate_per_tick),
            delay_sensitivity=float(config.delay_sensitivity),
            enable_cascading_delays=enable_cascading_delays,
        )
        job.status = 'succeeded'
        job.finished_at = utcnow()
        job.details_json = stats
        await set_state(session, 'last_tick_run', {'at': job.finished_at.isoformat(), 'stats': stats})
        await session.commit()
        return stats
    except Exception as exc:
        await session.rollback()
        await _mark_job_failed(session, job, str(exc))
        raise


async def start_simulation(session: AsyncSession) -> dict[str, str]:
    await _get_or_create_config(session)
    await set_state(session, 'simulation_runtime', {'desired_state': 'running', 'updated_at': utcnow().isoformat()})
    await session.commit()
    return {'status': 'running', 'note': 'Start the data-engine container explicitly for continuous ticks.'}


async def stop_simulation(session: AsyncSession) -> dict[str, str]:
    await _get_or_create_config(session)
    await set_state(session, 'simulation_runtime', {'desired_state': 'stopped', 'updated_at': utcnow().isoformat()})
    await session.commit()
    return {'status': 'stopped', 'note': 'Running data-engine containers will pause after their current tick.'}


async def update_simulation_config(session: AsyncSession, payload: SimulationConfigPayload) -> dict:
    config = await _get_or_create_config(session)
    config.booking_rate_per_tick = Decimal(str(payload.booking_rate_per_tick))
    config.cancellation_rate_per_tick = Decimal(str(payload.cancellation_rate_per_tick))
    config.incident_rate_per_tick = Decimal(str(payload.incident_rate_per_tick))
    config.delay_sensitivity = Decimal(str(payload.delay_sensitivity))
    config.tick_interval_seconds = payload.tick_interval_seconds
    config.updated_at = utcnow()
    await session.commit()
    return {
        'config_name': config.config_name,
        'booking_rate_per_tick': float(config.booking_rate_per_tick),
        'cancellation_rate_per_tick': float(config.cancellation_rate_per_tick),
        'incident_rate_per_tick': float(config.incident_rate_per_tick),
        'delay_sensitivity': float(config.delay_sensitivity),
        'tick_interval_seconds': config.tick_interval_seconds,
    }


async def get_engine_status(session: AsyncSession) -> dict:
    config = await _get_or_create_config(session)
    runtime = await get_state(session, 'simulation_runtime', default={'desired_state': 'running'})
    heartbeat = await get_state(session, 'engine_process')
    last_seed = await get_state(session, 'last_seed_run')
    last_tick = await get_state(session, 'last_tick_run')
    heartbeat_at = heartbeat.get('last_heartbeat_at')
    heartbeat_recent = False
    if heartbeat_at:
        try:
            parsed = datetime.fromisoformat(heartbeat_at)
            heartbeat_recent = utcnow() - parsed <= _engine_stale_after(config.tick_interval_seconds)
        except ValueError:
            heartbeat_recent = False
    stopped_at = heartbeat.get('stopped_at')
    if stopped_at:
        heartbeat_recent = False

    recent_jobs = (
        await session.execute(select(SimulationJob).order_by(SimulationJob.created_at.desc()).limit(8))
    ).scalars().all()

    trips_in_progress = await session.scalar(
        select(func.count(Trip.id)).where(Trip.status.in_(('boarding', 'in_transit', 'delayed')))
    )
    delayed_trips = await session.scalar(select(func.count(Trip.id)).where(Trip.status == 'delayed'))
    active_incidents = await session.scalar(
        select(func.count(Incident.id)).where(Incident.occurred_at >= utcnow().replace(hour=0, minute=0, second=0, microsecond=0))
    )
    reservation_total = await session.scalar(select(func.count(Reservation.id)))
    route_total = await session.scalar(select(func.count(Route.id)))

    return {
        'engine': {
            'is_running': heartbeat_recent,
            'runtime_requested': runtime.get('desired_state', 'running'),
            'process': heartbeat or {},
            'config': {
                'config_name': config.config_name,
                'booking_rate_per_tick': float(config.booking_rate_per_tick),
                'cancellation_rate_per_tick': float(config.cancellation_rate_per_tick),
                'incident_rate_per_tick': float(config.incident_rate_per_tick),
                'delay_sensitivity': float(config.delay_sensitivity),
                'tick_interval_seconds': config.tick_interval_seconds,
            },
            'last_seed_run': last_seed,
            'last_tick_run': last_tick,
        },
        'jobs': [
            {
                'job_id': str(job.id),
                'job_type': job.job_type,
                'status': job.status,
                'started_at': job.started_at,
                'finished_at': job.finished_at,
                'triggered_by': job.triggered_by,
                'details': job.details_json or {},
            }
            for job in recent_jobs
        ],
        'metrics': {
            'route_count': int(route_total or 0),
            'reservation_count': int(reservation_total or 0),
            'trips_in_progress': int(trips_in_progress or 0),
            'delayed_trips': int(delayed_trips or 0),
            'active_incidents': int(active_incidents or 0),
            'server_time': datetime.now(timezone.utc).isoformat(),
        },
    }


async def mark_engine_heartbeat(
    session: AsyncSession,
    *,
    mode: str,
    pid: int,
    hostname: str | None = None,
    tick_interval_seconds: int | None = None,
) -> None:
    payload = {
        'mode': mode,
        'pid': pid,
        'hostname': hostname or socket.gethostname(),
        'last_heartbeat_at': utcnow().isoformat(),
    }
    if tick_interval_seconds is not None:
        payload['tick_interval_seconds'] = tick_interval_seconds
    current = await get_state(session, 'engine_process')
    if not current.get('started_at'):
        payload['started_at'] = utcnow().isoformat()
    else:
        payload['started_at'] = current['started_at']
    await set_state(session, 'engine_process', payload)
    await session.commit()


async def mark_engine_stopped(
    session: AsyncSession,
    *,
    mode: str,
    pid: int,
    hostname: str | None = None,
) -> None:
    await set_state(
        session,
        'engine_process',
        {
            'mode': mode,
            'pid': pid,
            'hostname': hostname or socket.gethostname(),
            'stopped_at': utcnow().isoformat(),
            'last_heartbeat_at': utcnow().isoformat(),
        },
    )
    await session.commit()
