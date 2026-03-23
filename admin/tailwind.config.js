/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        'off-black': '#232222',
        'off-white': '#F4F4F4',
        brown: '#91877A',
        beige: '#E5E6DF',
        navy: '#002656',
        'brand-blue': '#3164FD',
        'blue-light': '#4AA1FF',
        red: '#C41230',
        orange: '#FF8D5A',
        yellow: '#F7E36E',
      },
      fontFamily: {
        sans: ['"Host Grotesk"', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        h1: ['3.3333rem', { lineHeight: '3.7778rem', fontWeight: '400' }],
        h2: ['2.3333rem', { lineHeight: '2.6667rem', fontWeight: '400' }],
        h5: ['1.1111rem', { lineHeight: '1.3333rem', fontWeight: '600' }],
        body: ['0.9375rem', { lineHeight: '1.375rem', fontWeight: '400' }],
        'label-sm': ['0.75rem', { lineHeight: '1rem', fontWeight: '600', letterSpacing: '0.05em' }],
      },
    },
  },
  plugins: [],
}
