import { cn } from '@/lib/cn';

interface Props {
  breached: boolean;
  dueAt: string | null;
  paused?: boolean;
  className?: string;
}

function formatTimeRemaining(dueAt: string): { label: string; atRisk: boolean } {
  const due = new Date(dueAt).getTime();
  const now = Date.now();
  const diffMs = due - now;
  const diffMins = Math.round(diffMs / 60_000);

  if (diffMs < 0) {
    // Past due
    const absMins = Math.abs(diffMins);
    if (absMins < 60) return { label: `${absMins}m overdue`, atRisk: false };
    const hrs = Math.floor(absMins / 60);
    const mins = absMins % 60;
    return { label: mins > 0 ? `${hrs}h ${mins}m overdue` : `${hrs}h overdue`, atRisk: false };
  }

  const atRisk = diffMs <= 30 * 60_000; // within 30 minutes

  if (diffMins < 60) return { label: `${diffMins}m left`, atRisk };
  const hrs = Math.floor(diffMins / 60);
  const mins = diffMins % 60;
  return { label: mins > 0 ? `${hrs}h ${mins}m left` : `${hrs}h left`, atRisk };
}

export function SLABadge({ breached, dueAt, paused = false, className }: Props) {
  if (paused) {
    return (
      <span className={cn('pill bg-slate-100 text-slate-600', className)}>
        <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M10 4H6v16h4V4zM18 4h-4v16h4V4z" />
        </svg>
        SLA Paused
      </span>
    );
  }

  if (breached) {
    const timeInfo = dueAt ? formatTimeRemaining(dueAt) : null;
    return (
      <span className={cn('pill bg-red-100 text-red-700', className)}>
        <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 9v4M12 17h.01M4.93 19h14.14L12 5z" />
        </svg>
        Breached
        {timeInfo && <span className="opacity-75 ml-0.5">· {timeInfo.label}</span>}
      </span>
    );
  }

  if (dueAt) {
    const { label, atRisk } = formatTimeRemaining(dueAt);
    if (atRisk) {
      return (
        <span className={cn('pill bg-amber-100 text-amber-700', className)}>
          <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 8v4l3 2" />
          </svg>
          At Risk · {label}
        </span>
      );
    }
    return (
      <span className={cn('pill bg-emerald-100 text-emerald-700', className)}>
        <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M20 12a8 8 0 1 1-16 0 8 8 0 0 1 16 0z" />
          <path d="M12 8v4l2 2" />
        </svg>
        SLA OK · {label}
      </span>
    );
  }

  return (
    <span className={cn('pill bg-emerald-100 text-emerald-700', className)}>
      <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M5 13l4 4L19 7" />
      </svg>
      SLA OK
    </span>
  );
}
