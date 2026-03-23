/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#8B5CF6',
          50: '#F5F3FF',
          100: '#EDE9FE',
          400: '#A78BFA',
          500: '#8B5CF6',
          600: '#7C3AED',
          700: '#6D28D9',
        },
        surface: {
          950: '#05030A',
          900: '#0B0912',
          850: '#11101B',
          800: '#171522',
          700: '#242032',
        },
      },
      boxShadow: {
        soft: '0 18px 50px -24px rgba(8, 5, 17, 0.85)',
        glow: '0 0 0 1px rgba(167, 139, 250, 0.14), 0 24px 80px -32px rgba(124, 58, 237, 0.55)',
      },
      fontFamily: {
        sans: ['Manrope', 'Avenir Next', 'Segoe UI', 'sans-serif'],
        heading: ['Space Grotesk', 'Sora', 'Manrope', 'Avenir Next', 'sans-serif'],
      },
      keyframes: {
        spotlight: {
          '0%': { opacity: '0.22', transform: 'translate3d(0px, 0px, 0px) scale(1)' },
          '50%': { opacity: '0.42', transform: 'translate3d(0px, -8px, 0px) scale(1.04)' },
          '100%': { opacity: '0.22', transform: 'translate3d(0px, 0px, 0px) scale(1)' },
        },
        beam: {
          '0%': { transform: 'translateX(-26%)', opacity: '0' },
          '20%': { opacity: '0.32' },
          '100%': { transform: 'translateX(26%)', opacity: '0' },
        },
        pulseDot: {
          '0%, 80%, 100%': { transform: 'scale(0.75)', opacity: '0.35' },
          '40%': { transform: 'scale(1)', opacity: '1' },
        },
        floatField: {
          '0%, 100%': { transform: 'translate3d(0px, 0px, 0px)' },
          '50%': { transform: 'translate3d(0px, -10px, 0px)' },
        },
      },
      animation: {
        spotlight: 'spotlight 8s ease-in-out infinite',
        beam: 'beam 9s linear infinite',
        pulseDot: 'pulseDot 1.2s ease-in-out infinite',
        floatField: 'floatField 10s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
