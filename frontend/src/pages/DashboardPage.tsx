import { useQueries } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { listTickets } from '@/features/tickets/api';
import { PriorityBadge, StatusBadge } from '@/features/tickets/components/StatusBadge';
import { formatRelative, isBreached } from '@/lib/format';

const OPEN_STATUSES = ['new', 'acknowledged', 'assigned', 'in_progress', 'on_hold', 'escalated', 'reopened'] as const;

export function DashboardPage() {
  const queries = useQueries({
    queries: [
      { queryKey: ['kpi', 'open'],     queryFn: () => listTickets({ status: [...OPEN_STATUSES], page: 1, size: 1 }) },
      { queryKey: ['kpi', 'breached'], queryFn: () => listTickets({ breached: true, page: 1, size: 1 }) },
      { queryKey: ['kpi', 'critical'], queryFn: () => listTickets({ priority: ['critical'], status: [...OPEN_STATUSES], page: 1, size: 1 }) },
      { queryKey: ['kpi', 'resolved'], queryFn: () => listTickets({ status: ['resolved', 'closed'], page: 1, size: 1 }) },
      { queryKey: ['recent'],          queryFn: () => listTickets({ page: 1, size: 8 }) },
    ],
  });

  const [open, breached, critical, resolved, recent] = queries;

  const kpis = [
    { label: 'Open tickets',     value: open.data?.meta.total,     tone: 'info' as const },
    { label: 'SLA breached',     value: breached.data?.meta.total, tone: 'danger' as const },
    { label: 'Critical open',    value: critical.data?.meta.total, tone: 'warning' as const },
    { label: 'Resolved/closed',  value: resolved.data?.meta.total, tone: 'success' as const },
  ];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Operational overview of the SUCCESS Bank ticketing platform.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {kpis.map((k) => (
          <Card key={k.label} className="kpi">
            <span className="text-xs uppercase tracking-wide text-slate-500">{k.label}</span>
            <div className="flex items-end justify-between">
              <span className="text-3xl font-semibold">
                {k.value == null ? '—' : k.value}
              </span>
              <Badge tone={k.tone}>live</Badge>
            </div>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <Card className="xl:col-span-2">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">Recent tickets</h2>
            <Link to="/tickets" className="text-sm text-brand-700 hover:underline">View all →</Link>
          </div>

          <div className="mt-4 -mx-2">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-2 py-2">Ticket</th>
                  <th className="px-2 py-2">Title</th>
                  <th className="px-2 py-2">Status</th>
                  <th className="px-2 py-2">Priority</th>
                  <th className="px-2 py-2">SLA</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {recent.isLoading && <tr><td colSpan={5} className="px-2 py-6 text-center text-slate-400">Loading…</td></tr>}
                {recent.data?.items.length === 0 && (
                  <tr><td colSpan={5} className="px-2 py-6 text-center text-slate-400">No tickets yet.</td></tr>
                )}
                {recent.data?.items.map((t) => (
                  <tr key={t.id} className="hover:bg-surface-muted/60 dark:hover:bg-slate-800/40">
                    <td className="px-2 py-2 font-mono text-xs">
                      <Link className="text-brand-700 hover:underline" to={`/tickets/${t.id}`}>{t.ticket_no}</Link>
                    </td>
                    <td className="px-2 py-2 truncate max-w-[280px]">{t.title}</td>
                    <td className="px-2 py-2"><StatusBadge status={t.status} /></td>
                    <td className="px-2 py-2"><PriorityBadge priority={t.priority} /></td>
                    <td className="px-2 py-2">
                      {t.sla_due_at ? (
                        <Badge tone={isBreached(t.sla_due_at) ? 'danger' : 'success'}>
                          {formatRelative(t.sla_due_at)}
                        </Badge>
                      ) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card>
          <h2 className="text-base font-semibold">SLA health</h2>
          <p className="mt-2 text-sm text-slate-500">
            Live breach feed and gauge land in Phase P4 / P7 once the SLA scheduler ticks.
          </p>
          <div className="mt-6 flex items-center justify-between">
            <span className="text-sm text-slate-500">Currently breached</span>
            <Badge tone="danger">
              {breached.data?.meta.total ?? '—'}
            </Badge>
          </div>
          <div className="mt-3 flex items-center justify-between">
            <span className="text-sm text-slate-500">Critical, open</span>
            <Badge tone="warning">
              {critical.data?.meta.total ?? '—'}
            </Badge>
          </div>
        </Card>
      </div>
    </div>
  );
}
