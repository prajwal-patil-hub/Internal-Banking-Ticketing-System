import type { Config } from 'tailwindcss';

/**
 * SUCCESS Bank — Warm Neumorphic Design System
 *
 * Brand: deep teal (#0F5C5C family)
 * Surface: warm cream (#EDE4D8) — same as background; shadows do the depth work
 * Shadow pair: dark (#C8BAA8 ↘) + light (#FFFFFF ↖)
 * Status: unchanged semantic palette
 *
 * darkMode: 'class' — toggle via <html class="dark">
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Brand — teal
        brand: {
          50:  '#D6ECEC',
          100: '#A8D8D8',
          200: '#70BCBC',
          300: '#3DBCBC',
          400: '#2AAFAF',
          500: '#1A7A7A',
          600: '#0F5C5C',  // primary
          700: '#0A4444',
          800: '#073333',
          900: '#041F1F',
        },
        // Warm cream surface — key: same tone as background
        surface: {
          DEFAULT: '#EDE4D8',
          raised:  '#F0E7DB',
          inset:   '#E8DFCF',
          // Dark mode surfaces
          dark:       '#1A2828',
          'dark-raised': '#1E2E2E',
          'dark-inset':  '#162020',
        },
        // Shadow pair — derived from cream bg
        shadow: {
          warm:  '#C8BAA8',
          light: '#FFFFFF',
        },
        // Text on warm background
        ink: {
          DEFAULT: '#1A1A1C',
          muted:   '#4A4A4C',
          faint:   '#8A8A8C',
          'on-brand': '#FFFFFF',
        },
        // Semantic status (unchanged)
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
        'xs':  '4px',
        'sm':  '8px',
        'md':  '12px',
        'lg':  '16px',
        'xl':  '24px',
        '2xl': '32px',
        'full': '9999px',
      },
      boxShadow: {
        // Neumorphic raised elevations — dual shadow (dark ↘ + light ↖)
        'neu-xs': '2px 2px 5px #C8BAA8, -2px -2px 5px #FFFFFF',
        'neu-sm': '4px 4px 8px #C8BAA8, -4px -4px 8px #FFFFFF',
        'neu-md': '8px 8px 16px #C8BAA8, -8px -8px 16px #FFFFFF',
        'neu-lg': '12px 12px 24px rgba(180,160,136,.55), -12px -12px 24px rgba(255,255,255,.90)',
        // Neumorphic inset (sunken) — inputs, pressed states
        'neu-in':      'inset 3px 3px 7px #C8BAA8, inset -3px -3px 7px #FFFFFF',
        'neu-in-deep': 'inset 5px 5px 10px #C8BAA8, inset -5px -5px 10px #FFFFFF',
        // Pressed button
        'neu-btn-press': 'inset 3px 3px 6px rgba(10,68,68,.30), inset -2px -2px 4px rgba(40,120,120,.10)',
        // Overlay drop shadow (modals, toasts)
        'drop-md': '0 10px 32px rgba(120,100,80,.22)',
        'drop-lg': '0 20px 56px rgba(100,80,60,.30)',
        // Legacy alias (keeps existing .card working)
        card:   '4px 4px 8px #C8BAA8, -4px -4px 8px #FFFFFF',
        cardLg: '8px 8px 16px #C8BAA8, -8px -8px 16px #FFFFFF',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['SF Mono', 'Fira Mono', 'ui-monospace', 'monospace'],
      },
      transitionDuration: {
        fast: '100ms',
        base: '160ms',
        slow: '260ms',
      },
    },
  },
  plugins: [],
} satisfies Config;
