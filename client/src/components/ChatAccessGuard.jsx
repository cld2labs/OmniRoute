import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getRoutes } from '../lib/apiClient'

function LoadingState() {
  return (
    <section className="container-shell py-12 md:py-16">
      <div className="mx-auto max-w-6xl">
        <section className="surface-card flex min-h-[46rem] items-center justify-center px-6 py-10">
          <div className="flex items-center gap-3 text-sm text-zinc-300">
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-primary" />
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-primary [animation-delay:0.15s]" />
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-primary [animation-delay:0.3s]" />
            <span className="ml-2">Checking route data before opening chat.</span>
          </div>
        </section>
      </div>
    </section>
  )
}

function MissingDataModal({ onConfirm }) {
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-surface-950/82 px-4 backdrop-blur-md">
      <div className="surface-card w-full max-w-md rounded-[30px] p-7 shadow-[0_24px_90px_rgba(0,0,0,0.45)]">
        <span className="section-label">Chat unavailable</span>
        <h2 className="mt-5 font-heading text-2xl font-bold tracking-tight text-white">Add route data before using chat.</h2>
        <p className="mt-3 text-sm leading-7 text-zinc-300">
          OmniRoute needs route data in the database before the chat section can answer grounded operational questions.
        </p>
        <p className="mt-2 text-sm leading-7 text-zinc-400">Click OK to go to the upload section and load your data.</p>
        <div className="mt-6 flex justify-end">
          <button className="button-primary min-w-[120px]" onClick={onConfirm} type="button">
            OK
          </button>
        </div>
      </div>
    </div>
  )
}

export default function ChatAccessGuard({ children }) {
  const navigate = useNavigate()
  const [status, setStatus] = useState('checking')

  useEffect(() => {
    let isMounted = true

    const checkRoutes = async () => {
      try {
        const data = await getRoutes()
        if (!isMounted) {
          return
        }
        setStatus(Array.isArray(data?.routes) && data.routes.length > 0 ? 'allowed' : 'missing')
      } catch {
        if (isMounted) {
          setStatus('allowed')
        }
      }
    }

    void checkRoutes()

    return () => {
      isMounted = false
    }
  }, [])

  if (status === 'checking') {
    return <LoadingState />
  }

  if (status === 'missing') {
    return <MissingDataModal onConfirm={() => navigate('/upload', { replace: true })} />
  }

  return children
}
