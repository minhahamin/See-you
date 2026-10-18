/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#FFF1F5',
        surface: '#FFFFFF',
        primary: '#EE7BA6',
        'primary-ink': '#C2457A',
        'text-main': '#1F2937',
        'text-sub': '#9CA3AF',
        'cat-sight': '#22C55E',
        'cat-food': '#FF8A4C',
        'cat-cafe': '#FFC53D',
        'cat-stay': '#8B5CF6',
        'cat-activity': '#4FA3F7',
        changed: '#0D9488',
        // 토큰 표 외 보조색: 타임라인 행 배경, 비 오는 날 행 배경
        row: '#FFF8FB',
        rain: '#E8F2FF',
      },
      fontFamily: {
        sans: ['"Pretendard Variable"', 'Pretendard', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        soft: '0 12px 40px -12px rgba(238, 123, 166, 0.22)',
      },
    },
  },
  plugins: [],
};
