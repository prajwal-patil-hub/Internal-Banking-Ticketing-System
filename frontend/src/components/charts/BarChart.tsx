import { motion } from 'framer-motion';

interface Row {
  label: string;
  value: number;
  /** Optional secondary value (e.g. critical-only count). */
  highlight?: number;
  /** Optional tone override. */
  tone?: 'brand' | 'success' | 'warning' | 'danger' | 'info' | 'brass';
}

interface Props {
  rows: Row[];
  formatValue?: (v: number) => string;
  showHighlight?: boolean;
  className?: string;
}

const TONE_BG: Record<NonNullable<Row['tone']>, string> = {
  brand:   'bg-brand-600',
  success: 'bg-success',
  warning: 'bg-warning',
  danger:  'bg-danger',
  info:    'bg-info',
  brass:   'bg-brass-500',
};
const TONE_HL: Record<NonNullable<Row['tone']>, string> = {
  brand:   'bg-brand-800',
  success: 'bg-success-deep',
  warning: 'bg-warning-deep',
  danger:  'bg-danger-deep',
  info:    'bg-info-deep',
  brass:   'bg-brass-600',
};

/**
 * Horizontal bar chart. CSS-only — values mapped to width %.
 * Designed for short categorical series like by-priority or by-category.
 */
export function BarChart({ rows, formatValue = (v) => String(v), showHighlight = false, className }: Props) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div className={className}>
      <div className="space-y-3">
        {rows.length === 0 && (
          <div className="text-sm text-ink-muted">No data.</div>
        )}
        {rows.map((r, i) => {
          const tone = r.tone ?? 'brand';
          const widthPct = (r.value / max) * 100;
          const hlPct = r.highlight && r.value
            ? Math.max(0, Math.min(100, (r.highlight / r.value) * widthPct))
            : 0;
          return (
            <div key={`${r.label}-${i}`}>
              <div className="flex items-center justify-between gap-3 mb-1">
                <span className="text-sm text-ink truncate">{r.label}</span>
                <span className="text-sm font-semibold tabular-nums text-ink">
                  {formatValue(r.value)}
                  {showHighlight && r.highlight ? (
                    <span className="text-2xs text-ink-muted ml-1.5">({r.highlight})</span>
                  ) : null}
                </span>
              </div>
              <div className="relative h-2 rounded-pill bg-canvas-alt overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${widthPct}%` }}
                  transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
                  className={`absolute inset-y-0 left-0 ${TONE_BG[tone]} rounded-pill`}
                />
                {showHighlight && hlPct > 0 && (
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${hlPct}%` }}
                    transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: 0.05 }}
                    className={`absolute inset-y-0 left-0 ${TONE_HL[tone]} rounded-pill opacity-90`}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
