import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/Button';
import { cn } from '@/lib/cn';
import { extractError } from '@/lib/api';
import {
  getTicketTimeline,
  escalateTicket,
  type TimelineEvent,
  type TimelineKind,
  type Ticket,
} from '@/features/tickets/api';
import { useAuth } from '@/store/auth';

/**
 * The ticket's history as one vertical thread.
 *
 * Events come from three tables — comments, the audit log and escalation
 * events — merged server-side. Rendering them together is the point: reading a
 * ticket's story previously meant opening three different views and mentally
 * interleaving the timestamps.
 */

const KIND_STYLE: Record<TimelineKind, { ring: string; icon: string; path: string }> = {
  created:       { ring: 'bg-[var(--brand-xs)] text-[var(--brand)]', icon: 'plus',   path: 'M12 5v14M5 12h14' },
  comment:       { ring: 'bg-[var(--brand-xs)] text-[var(--brand)]', icon: 'chat',   path: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z' },
  internal_note: { ring: 'bg-[var(--brand-xs)] text-[var(--brand)]', icon: 'note',   path: 'M4 5h16v14H4zM8 9h8M8 13h5' },
  status_change: { ring: 'bg-[var(--warn-bg)] text-[var(--warn)]',   icon: 'arrow',  path: 'M4 12h16M14 6l6 6-6 6' },
  assignment:    { ring: 'bg-[var(--brand-xs)] text-[var(--brand)]', icon: 'user',   path: 'M16 11a4 4 0 1 0-8 0 4 4 0 0 0 8 0zM3 21a8 8 0 0 1 16 0' },
  escalation:    { ring: 'bg-[var(--err-bg)] text-[var(--err)]',     icon: 'up',     path: 'M12 19V5M5 12l7-7 7 7' },
  resolved:      { ring: 'bg-[var(--ok-bg)] text-[var(--ok)]',       icon: 'check',  path: 'M20 6 9 17l-5-5' },
  closed:        { ring: 'bg-[var(--ok-bg)] text-[var(--ok)]',       icon: 'lock',   path: 'M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4' },
};

function formatWhen(iso: string): string {
  const at = new Date(iso);
  const now = new Date();
  const sameDay = at.toDateString() === now.toDateString();
  const time = at.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

  if (sameDay) return `Today ${time}`;

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (at.toDateString() === yesterday.toDateString()) return `Yesterday ${time}`;

  return `${at.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })} ${time}`;
}

/** "2:14 overdue" — how late the escalation was, when we can tell. */
function overdueSuffix(event: TimelineEvent, ticket: Ticket): string | null {
  if (event.kind !== 'escalation' || !ticket.resolution_due_at) return null;
  const lateMs = new Date(event.at).getTime() - new Date(ticket.resolution_due_at).getTime();
  if (lateMs <= 0) return null;
  const hours = Math.floor(lateMs / 3.6e6);
  const mins = Math.floor((lateMs % 3.6e6) / 6e4);
  return `${hours}:${String(mins).padStart(2, '0')} overdue`;
}

function TimelineRow({
  event, ticket, isLast,
}: { event: TimelineEvent; ticket: Ticket; isLast: boolean }) {
  const style = KIND_STYLE[event.kind] ?? KIND_STYLE.comment;
  const overdue = overdueSuffix(event, ticket);

  return (
    <li className="relative flex gap-3 pb-5 last:pb-0">
      {/* The thread. Stops at the last node so it does not dangle. */}
      {!isLast && (
        <span
          className="absolute left-[13px] top-7 bottom-0 w-px bg-[var(--line)]"
          aria-hidden="true"
        />
      )}
      <span
        className={cn(
          'relative z-10 h-[27px] w-[27px] rounded-full shrink-0',
          'flex items-center justify-center',
          style.ring,
        )}
      >
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d={style.path} />
        </svg>
      </span>

      <div className="min-w-0 flex-1 -mt-0.5">
        <p className="text-sm font-semibold text-[var(--tx)] leading-snug">
          {event.title}
        </p>
        <p className="text-xs text-[var(--tx-3)] mt-0.5">
          {formatWhen(event.at)}
          {overdue && <span className="text-[var(--err)]"> · {overdue}</span>}
          {event.automatic && <span className="pill pill-neu ml-2">automatic</span>}
        </p>
        {event.detail && (
          <p className="text-xs text-[var(--tx-2)] mt-1 line-clamp-3">{event.detail}</p>
        )}
      </div>
    </li>
  );
}

export function EscalationTimeline({ ticket }: { ticket: Ticket }) {
  const queryClient = useQueryClient();
  const role = useAuth((s) => s.user?.role);
  const canEscalate = role === 'agent' || role === 'supervisor' || role === 'admin';

  const [reason, setReason] = useState('');
  const [composing, setComposing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: events = [], isLoading } = useQuery({
    queryKey: ['ticket-timeline', ticket.id],
    queryFn: () => getTicketTimeline(ticket.id),
  });

  const escalate = useMutation({
    mutationFn: () => escalateTicket(ticket.id, reason || 'Escalated manually.'),
    onSuccess: () => {
      setComposing(false);
      setReason('');
      setError(null);
      // The ticket's status and assignee both changed, so refresh those too.
      queryClient.invalidateQueries({ queryKey: ['ticket-timeline', ticket.id] });
      queryClient.invalidateQueries({ queryKey: ['ticket', ticket.id] });
    },
    onError: (e) => setError(extractError(e).message),
  });

  const alreadyEscalated = ticket.status === 'escalated';
  const isFinished = ticket.status === 'resolved' || ticket.status === 'closed';

  return (
    <div className="card-sm flex flex-col gap-4">
      <h3 className="text-[11px] uppercase tracking-widest text-[var(--tx-3)] font-semibold">
        Escalation Timeline
      </h3>

      {isLoading ? (
        <div className="animate-pulse space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex gap-3">
              <div className="h-[27px] w-[27px] rounded-full bg-[var(--inset)] shrink-0" />
              <div className="flex-1 space-y-1.5 pt-1">
                <div className="h-3 bg-[var(--inset)] rounded w-2/3" />
                <div className="h-2 bg-[var(--inset)] rounded w-1/3" />
              </div>
            </div>
          ))}
        </div>
      ) : events.length === 0 ? (
        <p className="text-xs text-[var(--tx-3)]">Nothing has happened yet.</p>
      ) : (
        <ol className="flex flex-col">
          {events.map((event, i) => (
            <TimelineRow
              key={`${event.kind}-${event.at}-${i}`}
              event={event}
              ticket={ticket}
              isLast={i === events.length - 1}
            />
          ))}
        </ol>
      )}

      {canEscalate && !isFinished && (
        <div className="flex flex-col gap-2 pt-1 border-t border-[var(--line)]">
          {error && <p className="text-xs text-[var(--err)]">{error}</p>}

          {composing ? (
            <>
              <label htmlFor="escalation-reason" className="text-xs text-[var(--tx-2)]">
                Why does this need escalating?
              </label>
              <textarea
                id="escalation-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={2}
                autoFocus
                placeholder="Customer has called three times; needs a senior decision."
                className="w-full resize-none rounded-lg border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm text-[var(--tx)] outline-none focus:border-[var(--brand)]"
              />
              <div className="flex gap-2">
                <Button
                  variant="danger"
                  onClick={() => escalate.mutate()}
                  disabled={escalate.isPending}
                  className="flex-1"
                >
                  {escalate.isPending ? 'Escalating…' : 'Confirm escalation'}
                </Button>
                <Button variant="ghost" onClick={() => { setComposing(false); setError(null); }}>
                  Cancel
                </Button>
              </div>
            </>
          ) : (
            <Button
              variant="danger"
              onClick={() => setComposing(true)}
              disabled={alreadyEscalated}
              title={alreadyEscalated ? 'This ticket is already escalated' : undefined}
              className="w-full"
            >
              {alreadyEscalated ? 'Already escalated' : 'Escalate to Manager'}
            </Button>
          )}
          <p className="text-[10px] text-[var(--tx-3)] text-center">
            Routes to the target named by the matching escalation rule.
          </p>
        </div>
      )}
    </div>
  );
}
