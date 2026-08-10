import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { cn } from '@/lib/cn';
import { getSLAStatus } from '@/features/dashboard/api';
import { listTickets } from '@/features/tickets/api';
import type { Ticket } from '@/features/tickets/api';

const STALE = 30_000;
const OPEN_STATUSES = ['new', 'acknowledged', 'assigned', 'in_progress', 'escalated', 'reopened'];

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatCountdown(isoDate: string | null | undefined): {
  label: string;
  tone: 'ok' | 'warn' | 'err' | 'neutral';
} {
  if (!isoDate) return { label: '—', tone: 'neutral' };
  const due = new Date(isoDate).getTime();
  const now = Date.now();
  const diffMs = due - now;

  if (diffMs < 0) {
    const mins = Math.abs(Math.floor(diffMs / 60_000));
    if (mins < 60) return { label: `-${mins}m`, tone: 'err' };
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return { label: `-${hrs}h ${mins % 60}m`, tone: 'err' };
    return { label: `-${Math.floor(hrs / 24)}d ${hrs % 24}h`, tone: 'err' };
  }

  const mins = Math.floor(diffMs / 60_000);
  if (mins < 60) return { label: `${mins}m`, tone: 'err' };
  const hrs = Math.floor(mins / 60);
  if (hrs < 4) return { label: `${hrs}h ${mins % 60}m`, tone: 'warn' };
  if (hrs < 24) return { label: `${hrs}h`, tone: 'warn' };
  const days = Math.floor(hrs / 24);
  return { label: `${days}d ${hrs % 24}h`, tone: 'ok' };
}

