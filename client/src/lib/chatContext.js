const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

const routeStopWords = new Set([
  'today',
  'tomorrow',
  'yesterday',
  'for',
  'with',
  'on',
  'in',
  'at',
  'from',
  'to',
  'between',
  'and',
  'after',
  'before',
  'this',
  'next',
  'week',
  'month',
  'status',
  'delay',
  'delayed',
  'schedule',
  'trips',
  'trip',
  'incidents',
  'incident',
  'happened',
  'happens',
])

const routeReferencePattern = /\b(that|this|same)\s+route\b/i
const tripReferencePattern = /\b(that|this|same)\s+trip\b/i
const reservationReferencePattern = /\b(that|this|same)\s+reservation\b/i

export function buildFiltersForQuery(query, context) {
  const text = String(query || '')
  const filters = {}

  if (routeReferencePattern.test(text) && context?.route_name) {
    filters.route_name = context.route_name
  }
  if (tripReferencePattern.test(text) && context?.trip_id && isUuid(context.trip_id)) {
    filters.trip_id = context.trip_id
  }
  if (reservationReferencePattern.test(text) && context?.reservation_id && isUuid(context.reservation_id)) {
    filters.reservation_id = context.reservation_id
  }

  return filters
}

export function nextChatContext({ query, previousContext, assistantText, evidence }) {
  const next = {
    route_name: previousContext?.route_name || null,
    trip_id: previousContext?.trip_id || null,
    reservation_id: previousContext?.reservation_id || null,
  }

  const explicitRoute = extractRouteNameHint(query)
  if (explicitRoute) {
    next.route_name = explicitRoute
  }

  const explicitTripId = extractExplicitTripId(query)
  if (explicitTripId) {
    next.trip_id = explicitTripId
  }

  const explicitReservationId = extractExplicitReservationId(query)
  if (explicitReservationId) {
    next.reservation_id = explicitReservationId
  }

  const evidenceDerived = deriveContextFromEvidence(evidence)
  if (!next.route_name && evidenceDerived.route_name) {
    next.route_name = evidenceDerived.route_name
  }
  if (!next.trip_id && evidenceDerived.trip_id) {
    next.trip_id = evidenceDerived.trip_id
  }
  if (!next.reservation_id && evidenceDerived.reservation_id) {
    next.reservation_id = evidenceDerived.reservation_id
  }

  if (!next.route_name) {
    const routeFromAssistant = extractRouteNameHint(assistantText)
    if (routeFromAssistant) {
      next.route_name = routeFromAssistant
    }
  }

  return next
}

function deriveContextFromEvidence(evidence) {
  const context = { route_name: null, trip_id: null, reservation_id: null }
  for (const item of evidence || []) {
    if (!item || item.type !== 'sql' || !Array.isArray(item.records)) {
      continue
    }

    for (const record of item.records) {
      if (!context.route_name && typeof record?.route_name === 'string' && record.route_name.trim()) {
        context.route_name = record.route_name.trim()
      }
      if (!context.trip_id && isUuid(record?.trip_id)) {
        context.trip_id = String(record.trip_id)
      }
      if (!context.reservation_id && isUuid(record?.reservation_id)) {
        context.reservation_id = String(record.reservation_id)
      }
    }
  }
  return context
}

function extractRouteNameHint(text) {
  const query = String(text || '')
  const match = query.match(/\broutes?\s+([a-z0-9][a-z0-9\-\s]{0,60})/i)
  if (!match) {
    return null
  }

  const tokens = match[1]
    .replace(/[.,!?]/g, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean)

  const kept = []
  for (const token of tokens) {
    if (routeStopWords.has(token.toLowerCase())) {
      break
    }
    kept.push(token)
  }
  if (kept.length === 0) {
    return null
  }

  const candidate = kept.join(' ').trim()
  if (/^\d/.test(candidate)) {
    return `Route ${candidate}`
  }
  return /^route\s+/i.test(candidate) ? candidate : `Route ${candidate}`
}

function extractExplicitTripId(query) {
  const text = String(query || '')
  const match = text.match(/\btrip(?:\s+id)?\s*[:#-]?\s*([0-9a-f-]{36})\b/i)
  if (!match) {
    return null
  }
  const candidate = match[1]
  return isUuid(candidate) ? candidate : null
}

function extractExplicitReservationId(query) {
  const text = String(query || '')
  const match = text.match(/\breservation(?:\s+id)?\s*[:#-]?\s*([a-z0-9-]{4,64})\b/i)
  if (!match) {
    return null
  }
  const candidate = String(match[1] || '').trim()
  if (!candidate) {
    return null
  }
  return candidate
}

function isUuid(value) {
  return uuidPattern.test(String(value || '').trim())
}

