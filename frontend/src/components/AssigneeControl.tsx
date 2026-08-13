import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  assignTicket,
  autoAssignTicket,
  getWorkload,
  type Ticket,
} from '@/features/tickets/api';
import { extractError } from '@/lib/api';
import { cn } from '@/lib/cn';
import { leaveLabel, rankCandidates } from '@/features/tickets/assignees';

interface Props {
  ticket: Ticket;
  /** Agent and above. Auditors and branch users get the read-only name. */
  canAssign: boolean;
  /** Supervisor and above. Only they may hand the choice to the router. */
  canAutoAssign: boolean;
}

/**
 * Who owns this ticket, and the means to change it.
 *
 * The assignee used to be a line of read-only text: the API could assign, but
 * nothing in the interface called it, so a ticket could never be handed over.
 *
 * Each candidate shows their open-ticket count, because that is the number the
 * router itself ranks on — a supervisor overriding it should be able to see
 * what they are overriding. People on leave stay in the list but are marked and
 * pushed to the bottom: a supervisor may knowingly assign to someone back
 * tomorrow, but should never do it by accident.
 */
export function AssigneeControl({ ticket, canAssign, canAutoAssign }: Props) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const workloadQuery = useQuery({
    queryKey: ['assignment', 'workload'],
    queryFn: getWorkload,
    enabled: open && canAssign,
    staleTime: 15_000,
  });

  const onDone = (updated: Ticket) => {
    queryClient.setQueryData(['tickets', ticket.id], updated);
    queryClient.invalidateQueries({ queryKey: ['assignment', 'workload'] });
    queryClient.invalidateQueries({ queryKey: ['tickets', ticket.id, 'timeline'] });
    setOpen(false);
    setError(null);
  };

  const assignMutation = useMutation({
    mutationFn: (userId: string) => assignTicket(ticket.id, userId),
    onSuccess: onDone,
    onError: (e) => setError(extractError(e).message),
  });

  const autoMutation = useMutation({
    mutationFn: () => autoAssignTicket(ticket.id),
    onSuccess: onDone,
    // The server answers with a real reason when nobody is available —
    // "everyone is on leave" is exactly what the supervisor needs to read.
    onError: (e) => setError(extractError(e).message),
  });

  const busy = assignMutation.isPending || autoMutation.isPending;
  const current = ticket.assignee?.full_name ?? null;

  if (!canAssign) {
    return <span className="text-slate-700 dark:text-slate-300">{current ?? 'Unassigned'}</span>;
  }

  const entries = rankCandidates(workloadQuery.data ?? []);

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-2">
        <span className={cn('text-slate-700 dark:text-slate-300', !current && 'italic text-[var(--tx-3)]')}>
          {current ?? 'Unassigned'}
        </span>
        <button
          type="button"
          onClick={() => { setOpen((v) => !v); setError(null); }}
          disabled={busy}
          // The status-transition row also has a button labelled "Assign" —
          // that one moves the ticket to the Assigned state, this one chooses
          // a person. Identical accessible names made them indistinguishable
          // to a screen reader, and to anything driving the page by role.
          aria-label={current ? 'Change who this ticket is assigned to' : 'Choose who to assign this ticket to'}
          className="text-xs text-[var(--brand)] hover:underline font-medium disabled:opacity-50"
        >
          {open ? 'Cancel' : current ? 'Reassign' : 'Assign'}
        </button>
      </div>

      {open && (
        <div className="mt-1 w-64 rounded-lg border border-[var(--line)] bg-[var(--surface)] p-2 shadow-sm">
          {canAutoAssign && (
            <button
              type="button"
              onClick={() => autoMutation.mutate()}
              disabled={busy}
              className={cn(
                'w-full rounded-md px-2 py-1.5 text-left text-xs font-semibold',
                'text-[var(--brand)] hover:bg-[var(--inset)] disabled:opacity-50',
              )}
            >
              {autoMutation.isPending ? 'Assigning…' : 'Auto-assign (lightest queue)'}
            </button>
          )}

          {workloadQuery.isLoading && (
            <p className="px-2 py-2 text-xs text-[var(--tx-3)]">Loading the queue…</p>
          )}
          {workloadQuery.isError && (
            <p className="px-2 py-2 text-xs text-[var(--err)]">
              Could not load who is available.
            </p>
          )}

          <div className="max-h-56 overflow-y-auto">
            {entries.map((e) => (
              <button
                key={e.user_id}
                type="button"
                onClick={() => assignMutation.mutate(e.user_id)}
                disabled={busy || e.user_id === ticket.assignee_id}
                title={e.leave_note ?? undefined}
                className={cn(
                  'flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left',
                  'hover:bg-[var(--inset)] disabled:opacity-40 disabled:hover:bg-transparent',
                )}
              >
                <span className="min-w-0">
                  <span className="block truncate text-xs text-[var(--tx)]">{e.full_name}</span>
                  <span className="block truncate text-[10px] text-[var(--tx-3)]">
                    {leaveLabel(e) ?? e.role}
                  </span>
                </span>
                <span
                  className={cn(
                    'shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold tabular-nums',
                    e.on_leave
                      ? 'bg-[var(--warn-bg)] text-[var(--warn)]'
                      : 'bg-[var(--inset)] text-[var(--tx-2)]',
                  )}
                >
                  {e.open_count} open
                </span>
              </button>
            ))}
            {workloadQuery.isSuccess && entries.length === 0 && (
              <p className="px-2 py-2 text-xs text-[var(--tx-3)]">
                Nobody can be assigned work right now.
              </p>
            )}
          </div>
        </div>
      )}

      {error && <p className="max-w-64 text-right text-[11px] text-[var(--err)]">{error}</p>}
    </div>
  );
}
