import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getDashboardOverview } from '../lib/apiClient'

const quickLinks = [
  { title: 'AI Query Console', to: '/admin/chat', description: 'Ask grounded questions over live operational data.' },
  { title: 'Data Engine', to: '/admin/data', description: 'Inspect generated data domains and seed state.' },
  { title: 'Incidents Console', to: '/admin/incidents', description: 'Monitor incidents and report new operational issues.' },
  { title: 'Simulation Controls', to: '/admin/simulation', description: 'Start, stop, and tick the simulation engine.' },
]

function MetricCard({ label, value }) {
  return (
    <article className="surface-card rounded-2xl p-5">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">{label}</p>
      <p className="mt-3 font-heading text-3xl font-semibold tracking-tight text-zinc-900">{value}</p>
    </article>
  )
}

export default function AdminDashboard() {
  const [overview, setOverview] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let mounted = true

    const load = async () => {
      try {
        const data = await getDashboardOverview()
        if (mounted) {
          setOverview(data)
          setError('')
        }
      } catch (err) {
        if (mounted) {
          setError(err?.message || 'Failed to load dashboard overview.')
        }
      } finally {
        if (mounted) {
          setLoading(false)
        }
      }
    }

    void load()
    return () => {
      mounted = false
    }
  }, [])

  const metrics = overview?.metrics || {}

  return (
    <section className="mx-auto w-full max-w-6xl space-y-8">
      <header className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Trusted Internal Platform</p>
        <h1 className="font-heading text-4xl font-semibold tracking-tight text-zinc-900">Admin Operations Console</h1>
        <p className="max-w-3xl text-sm leading-6 text-zinc-600">
          OmniRoute now runs as an internal operations simulation platform. Monitor routes, trips, reservations, incidents,
          and the Data Engine from a single admin surface.
        </p>
      </header>

      {error && <p className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Active Routes" value={loading ? '...' : metrics.active_routes ?? 0} />
        <MetricCard label="Trips In Progress" value={loading ? '...' : metrics.trips_in_progress ?? 0} />
        <MetricCard label="Delayed Trips" value={loading ? '...' : metrics.delayed_trips ?? 0} />
        <MetricCard label="Seat Utilization" value={loading ? '...' : `${Math.round((metrics.seat_utilization_pct ?? 0) * 100)}%`} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.4fr,1fr]">
        <section className="surface-card rounded-2xl p-6">
          <h2 className="font-heading text-2xl font-semibold tracking-tight text-zinc-900">Operational Snapshot</h2>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            {Object.entries(overview?.status_breakdown || {}).map(([status, count]) => (
              <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4" key={status}>
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">{status}</p>
                <p className="mt-2 text-2xl font-semibold text-zinc-900">{count}</p>
              </div>
            ))}
          </div>

          <div className="mt-6 rounded-2xl border border-zinc-200 bg-zinc-50 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">Simulation Runtime</p>
            <p className="mt-2 text-sm text-zinc-700">
              Status: <span className="font-semibold text-zinc-900">{overview?.simulation?.is_running ? 'Running' : 'Paused'}</span>
            </p>
            <p className="mt-1 text-sm text-zinc-700">Last tick: {overview?.simulation?.last_tick_run?.at || 'Not yet run'}</p>
            <p className="mt-1 text-sm text-zinc-700">Last seed: {overview?.simulation?.last_seed_run?.at || 'Not yet run'}</p>
          </div>
        </section>

        <section className="surface-card rounded-2xl p-6">
          <h2 className="font-heading text-2xl font-semibold tracking-tight text-zinc-900">Recent Incidents</h2>
          <div className="mt-4 space-y-3">
            {(overview?.recent_incidents || []).map((incident) => (
              <article className="rounded-xl border border-zinc-200 bg-zinc-50 p-4" key={incident.incident_id}>
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">{incident.incident_type}</p>
                <p className="mt-2 text-sm font-medium text-zinc-900">{incident.summary}</p>
                <p className="mt-2 text-xs text-zinc-500">{incident.occurred_at}</p>
              </article>
            ))}
            {!loading && (overview?.recent_incidents || []).length === 0 && (
              <p className="rounded-xl border border-dashed border-zinc-300 px-4 py-6 text-sm text-zinc-500">
                No incidents are currently recorded.
              </p>
            )}
          </div>
        </section>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {quickLinks.map((card) => (
          <Link className="surface-card rounded-2xl p-6 transition hover:-translate-y-0.5 hover:border-primary/35 hover:shadow-soft" key={card.title} to={card.to}>
            <h2 className="font-heading text-xl font-semibold tracking-tight text-zinc-900">{card.title}</h2>
            <p className="mt-3 text-sm leading-6 text-zinc-600">{card.description}</p>
          </Link>
        ))}
      </div>
    </section>
  )
}
