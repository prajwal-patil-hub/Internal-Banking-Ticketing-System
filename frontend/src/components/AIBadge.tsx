import { cn } from '@/lib/cn';

interface Props {
  category: string | null;
  confidence: number | null;
  riskScore: number | null;
  className?: string;
}

function confidenceClass(confidence: number): string {
  if (confidence >= 0.8) return 'bg-emerald-100 text-emerald-700';
  if (confidence >= 0.5) return 'bg-amber-100 text-amber-700';
  return 'bg-red-100 text-red-700';
}

function riskClass(risk: number): string {
  if (risk >= 0.7) return 'bg-red-100 text-red-700';
  if (risk >= 0.3) return 'bg-amber-100 text-amber-700';
  return 'bg-emerald-100 text-emerald-700';
}

function riskLabel(risk: number): string {
  if (risk >= 0.7) return 'High Risk';
  if (risk >= 0.3) return 'Med Risk';
  return 'Low Risk';
}

export function AIBadge({ category, confidence, riskScore, className }: Props) {
  if (!category && riskScore === null) return null;

  return (
    <span className={cn('inline-flex items-center gap-2 flex-wrap', className)}>
      {category && confidence !== null && (
        <span className={cn('pill text-xs', confidenceClass(confidence))}>
          <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2z" />
            <path d="M12 16v-4M12 8h.01" />
          </svg>
          AI: {category} ({Math.round(confidence * 100)}%)
        </span>
      )}
      {riskScore !== null && (
        <span className={cn('pill text-xs', riskClass(riskScore))}>
          <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 9v4M12 17h.01M4.93 19h14.14L12 5z" />
          </svg>
          {riskLabel(riskScore)} ({Math.round(riskScore * 100)}%)
        </span>
      )}
    </span>
  );
}
