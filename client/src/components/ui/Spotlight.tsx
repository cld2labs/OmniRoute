export default function Spotlight({ className = '' }) {
  return (
    <div
      aria-hidden="true"
      className={`pointer-events-none absolute h-[28rem] w-[28rem] rounded-full bg-[radial-gradient(circle,_rgba(139,92,246,0.34)_0%,_rgba(124,58,237,0.15)_38%,_transparent_72%)] blur-3xl ${className}`}
    />
  )
}
