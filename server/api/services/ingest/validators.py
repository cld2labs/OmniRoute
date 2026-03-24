from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .parsing import CSVParsingError, parse_stops_json


OPS_STATUS_VALUES = {'scheduled', 'delayed', 'cancelled', 'completed'}
RESERVATION_STATUS_VALUES = {'confirmed', 'cancelled', 'refunded'}
INCIDENT_TYPE_VALUES = {'delay', 'accident', 'weather', 'maintenance', 'other'}


class IngestValidationError(ValueError):
    def __init__(self, message: str, code: str = 'VALIDATION_ERROR'):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class StopInput:
    stop_order: int
    stop_name: str
    scheduled_offset_min: int


@dataclass(frozen=True)
class OpsRowInput:
    route_name: str
    origin_name: str
    destination_name: str
    base_price_cents: int
    stops: list[StopInput]
    departure_time: datetime
    arrival_time: datetime
    capacity_total: int
    seats_available: int
    status: str
    delay_minutes: int


@dataclass(frozen=True)
class ReservationRowInput:
    external_id: str
    route_name: str
    departure_time: datetime
    customer_name: str
    email: str
    phone_number: str
    seats_booked: int
    status: str
    amount_paid_cents: int


@dataclass(frozen=True)
class IncidentRowInput:
    external_id: str
    route_name: str
    departure_time: datetime | None
    incident_type: str
    occurred_at: datetime
    summary: str
    details: str
    proof_url: str | None


def _get_required_str(row: dict[str, str], field_name: str) -> str:
    value = (row.get(field_name) or '').strip()
    if not value:
        raise IngestValidationError(f'{field_name} is required.')
    return value


def _get_optional_str(row: dict[str, str], field_name: str) -> str:
    return (row.get(field_name) or '').strip()


def _parse_int(value: str, field_name: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise IngestValidationError(f'{field_name} must be an integer.') from exc


def _parse_iso8601(value: str, field_name: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith('Z'):
        normalized = f'{normalized[:-1]}+00:00'
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise IngestValidationError(f'{field_name} must be ISO 8601 timestamp.') from exc
    if parsed.tzinfo is None:
        raise IngestValidationError(f'{field_name} must include timezone offset.')
    return parsed


def validate_ops_row(row: dict[str, str]) -> OpsRowInput:
    route_name = _get_required_str(row, 'route_name')
    origin_name = _get_required_str(row, 'origin_name')
    destination_name = _get_required_str(row, 'destination_name')
    base_price_cents = _parse_int(_get_required_str(row, 'base_price_cents'), 'base_price_cents')
    departure_time = _parse_iso8601(_get_required_str(row, 'departure_time'), 'departure_time')
    arrival_time = _parse_iso8601(_get_required_str(row, 'arrival_time'), 'arrival_time')
    capacity_total = _parse_int(_get_required_str(row, 'capacity_total'), 'capacity_total')
    seats_available = _parse_int(_get_required_str(row, 'seats_available'), 'seats_available')
    delay_minutes = _parse_int(_get_required_str(row, 'delay_minutes'), 'delay_minutes')
    status = _get_required_str(row, 'status').lower()

    if status not in OPS_STATUS_VALUES:
        allowed = ', '.join(sorted(OPS_STATUS_VALUES))
        raise IngestValidationError(f'status must be one of: {allowed}.')

    if seats_available < 0 or seats_available > capacity_total:
        raise IngestValidationError('seats_available must satisfy 0 <= seats_available <= capacity_total.')

    stops_raw = _get_required_str(row, 'stops_json')
    try:
        stops_json = parse_stops_json(stops_raw)
    except CSVParsingError as exc:
        raise IngestValidationError(str(exc)) from exc

    stops: list[StopInput] = []
    stop_order_values: set[int] = set()
    for stop in stops_json:
        order_str = str(stop.get('stop_order', '')).strip()
        stop_name = str(stop.get('stop_name', '')).strip()
        offset_str = str(stop.get('scheduled_offset_min', '')).strip()

        stop_order = _parse_int(order_str, 'stop_order')
        if stop_order in stop_order_values:
            raise IngestValidationError('stop_order values must be unique within stops_json.')
        stop_order_values.add(stop_order)

        if not stop_name:
            raise IngestValidationError('stop_name is required in stops_json.')
        scheduled_offset_min = _parse_int(offset_str, 'scheduled_offset_min')
        stops.append(
            StopInput(
                stop_order=stop_order,
                stop_name=stop_name,
                scheduled_offset_min=scheduled_offset_min,
            )
        )

    return OpsRowInput(
        route_name=route_name,
        origin_name=origin_name,
        destination_name=destination_name,
        base_price_cents=base_price_cents,
        stops=stops,
        departure_time=departure_time,
        arrival_time=arrival_time,
        capacity_total=capacity_total,
        seats_available=seats_available,
        status=status,
        delay_minutes=delay_minutes,
    )


def validate_reservation_row(row: dict[str, str]) -> ReservationRowInput:
    status = _get_required_str(row, 'status').lower()
    if status not in RESERVATION_STATUS_VALUES:
        allowed = ', '.join(sorted(RESERVATION_STATUS_VALUES))
        raise IngestValidationError(f'status must be one of: {allowed}.')

    seats_booked = _parse_int(_get_required_str(row, 'seats_booked'), 'seats_booked')
    if seats_booked < 1:
        raise IngestValidationError('seats_booked must be >= 1.')

    amount_paid_cents = _parse_int(_get_required_str(row, 'amount_paid_cents'), 'amount_paid_cents')
    if amount_paid_cents < 0:
        raise IngestValidationError('amount_paid_cents must be >= 0.')

    return ReservationRowInput(
        external_id=_get_required_str(row, 'reservation_external_id'),
        route_name=_get_required_str(row, 'route_name'),
        departure_time=_parse_iso8601(_get_required_str(row, 'departure_time'), 'departure_time'),
        customer_name=_get_required_str(row, 'customer_name'),
        email=_get_required_str(row, 'email'),
        phone_number=_get_required_str(row, 'phone_number'),
        seats_booked=seats_booked,
        status=status,
        amount_paid_cents=amount_paid_cents,
    )


def validate_incident_row(row: dict[str, str]) -> IncidentRowInput:
    incident_type = _get_required_str(row, 'incident_type').lower()
    if incident_type not in INCIDENT_TYPE_VALUES:
        allowed = ', '.join(sorted(INCIDENT_TYPE_VALUES))
        raise IngestValidationError(f'incident_type must be one of: {allowed}.')

    departure_raw = _get_optional_str(row, 'departure_time')
    departure_time = _parse_iso8601(departure_raw, 'departure_time') if departure_raw else None

    proof_url = _get_optional_str(row, 'proof_url')

    return IncidentRowInput(
        external_id=_get_required_str(row, 'incident_external_id'),
        route_name=_get_required_str(row, 'route_name'),
        departure_time=departure_time,
        incident_type=incident_type,
        occurred_at=_parse_iso8601(_get_required_str(row, 'occurred_at'), 'occurred_at'),
        summary=_get_required_str(row, 'summary'),
        details=_get_optional_str(row, 'details'),
        proof_url=proof_url or None,
    )
