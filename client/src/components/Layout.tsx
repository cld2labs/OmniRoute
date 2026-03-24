import { Outlet } from 'react-router-dom'
import Footer from './Footer'
import Navbar from './Navbar'

export default function Layout() {
  return (
    <div className="min-h-screen bg-surface-950 text-zinc-100">
      <Navbar />
      <main className="relative">
        <Outlet />
      </main>
      <Footer />
    </div>
  )
}
