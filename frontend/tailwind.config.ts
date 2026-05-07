import type { Config } from 'tailwindcss';

/**
 * SUCCESS Bank — 2026 design system.
 *
 * Light, glassmorphic, premium. Tokens curated for an enterprise fintech
 * aesthetic inspired by Linear / Stripe / Ramp / Revolut Business / Notion.
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Surfaces
        canvas: {
          DEFAULT: '#F5F7FB',
          alt:     '#EEF2FF',
        },
        ink: {
          DEFAULT: '#111827',
          muted:   '#6B7280',
          subtle:  '#9CA3AF',
        },
        // Brand (indigo blue)
        brand: {
          50:  '#EEF2FF',
          100: '#E0E7FF',
          200: '#C7D2FE',
          300: '#A5B4FC',
          400: '#818CF8',
          500: '#6366F1',
          600: '#4F46E5',  // primary
          700: '#4338CA',
          800: '#3730A3',
          900: '#312E81',
        },
        accent: {
          50:  '#F5F3FF',
          100: '#EDE9FE',
          200: '#DDD6FE',
          400: '#A78BFA',
          500: '#8B5CF6',
        },
        success: { DEFAULT: '#10B981', soft: 'rgba(16,185,129,0.12)', deep: '#059669' },
        warning: { DEFAULT: '#F59E0B', soft: 'rgba(245,158,11,0.12)', deep: '#D97706' },
        danger:  { DEFAULT: '#EF4444', soft: 'rgba(239,68,68,0.12)',  deep: '#DC2626' },
        info:    { DEFAULT: '#3B82F6', soft: 'rgba(59,130,246,0.12)', deep: '#2563EB' },
        // Legacy alias kept so existing classes don't break during the
        // visual migration (e.g. "bg-surface-muted").
        surface: {
          DEFAULT: '#FFFFFF',
          muted:   '#F5F7FB',
          subtle:  '#EEF2FF',
        },
      },
      borderRadius: {
        pill: '9999px',
        lg: '12px',
        xl: '14px',
        '2xl': '16px',
        '3xl': '20px',
        '4xl': '24px',
        '5xl': '32px',
      },
      boxShadow: {
        glass:    '0 8px 32px rgba(31,38,135,0.06)',
        glassLg:  '0 20px 60px rgba(31,38,135,0.12)',
        soft:     '0 1px 2px rgba(17,24,39,0.04), 0 8px 24px rgba(17,24,39,0.04)',
        ring:     '0 0 0 4px rgba(99,102,241,0.10)',
        glow:     '0 8px 24px rgba(79,70,229,0.18)',
        // Legacy aliases
        card:     '0 8px 32px rgba(31,38,135,0.06)',
        cardLg:   '0 20px 60px rgba(31,38,135,0.12)',
      },
      backdropBlur: {
        xs: '2px',
        sm: '6px',
      },
      fontFamily: {
        sans: ['Inter', 'SF Pro Display', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        '2xs':  ['11px', { lineHeight: '14px' }],
        xs:     ['12px', { lineHeight: '16px' }],
        sm:     ['13px', { lineHeight: '18px' }],
        base:   ['14px', { lineHeight: '22px' }],
        md:     ['15px', { lineHeight: '22px' }],
        lg:     ['16px', { lineHeight: '24px' }],
        xl:     ['18px', { lineHeight: '26px' }],
        '2xl':  ['20px', { lineHeight: '28px' }],
        '3xl':  ['24px', { lineHeight: '32px' }],
        '4xl':  ['28px', { lineHeight: '36px' }],
        '5xl':  ['32px', { lineHeight: '40px' }],
        '6xl':  ['40px', { lineHeight: '48px' }],
      },
      letterSpacing: {
        tightish: '-0.011em',
        tight:    '-0.02em',
      },
      backgroundImage: {
        'app-canvas':
          "radial-gradient(circle at 8% 0%, rgba(99,102,241,0.10), transparent 38%), " +
          "radial-gradient(circle at 95% 100%, rgba(16,185,129,0.07), transparent 36%), " +
          "radial-gradient(circle at 60% 18%, rgba(167,139,250,0.06), transparent 30%), " +
          "linear-gradient(180deg, #F7F9FE 0%, #F5F7FB 100%)",
        'sidebar-active':
          'linear-gradient(135deg, rgba(79,70,229,0.18), rgba(99,102,241,0.08))',
        'btn-primary':
          'linear-gradient(135deg, #4F46E5 0%, #6366F1 100%)',
        'btn-primary-hover':
          'linear-gradient(135deg, #4338CA 0%, #4F46E5 100%)',
        'sla-good':
          'linear-gradient(135deg, rgba(16,185,129,0.18), rgba(52,211,153,0.10))',
        'sla-bad':
          'linear-gradient(135deg, rgba(239,68,68,0.18), rgba(248,113,113,0.10))',
      },
      transitionTimingFunction: {
        smooth: 'cubic-bezier(0.22, 1, 0.36, 1)',
      },
      keyframes: {
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.35s ease-out both',
      },
    },
  },
  plugins: [],
} satisfies Config;
