import type { Config } from 'tailwindcss';

/**
 * SUCCESS Bank design tokens.
 *
 * Palette derived from reference UI:
 *   - sidebar / primary surface : deep indigo  (#3F2FBE family)
 *   - accent / interactive       : lavender    (#A78BFA family)
 *   - surface                    : white / slate-50
 *   - status pills               : success/info/warning/danger
 *
 * `darkMode: 'class'` lets us toggle via <html class="dark">.
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50:  '#EEEAFE',
          100: '#DAD0FB',
          200: '#B5A2F8',
          300: '#8E72F2',
          400: '#6A4DEB',
          500: '#4F36DC',  // primary
          600: '#3F2FBE',  // sidebar
          700: '#33269A',
          800: '#281D77',
          900: '#1C1455',
        },
        accent: {
          50:  '#F5F1FF',
          100: '#E9DFFF',
          200: '#D3BFFF',
          300: '#B89AFF',
          400: '#9B73FF',
          500: '#7E4DFF',
        },
        surface: {
          DEFAULT: '#FFFFFF',
          muted:   '#F6F4FB',
          subtle:  '#EEEBF6',
        },
        status: {
          new:        '#6B7280',
          ack:        '#3B82F6',
          assigned:   '#8B5CF6',
          progress:   '#0EA5E9',
          hold:       '#F59E0B',
          escalated:  '#EF4444',
          resolved:   '#10B981',
          closed:     '#1F2937',
          reopened:   '#DB2777',
        },
      },
      borderRadius: {
        '2xl': '1.25rem',
        '3xl': '1.75rem',
      },
      boxShadow: {
        card: '0 4px 16px -2px rgba(63, 47, 190, 0.08)',
        cardLg: '0 10px 30px -8px rgba(63, 47, 190, 0.18)',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config;
