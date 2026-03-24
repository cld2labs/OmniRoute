from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str


class OKResponse(BaseModel):
    ok: bool = True


class IngestErrorItem(BaseModel):
    row: int
    code: str
    message: str


class IngestSummaryResponse(OKResponse):
    rows_total: int
    rows_processed: int
    rows_failed: int
    errors: list[IngestErrorItem] = Field(default_factory=list)


class CsvUploadResponse(IngestSummaryResponse):
    dataset: Literal['ops', 'reservations', 'incidents']
    filename: str


class DashboardMetrics(BaseModel):
    active_routes: int
    trips_in_progress: int
    delayed_trips: int
    cancelled_trips: int
    active_incidents: int
    reservations_today: int
    seat_utilization_pct: float


class DashboardOverviewResponse(BaseModel):
    metrics: DashboardMetrics
    status_breakdown: dict[str, int] = Field(default_factory=dict)
    recent_incidents: list[dict[str, Any]] = Field(default_factory=list)
    simulation: dict[str, Any] = Field(default_factory=dict)


class RouteRecord(BaseModel):
    route_id: UUID
    route_name: str
    origin_name: str
    destination_name: str
    base_price_cents: int
    popularity_score: int
    is_active: bool


class RouteListResponse(BaseModel):
    routes: list[RouteRecord]


class TripRecord(BaseModel):
    trip_id: UUID
    route_id: UUID
    route_name: str | None = None
    departure_time: datetime
    arrival_time: datetime | None = None
    capacity_total: int
    seats_available: int
    status: Literal['scheduled', 'boarding', 'in_transit', 'delayed', 'cancelled', 'completed']
    delay_minutes: int
    last_simulated_at: datetime | None = None


class TripListResponse(BaseModel):
    trips: list[TripRecord]


class ReservationRecord(BaseModel):
    reservation_id: UUID
    trip_id: UUID
    customer_name: str
    email: str
    phone_number: str
    seats_booked: int
    amount_paid_cents: int
    booking_channel: str
    status: Literal['confirmed', 'cancelled', 'refunded']
    created_at: datetime
    updated_at: datetime


class ReservationListResponse(BaseModel):
    reservations: list[ReservationRecord]


class IncidentRecord(BaseModel):
    incident_id: UUID
    route_id: UUID | None = None
    trip_id: UUID | None = None
    incident_type: Literal['delay', 'accident', 'weather', 'maintenance', 'mechanical_issue', 'traffic_disruption', 'staffing_issue', 'other']
    delay_minutes: int | None = None
    severity: Literal['low', 'medium', 'high', 'critical']
    source_type: Literal['manual', 'simulated', 'ingested']
    occurred_at: datetime
    summary: str
    details: str
    proof_url: str | None = None


class IncidentListResponse(BaseModel):
    incidents: list[IncidentRecord]


class IncidentCreateRequest(BaseModel):
    route_id: UUID | None = None
    trip_id: UUID | None = None
    incident_type: Literal['delay', 'accident', 'weather', 'maintenance', 'mechanical_issue', 'traffic_disruption', 'staffing_issue', 'other']
    severity: Literal['low', 'medium', 'high', 'critical'] = 'medium'
    occurred_at: datetime
    summary: str = Field(min_length=1)
    details: str = Field(min_length=1)
    proof_url: str | None = None
    delay_minutes: int | None = Field(default=None, ge=0)
    source_type: Literal['manual', 'simulated', 'ingested'] = 'manual'

    @model_validator(mode='after')
    def validate_scope(self) -> 'IncidentCreateRequest':
        if self.route_id is None and self.trip_id is None:
            raise ValueError('route_id or trip_id is required.')
        if self.incident_type == 'delay' and self.trip_id is not None and self.delay_minutes is None:
            raise ValueError('delay_minutes is required when reporting a trip delay.')
        return self


class IncidentCreateResponse(OKResponse):
    incident_id: str


class SimulationConfigPayload(BaseModel):
    booking_rate_per_tick: float = Field(default=3.0, ge=0)
    cancellation_rate_per_tick: float = Field(default=0.8, ge=0)
    incident_rate_per_tick: float = Field(default=0.4, ge=0)
    delay_sensitivity: float = Field(default=1.0, ge=0)
    tick_interval_seconds: int = Field(default=60, ge=1)


