from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import socket
from contextlib import suppress

from sqlalchemy import select

from ...db import SessionLocal
from ...models.schemas import DataSeedRequest, SimulationConfigPayload
from ...models.tables import Route
from .config import DataEngineSettings, get_data_engine_settings
from .scheduler import (
    get_engine_status,
    mark_engine_heartbeat,
    mark_engine_stopped,
    seed_data,
    tick_simulation,
    update_simulation_config,
)
from .state import get_state


logger = logging.getLogger('omniroute.data_engine')


def _log(event: str, **fields: object) -> None:
    payload = {'event': event, 'service': 'data-engine', **fields}
    logger.info(json.dumps(payload, default=str))


async def _apply_env_config(settings: DataEngineSettings) -> None:
    async with SessionLocal() as session:
        await update_simulation_config(
            session,
            SimulationConfigPayload(
                booking_rate_per_tick=settings.booking_rate_per_tick,
                cancellation_rate_per_tick=settings.cancellation_rate_per_tick,
                incident_rate_per_tick=settings.incident_rate_per_tick,
                delay_sensitivity=settings.delay_sensitivity,
                tick_interval_seconds=settings.tick_interval_seconds,
            ),
        )


async def _seed_if_empty(settings: DataEngineSettings) -> None:
    if not settings.seed_if_empty:
        return

    async with SessionLocal() as session:
        route_id = await session.scalar(select(Route.id).limit(1))
        if route_id is not None:
            return

    async with SessionLocal() as session:
        _log('seed_started', trigger='engine_boot', mode='run')
        stats = await seed_data(
            session,
            DataSeedRequest(days=settings.seed_days, routes=settings.seed_routes),
        )
        _log('seed_completed', trigger='engine_boot', stats=stats)


async def _run_seed(settings: DataEngineSettings) -> int:
    async with SessionLocal() as session:
        _log('seed_started', trigger='manual', mode='seed')
        stats = await seed_data(session, DataSeedRequest(days=settings.seed_days, routes=settings.seed_routes))
        _log('seed_completed', trigger='manual', stats=stats)
    return 0


async def _run_tick(settings: DataEngineSettings) -> int:
    await _apply_env_config(settings)
    async with SessionLocal() as session:
        _log('tick_started', trigger='manual', mode='tick')
        stats = await tick_simulation(
            session,
            triggered_by='docker_manual',
            enable_cascading_delays=settings.enable_cascading_delays,
        )
        _log('tick_completed', trigger='manual', stats=stats)
    return 0


async def _should_tick(settings: DataEngineSettings) -> bool:
    async with SessionLocal() as session:
        runtime = await get_state(session, settings.runtime_key, default={'desired_state': 'running'})
    return runtime.get('desired_state', 'running') == 'running'


async def _run_loop(settings: DataEngineSettings) -> int:
    hostname = socket.gethostname()
    pid = os.getpid()
    await _apply_env_config(settings)
    await _seed_if_empty(settings)

    _log(
        'engine_started',
        mode='run',
        pid=pid,
        hostname=hostname,
        tick_interval_seconds=settings.tick_interval_seconds,
    )

    try:
        while True:
            async with SessionLocal() as session:
                await mark_engine_heartbeat(
                    session,
                    mode='run',
                    pid=pid,
                    hostname=hostname,
                    tick_interval_seconds=settings.tick_interval_seconds,
                )

            if await _should_tick(settings):
                async with SessionLocal() as session:
                    _log('tick_started', trigger='run_loop', mode='run')
                    stats = await tick_simulation(
                        session,
                        triggered_by='docker_run_loop',
                        enable_cascading_delays=settings.enable_cascading_delays,
                    )
                    _log('tick_completed', trigger='run_loop', stats=stats)
            else:
                _log('tick_skipped', reason='runtime_paused')

            _log('engine_sleeping', sleep_seconds=settings.tick_interval_seconds)
            await asyncio.sleep(settings.tick_interval_seconds)
    except asyncio.CancelledError:
        raise
    finally:
        async with SessionLocal() as session:
            await mark_engine_stopped(session, mode='run', pid=pid, hostname=hostname)
        _log('engine_stopped', mode='run', pid=pid, hostname=hostname)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='OmniRoute Data Engine')
    parser.add_argument(
        'mode',
        nargs='?',
        choices=('seed', 'tick', 'run', 'status'),
        default=get_data_engine_settings().mode,
        help='Execution mode for the data engine.',
    )
    return parser


async def _run_mode(mode: str) -> int:
    settings = get_data_engine_settings()
    if mode == 'seed':
        return await _run_seed(settings)
    if mode == 'tick':
        return await _run_tick(settings)
    if mode == 'status':
        async with SessionLocal() as session:
            print(json.dumps(await get_engine_status(session), default=str, indent=2))
        return 0
    return await _run_loop(settings)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    parser = _build_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(_run_mode(args.mode))
    except KeyboardInterrupt:
        with suppress(BrokenPipeError):
            _log('engine_interrupted')
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
