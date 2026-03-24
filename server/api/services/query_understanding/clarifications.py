from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ClarificationDecision:
    needs_clarification: bool = False
    reason: str | None = None
    question: str | None = None
    options: list[str] = field(default_factory=list)


def ambiguous_location_reference(value: str) -> ClarificationDecision:
    label = value.strip() or 'that location'
    return ClarificationDecision(
        needs_clarification=True,
        reason='ambiguous_route_location_reference',
        question=(
            f"I couldn't deterministically map '{label}' to a route. "
            f"Do you mean a route name, routes originating in {label}, or routes arriving in {label}?"
        ),
        options=['route_name', 'origin', 'destination'],
    )


def multiple_route_matches(options: list[str]) -> ClarificationDecision:
    return ClarificationDecision(
        needs_clarification=True,
        reason='ambiguous_route_reference',
        question='I found multiple routes matching that reference. Which route did you mean?',
        options=options[:5],
    )
