from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from ...config import get_settings
from ...models.schemas import AdminQueryRequest, ChatFilters, IntentFilters, StructuredIntent
from ...observability import wrap_openai_client

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover
    AsyncOpenAI = None  # type: ignore[assignment]


ENTITY_KEYWORDS = {
    'routes': ('route', 'routes'),
    'trips': ('trip', 'trips'),
    'reservations': ('reservation', 'reservations', 'booking', 'bookings'),
    'incidents': ('incident', 'incidents', 'delay', 'delayed', 'cause', 'why', 'explain'),
}

STATUS_TOKENS = {
    'active': 'active',
    'delayed': 'delayed',
    'delay': 'delayed',
    'cancelled': 'cancelled',
    'canceled': 'cancelled',
    'completed': 'completed',
    'scheduled': 'scheduled',
    'boarding': 'boarding',
    'in transit': 'in_transit',
    'confirmed': 'confirmed',
    'refunded': 'refunded',
}

INCIDENT_TOKENS = {
    'delay': 'delay',
    'accident': 'accident',
    'weather': 'weather',
    'maintenance': 'maintenance',
    'mechanical': 'mechanical_issue',
    'traffic': 'traffic_disruption',
    'staffing': 'staffing_issue',
}

TIME_PATTERNS = {
    'today': 'today',
    'right now': 'now',
    'now': 'now',
    'this week': 'this_week',
    'last week': 'last_week',
    'this month': 'this_month',
    'recently': 'recently',
    'lately': 'recently',
}

MONTH_NAME_TO_NUMBER = {
    'january': 1,
    'february': 2,
    'march': 3,
    'april': 4,
    'may': 5,
    'june': 6,
    'july': 7,
    'august': 8,
    'september': 9,
    'october': 10,
    'november': 11,
    'december': 12,
}

TEXT_NORMALIZATIONS = (
    (r'\bdealyed\b', 'delayed'),
    (r'\bdelayd\b', 'delayed'),
    (r'\broute[s]?\s+dealyed\b', 'route delayed'),
)


@dataclass(slots=True)
class SemanticParserResult:
    intent: StructuredIntent
    source: str


