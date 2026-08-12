import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { cn } from '@/lib/cn';
import { listTickets } from '@/features/tickets/api';
import type { Ticket } from '@/features/tickets/api';
import { listEscalationRules, listEscalationEvents } from '@/features/escalations/api';
import type { EscalationRule, EscalationEvent } from '@/features/escalations/api';

const STALE = 30_000;

// ── Helpers ───────────────────────────────────────────────────────────────────

function timeAgo(isoDate: string): string {
  const diffMs = Date.now() - new Date(isoDate).getTime();
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

const TRIGGER_LABELS: Record<string, string> = {
  sla_breach:  'SLA Breach',
  manual:      'Manual',
  high_risk:   'High Risk',
  vip_customer: 'VIP Customer',
  regulatory:  'Regulatory',
};

const PRIORITY_TONE: Record<string, string> = {
  critical: 'pill-err',
  high:     'pill-warn',
  medium:   'bg-[var(--brand-xs)] text-[var(--brand)]',
  low:      '',
};

// ── Skeleton ──────────────────────────────────────────────────────────────────

function Sk({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-lg bg-[var(--inset)]', className)} />;
}

// ── Active Escalation Row ─────────────────────────────────────────────────────

function EscalatedTicketRow({ ticket, onClick }: { ticket: Ticket; onClick: () => void }) {
  return (
    <tr
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => e.key === 'Enter' && onClick()}
      className="cursor-pointer transition-colors hover:bg-[var(--raised)]"
    >
      <td className="px-4 py-3">
        <span className="font-mono text-[11px] font-bold text-[var(--brand)] bg-[var(--brand-xs)] px-1.5 py-0.5 rounded">
          {ticket.ticket_number}
        </span>
      </td>
      <td className="px-3 py-3">
        <span className="text-sm text-[var(--tx)] line-clamp-1 max-w-[220px]">{ticket.title}</span>
      </td>
      <td className="px-3 py-3">
        <span className={cn('pill capitalize', PRIORITY_TONE[ticket.priority])}>
          {ticket.priority}
        </span>
      </td>
      <td className="px-3 py-3">
        <span className="text-xs text-[var(--tx-3)]">{ticket.department ?? '—'}</span>
      </td>
      <td className="px-3 py-3">
        {ticket.sla_breached ? (
          <span className="pill pill-err">SLA Breached</span>
        ) : (
          <span className="text-xs text-[var(--tx-3)]">—</span>
        )}
      </td>
      <td className="px-4 py-3 text-right">
        <span className="text-[11px] text-[var(--tx-3)]">
          {timeAgo(ticket.created_at)}
        </span>
      </td>
    </tr>
  );
}

// ── Event Row ─────────────────────────────────────────────────────────────────

function EventRow({ event }: { event: EscalationEvent }) {
  const navigate = useNavigate();

  return (
    <tr className="border-b border-[var(--line)] last:border-0">
      <td className="px-4 py-3">
        <button
          onClick={() => navigate(`/tickets/${event.ticket_id}`)}
          className="font-mono text-[11px] font-bold text-[var(--brand)] hover:underline"
        >
          View
        </button>
      </td>
      <td className="px-3 py-3">
        <span className="pill">
          {TRIGGER_LABELS[event.trigger] ?? event.trigger}
        </span>
      </td>
      <td className="px-3 py-3">
        <span className="text-xs text-[var(--tx-2)]">
          {event.escalated_to?.full_name ?? event.rule_name ?? '—'}
        </span>
      </td>
      <td className="px-3 py-3">
        <span className="text-xs text-[var(--tx-3)] line-clamp-1 max-w-[200px]">
          {event.reason ?? '—'}
        </span>
      </td>
      <td className="px-3 py-3">
        {event.resolved_at ? (
          <span className="pill pill-ok">Resolved</span>
        ) : (
          <span className="pill pill-err">Open</span>
        )}
      </td>
      <td className="px-4 py-3 text-right">
        <span className="text-[11px] text-[var(--tx-3)]">{timeAgo(event.triggered_at)}</span>
      </td>
    </tr>
  );
}

// ── Rules Panel ───────────────────────────────────────────────────────────────

function RulesPanel({ rules, loading }: { rules: EscalationRule[]; loading: boolean }) {
  return (
    <div className="card-sm !p-0 overflow-hidden">
      <div className="px-4 py-3 border-b border-[var(--line)] flex items-center justify-between">
        <span className="text-sm font-semibold text-[var(--tx)]">Escalation Rules</span>
        <span className="text-[11px] text-[var(--tx-3)]">{rules.length} rule{rules.length !== 1 ? 's' : ''}</span>
      </div>
      {loading ? (
        <div className="p-4 flex flex-col gap-2">
          {Array.from({ length: 3 }).map((_, i) => <Sk key={i} className="h-12" />)}
        </div>
      ) : rules.length === 0 ? (
        <div className="p-6 text-center text-xs text-[var(--tx-3)]">No escalation rules configured.</div>
      ) : (
        <ul className="divide-y divide-[var(--line)]">
          {rules.map((rule) => (
            <li key={rule.id} className="px-4 py-3 flex items-start gap-3">
              <div className={cn(
                'h-2 w-2 rounded-full mt-1.5 shrink-0',
                rule.is_active ? 'bg-emerald-500' : 'bg-[var(--tx-3)]',
              )} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-semibold text-[var(--tx)]">{rule.name}</span>
                  <span className="pill">{TRIGGER_LABELS[rule.trigger] ?? rule.trigger}</span>
                  {!rule.is_active && (
                    <span className="text-[10px] text-[var(--tx-3)] font-medium">Inactive</span>
                  )}
                </div>
                <div className="flex items-center gap-3 mt-0.5 flex-wrap">
                  <span className="text-[11px] text-[var(--tx-3)]">
                    → <span className="text-[var(--tx-2)] font-medium">{rule.escalate_to_role}</span>
                  </span>
                  {rule.trigger_after_minutes && (
                    <span className="text-[11px] text-[var(--tx-3)]">after {rule.trigger_after_minutes}m</span>
                  )}
                  {rule.priority_threshold && (
                    <span className="text-[11px] text-[var(--tx-3)]">
                      min priority: <span className="capitalize">{rule.priority_threshold}</span>
                    </span>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function EscalationsPage() {
  const navigate = useNavigate();

  const escalatedQuery = useQuery({
    queryKey: ['tickets', 'escalated'],
    queryFn: () => listTickets({ status: 'escalated', page_size: 50 }),
    staleTime: STALE,
    refetchInterval: STALE,
  });

  const eventsQuery = useQuery({
    queryKey: ['escalations', 'events'],
    queryFn: () => listEscalationEvents({ page_size: 20 }),
    staleTime: STALE,
    refetchInterval: STALE,
  });

  const rulesQuery = useQuery({
    queryKey: ['escalations', 'rules'],
    queryFn: listEscalationRules,
    staleTime: 60_000,
  });

  const escalatedTickets = (escalatedQuery.data?.items ?? []) as unknown as Ticket[];
  const events = eventsQuery.data?.items ?? [];
  const rules = rulesQuery.data ?? [];
  const activeCount = escalatedTickets.length;

  return (
    <div className="flex flex-col gap-5">

      {/* ── Header ──────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-[var(--tx)]">Escalations</h1>
          <p className="text-xs text-[var(--tx-3)] mt-0.5">Active escalations and escalation rule management</p>
        </div>
        {activeCount > 0 && (
          <span className="pill pill-err text-sm px-3 py-1">
            {activeCount} Active
          </span>
        )}
      </div>

      {/* ── Summary cards ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="card-sm flex flex-col gap-2">
          <span className="text-[11px] uppercase tracking-widest text-[var(--tx-3)] font-semibold">Active Escalations</span>
          <span className={cn('text-2xl font-bold tabular-nums', activeCount > 0 ? 'text-[var(--err)]' : 'text-[var(--tx)]')}>
            {escalatedQuery.isLoading ? '—' : activeCount}
          </span>
        </div>
        <div className="card-sm flex flex-col gap-2">
          <span className="text-[11px] uppercase tracking-widest text-[var(--tx-3)] font-semibold">Active Rules</span>
          <span className="text-2xl font-bold tabular-nums text-[var(--tx)]">
            {rulesQuery.isLoading ? '—' : rules.filter((r) => r.is_active).length}
          </span>
        </div>
        <div className="card-sm flex flex-col gap-2">
          <span className="text-[11px] uppercase tracking-widest text-[var(--tx-3)] font-semibold">Unresolved Events</span>
          <span className="text-2xl font-bold tabular-nums text-[var(--tx)]">
            {eventsQuery.isLoading ? '—' : eventsQuery.data?.total ?? 0}
          </span>
        </div>
      </div>

      {/* ── Two-column layout ───────────────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">

        {/* Left: escalated tickets table (2/3 width) */}
        <div className="xl:col-span-2 card-sm !p-0 overflow-hidden">
          <div className="px-4 py-3 border-b border-[var(--line)]">
            <span className="text-sm font-semibold text-[var(--tx)]">Escalated Tickets</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[var(--line)] bg-[var(--raised)]">
                  <th className="text-left px-4 py-2.5 text-[10px] uppercase tracking-wider text-[var(--tx-3)] font-semibold">Ticket</th>
                  <th className="text-left px-3 py-2.5 text-[10px] uppercase tracking-wider text-[var(--tx-3)] font-semibold">Title</th>
                  <th className="text-left px-3 py-2.5 text-[10px] uppercase tracking-wider text-[var(--tx-3)] font-semibold">Priority</th>
                  <th className="text-left px-3 py-2.5 text-[10px] uppercase tracking-wider text-[var(--tx-3)] font-semibold">Dept</th>
                  <th className="text-left px-3 py-2.5 text-[10px] uppercase tracking-wider text-[var(--tx-3)] font-semibold">SLA</th>
                  <th className="text-right px-4 py-2.5 text-[10px] uppercase tracking-wider text-[var(--tx-3)] font-semibold">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--line)]">
                {escalatedQuery.isLoading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <tr key={i}>
                      <td colSpan={6} className="px-4 py-3"><Sk className="h-4 w-full" /></td>
                    </tr>
                  ))
                ) : escalatedTickets.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-12 text-center">
                      <div className="flex flex-col items-center gap-2 text-[var(--tx-3)]">
                        <svg className="h-8 w-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                          <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                        <p className="text-sm">No active escalations</p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  escalatedTickets.map((ticket) => (
                    <EscalatedTicketRow
                      key={ticket.id}
                      ticket={ticket}
                      onClick={() => navigate(`/tickets/${ticket.id}`)}
                    />
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right: rules panel (1/3 width) */}
        <div>
          <RulesPanel rules={rules} loading={rulesQuery.isLoading} />
        </div>
      </div>

      {/* ── Escalation events log ────────────────────────────────── */}
      <div className="card-sm !p-0 overflow-hidden">
        <div className="px-4 py-3 border-b border-[var(--line)] flex items-center justify-between">
          <span className="text-sm font-semibold text-[var(--tx)]">Escalation Event Log</span>
          <span className="text-[11px] text-[var(--tx-3)]">
            {eventsQuery.isLoading ? '…' : `${eventsQuery.data?.total ?? 0} total events`}
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[var(--line)] bg-[var(--raised)]">
                <th className="text-left px-4 py-2.5 text-[10px] uppercase tracking-wider text-[var(--tx-3)] font-semibold">Ticket</th>
                <th className="text-left px-3 py-2.5 text-[10px] uppercase tracking-wider text-[var(--tx-3)] font-semibold">Trigger</th>
                <th className="text-left px-3 py-2.5 text-[10px] uppercase tracking-wider text-[var(--tx-3)] font-semibold">Escalated To</th>
                <th className="text-left px-3 py-2.5 text-[10px] uppercase tracking-wider text-[var(--tx-3)] font-semibold">Reason</th>
                <th className="text-left px-3 py-2.5 text-[10px] uppercase tracking-wider text-[var(--tx-3)] font-semibold">Status</th>
                <th className="text-right px-4 py-2.5 text-[10px] uppercase tracking-wider text-[var(--tx-3)] font-semibold">When</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--line)]">
              {eventsQuery.isLoading ? (
                Array.from({ length: 4 }).map((_, i) => (
                  <tr key={i}>
                    <td colSpan={6} className="px-4 py-3"><Sk className="h-4 w-full" /></td>
                  </tr>
                ))
              ) : events.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-xs text-[var(--tx-3)]">
                    No escalation events recorded
                  </td>
                </tr>
              ) : (
                events.map((event) => <EventRow key={event.id} event={event} />)
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
