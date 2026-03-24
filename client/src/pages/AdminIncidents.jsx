import { useEffect, useState } from 'react'
import { createIncident, getIncidents, getRoutes, getTrips } from '../lib/apiClient'

const incidentTypes = ['delay', 'accident', 'weather', 'maintenance', 'mechanical_issue', 'traffic_disruption', 'staffing_issue', 'other']
const severities = ['low', 'medium', 'high', 'critical']

const initialForm = {
  route_id: '',
  trip_id: '',
  incident_type: 'delay',
  severity: 'medium',
  delay_minutes: '',
  occurred_at: '',
  summary: '',
  details: '',
  proof_url: '',
}

export default function AdminIncidents() {
  const [routes, setRoutes] = useState([])
  const [trips, setTrips] = useState([])
  const [incidents, setIncidents] = useState([])
  const [form, setForm] = useState(initialForm)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const load = async () => {
    try {
      const [routeData, incidentData] = await Promise.all([getRoutes(), getIncidents({ limit: 12 })])
      setRoutes(routeData?.routes || [])
      setIncidents(incidentData?.incidents || [])
      setError('')
    } catch (err) {
      setError(err?.message || 'Unable to load incidents.')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  useEffect(() => {
    if (!form.route_id) {
      setTrips([])
      return
    }

    void getTrips({ route_id: form.route_id, limit: 12 })
      .then((data) => setTrips(data?.trips || []))
      .catch(() => setTrips([]))
  }, [form.route_id])

  const onChange = (field) => (event) => {
    setForm((prev) => ({ ...prev, [field]: event.target.value }))
    setError('')
    setSuccess('')
  }

  const submit = async (event) => {
    event.preventDefault()
    if (submitting) return

    setSubmitting(true)
    setError('')
    setSuccess('')
    try {
      await createIncident({
        route_id: form.route_id || null,
        trip_id: form.trip_id || null,
        incident_type: form.incident_type,
        severity: form.severity,
        delay_minutes: form.delay_minutes ? Number.parseInt(form.delay_minutes, 10) : null,
        occurred_at: new Date(form.occurred_at).toISOString(),
        summary: form.summary,
        details: form.details,
        proof_url: form.proof_url || null,
        source_type: 'manual',
      })
      setSuccess('Incident recorded and queued for embedding processing.')
      setForm(initialForm)
      await load()
    } catch (err) {
      setError(err?.message || 'Unable to submit incident.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="mx-auto w-full max-w-6xl space-y-6">
      <header>
        <h1 className="font-heading text-4xl font-semibold tracking-tight text-zinc-900">Incidents Console</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-600">
          Review recent incidents and create new records that feed grounded operational analysis and incident intelligence.
        </p>
      </header>

      {error && <p className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
      {success && <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</p>}

      <div className="grid gap-6 lg:grid-cols-[1.1fr,1fr]">
        <section className="surface-card rounded-2xl p-6">
          <h2 className="font-heading text-2xl font-semibold tracking-tight text-zinc-900">Recent Incident Feed</h2>
          <div className="mt-4 space-y-3">
            {incidents.map((incident) => (
              <article className="rounded-xl border border-zinc-200 bg-zinc-50 p-4" key={incident.incident_id}>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-medium text-zinc-900">{incident.summary}</p>
                    <p className="text-sm text-zinc-600">{incident.incident_type.replaceAll('_', ' ')}</p>
                  </div>
                  <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium uppercase tracking-[0.08em] text-zinc-700">
                    {incident.severity}
                  </span>
                </div>
                <p className="mt-3 text-sm leading-6 text-zinc-600">{incident.details}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="surface-card rounded-2xl p-6">
          <h2 className="font-heading text-2xl font-semibold tracking-tight text-zinc-900">Report Incident</h2>
          <form className="mt-4 space-y-4" onSubmit={submit}>
            <select className="h-11 w-full rounded-xl border border-zinc-300 bg-white px-3.5 text-sm" onChange={onChange('route_id')} value={form.route_id}>
              <option value="">Select route</option>
              {routes.map((route) => (
                <option key={route.route_id} value={route.route_id}>
                  {route.route_name}
                </option>
              ))}
            </select>

            <select className="h-11 w-full rounded-xl border border-zinc-300 bg-white px-3.5 text-sm" onChange={onChange('trip_id')} value={form.trip_id}>
              <option value="">Optional trip</option>
              {trips.map((trip) => (
                <option key={trip.trip_id} value={trip.trip_id}>
                  {trip.route_name} | {trip.departure_time}
                </option>
              ))}
            </select>

            <div className="grid gap-4 sm:grid-cols-2">
              <select className="h-11 w-full rounded-xl border border-zinc-300 bg-white px-3.5 text-sm" onChange={onChange('incident_type')} value={form.incident_type}>
                {incidentTypes.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
              <select className="h-11 w-full rounded-xl border border-zinc-300 bg-white px-3.5 text-sm" onChange={onChange('severity')} value={form.severity}>
                {severities.map((level) => (
                  <option key={level} value={level}>
                    {level}
                  </option>
                ))}
              </select>
            </div>

            <input className="h-11 w-full rounded-xl border border-zinc-300 px-3.5 text-sm" onChange={onChange('delay_minutes')} placeholder="Delay minutes if applicable" type="number" value={form.delay_minutes} />
            <input className="h-11 w-full rounded-xl border border-zinc-300 px-3.5 text-sm" onChange={onChange('occurred_at')} required type="datetime-local" value={form.occurred_at} />
            <input className="h-11 w-full rounded-xl border border-zinc-300 px-3.5 text-sm" onChange={onChange('summary')} placeholder="Summary" required value={form.summary} />
            <textarea className="min-h-32 w-full rounded-xl border border-zinc-300 px-3.5 py-3 text-sm" onChange={onChange('details')} placeholder="Details" required value={form.details} />
            <input className="h-11 w-full rounded-xl border border-zinc-300 px-3.5 text-sm" onChange={onChange('proof_url')} placeholder="Proof URL" value={form.proof_url} />

            <button className="button-primary w-full" disabled={submitting} type="submit">
              {submitting ? 'Submitting…' : 'Create Incident'}
            </button>
          </form>
        </section>
      </div>
    </section>
  )
}