function getSLAFilter(ticket: Ticket & { resolution_due_at?: string | null }): 'breached' | 'at_risk' | 'on_time' {
  if (ticket.sla_breached) return 'breached';
  if (!ticket.resolution_due_at) return 'on_time';
  const minutesLeft = (new Date(ticket.resolution_due_at).getTime() - Date.now()) / 60_000;
  if (minutesLeft < 60) return 'at_risk';
  return 'on_time';
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function Sk({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-lg bg-[var(--inset)]', className)} />;
}

// ── Metric Card ───────────────────────────────────────────────────────────────

function MetricCard({
  label, value, tone = 'default', icon,
}: {
  label: string;
  value: number;
  tone?: 'default' | 'danger' | 'success' | 'warning';
  icon: string;
}) {
  const tones = {
    default: { value: 'text-[var(--tx)]',   icon: 'bg-[var(--brand-xs)] text-[var(--brand)]' },
    danger:  { value: 'text-[var(--err)]',  icon: 'bg-[var(--err-bg)] text-[var(--err)]' },
    success: { value: 'text-[var(--ok)]',   icon: 'bg-[var(--ok-bg)] text-[var(--ok)]' },
    warning: { value: 'text-[var(--warn)]', icon: 'bg-[var(--warn-bg)] text-[var(--warn)]' },
  }[tone];

  return (
    <div className="card-sm flex flex-col gap-2.5">
      <div className="flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-widest text-[var(--tx-3)] font-semibold">{label}</span>
        <div className={cn('h-7 w-7 rounded-lg flex items-center justify-center', tones.icon)}>
          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d={icon} />
          </svg>
        </div>
      </div>
      <span className={cn('text-2xl font-bold tabular-nums', tones.value)}>{value}</span>
    </div>
  );
}

// ── SLA Table Row ─────────────────────────────────────────────────────────────

const PRIORITY_TONE: Record<string, string> = {
  critical: 'text-[var(--err)] font-bold',
  high:     'text-[var(--warn)] font-semibold',
  medium:   'text-[var(--tx-2)]',
  low:      'text-[var(--tx-3)]',
};

const STATUS_LABEL: Record<string, string> = {
  new:          'New',
  acknowledged: 'Acknowledged',
  assigned:     'Assigned',
  in_progress:  'In Progress',
  escalated:    'Escalated',
  on_hold:      'On Hold',
  reopened:     'Reopened',
};

function SLATableRow({ ticket, onClick }: { ticket: Ticket; onClick: () => void }) {
  const cd = formatCountdown((ticket as Ticket & { resolution_due_at?: string | null }).resolution_due_at);
  const countdownClass = {
    ok:      'text-[var(--ok)] font-medium',
    warn:    'text-[var(--warn)] font-semibold',
    err:     'text-[var(--err)] font-bold',
    neutral: 'text-[var(--tx-3)]',
  }[cd.tone];

  return (
    <tr
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => e.key === 'Enter' && onClick()}
      className={cn(
        'cursor-pointer transition-colors hover:bg-[var(--raised)]',
        ticket.sla_breached && 'bg-[var(--err-bg)]/20',
      )}
    >
      <td className="px-4 py-3">
        <span className="font-mono text-[11px] font-bold text-[var(--brand)] bg-[var(--brand-xs)] px-1.5 py-0.5 rounded">
          {ticket.ticket_number}
        </span>
      </td>
      <td className="px-3 py-3">
        <span className="text-sm text-[var(--tx)] line-clamp-1 max-w-[240px]">{ticket.title}</span>
      </td>
      <td className="px-3 py-3">
        <span className={cn('text-xs capitalize', PRIORITY_TONE[ticket.priority] ?? 'text-[var(--tx-2)]')}>
          {ticket.priority}
        </span>
      </td>
      <td className="px-3 py-3">
        <span className="pill">
          {STATUS_LABEL[ticket.status] ?? ticket.status}
        </span>
      </td>
      <td className="px-3 py-3">
        <span className="text-xs text-[var(--tx-3)]">{ticket.department ?? '—'}</span>
      </td>
      <td className="px-4 py-3 text-right">
        <span className={cn('text-xs tabular-nums', countdownClass)}>
          {ticket.sla_breached && cd.tone !== 'err' ? (
            <span className="text-[var(--err)] font-bold">Breached</span>
          ) : cd.label}
        </span>
      </td>
    </tr>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

type SLAFilter = 'all' | 'breached' | 'at_risk' | 'on_time';

const TABS: { key: SLAFilter; label: string }[] = [
  { key: 'all',      label: 'All Open' },
  { key: 'breached', label: 'Breached' },
  { key: 'at_risk',  label: 'At Risk' },
  { key: 'on_time',  label: 'On Time' },
];

export function SLAMonitorPage() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<SLAFilter>('all');

  const slaQuery = useQuery({
    queryKey: ['dashboard', 'sla'],
    queryFn: getSLAStatus,
    staleTime: STALE,
    refetchInterval: STALE,
  });

  // Fetch all open tickets for the table (up to 100 per page, most recently breached first)
  const ticketsQuery = useQuery({
    queryKey: ['sla-monitor', 'tickets'],
    queryFn: () => listTickets({ page_size: 100 }),
    staleTime: STALE,
    refetchInterval: STALE,
  });

  const sla = slaQuery.data;
  const allTickets = (ticketsQuery.data?.items ?? []) as unknown as Ticket[];

  // Filter to open tickets only
  const openTickets = allTickets.filter((t) => OPEN_STATUSES.includes(t.status));

  const filtered = openTickets.filter((t) => {
    if (activeTab === 'all') return true;
    return getSLAFilter(t) === activeTab;
  });

  // Sort: breached first, then by resolution_due_at ascending
  const sorted = [...filtered].sort((a, b) => {
    if (a.sla_breached !== b.sla_breached) return a.sla_breached ? -1 : 1;
    const ad = (a as Ticket & { resolution_due_at?: string }).resolution_due_at;
    const bd = (b as Ticket & { resolution_due_at?: string }).resolution_due_at;
    if (!ad && !bd) return 0;
    if (!ad) return 1;
    if (!bd) return -1;
    return new Date(ad).getTime() - new Date(bd).getTime();
  });

  const isLoading = slaQuery.isLoading || ticketsQuery.isLoading;

  return (
    <div className="flex flex-col gap-5">

      {/* ── Header ──────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-[var(--tx)]">SLA Monitor</h1>
          <p className="text-xs text-[var(--tx-3)] mt-0.5">Real-time service level agreement tracking</p>
        </div>
        {sla && (
          <span className={cn(
            'pill text-sm px-3 py-1',
            sla.compliance_rate >= 90 ? 'pill-ok' :
            sla.compliance_rate >= 75 ? 'pill-warn' :
            'pill-err',
          )}>
            {sla.compliance_rate.toFixed(1)}% SLO Compliance
          </span>
        )}
      </div>

      {/* ── Metric cards ─────────────────────────────────────────── */}
      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="card-sm"><Sk className="h-16" /></div>
          ))}
        </div>
      ) : sla ? (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <MetricCard
            label="Breached"
            value={sla.breached}
            tone={sla.breached > 0 ? 'danger' : 'default'}
            icon="M12 9v4M12 17h.01M4.93 19h14.14L12 5z"
          />
          <MetricCard
            label="At Risk (< 1h)"
            value={sla.at_risk}
            tone={sla.at_risk > 0 ? 'warning' : 'default'}
            icon="M12 8v4l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z"
          />
          <MetricCard
            label="On Time"
            value={sla.on_time}
            tone="success"
            icon="M5 13l4 4L19 7"
          />
        </div>
      ) : null}

      {/* ── Compliance bar ──────────────────────────────────────── */}
      {sla && (() => {
        const total = sla.on_time + sla.at_risk + sla.breached;
        const pct = (n: number) => (total > 0 ? (n / total) * 100 : 0);
        return (
          <div className="card-sm">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-[var(--tx-2)]">SLA Distribution</span>
              <span className="text-[10px] text-[var(--tx-3)]">{total} tracked tickets</span>
            </div>
            <div className="flex rounded-full overflow-hidden h-3 gap-px bg-[var(--inset)]">
              {pct(sla.on_time) > 0 && (
                <div className="bg-emerald-500 transition-all duration-700" style={{ width: `${pct(sla.on_time)}%` }} title={`On time: ${sla.on_time}`} />
              )}
              {pct(sla.at_risk) > 0 && (
                <div className="bg-amber-400 transition-all duration-700" style={{ width: `${pct(sla.at_risk)}%` }} title={`At risk: ${sla.at_risk}`} />
              )}
              {pct(sla.breached) > 0 && (
                <div className="bg-red-500 transition-all duration-700" style={{ width: `${pct(sla.breached)}%` }} title={`Breached: ${sla.breached}`} />
              )}
            </div>
            <div className="flex items-center gap-4 mt-2">
              {[
                { label: 'On Time',  count: sla.on_time,  color: 'bg-emerald-500' },
                { label: 'At Risk',  count: sla.at_risk,  color: 'bg-amber-400' },
                { label: 'Breached', count: sla.breached, color: 'bg-red-500' },
              ].map(({ label, count, color }) => (
                <div key={label} className="flex items-center gap-1.5">
                  <span className={cn('h-2 w-2 rounded-full', color)} />
                  <span className="text-[11px] text-[var(--tx-3)]">{label}: <strong className="text-[var(--tx-2)]">{count}</strong></span>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      {/* ── Ticket table ────────────────────────────────────────── */}
      <div className="card-sm !p-0 overflow-hidden">
        {/* Tabs */}
        <div className="flex items-center gap-0 border-b border-[var(--line)] px-4 pt-3">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                'px-4 py-2 text-xs font-semibold transition-colors border-b-2 -mb-px',
                activeTab === tab.key
                  ? 'border-[var(--brand)] text-[var(--brand)]'
                  : 'border-transparent text-[var(--tx-3)] hover:text-[var(--tx-2)]',
              )}
            >
              {tab.label}
              {tab.key === 'breached' && (sla?.breached ?? 0) > 0 && (
                <span className="ml-1.5 bg-[var(--err)] text-white text-[9px] font-bold rounded-full px-1.5 py-0.5">
                  {sla?.breached}
                </span>
              )}
              {tab.key === 'at_risk' && (sla?.at_risk ?? 0) > 0 && (
                <span className="ml-1.5 bg-[var(--warn)] text-white text-[9px] font-bold rounded-full px-1.5 py-0.5">
                  {sla?.at_risk}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[var(--line)] bg-[var(--raised)]">
                <th className="text-left px-4 py-2.5 text-[10px] uppercase tracking-wider text-[var(--tx-3)] font-semibold">Ticket</th>
                <th className="text-left px-3 py-2.5 text-[10px] uppercase tracking-wider text-[var(--tx-3)] font-semibold">Title</th>
                <th className="text-left px-3 py-2.5 text-[10px] uppercase tracking-wider text-[var(--tx-3)] font-semibold">Priority</th>
                <th className="text-left px-3 py-2.5 text-[10px] uppercase tracking-wider text-[var(--tx-3)] font-semibold">Status</th>
                <th className="text-left px-3 py-2.5 text-[10px] uppercase tracking-wider text-[var(--tx-3)] font-semibold">Department</th>
                <th className="text-right px-4 py-2.5 text-[10px] uppercase tracking-wider text-[var(--tx-3)] font-semibold">Time Remaining</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--line)]">
              {ticketsQuery.isLoading ? (
                Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i}>
                    <td colSpan={6} className="px-4 py-3">
                      <Sk className="h-4 w-full" />
                    </td>
                  </tr>
                ))
              ) : sorted.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center">
                    <div className="flex flex-col items-center gap-2 text-[var(--tx-3)]">
                      <svg className="h-8 w-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                      <p className="text-sm">
                        {activeTab === 'all' ? 'No open tickets' :
                         activeTab === 'breached' ? 'No SLA breaches — great work!' :
                         activeTab === 'at_risk' ? 'No tickets at risk' :
                         'All tickets are within SLA'}
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                sorted.map((ticket) => (
                  <SLATableRow
                    key={ticket.id}
                    ticket={ticket}
                    onClick={() => navigate(`/tickets/${ticket.id}`)}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>

        {sorted.length > 0 && (
          <div className="px-4 py-2.5 border-t border-[var(--line)] text-[10px] text-[var(--tx-3)]">
            Showing {sorted.length} ticket{sorted.length !== 1 ? 's' : ''} · sorted by urgency
          </div>
        )}
      </div>
    </div>
  );
}
