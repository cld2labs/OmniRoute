import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import logo from '../assets/cloud2labs-logo.png'

export default function Navbar() {
  const [isScrolled, setIsScrolled] = useState(false)
  const location = useLocation()

  useEffect(() => {
    const onScroll = () => setIsScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })

    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header
      className={`sticky top-0 z-50 bg-surface-950/78 backdrop-blur-xl transition-shadow duration-300 ${
        isScrolled ? 'shadow-soft' : 'shadow-none'
      }`}
    >
      <div className="container-shell flex h-16 items-center justify-between gap-4">
        <Link className="flex items-center gap-3" to="/">
          <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-white/[0.05] p-2 shadow-soft">
            <img alt="Cloud2Labs logo" className="h-8 w-auto brightness-110" src={logo} />
          </div>
          <div className="leading-tight">
            <p className="font-heading text-base font-semibold tracking-tight text-white">OmniRoute</p>
            <p className="text-xs text-zinc-400">Transportation Operations Intelligence</p>
          </div>
        </Link>

        <nav className="flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.04] p-1.5 backdrop-blur">
          {[
            ['/', 'Home'],
            ['/chat', 'Chat'],
            ['/upload', 'Upload'],
          ].map(([to, label]) => (
            <Link
              className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                location.pathname === to ? 'bg-primary text-white shadow-glow' : 'text-zinc-300 hover:bg-white/[0.06] hover:text-white'
              }`}
              key={to}
              to={to}
            >
              {label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  )
}
