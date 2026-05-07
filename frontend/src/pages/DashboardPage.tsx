import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Ring } from '@/components/Ring';
import { Skeleton } from '@/components/Skeleton';
import { PriorityBadge, StatusBadge } from '@/features/tickets/components/StatusBadge';
import { dashboardOverview, type DashboardOverview } from '@/features/dashboard/api';
import { extractError } from '@/lib/api';
import { formatRelative, isBreached } from '@/lib/format';
import { useAuth } from '@/store/auth';
import type { Priority, TicketStatus } from '@/features/tickets/types';

export function DashboardPage() {
  const { user } = useAuth();
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['dashboard', 'overview'],
    queryFn: dashboardOverview,
    refetchInterval: 60_000,
  });

  if (isError) {
    return (
      <Card>
        <h2 className="text-lg font-semibold">Couldn't load the dashboard.</h2>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-2">
          {extractError(error).message}
        </p>
        <button onClick={() => refetch()} className="btn-primary mt-4">Try again</button>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Welcome back{user ? `, ${user.full_name.split(' ')[0]}` : ''}.
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Operational overview of the SUCCESS Bank ticketing platform.
        </p>
      </div>

      <KpiStrip data={data} isLoading={isLoading} />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <RecentTickets data={data} isLoading={isLoading} />
        <SlaHealthCard data={data} isLoading={isLoading} />
      </div>

      {data && <RoleSpecificCards data={data} />}
    </div>
  );
}

function KpiStrip({ data, isLoading }: { data: DashboardOverview | undefined; isLoading: boolean }) {
  const tiles = [
    { label: 'Open tickets',          value: data?.kpis.open,               tone: 'info' as const },
    { label: 'Resolution breached',   value: data?.kpis.breached,           tone: 'danger' as const },
    { label: 'First-response missed', value: data?.kpis.response_breached,  tone: 'warning' as const },
    { label: 'Critical, open',        value: data?.kpis.critical_open,      tone: 'warning' as const },
    { label: 'Resolved / closed',     value: data?.kpis.resolved,           tone: 'success' as const },
  ];
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-4">
      {tiles.map((t) => (
        <Card key={t.label} className="kpi">
          <span className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{t.label}</span>
          <div className="flex items-end justify-between gap-2">
            {isLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <span className="text-3xl font-semibold tabular-nums">{t.value ?? 0}</span>
            )}
            <Badge tone={t.tone}>live</Badge>
          </div>
        </Card>
      ))}
    </div>
  );
}

function RecentTickets({ data, isLoading }: { data: DashboardOverview | undefined; isLoading: boolean }) {
  return (
    <Card className="xl:col-span-2">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">Recent tickets</h2>
        <Link to="/tickets" className="text-sm text-brand-700 dark:text-brand-300 hover:underline">
          View all →
        </Link>
      </div>

      <div className="mt-4 -mx-2 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
            <tr>
              <th className="px-2 py-2">Ticket</th>
              <th className="px-2 py-2">Title</th>
              <th className="px-2 py-2">Status</th>
              <th className="px-2 py-2">Priority</th>
              <th className="px-2 py-2">SLA</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {isLoading &&
              Array.from({ length: 4 }).map((_, i) => (
                <tr key={i}>
                  {Array.from({ length: 5 }).map((__, j) => (
                    <td key={j} className="px-2 py-3"><Skeleton className="h-4 w-full max-w-[160px]" /></td>
                  ))}
                </tr>
              ))}
            {!isLoading && (data?.recent.length ?? 0) === 0 && (
              <tr>
                <td colSpan={5} className="px-2 py-6 text-center text-slate-400">No tickets yet.</td>
              </tr>
            )}
            {data?.recent.map((t) => (
              <tr key={t.id} className="hover:bg-surface-muted/60 dark:hover:bg-slate-800/40">
                <td className="px-2 py-2 font-mono text-xs">
                  <Link className="text-brand-700 dark:text-brand-300 hover:underline" to={`/tickets/${t.id}`}>
                    {t.ticket_no}
                  </Link>
                </td>
                <td className="px-2 py-2 truncate max-w-[280px]">{t.title}</td>
                <td className="px-2 py-2"><StatusBadge status={t.status as TicketStatus} /></td>
                <td className="px-2 py-2"><PriorityBadge priority={t.priority as Priority} /></td>
                <td className="px-2 py-2">
                  {t.sla_due_at ? (
                    <Badge tone={isBreached(t.sla_due_at) ? 'danger' : 'success'}>
                      {formatRelative(t.sla_due_at)}
                    </Badge>
                  ) : (
                    <span className="text-slate-400">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function SlaHealthCard({ data, isLoading }: { data: DashboardOverview | undefined; isLoading: boolean }) {
  return (
    <Card className="flex flex-col text-center">
      <h2 className="text-base font-semibold self-start">SLA health</h2>
      <div className="my-4 flex justify-center">
        {isLoading ? (
          <Skeleton className="h-32 w-32" rounded="full" />
        ) : (
          <Ring value={data?.kpis.sla_health ?? 0} label="on track" />
        )}
      </div>
      <div className="w-full grid grid-cols-2 gap-2 text-xs">
        <Tile label="Breached"     value={data?.kpis.breached} loading={isLoading} />
        <Tile label="Critical open" value={data?.kpis.critical_open} loading={isLoading} />
      </div>
    </Card>
  );
}

function Tile({ label, value, loading }: { label: string; value: number | undefined; loading?: boolean }) {
  return (
    <div className="rounded-xl bg-surface-muted dark:bg-slate-800/60 p-3 text-left">
      <div className="text-slate-500 dark:text-slate-400 text-xs">{label}</div>
      <div className="text-lg font-semibold mt-1 tabular-nums">
        {loading ? <Skeleton className="h-5 w-10" /> : (value ?? 0)}
      </div>
    </div>
  );
}

function RoleSpecificCards({ data }: { data: DashboardOverview }) {
  const role = data.kpis.role;
  const rs = data.role_specific;

  if (role === 'admin') {
    return (
      <Card>
        <h2 className="text-base font-semibold">Admin queue</h2>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Tickets awaiting acknowledgement / assignment.
        </p>
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
          <BigTile label="Unassigned"        value={rs.unassigned_admin_queue ?? 0} />
          <BigTile label="Open escalations"  value={data.kpis.open_escalations ?? 0} />
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
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
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Tickets currently assigned to you.
        </p>
        <div className="mt-4">
          <BigTile label="My open" value={rs.my_open ?? 0} />
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
          <BigTile label="Critical breaches" value={rs.critical_breaches ?? 0} />
          <BigTile label="Open escalations"  value={data.kpis.open_escalations ?? 0} />
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
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
          <BigTile label="My open" value={rs.my_open ?? 0} />
        </div>
        <div className="mt-4">
          <Link to="/tickets" className="btn-primary">View my tickets</Link>
        </div>
      </Card>
    );
  }

  return null;
}

function BigTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl bg-surface-muted dark:bg-slate-800/60 p-4">
      <div className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wide">{label}</div>
      <div className="text-2xl font-semibold mt-1 tabular-nums">{value}</div>
    </div>
  );
}
