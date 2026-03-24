import { useEffect, useMemo, useRef, useState } from 'react'
import { createIncident, getRoutes, getTrips, uploadCsv } from '../lib/apiClient'

const datasetOptions = [
  {
    value: 'ops',
    title: 'Routes & Trips',
    description: 'Routes, stops, trip timing, capacity, seats available, status, and delays.',
    requiredFields: [
      'route_name',
      'origin_name',
      'destination_name',
      'base_price_cents',
      'stops_json',
      'departure_time',
      'arrival_time',
      'capacity_total',
      'seats_available',
      'status',
      'delay_minutes',
    ],
    optionalFields: [],
  },
  {
    value: 'reservations',
    title: 'Reservations',
    description: 'Bookings, channels, passenger details, seat counts, and payment totals linked to a route and departure.',
    requiredFields: [
      'reservation_external_id',
      'route_name',
      'departure_time',
      'customer_name',
      'email',
      'phone_number',
      'seats_booked',
      'status',
      'amount_paid_cents',
    ],
    optionalFields: [],
  },
  {
    value: 'incidents',
    title: 'Incidents',
    description: 'Operational incidents tied to route context, timestamps, summaries, and optional trip matching.',
    requiredFields: [
      'incident_external_id',
      'route_name',
      'incident_type',
      'occurred_at',
      'summary',
    ],
    optionalFields: ['departure_time', 'details', 'proof_url'],
  },
]

const incidentTypes = ['delay', 'accident', 'weather', 'maintenance', 'mechanical_issue', 'traffic_disruption', 'staffing_issue', 'other']
const severities = ['low', 'medium', 'high', 'critical']

