from __future__ import annotations

FULL_SCHEMA_CONTEXT = """
OmniRoute SQL schema reference.

Rules:
- Use only the tables, columns, and view fields defined below.
- `incidents.embedding` must never appear in a SQL query. That column is reserved for vector similarity search only.
- PostgreSQL is the system of record for routes, trips, reservations, incidents, and simulation state.

routes:
- id: stable route UUID primary key used in evidence and joins.
- route_name: operator-facing route label, unique across the network.
- origin_name: starting city or terminal for the route.
- destination_name: ending city or terminal for the route.
- base_price_cents: default ticket price in cents before route-level adjustments.
- is_active: whether operators currently consider the route available for scheduling.
- popularity_score: simulation-weighting score used to bias booking demand.
- created_at: when the route record was first created.
- updated_at: when the route record was last updated.

route_stops:
- id: stable stop UUID primary key.
- route_id: parent route UUID for this stop sequence entry.
- stop_order: 1-based order of the stop within the route itinerary.
- stop_name: operator-facing stop or terminal name.
- scheduled_offset_min: minutes after route departure when the vehicle is planned to reach this stop.
- created_at: when the stop entry was created.

trips:
- id: stable trip UUID primary key.
- route_id: parent route UUID for this scheduled trip instance.
- departure_time: planned trip departure timestamp.
- arrival_time: planned or observed arrival timestamp when known.
- capacity_total: total sellable seats for the trip, always greater than 0.
- seats_available: remaining bookable seats, always >= 0 and <= capacity_total.
- status: operational lifecycle state: scheduled, boarding, in_transit, delayed, cancelled, or completed.
- delay_minutes: current delay against schedule in whole minutes; 0 means on time.
- created_at: when the trip record was created.
- updated_at: when the trip record was last updated.
- last_simulated_at: last simulation tick that modified this trip.

reservations:
- id: stable reservation UUID primary key.
- trip_id: trip UUID the reservation is attached to.
- customer_name: passenger or booking contact full name.
- email: booking contact email used for matching or outreach.
- phone_number: booking contact phone number.
- seats_booked: number of seats held by the reservation, always > 0.
- amount_paid_cents: total charged amount in cents for the reservation.
- status: reservation lifecycle state: confirmed, cancelled, or refunded.
- created_at: when the reservation was first created.
- updated_at: when the reservation was last updated.
- external_id: source-system reservation identifier when the record was ingested.
- booking_channel: source of the booking such as simulated or imported workflow.

incidents:
- id: stable incident UUID primary key.
- route_id: directly affected route UUID when known.
- trip_id: directly affected trip UUID when known.
- incident_type: classified incident category such as delay, weather, maintenance, or traffic_disruption.
- delay_minutes: delay impact recorded on the incident when the incident directly delayed a trip.
- occurred_at: timestamp when the incident happened or was first observed.
- summary: short operator-facing incident headline.
- details: longer narrative used for grounded explanations.
- proof_url: supporting link or document reference when available.
- created_at: when the incident record was stored.
- external_id: source-system incident identifier when the record was ingested.
- severity: operational severity level: low, medium, high, or critical.
- source_type: incident source classification such as manual, simulated, or ingested.
- embedding: vector embedding for similarity search only. Never reference this column in SQL.

simulation_configs:
- id: simulation configuration UUID primary key.
- config_name: unique admin label for the simulation preset.
- is_active: whether this configuration is currently selected for simulation runs.
- booking_rate_per_tick: expected reservation creation volume per simulation tick.
- cancellation_rate_per_tick: expected reservation cancellation volume per simulation tick.
- incident_rate_per_tick: expected incident creation volume per simulation tick.
- delay_sensitivity: multiplier controlling how aggressively incidents translate into delays.
- tick_interval_seconds: scheduler cadence in seconds for simulation updates.
- created_at: when the configuration was created.
- updated_at: when the configuration was last changed.

simulation_jobs:
- id: simulation job UUID primary key.
- job_type: worker task category such as seed, tick, reservation_simulator, incident_simulator, or trip_updater.
- status: job execution state: queued, running, succeeded, or failed.
- started_at: timestamp when execution began.
- finished_at: timestamp when execution ended.
- triggered_by: operator or system source that kicked off the job.
- details_json: structured job metadata payload for diagnostics.
- error_message: failure detail captured when the job fails.
- created_at: when the job record was created.

simulation_state:
- state_key: named simulation state slot primary key.
- state_value_json: structured persisted state payload for that slot.
- updated_at: when the state slot was last written.

route_operational_status:
- route_id: route UUID represented by the summary row.
- route_name: operator-facing route label.
- origin_name: route origin city or terminal.
- destination_name: route destination city or terminal.
- is_active: whether the route is active.
- derived view only: this is a convenience summary over trips, not the source of truth for delay facts.
- total_trips_24h: count of trips on the route across the rolling 24-hour lookback and 24-hour lookahead window.
- scheduled_count: number of trips in scheduled state in that window.
- delayed_count: number of trips in delayed state in that window; use trips for exact delayed-route checks.
- cancelled_count: number of trips in cancelled state in that window.
- completed_count: number of trips in completed state in that window.
- avg_delay_minutes: average delay for delayed trips in that window.
- has_upcoming_delay: true when the active route has at least one delayed trip departing in the next 24 hours.
""".strip()

AGENT_SECTIONS = {
    'operations': ('routes', 'route_stops', 'trips', 'incidents', 'route_operational_status'),
    'reservations': ('trips', 'reservations', 'routes'),
    'insights': ('incidents', 'trips', 'routes', 'route_operational_status'),
}


def get_full_schema_context() -> str:
    return FULL_SCHEMA_CONTEXT


def get_agent_schema_context(agent: str) -> str:
    allowed_sections = AGENT_SECTIONS.get(agent, AGENT_SECTIONS['operations'])
    chunks = FULL_SCHEMA_CONTEXT.split('\n\n')
    selected: list[str] = []
    for chunk in chunks:
        heading = chunk.splitlines()[0].strip().rstrip(':')
        if heading in {'OmniRoute SQL schema reference.', 'Rules'} or heading in allowed_sections:
            selected.append(chunk)
    return '\n\n'.join(selected)
