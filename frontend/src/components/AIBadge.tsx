import { cn } from '@/lib/cn';

/**
 * The AI category and risk pills on a ticket.
 *
 * `riskBand` comes from the API and is rendered as given. This component used
 * to derive the band itself with 0.7/0.3 cut-offs while the backend banded at
 * 0.7/0.4, so a ticket scored 0.35 showed "Med Risk" here and was returned as
 * low risk by every list filter and dashboard tile — the same number
 * contradicting itself depending on the screen. One owner per threshold, and
 * it is the server.
 */

export type RiskBand = 'high' | 'medium' | 'low';

interface Props {
  category: string | null;
  confidence: number | null;
  riskScore: number | null;
  riskBand: RiskBand | null;
  className?: string;
}

function confidenceClass(confidence: number): string {
  if (confidence >= 0.8) return 'bg-emerald-100 text-emerald-700';
  if (confidence >= 0.5) return 'bg-amber-100 text-amber-700';
  return 'bg-red-100 text-red-700';
}

const BAND_META: Record<RiskBand, { label: string; className: string }> = {
  high:   { label: 'High Risk', className: 'bg-red-100 text-red-700' },
  medium: { label: 'Med Risk',  className: 'bg-amber-100 text-amber-700' },
  low:    { label: 'Low Risk',  className: 'bg-emerald-100 text-emerald-700' },
};

export function AIBadge({ category, confidence, riskScore, riskBand, className }: Props) {
  if (!category && riskScore === null) return null;

  // A score with no band means an API older than the banding change. Showing
  // the percentage without a verdict is honest; guessing the verdict here is
  // how the two drifted apart in the first place.
  const band = riskBand ? BAND_META[riskBand] : null;

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
        <span className={cn('pill text-xs', band?.className ?? 'bg-slate-100 text-slate-700')}>
          <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 9v4M12 17h.01M4.93 19h14.14L12 5z" />
          </svg>
          {band ? `${band.label} (${Math.round(riskScore * 100)}%)` : `Risk ${Math.round(riskScore * 100)}%`}
        </span>
      )}
    </span>
  );
}