const initialIncidentForm = {
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

function SummaryCard({ summary }) {
  if (!summary) return null

  return (
    <section className="surface-card p-6">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary-100">Latest upload</p>
      <h2 className="mt-3 font-heading text-2xl font-bold text-white">{summary.filename}</h2>
      <p className="mt-2 text-sm text-zinc-400">Dataset: {summary.dataset}</p>
      <div className="mt-5 grid gap-4 sm:grid-cols-3">
        <div className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Rows total</p>
          <p className="mt-2 text-2xl font-bold text-white">{summary.rows_total}</p>
        </div>
        <div className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Processed</p>
          <p className="mt-2 text-2xl font-bold text-white">{summary.rows_processed}</p>
        </div>
        <div className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">Failed</p>
          <p className="mt-2 text-2xl font-bold text-white">{summary.rows_failed}</p>
        </div>
      </div>
      {summary.errors?.length > 0 && (
        <div className="mt-5 rounded-2xl border border-rose-500/20 bg-rose-500/8 p-4">
          <p className="text-sm font-semibold text-rose-200">Validation issues</p>
          <div className="mt-3 space-y-2 text-sm text-rose-100/90">
            {summary.errors.slice(0, 8).map((error) => (
              <p key={`${error.row}-${error.code}`}>
                Row {error.row}: {error.code} — {error.message}
              </p>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

export default function UploadPage() {
  const inputRef = useRef(null)
  const [dataset, setDataset] = useState('ops')
  const [file, setFile] = useState(null)
  const [dragActive, setDragActive] = useState(false)
  const [loading, setLoading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [summary, setSummary] = useState(null)
  const [routes, setRoutes] = useState([])
  const [trips, setTrips] = useState([])
  const [incidentForm, setIncidentForm] = useState(initialIncidentForm)
  const [incidentSubmitting, setIncidentSubmitting] = useState(false)
  const [incidentError, setIncidentError] = useState('')
  const [incidentSuccess, setIncidentSuccess] = useState('')

  const selectedDataset = useMemo(() => datasetOptions.find((option) => option.value === dataset), [dataset])
  const isIncidentDataset = dataset === 'incidents'

  useEffect(() => {
    if (!isIncidentDataset) {
      return
    }

    void getRoutes({ active: true })
      .then((data) => setRoutes(data?.routes || []))
      .catch(() => setRoutes([]))
  }, [isIncidentDataset])

  useEffect(() => {
    if (!isIncidentDataset || !incidentForm.route_id) {
      setTrips([])
      return
    }

    void getTrips({ route_id: incidentForm.route_id, limit: 50 })
      .then((data) => setTrips(data?.trips || []))
      .catch(() => setTrips([]))
  }, [incidentForm.route_id, isIncidentDataset])

  const handleFile = (nextFile) => {
    if (!nextFile) return
    setFile(nextFile)
    setUploadError('')
    setIncidentSuccess('')
  }

  const onDrop = (event) => {
    event.preventDefault()
    setDragActive(false)
    handleFile(event.dataTransfer.files?.[0] || null)
  }

  const submit = async (event) => {
    event.preventDefault()
    if (!file || loading) return

    setLoading(true)
    setUploadError('')

    try {
      const result = await uploadCsv({ dataset, file })
      setSummary(result)
    } catch (err) {
      setUploadError(err?.message || 'Upload failed.')
    } finally {
      setLoading(false)
    }
  }

  const onIncidentChange = (field) => (event) => {
    const value = event.target.value
    setIncidentForm((prev) => {
      if (field === 'route_id') {
        return { ...prev, route_id: value, trip_id: '' }
      }
      if (field === 'incident_type' && value !== 'delay') {
        return { ...prev, incident_type: value, delay_minutes: '' }
      }
      return { ...prev, [field]: value }
    })
    setIncidentError('')
    setIncidentSuccess('')
  }

  const submitIncident = async (event) => {
    event.preventDefault()
    if (incidentSubmitting) return

    setIncidentSubmitting(true)
    setIncidentError('')
    setIncidentSuccess('')

    try {
      await createIncident({
        route_id: incidentForm.route_id,
        trip_id: incidentForm.trip_id || null,
        incident_type: incidentForm.incident_type,
        severity: incidentForm.severity,
        delay_minutes: incidentForm.incident_type === 'delay' ? Number.parseInt(incidentForm.delay_minutes, 10) : null,
        occurred_at: new Date(incidentForm.occurred_at).toISOString(),
        summary: incidentForm.summary,
        details: incidentForm.details,
        proof_url: incidentForm.proof_url || null,
        source_type: 'manual',
      })
      setIncidentForm(initialIncidentForm)
      setTrips([])
      setIncidentSuccess('Incident created successfully.')
    } catch (err) {
      setIncidentError(err?.message || 'Incident submission failed.')
    } finally {
      setIncidentSubmitting(false)
    }
  }

  return (
    <section className="container-shell py-12 md:py-16">
      <div className="mx-auto max-w-6xl space-y-8">
        <header className="space-y-4">
          <span className="section-label">CSV ingestion</span>
          <h1 className="page-title">Load operational datasets into OmniRoute.</h1>
          <p className="max-w-3xl page-copy">
            Upload CSV files for operations, reservations, or incidents to establish a baseline before running simulation or chat-based analysis.
          </p>
        </header>

        <div className="space-y-6">
          <section className="surface-card mx-auto w-full max-w-5xl rounded-[30px] p-6 md:p-7">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary-100">Choose dataset</p>
                <p className="mt-2 text-sm leading-6 text-zinc-400">Pick the CSV type you want to ingest into the operational baseline.</p>
              </div>
              <span className="rounded-2xl border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-zinc-300">
                {selectedDataset?.title}
              </span>
            </div>
            <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {datasetOptions.map((option) => (
                <button
                  className={`min-w-[180px] rounded-2xl border px-5 py-4 text-left transition duration-200 ${
                    dataset === option.value
                      ? 'border-primary/50 bg-primary/10 text-white shadow-[0_0_0_1px_rgba(168,85,247,0.16),0_16px_36px_rgba(88,28,135,0.18)]'
                      : 'border-white/10 bg-white/[0.03] text-zinc-300 hover:border-primary/25 hover:bg-white/[0.05] hover:text-white'
                  }`}
                  key={option.value}
                  onClick={() => setDataset(option.value)}
                  type="button"
                >
                  <div>
                    <h2 className="font-heading text-lg font-bold">{option.title}</h2>
                    <p className={`mt-2 text-sm leading-6 ${dataset === option.value ? 'text-primary-100/90' : 'text-zinc-400'}`}>
                      {option.description}
                    </p>
                  </div>
                </button>
              ))}
            </div>
            <div className="mt-6 border-t border-white/8 pt-5">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500">CSV fields for {selectedDataset?.title}</p>
              <div className="mt-4">
                <p className="text-sm font-semibold text-white">Required fields</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {selectedDataset?.requiredFields.map((field) => (
                    <span
                      className="rounded-xl border border-primary/18 bg-primary/10 px-3 py-1.5 text-sm text-primary-50"
                      key={field}
                    >
                      {field}
                    </span>
                  ))}
                </div>
              </div>
              {selectedDataset?.optionalFields?.length > 0 && (
                <div className="mt-4">
                  <p className="text-sm font-semibold text-white">Optional fields</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {selectedDataset.optionalFields.map((field) => (
                      <span
                        className="rounded-xl border border-white/10 bg-white/[0.04] px-3 py-1.5 text-sm text-zinc-300"
                        key={field}
                      >
                        {field}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </section>

          <section className={`grid items-start gap-6 ${isIncidentDataset ? 'mx-auto max-w-5xl lg:grid-cols-2' : 'mx-auto max-w-5xl'}`}>
            <form
              className={`surface-card self-start rounded-[30px] p-6 transition md:p-7 ${
                dragActive ? 'border-primary/45 shadow-[0_0_0_1px_rgba(168,85,247,0.16),0_18px_48px_rgba(88,28,135,0.16)]' : ''
              }`}
              onDragEnter={(event) => {
                event.preventDefault()
                setDragActive(true)
              }}
              onDragLeave={(event) => {
                event.preventDefault()
                setDragActive(false)
              }}
              onDragOver={(event) => event.preventDefault()}
              onDrop={onDrop}
              onSubmit={submit}
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary-100">Upload file</p>
                  <p className="mt-2 text-sm leading-6 text-zinc-400">Select a CSV file to make the data available for operations review, simulation, and grounded chat responses.</p>
                </div>
                <button className="button-primary min-w-[120px]" disabled={!file || loading} type="submit">
                  {loading ? 'Uploading' : 'Upload CSV'}
                </button>
              </div>

              <div className="mt-6 flex flex-wrap items-center gap-3">
                <button className="button-primary" onClick={() => inputRef.current?.click()} type="button">
                  Choose CSV
                </button>
                <span className={`text-sm ${dragActive ? 'text-primary-100' : 'text-zinc-500'}`}>or drag and drop a CSV into this section</span>
                {file && (
                  <span className="inline-flex items-center rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm text-zinc-200">
                    {file.name}
                  </span>
                )}
              </div>
              {uploadError && <p className="mt-5 text-sm text-rose-400">{uploadError}</p>}
              <input
                accept=".csv,text/csv"
                className="hidden"
                onChange={(event) => handleFile(event.target.files?.[0] || null)}
                ref={inputRef}
                type="file"
              />
            </form>

            {isIncidentDataset && (
              <section className="surface-card self-start rounded-[30px] p-6 md:p-7">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary-100">Manual incident</p>
                    <p className="mt-2 text-sm leading-6 text-zinc-400">Create an incident directly when you do not have a CSV. Required fields are enforced before submission.</p>
                  </div>
                  <span className="rounded-2xl border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-zinc-300">
                    CSV or Form
                  </span>
                </div>

                <form className="mt-6 space-y-4" onSubmit={submitIncident}>
                  <div>
                    <label className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500" htmlFor="incident-route">Route *</label>
                    <select className="mt-2 h-11 w-full rounded-xl border border-white/10 bg-white/[0.04] px-3.5 text-sm text-white" id="incident-route" onChange={onIncidentChange('route_id')} required value={incidentForm.route_id}>
                      <option value="">Select route</option>
                      {routes.map((route) => (
                        <option key={route.route_id} value={route.route_id}>
                          {route.route_name} | {route.origin_name} to {route.destination_name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500" htmlFor="incident-trip">Trip</label>
                    <select className="mt-2 h-11 w-full rounded-xl border border-white/10 bg-white/[0.04] px-3.5 text-sm text-white" disabled={!incidentForm.route_id} id="incident-trip" onChange={onIncidentChange('trip_id')} value={incidentForm.trip_id}>
                      <option value="">Optional trip</option>
                      {trips.map((trip) => (
                        <option key={trip.trip_id} value={trip.trip_id}>
                          {trip.route_name} | {trip.departure_time} | {trip.status}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <label className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500" htmlFor="incident-type">Incident type *</label>
                      <select className="mt-2 h-11 w-full rounded-xl border border-white/10 bg-white/[0.04] px-3.5 text-sm text-white" id="incident-type" onChange={onIncidentChange('incident_type')} required value={incidentForm.incident_type}>
                        {incidentTypes.map((type) => (
                          <option key={type} value={type}>
                            {type.replaceAll('_', ' ')}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500" htmlFor="incident-severity">Severity *</label>
                      <select className="mt-2 h-11 w-full rounded-xl border border-white/10 bg-white/[0.04] px-3.5 text-sm text-white" id="incident-severity" onChange={onIncidentChange('severity')} required value={incidentForm.severity}>
                        {severities.map((severity) => (
                          <option key={severity} value={severity}>
                            {severity}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  {incidentForm.incident_type === 'delay' && (
                    <div>
                      <label className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500" htmlFor="incident-delay">Delay minutes *</label>
                      <input className="mt-2 h-11 w-full rounded-xl border border-white/10 bg-white/[0.04] px-3.5 text-sm text-white" id="incident-delay" min="0" onChange={onIncidentChange('delay_minutes')} placeholder="Enter delay minutes" required type="number" value={incidentForm.delay_minutes} />
                    </div>
                  )}

                  <div>
                    <label className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500" htmlFor="incident-occurred-at">Occurred at *</label>
                    <input className="mt-2 h-11 w-full rounded-xl border border-white/10 bg-white/[0.04] px-3.5 text-sm text-white" id="incident-occurred-at" onChange={onIncidentChange('occurred_at')} required type="datetime-local" value={incidentForm.occurred_at} />
                  </div>

                  <div>
                    <label className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500" htmlFor="incident-summary">Summary *</label>
                    <input className="mt-2 h-11 w-full rounded-xl border border-white/10 bg-white/[0.04] px-3.5 text-sm text-white" id="incident-summary" maxLength={255} onChange={onIncidentChange('summary')} placeholder="Short incident summary" required value={incidentForm.summary} />
                  </div>

                  <div>
                    <label className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500" htmlFor="incident-details">Details *</label>
                    <textarea className="mt-2 min-h-32 w-full rounded-xl border border-white/10 bg-white/[0.04] px-3.5 py-3 text-sm text-white" id="incident-details" onChange={onIncidentChange('details')} placeholder="Operational details for this incident" required value={incidentForm.details} />
                  </div>

                  <div>
                    <label className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500" htmlFor="incident-proof-url">Proof URL</label>
                    <input className="mt-2 h-11 w-full rounded-xl border border-white/10 bg-white/[0.04] px-3.5 text-sm text-white" id="incident-proof-url" onChange={onIncidentChange('proof_url')} placeholder="https://..." type="url" value={incidentForm.proof_url} />
                  </div>

                  {incidentError && <p className="text-sm text-rose-400">{incidentError}</p>}
                  {incidentSuccess && <p className="text-sm text-emerald-300">{incidentSuccess}</p>}

                  <button className="button-primary w-full" disabled={incidentSubmitting} type="submit">
                    {incidentSubmitting ? 'Submitting' : 'Create Incident'}
                  </button>
                </form>
              </section>
            )}
          </section>

          <SummaryCard summary={summary} />
        </div>
      </div>
    </section>
  )
}
