import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Inbox,
  AlertTriangle,
  Clock4,
  Flame,
  CheckCircle2,
  ArrowRight,
  Sparkles,
} from 'lucide-react';

import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Ring } from '@/components/Ring';
import { Skeleton } from '@/components/Skeleton';
import { PriorityBadge, StatusBadge } from '@/features/tickets/components/StatusBadge';
import { dashboardOverview, type DashboardOverview } from '@/features/dashboard/api';
import { extractError } from '@/lib/api';
import { formatRelative, isBreached } from '@/lib/format';
import { useAuth } from '@/store/auth';
import { cn } from '@/lib/cn';
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
        <h2 className="h-section">Couldn't load the dashboard.</h2>
        <p className="text-sm text-ink-muted mt-2">{extractError(error).message}</p>
        <button onClick={() => refetch()} className="btn-primary mt-4">Try again</button>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-7">
      <motion.header
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="flex flex-wrap items-end justify-between gap-4"
      >
        <div>
          <span className="label">Today</span>
          <h1 className="text-4xl font-semibold tracking-tight text-ink mt-1">
            Welcome back{user ? `, ${user.full_name.split(' ')[0]}` : ''}.
          </h1>
          <p className="text-sm text-ink-muted mt-1.5 max-w-2xl">
            A live snapshot of operations across all branches.
            Open tickets, breached SLAs, escalations and recent activity in one place.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/tickets" className="btn-secondary">
            View all tickets
          </Link>
          <Link to="/sla" className="btn-primary">
            <Sparkles className="h-4 w-4" />
            SLA monitor
          </Link>
        </div>
      </motion.header>

      <KpiStrip data={data} isLoading={isLoading} />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <RecentTickets data={data} isLoading={isLoading} />
        <SlaHealthCard data={data} isLoading={isLoading} />
      </div>

      {data && <RoleSpecificCards data={data} />}
    </div>
  );
}

/* ────────────────────────────── KPI STRIP ────────────────────────────── */

function KpiStrip({
  data,
  isLoading,
}: {
  data: DashboardOverview | undefined;
  isLoading: boolean;
}) {
  const OPEN = ['new', 'acknowledged', 'assigned', 'in_progress', 'on_hold', 'escalated', 'reopened'];

  const linkFor = (key: string) => {
    const params = new URLSearchParams();
    switch (key) {
      case 'open':
        OPEN.forEach((s) => params.append('status', s));
        break;
      case 'breached':
        params.set('breached', 'true');
        break;
      case 'response_breached':
        // No backend filter for response-breach yet; deep-link to all open
        // and surface a label so the user knows where they came from.
        OPEN.forEach((s) => params.append('status', s));
        break;
      case 'critical_open':
        OPEN.forEach((s) => params.append('status', s));
        params.append('priority', 'critical');
        break;
      case 'resolved':
        params.append('status', 'resolved');
        params.append('status', 'closed');
        break;
    }
    return `/tickets?${params.toString()}`;
  };

  const tiles = [
    { key: 'open',              label: 'Open tickets',          value: data?.kpis.open,              icon: Inbox,         tone: 'info' as const,    delta: 'view' },
    { key: 'breached',          label: 'Resolution breached',   value: data?.kpis.breached,          icon: AlertTriangle, tone: 'danger' as const,  delta: 'view' },
    { key: 'response_breached', label: 'First-response missed', value: data?.kpis.response_breached, icon: Clock4,        tone: 'warning' as const, delta: 'view' },
    { key: 'critical_open',     label: 'Critical, open',        value: data?.kpis.critical_open,     icon: Flame,         tone: 'warning' as const, delta: 'view' },
    { key: 'resolved',          label: 'Resolved / closed',     value: data?.kpis.resolved,          icon: CheckCircle2,  tone: 'success' as const, delta: 'view' },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-4">
      {tiles.map((t, i) => {
        const Icon = t.icon;
        const inner = (
          <>
            <div className="flex items-start justify-between gap-3">
              <span
                className={cn(
                  'h-9 w-9 grid place-items-center rounded-2xl',
                  t.tone === 'info'    && 'bg-info-soft text-info-deep',
                  t.tone === 'danger'  && 'bg-danger-soft text-danger-deep',
                  t.tone === 'warning' && 'bg-warning-soft text-warning-deep',
                  t.tone === 'success' && 'bg-success-soft text-success-deep',
                )}
              >
                <Icon className="h-[18px] w-[18px]" />
              </span>
              <Badge tone={t.tone}>{t.delta}</Badge>
            </div>
            <div className="mt-4 text-2xs uppercase tracking-wider text-ink-muted">{t.label}</div>
            {isLoading ? (
              <Skeleton className="h-8 w-20 mt-1.5" />
            ) : (
              <div className="text-4xl font-semibold tracking-tight text-ink mt-1 tabular-nums">
                {t.value ?? 0}
              </div>
            )}
          </>
        );
        return (
          <motion.div
            key={t.label}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.04 * i, ease: [0.22, 1, 0.36, 1] }}
            whileHover={{ y: -2 }}
          >
            <Link
              to={linkFor(t.key)}
              className="glass rounded-4xl p-5 hover:shadow-glassLg transition-shadow block focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-300"
              aria-label={`${t.label}: ${t.value ?? 0}. View matching tickets.`}
            >
              {inner}
            </Link>
          </motion.div>
        );
      })}
    </div>
  );
}

