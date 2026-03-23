import { useEffect, useState } from 'react'
import {
  getSimulationStatus,
  runSimulationTick,
  startSimulation,
  stopSimulation,
  updateSimulationConfig,
} from '../lib/apiClient'

const defaultConfig = {
  booking_rate_per_tick: 3,
  cancellation_rate_per_tick: 0.8,
  incident_rate_per_tick: 0.4,
  delay_sensitivity: 1,
  tick_interval_seconds: 60,
}

export default function AdminSimulation() {
  const [status, setStatus] = useState(null)
  const [config, setConfig] = useState(defaultConfig)
  const [busyAction, setBusyAction] = useState('')
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const data = await getSimulationStatus()
      setStatus(data)
      if (data?.engine?.config) {
        setConfig(data.engine.config)
      }
      setError('')
    } catch (err) {
      setError(err?.message || 'Unable to load simulation status.')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const doAction = async (label, action) => {
    setBusyAction(label)
    setError('')
    try {
      await action()
      await load()
    } catch (err) {
      setError(err?.message || 'Simulation action failed.')
    } finally {
      setBusyAction('')
    }
  }

  const onChange = (field) => (event) => {
    setConfig((prev) => ({ ...prev, [field]: Number(event.target.value) }))
  }

  return (
    <section className="mx-auto w-full max-w-6xl space-y-6">
      <header>
        <h1 className="font-heading text-4xl font-semibold tracking-tight text-zinc-900">Simulation Control Panel</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-600">
          Control the Data Engine, manage simulation parameters, and inspect recent seed and tick jobs.
        </p>
      </header>

      {error && <p className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

      <div className="grid gap-6 lg:grid-cols-[1fr,1.2fr]">
        <section className="surface-card rounded-2xl p-6">
          <h2 className="font-heading text-2xl font-semibold tracking-tight text-zinc-900">Runtime</h2>
          <div className="mt-5 space-y-3 text-sm text-zinc-700">
            <p>
              Engine status: <span className="font-semibold text-zinc-900">{status?.engine?.is_running ? 'Running' : 'Paused'}</span>
            </p>
            <p>Last seed: {status?.engine?.last_seed_run?.at || 'Not yet run'}</p>
            <p>Last tick: {status?.engine?.last_tick_run?.at || 'Not yet run'}</p>
          </div>

          <div className="mt-6 flex flex-wrap gap-3">
            <button className="button-primary" disabled={busyAction !== ''} onClick={() => doAction('start', startSimulation)} type="button">
              {busyAction === 'start' ? 'Starting…' : 'Start'}
            </button>
            <button className="button-secondary" disabled={busyAction !== ''} onClick={() => doAction('stop', stopSimulation)} type="button">
              {busyAction === 'stop' ? 'Stopping…' : 'Stop'}
            </button>
            <button className="button-secondary" disabled={busyAction !== ''} onClick={() => doAction('tick', runSimulationTick)} type="button">
              {busyAction === 'tick' ? 'Ticking…' : 'Run Tick'}
            </button>
          </div>
        </section>

        <section className="surface-card rounded-2xl p-6">
          <h2 className="font-heading text-2xl font-semibold tracking-tight text-zinc-900">Simulation Config</h2>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            {[
              ['booking_rate_per_tick', 'Booking Rate'],
              ['cancellation_rate_per_tick', 'Cancellation Rate'],
              ['incident_rate_per_tick', 'Incident Rate'],
              ['delay_sensitivity', 'Delay Sensitivity'],
              ['tick_interval_seconds', 'Tick Interval Seconds'],
            ].map(([field, label]) => (
              <label className="block space-y-2" key={field}>
                <span className="text-sm font-medium text-zinc-700">{label}</span>
                <input className="h-11 w-full rounded-xl border border-zinc-300 px-3.5 text-sm" onChange={onChange(field)} type="number" value={config[field]} />
              </label>
            ))}
          </div>

          <button
            className="button-primary mt-5"
            disabled={busyAction !== ''}
            onClick={() => doAction('config', () => updateSimulationConfig(config))}
            type="button"
          >
            {busyAction === 'config' ? 'Saving…' : 'Save Config'}
          </button>
        </section>
      </div>

      <section className="surface-card rounded-2xl p-6">
        <h2 className="font-heading text-2xl font-semibold tracking-tight text-zinc-900">Recent Simulation Jobs</h2>
        <div className="mt-4 space-y-3">
          {(status?.jobs || []).map((job) => (
            <article className="rounded-xl border border-zinc-200 bg-zinc-50 p-4" key={job.job_id}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-medium text-zinc-900">{job.job_type}</p>
                  <p className="text-sm text-zinc-600">{job.started_at || 'No start time'}</p>
                </div>
                <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium uppercase tracking-[0.08em] text-zinc-700">{job.status}</span>
              </div>
            </article>
          ))}
        </div>
      </section>
    </section>
  )
}
