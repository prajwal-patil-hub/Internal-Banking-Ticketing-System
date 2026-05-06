import { cn } from '@/lib/cn';

interface Props {
  value: number;
  size?: number;
  stroke?: number;
  className?: string;
  label?: string;
}

export function Ring({ value, size = 120, stroke = 12, className, label }: Props) {
  const v = Math.max(0, Math.min(100, value));
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const dash = (v / 100) * c;
  const tone = v >= 80 ? 'text-emerald-500' : v >= 50 ? 'text-amber-500' : 'text-red-500';

  return (
    <div className={cn('inline-flex flex-col items-center gap-1', className)}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle
          cx={size / 2} cy={size / 2} r={r}
          stroke="currentColor" strokeWidth={stroke} fill="none"
          className="text-slate-200 dark:text-slate-700"
        />
        <circle
          cx={size / 2} cy={size / 2} r={r}
          stroke="currentColor" strokeWidth={stroke} fill="none"
          strokeDasharray={`${dash} ${c - dash}`} strokeLinecap="round"
          className={tone}
        />
      </svg>
      <div className="text-center -mt-[calc(50%+10px)] pointer-events-none select-none">
        <div className="text-2xl font-semibold">{v}<span className="text-sm text-slate-500">%</span></div>
        {label && <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>}
      </div>
    </div>
  );
}
