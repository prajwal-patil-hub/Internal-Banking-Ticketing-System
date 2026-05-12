import type { Config } from 'tailwindcss';

/**
 * SUCCESS Bank — Old-money palette.
 *
 * Inspired by the printed annual reports of private banks: warm
 * parchment paper, deep Oxford / Yale navy ink, claret seals, antique
 * brass rules, hunter / sage accents. Muted, never neon.
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // ─── Surfaces ─────────────────────────────────────────────
        canvas: {
          DEFAULT: '#F5F1E8',  // parchment
          alt:     '#EFE8DA',  // warm cream
          raised:  '#FBF7EE',  // ivory paper
        },
        // ─── Ink (text) ───────────────────────────────────────────
        ink: {
          DEFAULT: '#1B1F2A',  // warm charcoal — never pure black
          muted:   '#56616F',  // graphite
          subtle:  '#8B95A2',  // taupe-grey
        },
        // ─── Brand — Oxford / Yale navy ───────────────────────────
        brand: {
          50:  '#E6EAF1',
          100: '#C7CFDD',
          200: '#99A6BC',
          300: '#6B7E9B',
          400: '#44597A',
          500: '#2A4366',
          600: '#1F3A5F',  // primary
          700: '#182D49',
          800: '#112236',
          900: '#0B1929',
        },
        // ─── Accent — claret / oxblood ────────────────────────────
        accent: {
          50:  '#F4E9EB',
          100: '#E6CCD2',
          200: '#CD9AA5',
          300: '#A55E6E',
          400: '#7E3848',
          500: '#6B2737',
          600: '#5A1F2D',
        },
        // ─── Brass / antique gold (rules, hairlines, prestige) ────
        brass: {
          100: '#F2EAD5',
          300: '#D9C68B',
          500: '#B8965A',
          600: '#9C7E48',
          soft: 'rgba(184,150,90,0.10)',
        },
        // ─── Status (functional but desaturated) ──────────────────
        success: { DEFAULT: '#4A7C59', soft: 'rgba(74,124,89,0.10)',  deep: '#3F6A4D' },
        warning: { DEFAULT: '#B8860B', soft: 'rgba(184,134,11,0.12)', deep: '#8E670A' },
        danger:  { DEFAULT: '#8B2635', soft: 'rgba(139,38,53,0.10)',  deep: '#6F1E2A' },
        info:    { DEFAULT: '#4A6FA5', soft: 'rgba(74,111,165,0.10)', deep: '#3A5784' },
        // ─── Legacy aliases (so older classes still resolve) ──────
        surface: {
          DEFAULT: '#FBF7EE',
          muted:   '#F5F1E8',
          subtle:  '#EFE8DA',
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
        glass:    '0 8px 32px rgba(31,58,95,0.08)',
        glassLg:  '0 20px 60px rgba(31,58,95,0.14)',
        soft:     '0 1px 2px rgba(27,31,42,0.04), 0 8px 24px rgba(27,31,42,0.05)',
        ring:     '0 0 0 4px rgba(31,58,95,0.10)',
        glow:     '0 8px 24px rgba(31,58,95,0.20)',
        // Legacy
        card:     '0 8px 32px rgba(31,58,95,0.08)',
        cardLg:   '0 20px 60px rgba(31,58,95,0.14)',
      },
      backdropBlur: { xs: '2px', sm: '6px' },
      fontFamily: {
        sans: ['Inter', 'SF Pro Display', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        serif: ['"Fraunces"', '"Playfair Display"', 'Georgia', 'ui-serif', 'serif'],
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
          "radial-gradient(circle at 8% 0%, rgba(31,58,95,0.07), transparent 38%), " +
          "radial-gradient(circle at 95% 100%, rgba(184,150,90,0.08), transparent 36%), " +
          "radial-gradient(circle at 60% 18%, rgba(107,39,55,0.04), transparent 30%), " +
          "linear-gradient(180deg, #FBF7EE 0%, #F5F1E8 100%)",
        'sidebar-active':
          'linear-gradient(135deg, rgba(31,58,95,0.14), rgba(184,150,90,0.10))',
        'btn-primary':
          'linear-gradient(135deg, #1F3A5F 0%, #2A4366 100%)',
        'btn-primary-hover':
          'linear-gradient(135deg, #182D49 0%, #1F3A5F 100%)',
        'sla-good':
          'linear-gradient(135deg, rgba(74,124,89,0.18), rgba(74,124,89,0.08))',
        'sla-bad':
          'linear-gradient(135deg, rgba(139,38,53,0.18), rgba(139,38,53,0.08))',
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
