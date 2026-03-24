import { useEffect, useState } from 'react'
import { getReservations, getRoutes, getSimulationStatus, getTrips, seedData } from '../lib/apiClient'

function SectionCard({ title, description, children }) {
  return (
    <section className="surface-card rounded-2xl p-6">
      <h2 className="font-heading text-2xl font-semibold tracking-tight text-zinc-900">{title}</h2>
      <p className="mt-2 text-sm text-zinc-600">{description}</p>
      <div className="mt-5">{children}</div>
    </section>
  )
}

export default function AdminData() {
  const [routes, setRoutes] = useState([])
  const [trips, setTrips] = useState([])
  const [reservations, setReservations] = useState([])
  const [engineStatus, setEngineStatus] = useState(null)
  const [seeding, setSeeding] = useState(false)
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const [routeData, tripData, reservationData, statusData] = await Promise.all([
        getRoutes(),
        getTrips({ limit: 8 }),
        getReservations({ limit: 8 }),
        getSimulationStatus(),
      ])
      setRoutes(routeData?.routes || [])
      setTrips(tripData?.trips || [])
      setReservations(reservationData?.reservations || [])
      setEngineStatus(statusData)
      setError('')
    } catch (err) {
      setError(err?.message || 'Unable to load admin data.')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const runSeed = async () => {
    if (seeding) return
    setSeeding(true)
    try {
      await seedData({ days: 3, routes: 6 })
      await load()
    } catch (err) {
      setError(err?.message || 'Seed job failed.')
    } finally {
      setSeeding(false)
    }
  }

  return (
    <section className="mx-auto w-full max-w-6xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-4xl font-semibold tracking-tight text-zinc-900">Data Engine Console</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-600">
            Inspect simulated routes, trips, reservations, and Data Engine status. Use this page to seed the environment and verify data freshness.
          </p>
        </div>
        <button className="button-primary" disabled={seeding} onClick={runSeed} type="button">
          {seeding ? 'Seeding…' : 'Seed Baseline Data'}
        </button>
      </header>

      {error && <p className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

      <div className="grid gap-6 lg:grid-cols-2">
        <SectionCard title="Route Inventory" description="Popular routes and baseline network shape used by the simulator.">
          <div className="space-y-3">
            {routes.slice(0, 6).map((route) => (
              <article className="rounded-xl border border-zinc-200 bg-zinc-50 p-4" key={route.route_id}>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-medium text-zinc-900">{route.route_name}</p>
                    <p className="text-sm text-zinc-600">
                      {route.origin_name} to {route.destination_name}
                    </p>
                  </div>
                  <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-zinc-700">
                    popularity {route.popularity_score}
                  </span>
                </div>
              </article>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="Engine Status" description="Current runtime and recent Data Engine activity.">
          <div className="space-y-3 rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-700">
            <p>
              Runtime: <span className="font-semibold text-zinc-900">{engineStatus?.engine?.is_running ? 'Running' : 'Paused'}</span>
            </p>
            <p>Last seed: {engineStatus?.engine?.last_seed_run?.at || 'Not yet run'}</p>
            <p>Last tick: {engineStatus?.engine?.last_tick_run?.at || 'Not yet run'}</p>
            <p>Route count: {engineStatus?.metrics?.route_count ?? 0}</p>
            <p>Reservation count: {engineStatus?.metrics?.reservation_count ?? 0}</p>
          </div>
        </SectionCard>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <SectionCard title="Trip Feed" description="Latest trips generated or updated by the simulation engine.">
          <div className="space-y-3">
            {trips.map((trip) => (
              <article className="rounded-xl border border-zinc-200 bg-zinc-50 p-4" key={trip.trip_id}>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-medium text-zinc-900">{trip.route_name || trip.route_id}</p>
                    <p className="text-sm text-zinc-600">{trip.departure_time}</p>
                  </div>
                  <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium capitalize text-zinc-700">{trip.status}</span>
                </div>
              </article>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="Reservation Feed" description="Recent bookings and cancellations produced by the simulator.">
          <div className="space-y-3">
            {reservations.map((reservation) => (
              <article className="rounded-xl border border-zinc-200 bg-zinc-50 p-4" key={reservation.reservation_id}>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-medium text-zinc-900">{reservation.customer_name}</p>
                    <p className="text-sm text-zinc-600">{reservation.booking_channel}</p>
                  </div>
                  <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium capitalize text-zinc-700">{reservation.status}</span>
                </div>
              </article>
            ))}
          </div>
        </SectionCard>
      </div>
    </section>
  )
}