/* ──────────────────────────── RECENT TICKETS ─────────────────────────── */

function RecentTickets({
  data,
  isLoading,
}: {
  data: DashboardOverview | undefined;
  isLoading: boolean;
}) {
  return (
    <Card className="xl:col-span-2 p-0 overflow-hidden">
      <div className="px-6 pt-5 pb-4 flex items-center justify-between">
        <div>
          <h2 className="h-section">Recent tickets</h2>
          <p className="text-xs text-ink-muted mt-0.5">Newest activity across the platform.</p>
        </div>
        <Link
          to="/tickets"
          className="text-xs font-semibold text-brand-700 hover:text-brand-800 flex items-center gap-1 group"
        >
          View all
          <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
        </Link>
      </div>

      <div className="overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>Ticket</th>
              <th>Title</th>
              <th>Status</th>
              <th>Priority</th>
              <th>SLA</th>
            </tr>
          </thead>
          <tbody>
            {isLoading &&
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i}>
                  {Array.from({ length: 5 }).map((__, j) => (
                    <td key={j}><Skeleton className="h-4 w-full max-w-[160px]" /></td>
                  ))}
                </tr>
              ))}
            {!isLoading && (data?.recent.length ?? 0) === 0 && (
              <tr>
                <td colSpan={5} className="py-10 text-center text-ink-muted">No tickets yet.</td>
              </tr>
            )}
            {data?.recent.map((t) => (
              <tr key={t.id}>
                <td className="font-mono text-2xs">
                  <Link className="text-brand-700 hover:text-brand-800 hover:underline" to={`/tickets/${t.id}`}>
                    {t.ticket_no}
                  </Link>
                </td>
                <td className="truncate max-w-[280px] text-ink">{t.title}</td>
                <td><StatusBadge status={t.status as TicketStatus} /></td>
                <td><PriorityBadge priority={t.priority as Priority} /></td>
                <td>
                  {t.sla_due_at ? (
                    <Badge tone={isBreached(t.sla_due_at) ? 'danger' : 'success'}>
                      {formatRelative(t.sla_due_at)}
                    </Badge>
                  ) : (
                    <span className="text-ink-subtle">—</span>
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

/* ─────────────────────────── SLA HEALTH RING ─────────────────────────── */

function SlaHealthCard({
  data,
  isLoading,
}: {
  data: DashboardOverview | undefined;
  isLoading: boolean;
}) {
  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="h-section">SLA health</h2>
          <p className="text-xs text-ink-muted mt-0.5">% of open tickets within SLA</p>
        </div>
        <Badge tone="info">live</Badge>
      </div>

      <div className="my-7 grid place-items-center">
        {isLoading ? (
          <Skeleton className="h-32 w-32" rounded="pill" />
        ) : (
          <Ring value={data?.kpis.sla_health ?? 0} label="on track" />
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <MiniTile label="Breached"      value={data?.kpis.breached}       loading={isLoading} tone="danger"  />
        <MiniTile label="Critical open" value={data?.kpis.critical_open}  loading={isLoading} tone="warning" />
      </div>
    </Card>
  );
}

function MiniTile({
  label,
  value,
  loading,
  tone,
}: {
  label: string;
  value: number | undefined;
  loading?: boolean;
  tone: 'danger' | 'warning' | 'success' | 'info';
}) {
  const ring = {
    danger:  'bg-danger-soft',
    warning: 'bg-warning-soft',
    success: 'bg-success-soft',
    info:    'bg-info-soft',
  }[tone];
  return (
    <div className={cn('rounded-2xl p-4', ring)}>
      <div className="text-2xs uppercase tracking-wider text-ink-muted">{label}</div>
      {loading ? (
        <Skeleton className="h-6 w-12 mt-1" />
      ) : (
        <div className="text-2xl font-semibold tracking-tight text-ink mt-1 tabular-nums">
          {value ?? 0}
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────── ROLE-SPECIFIC ─────────────────────────── */

function RoleSpecificCards({ data }: { data: DashboardOverview }) {
  const role = data.kpis.role;
  const rs = data.role_specific;

  if (role === 'admin') {
    return (
      <Card>
        <div className="flex items-start justify-between">
          <div>
            <h2 className="h-section">Admin queue</h2>
            <p className="text-sm text-ink-muted mt-1">Tickets awaiting acknowledgement or assignment.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link to="/tickets?status=new" className="btn-primary">Triage new tickets</Link>
            <Link to="/escalations" className="btn-secondary">Open escalations</Link>
          </div>
        </div>
        <div className="mt-5 grid grid-cols-2 sm:grid-cols-4 gap-3">
          <BigTile label="Unassigned"        value={rs.unassigned_admin_queue ?? 0} />
          <BigTile label="Open escalations"  value={data.kpis.open_escalations ?? 0} />
        </div>
      </Card>
    );
  }

  if (role === 'agent') {
    return (
      <Card>
        <div className="flex items-start justify-between">
          <div>
            <h2 className="h-section">My workbench</h2>
            <p className="text-sm text-ink-muted mt-1">Tickets currently assigned to you.</p>
          </div>
          <Link to="/tickets" className="btn-primary">Open my tickets</Link>
        </div>
        <div className="mt-5"><BigTile label="My open" value={rs.my_open ?? 0} /></div>
      </Card>
    );
  }

  if (role === 'supervisor') {
    return (
      <Card>
        <div className="flex items-start justify-between">
          <h2 className="h-section">Supervisor watch</h2>
          <div className="flex flex-wrap gap-2">
            <Link to="/sla" className="btn-primary">SLA monitor</Link>
            <Link to="/escalations" className="btn-secondary">Escalations</Link>
          </div>
        </div>
        <div className="mt-5 grid grid-cols-2 sm:grid-cols-3 gap-3">
          <BigTile label="Critical breaches" value={rs.critical_breaches ?? 0} />
          <BigTile label="Open escalations"  value={data.kpis.open_escalations ?? 0} />
        </div>
      </Card>
    );
  }

  if (role === 'branch_user') {
    return (
      <Card>
        <div className="flex items-start justify-between">
          <h2 className="h-section">My branch tickets</h2>
          <Link to="/tickets" className="btn-primary">View my tickets</Link>
        </div>
        <div className="mt-5"><BigTile label="My open" value={rs.my_open ?? 0} /></div>
      </Card>
    );
  }

  return null;
}

function BigTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="glass-subtle rounded-2xl p-4">
      <div className="text-2xs uppercase tracking-wider text-ink-muted">{label}</div>
      <div className="text-3xl font-semibold tracking-tight text-ink mt-1 tabular-nums">{value}</div>
    </div>
  );
}
