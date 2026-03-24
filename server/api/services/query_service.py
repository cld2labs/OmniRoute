from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents import CrewAIQueryOrchestrator
from ..models.schemas import (
    AdminQueryRequest,
    AgentResponse,
    QueryPlanTrace,
    SQLEvidence,
    StructuredIntent,
    ValidatedQueryIntent,
    VectorEvidence,
    VectorIncident,
)
from ..models.tables import Reservation, Route, Trip
from .conversation_state import cleanup_stale_sessions, clear_state, resolve_state, set_state
from .planner import QueryPlanner
from .query_understanding import (
    GroundedAnswerSynthesizer,
    QueryUnderstandingExecutor,
    QueryIntentValidator,
    SemanticQueryParser,
    build_internal_plan,
)
from .query_understanding.chained_queries import ChainedQuerySpec, build_chained_answer, detect_chained_query
from .query_understanding.synthesizer import synthesize_response


class AdminQueryService:
    def __init__(self) -> None:
        self._planner = QueryPlanner()
        self._orchestrator = CrewAIQueryOrchestrator(planner=self._planner)
        self._parser = SemanticQueryParser()
        self._validator = QueryIntentValidator()
        self._executor = QueryUnderstandingExecutor()
        self._answer_synthesizer = GroundedAnswerSynthesizer(llm_client=self._executor.llm_client)

    async def run(self, payload: AdminQueryRequest, db_session: AsyncSession) -> AgentResponse:
        cleanup_stale_sessions()
        self._answer_synthesizer = GroundedAnswerSynthesizer(llm_client=self._executor.llm_client)
        conversation_id = payload.conversation_id or str(uuid4())
        state = resolve_state(conversation_id)
        previous_intent = self._intent_from_state(state)

        booking_response = await self._continue_booking_flow(payload, db_session, conversation_id, state)
        if booking_response is not None:
            return booking_response

        initial_decision = self._planner.decide(payload, payload.filters.model_dump(exclude_none=True))
        parsed = await self._parser.parse(payload, previous_intent=previous_intent)
        intent = await self._validator.validate(parsed.intent, db_session=db_session, previous_intent=previous_intent)

        booking_response = await self._start_booking_flow_if_applicable(payload, intent, db_session, conversation_id)
        if booking_response is not None:
            return booking_response

        chained_query = detect_chained_query(payload.query, intent)
        orchestration = await self._orchestrator.orchestrate(
            payload=payload,
            intent=intent,
            initial_decision=initial_decision,
            chain_spec=chained_query,
        )
        planner_decision = orchestration.planner_decision

        print(
            json.dumps(
                {
                    'event': 'query_service_intent',
                    'query': payload.query,
                    'selected_agent': planner_decision.selected_agent,
                    'entity': intent.entity,
                    'operation': intent.operation,
                    'intent_family': intent.intent_family,
                    'needs_clarification': intent.needs_clarification,
                }
            ),
            file=sys.stdout,
            flush=True,
        )

        if intent.needs_clarification and chained_query is None:
            set_state(
                conversation_id,
                {
                    'pending_clarification': True,
                    'intent': intent.model_dump(mode='json'),
                    'last_query': payload.query,
                },
            )
            return AgentResponse(
                answer=intent.clarification_question or 'I need more information to answer that request.',
                conversation_id=conversation_id,
                needs_clarification=True,
                clarification_question=intent.clarification_question,
                clarification_options=intent.clarification_options,
                confidence='medium',
                query_plan=self._build_trace(planner_decision, intent, []),
            )

        if chained_query is not None:
            crew_execution = await self._orchestrator.execute_chained(
                payload=payload,
                chain_spec=chained_query,
                db_session=db_session,
                llm_client=self._executor.llm_client,
            )
            if crew_execution is not None:
                return self._build_chained_response(
                    conversation_id=conversation_id,
                    intent=intent,
                    chain_spec=chained_query,
                    orchestration=orchestration,
                    planner_decision=planner_decision,
                    payload=payload,
                    root_rows=crew_execution.root_rows,
                    delegated_results=crew_execution.delegated_results,
                    sql_records=crew_execution.sql_records,
                    vector_records=crew_execution.vector_records,
                    tool_calls=crew_execution.tool_calls,
                    assumptions=orchestration.assumptions + crew_execution.assumptions,
                    sql_queries=crew_execution.sql_queries,
                    plan_steps=crew_execution.plan_steps,
                    needs_clarification=crew_execution.needs_clarification,
                    clarification_question=crew_execution.clarification_question,
                )
            return await self._run_chained_query(
                payload=payload,
                conversation_id=conversation_id,
                intent=intent,
                chain_spec=chained_query,
                orchestration=orchestration,
                planner_decision=planner_decision,
                db_session=db_session,
            )

        plan = orchestration.plan
        print(
            json.dumps(
                {
                    'event': 'query_service_execute',
                    'query': payload.query,
                    'selected_agent': planner_decision.selected_agent,
                    'orchestration_backend': orchestration.backend,
                    'active_agents': orchestration.active_agents,
                    'plan_steps': plan.plan_steps,
                }
            ),
            file=sys.stdout,
            flush=True,
        )
        execution = await self._executor.execute(
            query_text=payload.query,
            intent=intent,
            plan=plan,
            db_session=db_session,
        )
        if execution.needs_clarification:
            question = execution.clarification_question or 'I need more information to answer that request.'
            set_state(
                conversation_id,
                {
                    'pending_clarification': True,
                    'intent': intent.model_dump(mode='json'),
                    'last_query': payload.query,
                },
            )
            return AgentResponse(
                answer=question,
                conversation_id=conversation_id,
                needs_clarification=True,
                clarification_question=question,
                evidence=[],
                followups=[],
                confidence='low',
                query_plan=self._build_trace(
                    planner_decision,
                    intent,
                    plan.plan_steps,
                    orchestration_backend=orchestration.backend,
                    active_agents=orchestration.active_agents,
                    handoffs=orchestration.handoffs,
                    tool_calls=execution.tool_calls,
                    assumptions=orchestration.assumptions + execution.assumptions,
                ),
            )
        deterministic_answer, confidence = synthesize_response(
            intent=intent,
            plan=plan,
            block_results=execution.block_results,
            vector_records=execution.vector_records,
        )
        answer = await self._answer_synthesizer.synthesize(
            query_text=payload.query,
            intent=intent,
            plan=plan,
            deterministic_answer=deterministic_answer,
            block_results=execution.block_results,
            vector_records=execution.vector_records,
        )

        evidence: list[Any] = []
        if execution.sql_records:
            evidence.append(SQLEvidence(records=execution.sql_records))
        if execution.vector_records:
            evidence.append(VectorEvidence(incidents=[VectorIncident(**record) for record in execution.vector_records]))

        set_state(
            conversation_id,
            {
                'pending_clarification': False,
                'intent': intent.model_dump(mode='json'),
                'last_query': payload.query,
            },
        )
        print(
            json.dumps(
                {
                    'event': 'query_service_sql_queries',
                    'query': payload.query,
                    'sql_queries': execution.sql_queries,
                }
            ),
            file=sys.stdout,
            flush=True,
        )
        return AgentResponse(
            answer=answer,
            conversation_id=conversation_id,
            evidence=evidence,
            followups=self._followups(intent),
            confidence=confidence,
            query_plan=self._build_trace(
                planner_decision,
                intent,
                plan.plan_steps,
                orchestration_backend=orchestration.backend,
                active_agents=orchestration.active_agents,
                handoffs=orchestration.handoffs,
                tool_calls=execution.tool_calls,
                assumptions=orchestration.assumptions
                + execution.assumptions
                + [f"SQL used: {sql}" for sql in execution.sql_queries],
            ),
        )

    async def _run_chained_query(
        self,
        *,
        payload: AdminQueryRequest,
        conversation_id: str,
        intent: ValidatedQueryIntent,
        chain_spec: ChainedQuerySpec,
        orchestration,
        planner_decision,
        db_session: AsyncSession,
    ) -> AgentResponse:
        root_execution = await self._executor.execute(
            query_text=chain_spec.root_query_text(),
            intent=chain_spec.root_intent,
            plan=chain_spec.root_plan,
            db_session=db_session,
        )
        if root_execution.needs_clarification:
            question = root_execution.clarification_question or 'I need more information to answer that request.'
            return AgentResponse(
                answer=question,
                conversation_id=conversation_id,
                needs_clarification=True,
                clarification_question=question,
                evidence=[],
                followups=[],
                confidence='low',
                query_plan=self._build_trace(
                    planner_decision,
                    intent,
                    chain_spec.root_plan.plan_steps,
                    orchestration_backend=orchestration.backend,
                    active_agents=orchestration.active_agents,
                    handoffs=orchestration.handoffs,
                    tool_calls=root_execution.tool_calls,
                    assumptions=orchestration.assumptions + root_execution.assumptions,
                ),
            )

        root_rows = root_execution.block_results.get('generated_sql') or []
        delegated_results: list[dict[str, Any]] = []
        aggregated_sql_records = list(root_execution.sql_records)
        aggregated_vector_records = list(root_execution.vector_records)
        aggregated_tool_calls = list(root_execution.tool_calls)
        aggregated_assumptions = orchestration.assumptions + root_execution.assumptions
        aggregated_sql_queries = list(root_execution.sql_queries)
        chained_plan_steps = list(chain_spec.root_plan.plan_steps)

        delegated_rows = root_rows[:3] if chain_spec.key == 'delayed_routes_with_causes' else [root_rows[0] if root_rows else {}]
        for row in delegated_rows:
            delegated_intent = chain_spec.delegated_intent_for_row(row)
            if delegated_intent is None:
                continue
            delegated_plan = self._executor_plan_for(chain_spec.delegated_agent, delegated_intent)
            delegated_query = chain_spec.delegated_query_for_row(row)
            delegated_execution = await self._executor.execute(
                query_text=delegated_query,
                intent=delegated_intent,
                plan=delegated_plan,
                db_session=db_session,
            )
            delegated_results.append(
                {
                    'route_row': row,
                    'sql_rows': delegated_execution.block_results.get('generated_sql') or [],
                    'vector_rows': delegated_execution.vector_records,
                }
            )
            aggregated_sql_records.extend(delegated_execution.sql_records)
            aggregated_vector_records.extend(delegated_execution.vector_records)
            aggregated_tool_calls.extend(delegated_execution.tool_calls)
            aggregated_assumptions.extend(delegated_execution.assumptions)
            aggregated_sql_queries.extend(delegated_execution.sql_queries)
            chained_plan_steps.append(f'delegate:{chain_spec.delegated_agent}')

        return self._build_chained_response(
            conversation_id=conversation_id,
            intent=intent,
            chain_spec=chain_spec,
            orchestration=orchestration,
            planner_decision=planner_decision,
            payload=payload,
            root_rows=root_rows,
            delegated_results=delegated_results,
            sql_records=aggregated_sql_records,
            vector_records=aggregated_vector_records,
            tool_calls=aggregated_tool_calls,
            assumptions=aggregated_assumptions,
            sql_queries=aggregated_sql_queries,
            plan_steps=chained_plan_steps,
            needs_clarification=False,
            clarification_question=None,
        )

    def _build_chained_response(
        self,
        *,
        conversation_id: str,
        intent: ValidatedQueryIntent,
        chain_spec: ChainedQuerySpec,
        orchestration,
        planner_decision,
        payload: AdminQueryRequest,
        root_rows: list[dict[str, Any]],
        delegated_results: list[dict[str, Any]],
        sql_records: list[dict[str, Any]],
        vector_records: list[dict[str, Any]],
        tool_calls: list[str],
        assumptions: list[str],
        sql_queries: list[str],
        plan_steps: list[str],
        needs_clarification: bool,
        clarification_question: str | None,
    ) -> AgentResponse:
        if needs_clarification:
            question = clarification_question or 'I need more information to answer that request.'
            set_state(
                conversation_id,
                {
                    'pending_clarification': True,
                    'intent': intent.model_dump(mode='json'),
                    'last_query': payload.query,
                },
            )
            return AgentResponse(
                answer=question,
                conversation_id=conversation_id,
                needs_clarification=True,
                clarification_question=question,
                evidence=[],
                followups=[],
                confidence='low',
                query_plan=self._build_trace(
                    planner_decision,
                    intent,
                    plan_steps,
                    orchestration_backend=orchestration.backend,
                    active_agents=orchestration.active_agents,
                    handoffs=orchestration.handoffs,
                    tool_calls=tool_calls,
                    assumptions=assumptions,
                ),
            )

        answer, confidence = build_chained_answer(
            chain_spec=chain_spec,
            root_rows=root_rows,
            delegated_results=delegated_results,
        )
        evidence: list[Any] = []
        if sql_records:
            evidence.append(SQLEvidence(records=sql_records))
        if vector_records:
            evidence.append(VectorEvidence(incidents=[VectorIncident(**record) for record in vector_records]))
        set_state(
            conversation_id,
            {
                'pending_clarification': False,
                'intent': intent.model_dump(mode='json'),
                'last_query': payload.query,
            },
        )
        return AgentResponse(
            answer=answer,
            conversation_id=conversation_id,
            evidence=evidence,
            followups=self._followups(intent),
            confidence=confidence,
            query_plan=self._build_trace(
                planner_decision,
                intent,
                plan_steps,
                orchestration_backend=orchestration.backend,
                active_agents=orchestration.active_agents,
                handoffs=orchestration.handoffs,
                tool_calls=tool_calls,
                assumptions=assumptions + [f"SQL used: {sql}" for sql in sql_queries],
            ),
        )

    @staticmethod
    def _executor_plan_for(selected_agent: str, delegated_intent: ValidatedQueryIntent):
        return build_internal_plan(selected_agent, delegated_intent)

    def _intent_from_state(self, state: dict[str, Any] | None) -> ValidatedQueryIntent | None:
        if not state or not state.get('intent'):
            return None
        try:
            return ValidatedQueryIntent.model_validate(state['intent'])
        except Exception:
            return None

    async def _continue_booking_flow(
        self,
        payload: AdminQueryRequest,
        db_session: AsyncSession,
        conversation_id: str,
        state: dict[str, Any] | None,
    ) -> AgentResponse | None:
        booking = (state or {}).get('booking_flow')
        if not isinstance(booking, dict):
            return None

        stage = booking.get('stage')
        if stage == 'awaiting_trip_selection':
            return await self._handle_booking_trip_selection(payload.query, db_session, conversation_id, state, booking)
        if stage == 'awaiting_contact_details':
            return self._handle_booking_contact_details(payload.query, conversation_id, state, booking)
        if stage == 'awaiting_confirmation':
            return await self._handle_booking_confirmation(payload.query, db_session, conversation_id, state, booking)
        return None

    async def _start_booking_flow_if_applicable(
        self,
        payload: AdminQueryRequest,
        intent: ValidatedQueryIntent,
        db_session: AsyncSession,
        conversation_id: str,
    ) -> AgentResponse | None:
        if not self._looks_like_booking_request(payload.query, intent):
            return None

        seats_requested = self._extract_requested_seats(payload.query)
        if seats_requested is None:
            return AgentResponse(
                answer='How many seats do you want to book?',
                conversation_id=conversation_id,
                needs_clarification=True,
                clarification_question='How many seats do you want to book?',
                confidence='medium',
            )

        if intent.filters.route_id is None or intent.filters.route_name is None:
            return AgentResponse(
                answer='Which route do you want to book?',
                conversation_id=conversation_id,
                needs_clarification=True,
                clarification_question='Which route do you want to book?',
                confidence='medium',
            )

        available_trips = await self._fetch_bookable_trips(db_session, intent.filters.route_id, seats_requested)
        if not available_trips:
            clear_state(conversation_id)
            return AgentResponse(
                answer=f'I did not find any active upcoming trips on {intent.filters.route_name} with at least {seats_requested} available seats.',
                conversation_id=conversation_id,
                confidence='medium',
            )

        booking_flow = {
            'stage': 'awaiting_trip_selection',
            'route_id': str(intent.filters.route_id),
            'route_name': intent.filters.route_name,
            'seats_requested': seats_requested,
            'trip_options': [str(row['trip_id']) for row in available_trips],
        }
        set_state(
            conversation_id,
            {
                'pending_clarification': True,
                'booking_flow': booking_flow,
                'last_query': payload.query,
            },
        )
        count = len(available_trips)
        trip_lines = [
            f"- trip {row['trip_id']} departing {self._format_booking_time(row.get('departure_time'))} with {row['seats_available']} seats available"
            for row in available_trips[:5]
        ]
        answer = (
            f'I found {count} available trips for {intent.filters.route_name} with {seats_requested} requested seats.\n'
            f"{chr(10).join(trip_lines)}\n"
            'Reply with the trip id you want to book.'
        )
        return AgentResponse(
            answer=answer,
            conversation_id=conversation_id,
            needs_clarification=True,
            clarification_question='Which trip id do you want to book?',
            evidence=[SQLEvidence(records=available_trips)],
            confidence='high',
        )

    async def _handle_booking_trip_selection(
        self,
        query: str,
        db_session: AsyncSession,
        conversation_id: str,
        state: dict[str, Any],
        booking: dict[str, Any],
    ) -> AgentResponse:
        trip_id = self._extract_uuid(query)
        if trip_id is None or trip_id not in set(booking.get('trip_options', [])):
            return AgentResponse(
                answer='Reply with one of the listed trip ids so I can continue the booking.',
                conversation_id=conversation_id,
                needs_clarification=True,
                clarification_question='Which trip id do you want to book?',
                confidence='medium',
            )

        trip = await self._fetch_trip_for_booking(db_session, UUID(trip_id), int(booking['seats_requested']))
        if trip is None:
            return AgentResponse(
                answer='That trip is no longer available with the requested number of seats. Pick another listed trip id.',
                conversation_id=conversation_id,
                needs_clarification=True,
                clarification_question='Which trip id do you want to book instead?',
                confidence='medium',
            )

        booking.update(
            {
                'stage': 'awaiting_contact_details',
                'selected_trip_id': trip_id,
                'selected_trip_departure': self._format_booking_time(trip.get('departure_time')),
            }
        )
        state['booking_flow'] = booking
        state['pending_clarification'] = True
        state['updated_at'] = datetime.now(timezone.utc)
        set_state(conversation_id, state)
        return AgentResponse(
            answer=(
                f"Selected trip {trip_id} departing {booking['selected_trip_departure']}. "
                'Send the passenger details as: first name, last name, email, phone number.'
            ),
            conversation_id=conversation_id,
            needs_clarification=True,
            clarification_question='Provide first name, last name, email, and phone number.',
            confidence='high',
        )

    def _handle_booking_contact_details(
        self,
        query: str,
        conversation_id: str,
        state: dict[str, Any],
        booking: dict[str, Any],
    ) -> AgentResponse:
        details = dict(booking.get('customer', {}))
        details.update(self._extract_contact_details(query))
        missing = [field for field in ('first_name', 'last_name', 'email', 'phone_number') if not details.get(field)]
        if missing:
            booking['customer'] = details
            state['booking_flow'] = booking
            set_state(conversation_id, state)
            labels = ', '.join(field.replace('_', ' ') for field in missing)
            return AgentResponse(
                answer=f'I still need: {labels}.',
                conversation_id=conversation_id,
                needs_clarification=True,
                clarification_question=f'Please provide: {labels}.',
                confidence='medium',
            )

        booking['customer'] = details
        booking['stage'] = 'awaiting_confirmation'
        state['booking_flow'] = booking
        state['pending_clarification'] = True
        set_state(conversation_id, state)
        return AgentResponse(
            answer=(
                f"Please confirm this reservation for {details['first_name']} {details['last_name']} "
                f"using {details['email']} and {details['phone_number']}. Reply 'confirm' or 'okay' to create it."
            ),
            conversation_id=conversation_id,
            needs_clarification=True,
            clarification_question='Reply confirm to create the reservation, or cancel to stop.',
            confidence='high',
        )

    async def _handle_booking_confirmation(
        self,
        query: str,
        db_session: AsyncSession,
        conversation_id: str,
        state: dict[str, Any],
        booking: dict[str, Any],
    ) -> AgentResponse:
        lowered = query.strip().lower()
        if lowered in {'cancel', 'stop', 'never mind', 'nevermind'}:
            clear_state(conversation_id)
            return AgentResponse(
                answer='Booking cancelled.',
                conversation_id=conversation_id,
                confidence='medium',
            )
        if lowered not in {'confirm', 'confirmed', 'ok', 'okay', 'yes'}:
            return AgentResponse(
                answer="Reply 'confirm' or 'okay' to create the reservation, or 'cancel' to stop.",
                conversation_id=conversation_id,
                needs_clarification=True,
                clarification_question="Reply 'confirm' or 'cancel'.",
                confidence='medium',
            )

        record = await self._create_chat_reservation(db_session, booking)
        clear_state(conversation_id)
        return AgentResponse(
            answer=(
                f"Reservation created for {record['customer_name']} on trip {record['trip_id']}. "
                f"Reservation id is {record['reservation_id']}."
            ),
            conversation_id=conversation_id,
            evidence=[SQLEvidence(records=[record])],
            confidence='high',
        )

    async def _fetch_bookable_trips(self, db_session: AsyncSession, route_id: UUID, seats_requested: int) -> list[dict[str, Any]]:
        rows = (
            await db_session.execute(
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
                )
                .join(Route, Route.id == Trip.route_id)
                .where(
                    Trip.route_id == route_id,
                    Route.is_active.is_(True),
                    Trip.status.in_(('scheduled', 'boarding', 'delayed')),
                    Trip.departure_time >= datetime.now(timezone.utc),
                    Trip.seats_available >= seats_requested,
                )
                .order_by(Trip.departure_time.asc())
                .limit(10)
            )
        ).mappings().all()
        return [dict(row) for row in rows]

    async def _fetch_trip_for_booking(self, db_session: AsyncSession, trip_id: UUID, seats_requested: int) -> dict[str, Any] | None:
        row = (
            await db_session.execute(
                select(
                    Trip.id.label('trip_id'),
                    Trip.route_id,
                    Route.route_name,
                    Route.base_price_cents,
                    Trip.departure_time,
                    Trip.seats_available,
                    Trip.status,
                )
                .join(Route, Route.id == Trip.route_id)
                .where(
                    Trip.id == trip_id,
                    Route.is_active.is_(True),
                    Trip.status.in_(('scheduled', 'boarding', 'delayed')),
                    Trip.departure_time >= datetime.now(timezone.utc),
                    Trip.seats_available >= seats_requested,
                )
            )
        ).mappings().first()
        return dict(row) if row else None

    async def _create_chat_reservation(self, db_session: AsyncSession, booking: dict[str, Any]) -> dict[str, Any]:
        trip = await db_session.get(Trip, UUID(booking['selected_trip_id']))
        if trip is None:
            raise ValueError('Selected trip no longer exists.')
        route = await db_session.get(Route, trip.route_id)
        if route is None or not route.is_active:
            raise ValueError('Selected route is not active.')
        seats_requested = int(booking['seats_requested'])
        if trip.status not in {'scheduled', 'boarding', 'delayed'} or trip.seats_available < seats_requested:
            raise ValueError('Selected trip is no longer available.')

        customer = booking['customer']
        reservation = Reservation(
            external_id=f"chat-{uuid4()}",
            trip_id=trip.id,
            customer_name=f"{customer['first_name']} {customer['last_name']}",
            email=customer['email'],
            phone_number=customer['phone_number'],
            seats_booked=seats_requested,
            amount_paid_cents=route.base_price_cents * seats_requested,
            booking_channel='admin_chat',
            status='confirmed',
        )
        trip.seats_available -= seats_requested
        db_session.add(reservation)
        await db_session.commit()
        await db_session.refresh(reservation)
        return {
            'reservation_id': str(reservation.id),
            'trip_id': str(reservation.trip_id),
            'customer_name': reservation.customer_name,
            'email': reservation.email,
            'phone_number': reservation.phone_number,
            'seats_booked': reservation.seats_booked,
            'amount_paid_cents': reservation.amount_paid_cents,
            'status': reservation.status,
        }

    @staticmethod
    def _looks_like_booking_request(query: str, intent: ValidatedQueryIntent) -> bool:
        lowered = query.lower()
        return intent.entity == 'reservations' and any(token in lowered for token in ('book', 'reserve')) and 'seat' in lowered

    @staticmethod
    def _extract_requested_seats(query: str) -> int | None:
        match = re.search(r'\b(\d+)\s+seats?\b', query, re.IGNORECASE)
        return int(match.group(1)) if match else None

    @staticmethod
    def _extract_uuid(query: str) -> str | None:
        match = re.search(r'\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b', query, re.IGNORECASE)
        return match.group(1) if match else None

    @staticmethod
    def _extract_contact_details(query: str) -> dict[str, str]:
        details: dict[str, str] = {}
        patterns = {
            'first_name': r'first name\s*(?:is|=|:)?\s*([a-zA-Z\'-]+)',
            'last_name': r'last name\s*(?:is|=|:)?\s*([a-zA-Z\'-]+)',
            'email': r'([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})',
            'phone_number': r'(\+?[0-9][0-9()\-\s]{7,}[0-9])',
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                details[key] = match.group(1).strip()
        return details

    @staticmethod
    def _format_booking_time(value: Any) -> str:
        if isinstance(value, datetime):
            return value.strftime('%Y-%m-%d %H:%M')
        return str(value)

    def _build_trace(
        self,
        planner_decision,
        intent: ValidatedQueryIntent,
        plan_steps: list[str],
        *,
        orchestration_backend: str | None = None,
        active_agents: list[str] | None = None,
        handoffs: list[str] | None = None,
        tool_calls: list[str] | None = None,
        assumptions: list[str] | None = None,
    ) -> QueryPlanTrace:
        return QueryPlanTrace(
            selected_agent=planner_decision.selected_agent,
            query_class=planner_decision.query_class,
            execution_mode=planner_decision.execution_mode,
            entity=intent.entity,
            operation=intent.operation,
            structured_intent=intent.model_dump(mode='json'),
            tool_hints=planner_decision.tool_hints,
            plan_steps=plan_steps,
            orchestration_backend=orchestration_backend,
            active_agents=active_agents or [],
            handoffs=handoffs or [],
            tool_calls=tool_calls or [],
            assumptions=assumptions or [],
        )

    def _followups(self, intent: StructuredIntent) -> list[str]:
        if intent.entity == 'routes':
            return ['Show trips for one of these routes.', 'Filter routes by origin or destination.']
        if intent.entity == 'trips':
            return ['Ask for delayed trips on a route.', 'Ask why a route is delayed.']
        if intent.entity == 'reservations':
            return ['Compare reservation activity across routes.', 'Count reservations for today.']
        return ['Ask which routes have the most incidents.', 'Ask for similar incidents on the same route.']
