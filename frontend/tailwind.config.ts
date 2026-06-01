import type { Config } from 'tailwindcss';

/**
 * SUCCESS Bank design tokens — "old money" palette.
 *
 * Research-anchored to Brunello Cucinelli / Loro Piana / Aman / Hermès web:
 *   - paper base (never #fff)
 *   - deep forest as primary (was vibrant indigo)
 *   - burnished brass + oxblood as accents
 *   - warm taupes/walnuts for neutrals
 *   - text = espresso on cream, ivory on espresso (dark mode)
 *   - tailored radius (sm/md, not 2xl), no purple-tinted shadows
 *
 * `darkMode: 'class'` lets us toggle via <html class="dark">.
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Primary — Deep forest, the dominant brand color.
        brand: {
          50:  '#EEF1EC',
          100: '#D6DED1',
          200: '#A9B8A1',
          300: '#7A9171',
          400: '#506E48',
          500: '#365033',
          600: '#1F3A2E',     // primary forest — buttons, sidebar
          700: '#172C23',
          800: '#10211A',
          900: '#0A1611',
        },
        // Accent — Burnished brass for highlights, links, focus rings.
        accent: {
          50:  '#F5EFE2',
          100: '#E7DAB9',
          200: '#D2BC85',
          300: '#BA9D58',
          400: '#A88959',
          500: '#8E7042',
          600: '#705634',
        },
        // Oxblood — used very sparingly for danger / critical only.
        oxblood: {
          DEFAULT: '#7B2D26',
          50:  '#F4E6E4',
          100: '#E2BBB6',
          500: '#7B2D26',
          700: '#561F1B',
        },
        // Surfaces — cream paper tones, never pure white.
        cream: {
          50:  '#FBF8F1',
          100: '#F5F0E6',
          200: '#EBE3D2',
          300: '#DDD2BB',
          400: '#C8B998',
        },
        // Espresso / walnut text scale.
        ink: {
          50:  '#F5F2EC',
          100: '#E8E1D2',
          300: '#9C8E76',
          500: '#6E614C',
          700: '#3D332A',
          900: '#2A211B',
        },
        surface: {
          DEFAULT: '#FBF8F1',
          muted:   '#F5F0E6',
          subtle:  '#EBE3D2',
        },
        status: {
          new:        '#6E614C',
          ack:        '#365033',
          assigned:   '#A88959',
          progress:   '#1F3A2E',
          hold:       '#BA9D58',
          escalated:  '#7B2D26',
          resolved:   '#506E48',
          closed:     '#3D332A',
          reopened:   '#8E7042',
        },
      },
      borderRadius: {
        none: '0',
        sm:   '2px',
        DEFAULT: '4px',
        md:   '6px',
        lg:   '8px',
        xl:   '10px',
        '2xl': '12px',
      },
      boxShadow: {
        card:   '0 1px 2px 0 rgba(42, 33, 27, 0.06), 0 1px 1px 0 rgba(42, 33, 27, 0.04)',
        cardLg: '0 4px 10px -3px rgba(42, 33, 27, 0.10), 0 2px 4px -2px rgba(42, 33, 27, 0.06)',
        inset:  'inset 0 0 0 1px rgba(42, 33, 27, 0.08)',
        focus:  '0 0 0 3px rgba(168, 137, 89, 0.35)',
      },
      fontFamily: {
        sans:    ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['"Source Serif 4"', '"Cormorant Garamond"', 'Georgia', 'serif'],
      },
      letterSpacing: {
        tight: '-0.01em',
        wide:  '0.08em',
      },
    },
  },
  plugins: [],
} satisfies Config;
