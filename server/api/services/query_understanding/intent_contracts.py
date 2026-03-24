from __future__ import annotations

# Canonical route delay intents should stay trip-derived. Route summaries are convenience views.
CANONICAL_SQL = {
    'routes_currently_delayed': """
        SELECT r.id AS route_id, r.route_name, r.origin_name, r.destination_name,
               COUNT(t.id) AS delayed_trip_count,
               MIN(t.departure_time) AS next_delayed_departure
        FROM routes r
        JOIN trips t ON t.route_id = r.id
        WHERE r.is_active = true
          AND t.status = 'delayed'
        GROUP BY r.id, r.route_name, r.origin_name, r.destination_name
        ORDER BY next_delayed_departure ASC
        LIMIT 50
    """,
    'routes_delayed_count': """
        SELECT COUNT(DISTINCT r.id) AS delayed_route_count
        FROM routes r
        JOIN trips t ON t.route_id = r.id
        WHERE r.is_active = true
          AND t.status = 'delayed'
    """,
    'route_delayed_trips': """
        SELECT t.id AS trip_id, t.departure_time, t.arrival_time,
               t.delay_minutes, t.seats_available, t.capacity_total, t.status
        FROM trips t
        JOIN routes r ON r.id = t.route_id
        WHERE r.route_name = %(route_name)s
          AND r.is_active = true
          AND t.status = 'delayed'
        ORDER BY t.departure_time ASC
        LIMIT 20
    """,
    'why_route_delayed': """
        SELECT i.id AS incident_id, i.incident_type, i.occurred_at,
               i.summary, i.details,
               t.id AS trip_id, t.departure_time, t.delay_minutes
        FROM incidents i
        JOIN routes r ON r.id = i.route_id
        LEFT JOIN trips t ON t.id = i.trip_id
        WHERE r.route_name = %(route_name)s
          AND i.occurred_at >= NOW() - INTERVAL '48 hours'
        ORDER BY i.occurred_at DESC
        LIMIT 10
    """,
    'why_trip_delayed': """
        SELECT i.id AS incident_id, i.incident_type, i.occurred_at,
               i.summary, i.details
        FROM incidents i
        WHERE i.trip_id = %(trip_id)s
          AND i.occurred_at >= NOW() - INTERVAL '48 hours'
        ORDER BY i.occurred_at DESC
        LIMIT 10
    """,
    'route_operational_summary': """
        SELECT r.id AS route_id, r.route_name, r.origin_name, r.destination_name,
               COUNT(t.id) AS total_trips,
               COUNT(t.id) FILTER (WHERE t.status = 'scheduled')  AS scheduled,
               COUNT(t.id) FILTER (WHERE t.status = 'delayed')    AS delayed,
               COUNT(t.id) FILTER (WHERE t.status = 'cancelled')  AS cancelled,
               COUNT(t.id) FILTER (WHERE t.status = 'completed')  AS completed,
               ROUND(AVG(t.delay_minutes) FILTER (WHERE t.status = 'delayed'), 1) AS avg_delay_minutes
        FROM routes r
        LEFT JOIN trips t ON t.route_id = r.id
          AND t.departure_time >= NOW() - INTERVAL '24 hours'
          AND t.departure_time <= NOW() + INTERVAL '24 hours'
        WHERE r.is_active = true
        GROUP BY r.id, r.route_name, r.origin_name, r.destination_name
        ORDER BY delayed DESC, route_name ASC
        LIMIT 100
    """,
}

INTENT_TO_CANONICAL = {
    'routes_delayed': 'routes_currently_delayed',
    'routes_delayed_count': 'routes_delayed_count',
    'route_delayed_trips': 'route_delayed_trips',
    'why_route_delayed': 'why_route_delayed',
    'why_trip_delayed': 'why_trip_delayed',
    'route_operational_summary': 'route_operational_summary',
}