class SemanticQueryParser:
    async def parse(
        self,
        payload: AdminQueryRequest,
        *,
        previous_intent: StructuredIntent | None = None,
    ) -> SemanticParserResult:
        llm_intent = await self._parse_with_llm(payload, previous_intent=previous_intent)
        if llm_intent is not None:
            return SemanticParserResult(intent=llm_intent, source='llm')
        return SemanticParserResult(intent=self._parse_heuristically(payload, previous_intent=previous_intent), source='heuristic')

    async def _parse_with_llm(
        self,
        payload: AdminQueryRequest,
        *,
        previous_intent: StructuredIntent | None,
    ) -> StructuredIntent | None:
        if os.getenv('PYTEST_CURRENT_TEST'):
            return None
        settings = get_settings()
        if AsyncOpenAI is None or not settings.llm_api_key:
            return None

        client = wrap_openai_client(
            AsyncOpenAI(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                timeout=float(settings.llm_timeout_seconds),
            ),
            settings,
        )
        prompt = (
            'You are a semantic parser for an admin transportation platform.\n'
            'Return JSON only. Do not answer the question.\n'
            'Map the user query into this canonical schema:\n'
            '{"entity":"routes|trips|reservations|incidents|unknown",'
            '"operation":"list|count|compare|explain|summarize|aggregate|unknown",'
            '"filters":{"route_id":null,"route_name":null,"trip_id":null,"reservation_id":null,'
            '"incident_id":null,"origin":null,"destination":null,"date_from":null,"date_to":null,'
            '"relative_time_window":null,"status":null,"incident_type":null,"sort_by":null,'
            '"sort_direction":null,"limit":20},"metric":null,"group_by":null,"sort_by":null,'
            '"sort_direction":null,"limit":20,"needs_clarification":false,"clarification_reason":null}\n'
            'Use filters only for explicit or strongly implied constraints. Do not invent facts.\n'
            f'Previous intent: {json.dumps(previous_intent.model_dump(mode="json"), default=str) if previous_intent else "null"}\n'
            f'User filters: {json.dumps(payload.filters.model_dump(mode="json"), default=str)}\n'
            f'User query: {payload.query}'
        )
        try:
            response = await client.responses.create(  # type: ignore[union-attr]
                model=settings.llm_model,
                temperature=settings.llm_temperature,
                input=prompt,
            )
            content = getattr(response, 'output_text', '') or ''
            parsed = json.loads(content)
            return StructuredIntent.model_validate(parsed)
        except Exception:  # pragma: no cover
            return None

    def _parse_heuristically(
        self,
        payload: AdminQueryRequest,
        *,
        previous_intent: StructuredIntent | None,
    ) -> StructuredIntent:
        query = payload.query.strip()
        text = self._normalize_text(query)
        filters = payload.filters.model_dump(exclude_none=True)

        entity = self._detect_entity(text, previous_intent=previous_intent)
        operation = self._detect_operation(text)
        parsed_filters = self._extract_filters(query, payload.filters, previous_intent=previous_intent)
        metric = self._extract_metric(text)
        group_by = self._extract_group_by(text)
        sort_by, sort_direction = self._extract_sort(text)

        if entity == 'unknown' and previous_intent is not None:
            entity = previous_intent.entity
        if operation == 'unknown' and previous_intent is not None:
            operation = previous_intent.operation

        if entity == 'incidents' and operation == 'unknown':
            operation = 'explain' if any(token in text for token in ('why', 'cause', 'explain')) else 'aggregate'
        if operation == 'unknown':
            operation = 'list'
        if operation == 'count' and self._is_yes_no_question(text):
            metric = 'boolean_check'
        intent_family = self._detect_intent_family(text, entity=entity, operation=operation, filters=parsed_filters)

        if entity == 'unknown':
            explicit_filters = bool(filters or parsed_filters)
            return StructuredIntent(
                entity='unknown',
                operation='unknown',
                intent_family=intent_family,
                filters=parsed_filters,
                metric=metric,
                group_by=group_by,
                sort_by=sort_by,
                sort_direction=sort_direction,
                limit=parsed_filters.limit or 20,
                needs_clarification=not explicit_filters,
                clarification_reason='unknown_entity',
            )

        needs_clarification = False
        clarification_reason = None
        if operation == 'list' and entity in {'routes', 'trips'} and self._is_broad_list(text, parsed_filters):
            needs_clarification = True
            clarification_reason = 'broad_unfiltered_list'

        return StructuredIntent(
            entity=entity,
            operation=operation,
            intent_family=intent_family,
            filters=parsed_filters,
            metric=metric,
            group_by=group_by,
            sort_by=sort_by,
            sort_direction=sort_direction,
            limit=parsed_filters.limit or 20,
            needs_clarification=needs_clarification,
            clarification_reason=clarification_reason,
        )

    def _normalize_text(self, text: str) -> str:
        normalized = text.lower()
        for pattern, replacement in TEXT_NORMALIZATIONS:
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
        return normalized

    def _detect_entity(self, text: str, *, previous_intent: StructuredIntent | None) -> str:
        if any(token in text for token in ('why', 'cause', 'explain', 'similar incident', 'most incidents')):
            return 'incidents'
        if 'reservation' in text or 'booking' in text or 'book' in text:
            return 'reservations'
        if 'trip' in text:
            return 'trips'
        if 'route' in text:
            return 'routes'
        if previous_intent is not None and text in {'active', 'active ones', 'delayed', 'delayed ones', 'completed', 'all', 'all of them'}:
            return previous_intent.entity
        return 'unknown'

    def _detect_operation(self, text: str) -> str:
        if any(token in text for token in ('why', 'cause', 'explain', 'reason')):
            return 'explain'
        if self._is_yes_no_question(text):
            return 'count'
        if any(token in text for token in ('how many', 'count', 'number of', 'total reservations')):
            return 'count'
        if any(token in text for token in ('compare', 'versus', 'vs', 'across')) or (
            'between' in text and not self._looks_like_date_range_phrase(text)
        ):
            return 'compare'
        if any(token in text for token in ('most', 'least', 'highest', 'lowest', 'top')):
            return 'aggregate'
        if any(token in text for token in ('summary', 'summarize')):
            return 'summarize'
        if any(token in text for token in ('show', 'list', 'which')):
            return 'list'
        return 'unknown'

    def _extract_filters(
        self,
        query: str,
        ui_filters: ChatFilters,
        *,
        previous_intent: StructuredIntent | None,
    ):
        text = self._normalize_text(query)
        data = ui_filters.model_dump(exclude_none=True)

        route_id = self._extract_uuid(r'\broute\s+([0-9a-f-]{36})\b', query) or data.get('route_id')
        trip_id = self._extract_uuid(r'\btrip\s+([0-9a-f-]{36})\b', query) or data.get('trip_id')
        reservation_id = self._extract_uuid(r'\breservation\s+([0-9a-f-]{36})\b', query) or data.get('reservation_id')
        incident_id = self._extract_uuid(r'\bincident\s+([0-9a-f-]{36})\b', query) or data.get('incident_id')

        route_name = data.get('route_name') or self._extract_route_name(query)
        origin = data.get('origin') or self._extract_city(query, prefix='from')
        destination = data.get('destination') or self._extract_city(query, prefix='to')

        if previous_intent is not None and self._looks_like_refinement_only(text):
            route_name = route_name or previous_intent.filters.route_name
            origin = origin or previous_intent.filters.origin
            destination = destination or previous_intent.filters.destination
            route_id = route_id or previous_intent.filters.route_id

        explicit_date_from, explicit_date_to = self._extract_explicit_date_range(query)
        relative_time_window = next((value for token, value in TIME_PATTERNS.items() if token in text), None)
        status = data.get('status') or next((value for token, value in STATUS_TOKENS.items() if token in text), None)
        incident_type = data.get('incident_type') or next((value for token, value in INCIDENT_TOKENS.items() if token in text), None)
        limit = data.get('limit') or self._extract_limit(text) or 20
        sort_by, sort_direction = self._extract_sort(text)

        return IntentFilters(
            route_id=route_id,
            route_name=route_name,
            trip_id=trip_id,
            reservation_id=reservation_id,
            incident_id=incident_id,
            origin=origin,
            destination=destination,
            date_from=data.get('date_from') or explicit_date_from,
            date_to=data.get('date_to') or explicit_date_to,
            relative_time_window=None if explicit_date_from or explicit_date_to else relative_time_window,
            status=status,
            incident_type=incident_type,
            sort_by=sort_by,
            sort_direction=sort_direction,
            limit=limit,
        )

    def _extract_metric(self, text: str) -> str | None:
        if 'reservation activity' in text or 'reservations' in text:
            return 'reservations'
        if 'incident' in text:
            return 'incidents'
        if 'delay' in text:
            return 'delays'
        return None

    def _detect_intent_family(self, text: str, *, entity: str, operation: str, filters: IntentFilters) -> str | None:
        if 'route' in text and 'delay' in text:
            if operation == 'explain':
                return 'route_delay_explanation'
            if self._is_yes_no_question(text):
                return 'route_delay_check'
        if entity == 'reservations' and filters.date_from is not None and filters.date_to is not None:
            if operation == 'count':
                return 'reservation_count_in_range'
            if operation == 'list':
                return 'reservation_list_in_range'
        if entity == 'routes' and operation == 'list' and filters.status in {'active', 'delayed', 'completed'}:
            return 'route_status_list'
        return None

    def _extract_group_by(self, text: str) -> str | None:
        if 'across active routes' in text or 'across routes' in text or 'by route' in text:
            return 'route'
        if 'by type' in text:
            return 'incident_type'
        if 'by day' in text or 'daily' in text:
            return 'day'
        return None

    def _extract_sort(self, text: str) -> tuple[str | None, str | None]:
        if any(token in text for token in ('most', 'highest', 'top')):
            return 'metric', 'desc'
        if any(token in text for token in ('least', 'lowest', 'fewest')):
            return 'metric', 'asc'
        return None, None

    def _extract_route_name(self, query: str) -> str | None:
        match = re.search(r'\broute\s+([a-z0-9][a-z0-9\s-]{0,40})\b', query, re.IGNORECASE)
        if match is None:
            return None
        value = re.split(
            r'\b(for|from|to|with|where|when|who|that|which|today|this week|this month|right now|now|recently|lately|is|are|was|were|and|did|reason|behind|it|delayed|active|completed|scheduled|cancelled|canceled)\b',
            match.group(1),
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        return value.strip(' ?,.') or None

    def _extract_city(self, query: str, *, prefix: str) -> str | None:
        patterns = {
            'from': r'\bfrom\s+([a-z][a-z\s-]{0,60}?)(?=\s+\b(where|with|for|on|during|today|this week|this month|recently|lately)\b|[?.!,]|$)',
            'to': r'\bto\s+([a-z][a-z\s-]{0,60}?)(?=\s+\b(where|with|for|on|during|today|this week|this month|recently|lately)\b|[?.!,]|$)',
        }
        match = re.search(patterns[prefix], query, re.IGNORECASE)
        if not match:
            return None
        value = re.sub(r'\s+', ' ', match.group(1)).strip(' -')
        if not value:
            return None
        return ' '.join(part.capitalize() for part in value.split())

    def _extract_uuid(self, pattern: str, query: str) -> UUID | None:
        match = re.search(pattern, query, re.IGNORECASE)
        if match is None:
            return None
        try:
            return UUID(match.group(1))
        except ValueError:
            return None

    def _extract_limit(self, text: str) -> int | None:
        match = re.search(r'\b(?:top|first|show(?:\s+me)?|list(?:\s+me)?)\s+(\d{1,3})\b', text)
        return int(match.group(1)) if match else None

    def _extract_explicit_date_range(self, query: str) -> tuple[date | None, date | None]:
        text = query.lower()
        day_month_pattern, month_day_pattern = self._date_patterns()
        range_patterns = [
            rf'\bbetween\s+(?P<first>{day_month_pattern}|{month_day_pattern})\s+and\s+(?P<second>{day_month_pattern}|{month_day_pattern})\b',
            rf'\bfrom\s+(?P<first>{day_month_pattern}|{month_day_pattern})\s+to\s+(?P<second>{day_month_pattern}|{month_day_pattern})\b',
        ]
        for pattern in range_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            first = self._parse_explicit_date(match.group('first'))
            second = self._parse_explicit_date(match.group('second'))
            if first is None or second is None:
                return None, None
            return (first, second) if first <= second else (second, first)

        for pattern in (day_month_pattern, month_day_pattern):
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            resolved = self._parse_explicit_date(match.group(0))
            if resolved is None:
                return None, None
            return resolved, resolved
        return None, None

    def _date_patterns(self) -> tuple[str, str]:
        month_pattern = '|'.join(MONTH_NAME_TO_NUMBER)
        return (
            rf'\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{month_pattern})(?:\s+\d{{4}})?',
            rf'(?:{month_pattern})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,\s*|\s+)?(?:\d{{4}})?',
        )

    def _parse_explicit_date(self, value: str) -> date | None:
        text = value.lower().strip()
        month_pattern = '|'.join(MONTH_NAME_TO_NUMBER)
        patterns = [
            rf'^(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month>{month_pattern})(?:\s+(?P<year>\d{{4}}))?$',
            rf'^(?P<month>{month_pattern})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:,\s*|\s+)?(?P<year>\d{{4}})?$',
        ]
        today = date.today()
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            day = int(match.group('day'))
            month_name = match.group('month').lower()
            year = int(match.group('year')) if match.groupdict().get('year') else today.year
            month = MONTH_NAME_TO_NUMBER[month_name]
            try:
                return date(year, month, day)
            except ValueError:
                return None
        return None

    def _is_broad_list(self, text: str, filters: Any) -> bool:
        meaningful = any(
            getattr(filters, field) is not None
            for field in ('route_id', 'route_name', 'trip_id', 'reservation_id', 'incident_id', 'origin', 'destination', 'status', 'incident_type')
        )
        return not meaningful and any(token in text for token in ('show', 'list', 'all', 'which'))

    def _looks_like_refinement_only(self, text: str) -> bool:
        return text in {'active', 'active ones', 'delayed', 'delayed ones', 'completed', 'completed ones', 'all', 'all of them'}

    def _is_yes_no_question(self, text: str) -> bool:
        normalized = text.strip()
        return bool(
            re.match(r'^(is|are|does|do|has|have|did|was|were)\b', normalized)
            or normalized.startswith('do we have')
            or normalized.startswith('have there been')
        )

    def _looks_like_date_range_phrase(self, text: str) -> bool:
        return bool(
            re.search(r'\bbetween\s+\d{1,2}(?:st|nd|rd|th)?\s+[a-z]+\s+and\s+\d{1,2}(?:st|nd|rd|th)?\s+[a-z]+\b', text)
            or re.search(r'\bfrom\s+\d{1,2}(?:st|nd|rd|th)?\s+[a-z]+\s+to\s+\d{1,2}(?:st|nd|rd|th)?\s+[a-z]+\b', text)
            or re.search(r'\bbetween\s+[a-z]+\s+\d{1,2}(?:st|nd|rd|th)?\s+and\s+[a-z]+\s+\d{1,2}(?:st|nd|rd|th)?\b', text)
            or re.search(r'\bfrom\s+[a-z]+\s+\d{1,2}(?:st|nd|rd|th)?\s+to\s+[a-z]+\s+\d{1,2}(?:st|nd|rd|th)?\b', text)
        )
