import { useQuery } from '@tanstack/react-query';
import { History } from 'lucide-react';

import { Card } from '@/components/Card';
import { Skeleton } from '@/components/Skeleton';
import { listAssignments } from '../workflow';
import { formatDateTime } from '@/lib/format';

export function AssignmentHistory({ ticketId }: { ticketId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['assignments', ticketId],
    queryFn: () => listAssignments(ticketId),
  });

  return (
    <Card>
      <h3 className="h-card flex items-center gap-2">
        <History className="h-4 w-4 text-brand-600" />
        Assignment history
      </h3>
      <ul className="mt-3 space-y-3">
        {isLoading && Array.from({ length: 2 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" rounded="xl" />
        ))}
        {!isLoading && (data?.length ?? 0) === 0 && (
          <p className="text-sm text-ink-muted">Never assigned.</p>
        )}
        {data?.map((a, i) => (
          <li key={a.id} className="relative pl-5 text-sm">
            <span className={`absolute left-1 top-1.5 h-2 w-2 rounded-pill ${a.unassigned_at ? 'bg-ink-subtle' : 'bg-brand-600'}`} />
            {i < (data.length - 1) && (
              <span className="absolute left-[7px] top-3 bottom-[-12px] w-px bg-white/60" />
            )}
            <div className="text-ink">
              {a.assigned_to_user_id ? (
                <code className="text-2xs text-ink">user {a.assigned_to_user_id.slice(0, 8)}</code>
              ) : <span className="text-ink-subtle">—</span>}
              {a.assigned_to_team_id && (
                <> · <code className="text-2xs">team {a.assigned_to_team_id.slice(0, 8)}</code></>
              )}
            </div>
            <div className="text-2xs text-ink-muted">
              by <code>{a.assigned_by.slice(0, 8)}</code> · {formatDateTime(a.assigned_at)}
              {a.unassigned_at && <> · until {formatDateTime(a.unassigned_at)}</>}
            </div>
            {a.reason && <div className="text-2xs text-ink-muted mt-1 italic">“{a.reason}”</div>}
          </li>
        ))}
      </ul>
    </Card>
  );
}
