import { Link } from 'react-router-dom'
import BackgroundBeams from '../components/ui/BackgroundBeams'
import CardHoverEffect from '../components/ui/CardHoverEffect'
import Spotlight from '../components/ui/Spotlight'

const howItWorksItems = [
  'Upload CSV files or start from generated operational activity.',
  'OmniRoute stores and updates routes, trips, reservations, and incidents.',
  'Use chat to inspect delays, trends, utilization, and incident context.',
]

const flowItems = [
  {
    step: '01',
    title: 'Load Data',
    description: 'Upload CSV datasets or start from generated activity to seed the operational state.',
  },
  {
    step: '02',
    title: 'Review Activity',
    description: 'Watch routes, trips, reservations, and incidents update inside the admin workspace.',
  },
  {
    step: '03',
    title: 'Ask Questions',
    description: 'Use grounded chat to inspect delays, utilization, anomalies, and incident context.',
  },
]

export default function HomePage() {
  return (
    <div className="pb-20">
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-radial-hero" />
        <BackgroundBeams />
        <Spotlight className="-left-24 top-0 animate-spotlight" />
        <Spotlight className="right-0 top-24 h-[24rem] w-[24rem] animate-spotlight [animation-delay:2.5s]" />
        <div className="container-shell relative py-20 md:py-28">
          <div className="max-w-4xl space-y-7">
            <span className="section-label">Transportation operations intelligence</span>
            <div className="space-y-5">
              <h1 className="font-heading text-5xl font-bold tracking-tight text-white md:text-7xl">
                OmniRoute gives operators a clean view of simulated transportation activity.
              </h1>
              <p className="max-w-2xl text-base leading-8 text-zinc-300 md:text-lg">
                It combines uploaded or generated operational data with grounded AI querying across routes, trips, reservations, delays, utilization, and incidents.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Link className="button-primary" to="/chat">
                Open Chat
              </Link>
              <a className="button-secondary" href="#how-it-works">
                How It Works
              </a>
            </div>
          </div>
        </div>
      </section>

      <section className="container-shell section-spacing" id="how-it-works">
        <div className="grid gap-8 lg:grid-cols-[0.9fr,1.1fr] lg:items-start">
          <header className="space-y-4">
            <span className="section-label">How it works</span>
            <h2 className="font-heading text-3xl font-bold tracking-tight text-white md:text-4xl">A simple loop from operational data to grounded answers.</h2>
            <p className="page-copy max-w-2xl">
              OmniRoute keeps the system readable: data enters through upload or simulation, the platform updates the operational state, and chat helps inspect what is happening.
            </p>
          </header>

          <div className="grid gap-4">
            {howItWorksItems.map((item, index) => (
              <article className="surface-card flex gap-4 p-6" key={item}>
                <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/10 text-sm font-semibold text-primary-100">
                  0{index + 1}
                </span>
                <p className="text-sm leading-7 text-zinc-300">{item}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="container-shell">
        <div className="panel-grid p-8 md:p-10">
          <div className="max-w-2xl space-y-4">
            <span className="section-label">Flow</span>
            <h2 className="font-heading text-3xl font-bold tracking-tight text-white md:text-4xl">A simple path from data to answers.</h2>
          </div>
          <div className="mt-8">
            <CardHoverEffect items={flowItems} />
          </div>
        </div>
      </section>
    </div>
  )
}
