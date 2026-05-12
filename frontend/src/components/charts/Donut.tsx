import { motion } from 'framer-motion';
import { cn } from '@/lib/cn';

interface Slice {
  label: string;
  value: number;
  color: string;
}

interface Props {
  slices: Slice[];
  size?: number;
  stroke?: number;
  className?: string;
  centerLabel?: string;
  centerValue?: string;
}

/**
 * Donut chart. Each slice rendered as a stroke arc.
 */
export function Donut({
  slices,
  size = 200,
  stroke = 22,
  className,
  centerLabel,
  centerValue,
}: Props) {
  const total = slices.reduce((s, x) => s + x.value, 0);
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;

  let cursor = 0;
  const arcs = slices
    .filter((s) => s.value > 0)
    .map((s, i) => {
      const frac = total > 0 ? s.value / total : 0;
      const len = frac * c;
      const dasharray = `${len} ${c - len}`;
      const dashoffset = -cursor;
      cursor += len;
      return { ...s, len, dasharray, dashoffset, i };
    });

  return (
    <div className={cn('flex items-center gap-5', className)}>
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            stroke="rgba(31,58,95,0.08)"
            strokeWidth={stroke}
            fill="none"
          />
          {arcs.map((a) => (
            <motion.circle
              key={a.label}
              cx={size / 2}
              cy={size / 2}
              r={r}
              stroke={a.color}
              strokeWidth={stroke}
              fill="none"
              strokeLinecap="butt"
              initial={{ strokeDasharray: `0 ${c}`, strokeDashoffset: 0 }}
              animate={{ strokeDasharray: a.dasharray, strokeDashoffset: a.dashoffset }}
              transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: a.i * 0.06 }}
            />
          ))}
        </svg>
        <div className="absolute inset-0 grid place-items-center text-center">
          <div>
            <div className="text-2xs uppercase tracking-[0.18em] text-ink-muted">{centerLabel ?? 'total'}</div>
            <div className="text-3xl font-semibold tabular-nums text-ink">{centerValue ?? total}</div>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        {slices.map((s) => {
          const pct = total > 0 ? Math.round((s.value / total) * 100) : 0;
          return (
            <div key={s.label} className="flex items-center gap-2 text-sm">
              <span
                className="h-2.5 w-2.5 rounded-pill shrink-0"
                style={{ background: s.color }}
                aria-hidden
              />
              <span className="text-ink capitalize flex-1">{s.label}</span>
              <span className="tabular-nums text-ink-muted text-2xs">{s.value} · {pct}%</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