class SimulationControlRequest(BaseModel):
    action: Literal['start', 'stop']


class DataSeedRequest(BaseModel):
    days: int = Field(default=3, ge=1, le=14)
    routes: int = Field(default=6, ge=1, le=24)


class SimulationStatusResponse(BaseModel):
    engine: dict[str, Any] = Field(default_factory=dict)
    jobs: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class ChatFilters(BaseModel):
    route_name: str | None = None
    route_id: UUID | None = None
    trip_id: UUID | None = None
    reservation_id: UUID | None = None
    incident_id: UUID | None = None
    origin: str | None = None
    destination: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    status: str | None = None
    incident_type: str | None = None
    metric: str | None = None
    grouping: str | None = None
    sort_direction: Literal['asc', 'desc'] | None = None
    limit: int | None = Field(default=None, ge=1, le=200)


class AdminQueryRequest(BaseModel):
    query: str = Field(min_length=1)
    conversation_id: str | None = None
    filters: ChatFilters = Field(default_factory=ChatFilters)


class IntentFilters(BaseModel):
    route_id: UUID | None = None
    route_name: str | None = None
    trip_id: UUID | None = None
    reservation_id: UUID | None = None
    incident_id: UUID | None = None
    origin: str | None = None
    destination: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    relative_time_window: str | None = None
    status: str | None = None
    incident_type: str | None = None
    sort_by: str | None = None
    sort_direction: Literal['asc', 'desc'] | None = None
    limit: int | None = Field(default=20, ge=1, le=200)


class StructuredIntent(BaseModel):
    entity: Literal['routes', 'trips', 'reservations', 'incidents', 'unknown'] = 'unknown'
    operation: Literal['list', 'count', 'compare', 'explain', 'summarize', 'aggregate', 'unknown'] = 'unknown'
    intent_family: str | None = None
    filters: IntentFilters = Field(default_factory=IntentFilters)
    metric: str | None = None
    group_by: str | None = None
    sort_by: str | None = None
    sort_direction: Literal['asc', 'desc'] | None = None
    limit: int = Field(default=20, ge=1, le=200)
    needs_clarification: bool = False
    clarification_reason: str | None = None


class ValidatedQueryIntent(StructuredIntent):
    entity: Literal['routes', 'trips', 'reservations', 'incidents']
    operation: Literal['list', 'count', 'compare', 'explain', 'summarize', 'aggregate']
    clarification_question: str | None = None
    clarification_options: list[str] = Field(default_factory=list)
    resolution_notes: list[str] = Field(default_factory=list)


class SQLEvidence(BaseModel):
    type: Literal['sql'] = 'sql'
    records: list[dict[str, Any]] = Field(default_factory=list)


class VectorIncident(BaseModel):
    incident_id: UUID | str
    occurred_at: datetime | None = None
    summary: str
    score: float


class VectorEvidence(BaseModel):
    type: Literal['vector'] = 'vector'
    incidents: list[VectorIncident] = Field(default_factory=list)


Evidence = SQLEvidence | VectorEvidence


class QueryPlanTrace(BaseModel):
    selected_agent: Literal['operations', 'reservations', 'insights']
    query_class: Literal['operations', 'reservations', 'insights', 'mixed']
    execution_mode: Literal['sql_only', 'sql_plus_vector']
    entity: Literal['routes', 'trips', 'reservations', 'incidents'] | None = None
    operation: Literal['list', 'count', 'compare', 'explain', 'summarize', 'aggregate'] | None = None
    structured_intent: dict[str, Any] = Field(default_factory=dict)
    tool_hints: list[str] = Field(default_factory=list)
    plan_steps: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    orchestration_backend: str | None = None
    active_agents: list[str] = Field(default_factory=list)
    handoffs: list[str] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)


class AgentResponse(BaseModel):
    answer: str
    conversation_id: str | None = None
    needs_clarification: bool | None = None
    clarification_question: str | None = None
    clarification_options: list[str] | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    followups: list[str] = Field(default_factory=list)
    confidence: Literal['low', 'medium', 'high']
    query_plan: QueryPlanTrace | None = None
