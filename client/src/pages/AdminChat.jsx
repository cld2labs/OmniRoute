import { useEffect, useMemo, useRef, useState } from 'react'
import { runAdminQuery } from '../lib/apiClient'

const initialMessage = {
  role: 'assistant',
  content: 'Ask about routes, trips, reservations, utilization, delays, or incidents.',
}

function formatEvidence(evidence = []) {
  if (!Array.isArray(evidence) || evidence.length === 0) {
    return null
  }
  return JSON.stringify(evidence, null, 2)
}

function hasEvidence(evidence = []) {
  return Array.isArray(evidence) && evidence.length > 0
}

function getSqlRecords(evidence = []) {
  return evidence
    .filter((item) => item?.type === 'sql' && Array.isArray(item.records))
    .flatMap((item) => item.records)
}

function formatAgentFlow(plan) {
  const activeAgents = Array.isArray(plan?.active_agents) ? plan.active_agents.filter(Boolean) : []
  if (activeAgents.length > 0) {
    return activeAgents.map((agent) => (agent === 'planner' ? 'Planner' : agent)).join(' -> ')
  }
  return `Planner -> ${plan?.selected_agent ?? 'operations'}`
}

function DetailRow({ label, value }) {
  return (
    <div className="rounded-lg bg-zinc-50 px-3 py-2">
      <dt className="text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-500">{label}</dt>
      <dd className="mt-1 break-words text-sm text-zinc-800">{String(value ?? 'N/A')}</dd>
    </div>
  )
}

function RecordCards({ records }) {
  if (!records.length) return null

  return (
    <div className="mt-3 space-y-3">
      {records.map((record, index) => (
        <section className="rounded-xl border border-zinc-200 bg-zinc-50/70 p-3" key={record.id || record.trip_id || record.reservation_id || index}>
          <dl className="grid gap-2 sm:grid-cols-2">
            {Object.entries(record).map(([key, value]) => (
              <DetailRow key={key} label={key.replaceAll('_', ' ')} value={value} />
            ))}
          </dl>
        </section>
      ))}
    </div>
  )
}

export default function AdminChat() {
  const [query, setQuery] = useState('')
  const [messages, setMessages] = useState([initialMessage])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [conversationId, setConversationId] = useState(null)
  const endRef = useRef(null)

  const canSend = useMemo(() => query.trim().length > 0 && !loading, [query, loading])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const submit = async (event) => {
    event.preventDefault()
    if (!canSend) return

    const userMessage = { role: 'user', content: query.trim() }
    const nextMessages = [...messages, userMessage]

    setMessages(nextMessages)
    setQuery('')
    setError('')
    setLoading(true)

    try {
      const data = await runAdminQuery({
        query: userMessage.content,
        conversation_id: conversationId,
        filters: {},
      })
      if (data?.conversation_id) {
        setConversationId(data.conversation_id)
      }
      setMessages([
        ...nextMessages,
        {
          role: 'assistant',
          content: data.answer || 'No answer returned.',
          evidence: data.evidence || [],
          plan: data.query_plan || null,
          needsClarification: Boolean(data.needs_clarification),
          clarificationOptions: data.clarification_options || [],
        },
      ])
    } catch (err) {
      const message = err?.message || 'Request failed. Please try again.'
      setError(message)
      setMessages([
        ...nextMessages,
        {
          role: 'assistant',
          content: 'I could not complete that request. Please try again.',
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="mx-auto flex h-[calc(100vh-12.5rem)] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-md">
      <header className="border-b border-zinc-200 px-5 py-4 sm:px-6">
        <h1 className="font-heading text-xl font-semibold tracking-tight text-zinc-900">Admin Query Console</h1>
        <p className="mt-1 text-sm text-zinc-500">SQL-first operational analysis with incident-only vector support.</p>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-5 sm:px-6">
        {messages.map((message, index) => {
          const sqlRecords = getSqlRecords(message.evidence)
          return (
            <article
              className={`max-w-[88%] rounded-2xl px-4 py-3 text-sm leading-6 ${
                message.role === 'user'
                  ? 'ml-auto bg-zinc-100 text-zinc-900'
                  : 'mr-auto border border-zinc-200 bg-white text-zinc-700'
              }`}
              key={`${message.role}-${index}`}
            >
              <p className="whitespace-pre-wrap">{message.content}</p>

              {message.plan && (
                <div className="mt-3 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.12em] text-zinc-500">
                  <span className="rounded-full bg-zinc-100 px-2 py-1">flow: {formatAgentFlow(message.plan)}</span>
                </div>
              )}

              <RecordCards records={sqlRecords} />

              {hasEvidence(message.evidence) && (
                <details className="mt-3 rounded-xl border border-zinc-200 bg-zinc-50 p-3">
                  <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.12em] text-zinc-600">
                    Grounding data
                  </summary>
                  <pre className="mt-2 overflow-x-auto text-xs text-zinc-700">{formatEvidence(message.evidence)}</pre>
                </details>
              )}
            </article>
          )
        })}

        {loading && (
          <article className="mr-auto inline-flex items-center gap-2 rounded-2xl border border-zinc-200 bg-white px-4 py-3">
            <span className="h-2 w-2 animate-pulse rounded-full bg-primary" />
            <span className="h-2 w-2 animate-pulse rounded-full bg-primary [animation-delay:0.15s]" />
            <span className="h-2 w-2 animate-pulse rounded-full bg-primary [animation-delay:0.3s]" />
          </article>
        )}

        <div ref={endRef} />
      </div>

      <div className="sticky bottom-0 border-t border-zinc-200 bg-white/95 p-4 backdrop-blur sm:p-5">
        <form className="flex items-center gap-3" onSubmit={submit}>
          <input
            aria-label="Admin chat input"
            className="h-12 flex-1 rounded-xl border border-zinc-300 px-4 text-sm text-zinc-900 outline-none transition focus:border-primary/80 focus:ring-2 focus:ring-primary/30"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Ask about operational state, utilization, delays, or similar incidents"
            value={query}
          />
          <button className="button-primary h-12 min-w-[96px]" disabled={!canSend} type="submit">
            {loading ? 'Sending' : 'Send'}
          </button>
        </form>

        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      </div>
    </section>
  )
}
