import { motion } from 'framer-motion';
import { cn } from '@/lib/cn';

interface Props {
  value: number;
  size?: number;
  stroke?: number;
  className?: string;
  label?: string;
}

/**
 * Premium SVG progress ring with gradient stroke and inset typography.
 */
export function Ring({ value, size = 132, stroke = 12, className, label }: Props) {
  const v = Math.max(0, Math.min(100, value));
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const dash = (v / 100) * c;
  const tone = v >= 80 ? 'good' : v >= 50 ? 'mid' : 'bad';
  const grad = {
    good: ['#10B981', '#34D399'],
    mid:  ['#F59E0B', '#FBBF24'],
    bad:  ['#EF4444', '#F87171'],
  }[tone];

  return (
    <div className={cn('relative inline-flex flex-col items-center', className)}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}
           className="-rotate-90"
           style={{ overflow: 'visible' }}>
        <defs>
          <linearGradient id={`ring-grad-${tone}`} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%"  stopColor={grad[0]} />
            <stop offset="100%" stopColor={grad[1]} />
          </linearGradient>
        </defs>
        <circle
          cx={size / 2} cy={size / 2} r={r}
          stroke="rgba(99,102,241,0.10)" strokeWidth={stroke} fill="none"
        />
        <motion.circle
          cx={size / 2} cy={size / 2} r={r}
          stroke={`url(#ring-grad-${tone})`} strokeWidth={stroke} fill="none"
          strokeLinecap="round"
          initial={{ strokeDasharray: `0 ${c}` }}
          animate={{ strokeDasharray: `${dash} ${c - dash}` }}
          transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-3xl font-semibold tracking-tight text-ink tabular-nums">
          {v}<span className="text-sm text-ink-muted ml-0.5">%</span>
        </div>
        {label && (
          <div className="text-2xs uppercase tracking-wider text-ink-muted mt-0.5">{label}</div>
        )}
      </div>
    </div>
  );
}
