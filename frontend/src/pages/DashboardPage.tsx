import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Ring } from '@/components/Ring';
import { PriorityBadge, StatusBadge } from '@/features/tickets/components/StatusBadge';
import { dashboardOverview } from '@/features/dashboard/api';
import { formatRelative, isBreached } from '@/lib/format';
import { useAuth } from '@/store/auth';
import type { Priority, TicketStatus } from '@/features/tickets/types';

export function DashboardPage() {
  const { user } = useAuth();
  const { data, isLoading } = useQuery({
    queryKey: ['dashboard', 'overview'],
    queryFn: dashboardOverview,
    refetchInterval: 60_000,
  });

  const tiles = [
    { label: 'Open tickets',          value: data?.kpis.open,               tone: 'info' as const },
    { label: 'Resolution breached',   value: data?.kpis.breached,           tone: 'danger' as const },
    { label: 'First-response missed', value: data?.kpis.response_breached,  tone: 'warning' as const },
    { label: 'Critical, open',        value: data?.kpis.critical_open,      tone: 'warning' as const },
    { label: 'Resolved / closed',     value: data?.kpis.resolved,           tone: 'success' as const },
  ];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Welcome back{user ? `, ${user.full_name.split(' ')[0]}` : ''}.</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Operational overview of the SUCCESS Bank ticketing platform.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {tiles.map((t) => (
          <Card key={t.label} className="kpi">
            <span className="text-xs uppercase tracking-wide text-slate-500">{t.label}</span>
            <div className="flex items-end justify-between">
              <span className="text-3xl font-semibold">
                {isLoading ? '—' : (t.value ?? 0)}
              </span>
              <Badge tone={t.tone}>live</Badge>
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

          <div className="mt-4 -mx-2 overflow-x-auto">
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
                {isLoading && <tr><td colSpan={5} className="px-2 py-6 text-center text-slate-400">Loading…</td></tr>}
                {!isLoading && (data?.recent.length ?? 0) === 0 && (
                  <tr><td colSpan={5} className="px-2 py-6 text-center text-slate-400">No tickets yet.</td></tr>
                )}
                {data?.recent.map((t) => (
                  <tr key={t.id} className="hover:bg-surface-muted/60 dark:hover:bg-slate-800/40">
                    <td className="px-2 py-2 font-mono text-xs">
                      <Link className="text-brand-700 hover:underline" to={`/tickets/${t.id}`}>{t.ticket_no}</Link>
                    </td>
                    <td className="px-2 py-2 truncate max-w-[280px]">{t.title}</td>
                    <td className="px-2 py-2"><StatusBadge status={t.status as TicketStatus} /></td>
                    <td className="px-2 py-2"><PriorityBadge priority={t.priority as Priority} /></td>
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

        <Card className="flex flex-col items-center justify-center text-center">
          <h2 className="text-base font-semibold self-start">SLA health</h2>
          <div className="my-4">
            <Ring value={data?.kpis.sla_health ?? 0} label="on track" />
          </div>
          <div className="w-full grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-xl bg-surface-muted dark:bg-slate-800/40 p-3">
              <div className="text-slate-500">Breached</div>
              <div className="text-lg font-semibold mt-1">{data?.kpis.breached ?? '—'}</div>
            </div>
            <div className="rounded-xl bg-surface-muted dark:bg-slate-800/40 p-3">
              <div className="text-slate-500">Critical open</div>
              <div className="text-lg font-semibold mt-1">{data?.kpis.critical_open ?? '—'}</div>
            </div>
          </div>
        </Card>
      </div>

      <RoleSpecificCards data={data} />
    </div>
  );
}

function RoleSpecificCards({ data }: { data: ReturnType<typeof useQuery>['data'] | { kpis: { role: string }; role_specific: Record<string, number> } | undefined }) {
  if (!data) return null;
  const d = data as { kpis: { role: string; open_escalations: number }; role_specific: Record<string, number> };
  const role = d.kpis.role;

  if (role === 'admin') {
    return (
      <Card>
        <h2 className="text-base font-semibold">Admin queue</h2>
        <p className="text-sm text-slate-500 mt-1">Tickets awaiting acknowledgement / assignment.</p>
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Tile label="Unassigned"   value={d.role_specific.unassigned_admin_queue ?? 0} />
          <Tile label="Open escalations" value={d.kpis.open_escalations ?? 0} />
        </div>
        <div className="mt-4 flex gap-2">
          <Link to="/tickets?status=new" className="btn-primary">Triage new tickets</Link>
          <Link to="/escalations" className="btn-ghost">Open escalations</Link>
        </div>
      </Card>
    );
  }

  if (role === 'agent') {
    return (
      <Card>
        <h2 className="text-base font-semibold">My workbench</h2>
        <p className="text-sm text-slate-500 mt-1">Tickets currently assigned to you.</p>
        <div className="mt-4">
          <Tile label="My open" value={d.role_specific.my_open ?? 0} />
        </div>
        <div className="mt-4">
          <Link to="/tickets" className="btn-primary">Open my tickets</Link>
        </div>
      </Card>
    );
  }

  if (role === 'supervisor') {
    return (
      <Card>
        <h2 className="text-base font-semibold">Supervisor watch</h2>
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-3 gap-3">
          <Tile label="Critical breaches" value={d.role_specific.critical_breaches ?? 0} />
          <Tile label="Open escalations"  value={d.kpis.open_escalations ?? 0} />
        </div>
        <div className="mt-4 flex gap-2">
          <Link to="/sla" className="btn-primary">SLA monitor</Link>
          <Link to="/escalations" className="btn-ghost">Escalations</Link>
        </div>
      </Card>
    );
  }

  if (role === 'branch_user') {
    return (
      <Card>
        <h2 className="text-base font-semibold">My branch tickets</h2>
        <div className="mt-4">
          <Tile label="My open" value={d.role_specific.my_open ?? 0} />
        </div>
        <div className="mt-4">
          <Link to="/tickets" className="btn-primary">View my tickets</Link>
        </div>
      </Card>
    );
  }

  return null;
}

function Tile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl bg-surface-muted dark:bg-slate-800/40 p-4">
      <div className="text-xs text-slate-500 uppercase tracking-wide">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
    </div>
  );
}
