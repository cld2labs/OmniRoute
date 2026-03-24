from __future__ import annotations

from dataclasses import dataclass, field

from .clarifications import ClarificationDecision, ambiguous_location_reference, multiple_route_matches


@dataclass(slots=True)
class RouteReferenceSnapshot:
    route_id: object
    route_name: str
    origin_name: str
    destination_name: str
    is_active: bool


@dataclass(slots=True)
class ReferenceResolution:
    route_id: object | None = None
    route_name: str | None = None
    origin: str | None = None
    destination: str | None = None
    notes: list[str] = field(default_factory=list)
    clarification: ClarificationDecision | None = None


def resolve_route_like_reference(candidate: str, route_refs: list[RouteReferenceSnapshot]) -> ReferenceResolution:
    value = candidate.strip()
    lowered = value.lower()

    exact_routes = [ref for ref in route_refs if ref.route_name.lower() == lowered]
    if len(exact_routes) == 1:
        ref = exact_routes[0]
        return ReferenceResolution(route_id=ref.route_id, route_name=ref.route_name)
    if len(exact_routes) > 1:
        return ReferenceResolution(clarification=multiple_route_matches([ref.route_name for ref in exact_routes]))

    prefixed = [ref for ref in route_refs if ref.route_name.lower() == f'route {lowered}']
    if len(prefixed) == 1:
        ref = prefixed[0]
        return ReferenceResolution(
            route_id=ref.route_id,
            route_name=ref.route_name,
            notes=[f"Resolved route reference '{value}' to '{ref.route_name}'."],
        )
    if len(prefixed) > 1:
        return ReferenceResolution(clarification=multiple_route_matches([ref.route_name for ref in prefixed]))

    partial_routes = [ref for ref in route_refs if lowered in ref.route_name.lower()]
    exact_origins = sorted({ref.origin_name for ref in route_refs if ref.origin_name.lower() == lowered})
    exact_destinations = sorted({ref.destination_name for ref in route_refs if ref.destination_name.lower() == lowered})

    if len(partial_routes) == 1 and not exact_origins and not exact_destinations:
        ref = partial_routes[0]
        return ReferenceResolution(
            route_id=ref.route_id,
            route_name=ref.route_name,
            notes=[f"Resolved route reference '{value}' to '{ref.route_name}'."],
        )
    if len(partial_routes) > 1:
        return ReferenceResolution(clarification=multiple_route_matches([ref.route_name for ref in partial_routes]))

    if exact_origins and exact_destinations:
        return ReferenceResolution(clarification=ambiguous_location_reference(value))
    if len(exact_origins) == 1:
        origin = exact_origins[0]
        return ReferenceResolution(origin=origin, notes=[f"Resolved '{value}' as origin '{origin}' instead of route_name."])
    if len(exact_destinations) == 1:
        destination = exact_destinations[0]
        return ReferenceResolution(destination=destination, notes=[f"Resolved '{value}' as destination '{destination}' instead of route_name."])

    partial_origins = sorted({ref.origin_name for ref in route_refs if lowered in ref.origin_name.lower()})
    partial_destinations = sorted({ref.destination_name for ref in route_refs if lowered in ref.destination_name.lower()})
    if partial_origins and partial_destinations:
        return ReferenceResolution(clarification=ambiguous_location_reference(value))
    if len(partial_origins) == 1:
        origin = partial_origins[0]
        return ReferenceResolution(origin=origin, notes=[f"Resolved '{value}' as origin '{origin}' instead of route_name."])
    if len(partial_destinations) == 1:
        destination = partial_destinations[0]
        return ReferenceResolution(destination=destination, notes=[f"Resolved '{value}' as destination '{destination}' instead of route_name."])

    return ReferenceResolution()
