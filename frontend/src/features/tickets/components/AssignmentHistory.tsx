import { useQuery } from '@tanstack/react-query';

import { Card } from '@/components/Card';
import { listAssignments } from '../workflow';
import { formatDateTime } from '@/lib/format';

export function AssignmentHistory({ ticketId }: { ticketId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['assignments', ticketId],
    queryFn: () => listAssignments(ticketId),
  });

  return (
    <Card>
      <h3 className="font-semibold">Assignment history</h3>
      <div className="mt-3 space-y-2 text-sm">
        {isLoading && <p className="text-slate-400">Loading…</p>}
        {!isLoading && (data?.length ?? 0) === 0 && <p className="text-slate-400">Never assigned.</p>}
        {data?.map((a) => (
          <div key={a.id} className="flex items-start justify-between border-b last:border-b-0 pb-2 dark:border-slate-800">
            <div className="min-w-0">
              <div>
                {a.assigned_to_user_id ? <code className="text-xs">user {a.assigned_to_user_id.slice(0, 8)}…</code> : '—'}
                {a.assigned_to_team_id && <> · <code className="text-xs">team {a.assigned_to_team_id.slice(0, 8)}…</code></>}
              </div>
              <div className="text-xs text-slate-500">
                by <code>{a.assigned_by.slice(0, 8)}</code> · {formatDateTime(a.assigned_at)}
                {a.unassigned_at && <> · until {formatDateTime(a.unassigned_at)}</>}
              </div>
              {a.reason && <div className="text-xs text-slate-500 mt-1">“{a.reason}”</div>}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
