import { useEffect, useMemo, useRef, useState } from 'react'
import { runAdminQuery } from '../lib/apiClient'

const promptSuggestions = [
  'Show delayed trips for today',
  'Which routes have the most incidents',
  'Compare reservation activity across active routes',
  'Why is route 21 delayed',
]

const initialMessage = {
  role: 'assistant',
  content: 'Ask about routes, trips, reservations, utilization, delays, or incidents. Responses stay grounded in operational records.',
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

function PromptChip({ label, onClick }) {
  return (
    <button
      className="rounded-full border border-white/10 bg-white/[0.03] px-4 py-2 text-left text-sm text-zinc-300 transition hover:border-primary/25 hover:bg-white/[0.06] hover:text-white"
      onClick={() => onClick(label)}
      type="button"
    >
      {label}
    </button>
  )
}

function RecordList({ records }) {
  if (!records.length) return null

  return (
    <div className="mt-4 space-y-3">
      {records.map((record, index) => (
        <section className="rounded-2xl border border-white/8 bg-white/[0.035] p-4" key={record.id || record.trip_id || record.reservation_id || index}>
          {record.route_name && record.origin_name && record.destination_name ? (
            <dl className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-white/6 bg-black/20 px-3 py-2.5">
                <dt className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">route</dt>
                <dd className="mt-1 break-words text-sm text-zinc-100">{record.route_name}</dd>
              </div>
              <div className="rounded-xl border border-white/6 bg-black/20 px-3 py-2.5">
                <dt className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">location</dt>
                <dd className="mt-1 break-words text-sm text-zinc-100">{record.origin_name} to {record.destination_name}</dd>
              </div>
              <div className="rounded-xl border border-white/6 bg-black/20 px-3 py-2.5">
                <dt className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">next departure</dt>
                <dd className="mt-1 break-words text-sm text-zinc-100">{String(record.next_departure_time ?? 'Not scheduled')}</dd>
              </div>
              <div className="rounded-xl border border-white/6 bg-black/20 px-3 py-2.5">
                <dt className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">base price</dt>
                <dd className="mt-1 break-words text-sm text-zinc-100">
                  {typeof record.base_price_cents === 'number' ? `$${(record.base_price_cents / 100).toFixed(2)}` : 'N/A'}
                </dd>
              </div>
            </dl>
          ) : (
            <dl className="grid gap-3 sm:grid-cols-2">
              {Object.entries(record).map(([key, value]) => (
                <div className="rounded-xl border border-white/6 bg-black/20 px-3 py-2.5" key={key}>
                  <dt className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">{key.replaceAll('_', ' ')}</dt>
                  <dd className="mt-1 break-words text-sm text-zinc-100">{String(value ?? 'N/A')}</dd>
                </div>
              ))}
            </dl>
          )}
        </section>
      ))}
    </div>
  )
}

export default function ChatPage() {
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

  const sendQuery = async (nextQuery) => {
    const trimmed = nextQuery.trim()
    if (!trimmed || loading) return

    const userMessage = { role: 'user', content: trimmed }
    const nextMessages = [...messages, userMessage]

    setMessages(nextMessages)
    setQuery('')
    setError('')
    setLoading(true)

    try {
      const data = await runAdminQuery({
        query: trimmed,
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

  const submit = async (event) => {
    event.preventDefault()
    await sendQuery(query)
  }

  return (
    <section className="container-shell py-12 md:py-16">
      <div className="mx-auto max-w-6xl space-y-8">
        <header className="space-y-4">
          <span className="section-label">Natural-language operations analysis</span>
          <h1 className="page-title">Ask OmniRoute about live operational state.</h1>
          <p className="max-w-3xl page-copy">
            Query routes, trips, reservations, delays, utilization, and incident patterns from a single evidence-aware chat workspace.
          </p>
        </header>

        <section className="surface-card flex min-h-[46rem] flex-col overflow-hidden">
            <header className="border-b border-white/8 px-5 py-5 sm:px-6">
              <h2 className="font-heading text-2xl font-bold tracking-tight text-white">Query Console</h2>
              <p className="mt-2 text-sm text-zinc-400">SQL-first answers with incident retrieval only when narrative context is relevant.</p>
            </header>

            <div className="flex-1 space-y-4 overflow-y-auto px-4 py-5 sm:px-6">
              {messages.map((message, index) => {
                const sqlRecords = getSqlRecords(message.evidence)
                return (
                  <article
                    className={`max-w-[92%] rounded-[28px] px-4 py-4 text-sm leading-7 ${
                      message.role === 'user'
                        ? 'ml-auto border border-primary/30 bg-primary/18 text-white'
                        : 'mr-auto border border-white/8 bg-white/[0.045] text-zinc-200'
                    }`}
                    key={`${message.role}-${index}`}
                  >
                    <p className="whitespace-pre-wrap">{message.content}</p>

                    {message.plan && (
                      <div className="mt-4 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.16em] text-zinc-400">
                        <span className="rounded-full border border-white/8 bg-black/20 px-2.5 py-1">flow: {formatAgentFlow(message.plan)}</span>
                      </div>
                    )}

                    <RecordList records={sqlRecords} />

                    {hasEvidence(message.evidence) && (
                      <details className="mt-4 rounded-2xl border border-white/8 bg-black/20 p-4">
                        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.18em] text-zinc-400">Grounding data</summary>
                        <pre className="mt-3 overflow-x-auto text-xs leading-6 text-zinc-300">{formatEvidence(message.evidence)}</pre>
                      </details>
                    )}
                  </article>
                )
              })}

              {loading && (
                <article className="mr-auto inline-flex items-center gap-2 rounded-2xl border border-white/8 bg-white/[0.045] px-4 py-3">
                  <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-primary" />
                  <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-primary [animation-delay:0.15s]" />
                  <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-primary [animation-delay:0.3s]" />
                </article>
              )}

              <div ref={endRef} />
            </div>

            <div className="border-t border-white/8 bg-surface-900/72 p-4 backdrop-blur sm:p-5">
              <form onSubmit={submit}>
                <div className="rounded-[26px] border border-white/10 bg-white/[0.04] px-4 py-3 shadow-soft">
                  <div className="flex items-end gap-3">
                    <textarea
                      aria-label="OmniRoute chat input"
                      className="max-h-48 min-h-[56px] flex-1 resize-none border-0 bg-transparent py-1 text-[15px] leading-7 text-zinc-100 outline-none placeholder:text-zinc-500"
                      onChange={(event) => setQuery(event.target.value)}
                      placeholder="Message OmniRoute about routes, trips, reservations, delays, or incidents."
                      value={query}
                    />
                    <button className="button-primary min-w-[96px] !rounded-2xl self-end" disabled={!canSend} type="submit">
                      {loading ? 'Sending' : 'Send'}
                    </button>
                  </div>
                </div>
                <p className="mt-3 text-xs text-zinc-500">Use route, trip, reservation, or incident references for exact records.</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {promptSuggestions.map((prompt) => (
                    <PromptChip key={prompt} label={prompt} onClick={setQuery} />
                  ))}
                </div>
              </form>

              {error && <p className="mt-3 text-sm text-rose-400">{error}</p>}
            </div>
        </section>
      </div>
    </section>
  )
}
