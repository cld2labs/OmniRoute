import { useState } from 'react'

export default function CardHoverEffect({ items }) {
  const [hoveredIndex, setHoveredIndex] = useState(null)

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {items.map((item, index) => {
        const isActive = hoveredIndex === index

        return (
          <article
            className={`group relative overflow-hidden rounded-[28px] border p-6 transition duration-300 ${
              isActive
                ? 'border-primary/40 bg-primary/[0.08] shadow-[0_20px_60px_rgba(88,28,135,0.2)]'
                : 'border-white/10 bg-white/[0.04] hover:border-primary/25 hover:bg-white/[0.06]'
            }`}
            key={item.title}
            onMouseEnter={() => setHoveredIndex(index)}
            onMouseLeave={() => setHoveredIndex(null)}
          >
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,_rgba(168,85,247,0.16),_transparent_38%)] opacity-80" />
            <div className="relative flex h-full flex-col">
              <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-primary/20 bg-primary/10 text-sm font-semibold text-primary-100">
                {item.step}
              </span>
              <h3 className="mt-5 font-heading text-2xl font-bold text-white">{item.title}</h3>
              <p className="mt-3 text-sm leading-7 text-zinc-300">{item.description}</p>
            </div>
          </article>
        )
      })}
    </div>
  )
}
