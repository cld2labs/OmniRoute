const beamRows = ['top-12', 'top-24', 'top-40', 'top-56', 'top-72']

export default function BackgroundBeams() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      {beamRows.map((row, index) => (
        <span
          key={row}
          className={`absolute left-[-25%] ${row} h-px w-[150%] bg-gradient-to-r from-transparent via-primary/35 to-transparent animate-beam ${
            index % 2 === 0 ? '' : '[animation-delay:1.8s]'
          }`}
        />
      ))}
    </div>
  )
}
