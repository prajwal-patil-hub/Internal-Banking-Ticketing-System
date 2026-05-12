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
  Building2,
  Timer,
} from 'lucide-react';

import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Ring } from '@/components/Ring';
import { Skeleton } from '@/components/Skeleton';
import { Sparkline } from '@/components/charts/Sparkline';
import { BarChart } from '@/components/charts/BarChart';
import { Donut } from '@/components/charts/Donut';
import { PriorityBadge, StatusBadge } from '@/features/tickets/components/StatusBadge';
import {
  dashboardAnalytics,
  dashboardOverview,
  type DashboardAnalytics,
  type DashboardOverview,
} from '@/features/dashboard/api';
import { extractError } from '@/lib/api';
import { formatRelative, isBreached } from '@/lib/format';
import { useAuth } from '@/store/auth';
import { cn } from '@/lib/cn';
import type { Priority, TicketStatus } from '@/features/tickets/types';

const PRIORITY_COLORS: Record<string, string> = {
  critical: '#8B2635',  // claret
  high:     '#B8860B',  // honey
  medium:   '#4A6FA5',  // dust
  low:      '#56616F',  // graphite
};

const OPEN_STATUSES = ['new', 'acknowledged', 'assigned', 'in_progress', 'on_hold', 'escalated', 'reopened'];

const linkForKpi = (key: string) => {
  const params = new URLSearchParams();
  switch (key) {
    case 'open':
      OPEN_STATUSES.forEach((s) => params.append('status', s));
      break;
    case 'breached':
      params.set('breached', 'true');
      break;
    case 'response_breached':
      OPEN_STATUSES.forEach((s) => params.append('status', s));
      break;
    case 'critical_open':
      OPEN_STATUSES.forEach((s) => params.append('status', s));
      params.append('priority', 'critical');
      break;
    case 'resolved':
      params.append('status', 'resolved');
      params.append('status', 'closed');
      break;
  }
  return `/tickets?${params.toString()}`;
};

export function DashboardPage() {
  const { user } = useAuth();

  const overview = useQuery({
    queryKey: ['dashboard', 'overview'],
    queryFn: dashboardOverview,
    refetchInterval: 60_000,
  });
  const analytics = useQuery({
    queryKey: ['dashboard', 'analytics'],
    queryFn: dashboardAnalytics,
    refetchInterval: 120_000,
  });

  if (overview.isError) {
    return (
      <Card>
        <h2 className="h-section">Couldn't load the dashboard.</h2>
        <p className="text-sm text-ink-muted mt-2">{extractError(overview.error).message}</p>
        <button onClick={() => overview.refetch()} className="btn-primary mt-4">Try again</button>
      </Card>
    );
  }

  const data = overview.data;
  const analyticsData = analytics.data;

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
            A live snapshot of operations across all branches. Open tickets, breached SLAs,
            escalations, and recent activity at a glance.
          </p>
          <div className="hairline-brass mt-4 max-w-xs" />
        </div>
        <div className="flex items-center gap-2">
          <Link to="/tickets" className="btn-secondary">View all tickets</Link>
          <Link to="/sla" className="btn-primary">
            <Sparkles className="h-4 w-4" />
            SLA monitor
          </Link>
        </div>
      </motion.header>

      <KpiStrip data={data} isLoading={overview.isLoading} analytics={analyticsData} />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <RecentTickets data={data} isLoading={overview.isLoading} />
        <SlaHealthCard data={data} isLoading={overview.isLoading} />
      </div>

      {/* Analytics row */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <DailyVolumeCard analytics={analyticsData} loading={analytics.isLoading} />
        <PriorityMixCard analytics={analyticsData} loading={analytics.isLoading} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <StatusBreakdownCard analytics={analyticsData} loading={analytics.isLoading} />
        <ResolutionTimeCard analytics={analyticsData} loading={analytics.isLoading} />
        <TopBranchesCard analytics={analyticsData} loading={analytics.isLoading} />
      </div>

      {data && <RoleSpecificCards data={data} />}
    </div>
  );
}

/* ────────────────────────────── KPI STRIP ────────────────────────────── */

function KpiStrip({
  data,
  isLoading,
  analytics,
}: {
  data: DashboardOverview | undefined;
  isLoading: boolean;
  analytics: DashboardAnalytics | undefined;
}) {
  const dailyTotals = analytics?.daily_volume.map((d) => d.total) ?? [];
  const dailyCritical = analytics?.daily_volume.map((d) => d.critical) ?? [];

  const tiles = [
    { key: 'open',              label: 'Open tickets',          value: data?.kpis.open,              icon: Inbox,         tone: 'info' as const,    series: dailyTotals,    sparkColor: '#1F3A5F' },
    { key: 'breached',          label: 'Resolution breached',   value: data?.kpis.breached,          icon: AlertTriangle, tone: 'danger' as const,  series: dailyCritical,  sparkColor: '#8B2635' },
    { key: 'response_breached', label: 'First-response missed', value: data?.kpis.response_breached, icon: Clock4,        tone: 'warning' as const, series: dailyCritical,  sparkColor: '#B8860B' },
    { key: 'critical_open',     label: 'Critical, open',        value: data?.kpis.critical_open,     icon: Flame,         tone: 'warning' as const, series: dailyCritical,  sparkColor: '#B8860B' },
    { key: 'resolved',          label: 'Resolved / closed',     value: data?.kpis.resolved,          icon: CheckCircle2,  tone: 'success' as const, series: dailyTotals,    sparkColor: '#4A7C59' },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-4">
      {tiles.map((t, i) => {
        const Icon = t.icon;
        return (
          <motion.div
            key={t.key}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.04 * i, ease: [0.22, 1, 0.36, 1] }}
            whileHover={{ y: -2 }}
          >
            <Link
              to={linkForKpi(t.key)}
              className="glass rounded-4xl p-5 hover:shadow-glassLg transition-shadow block focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-300 h-full"
              aria-label={`${t.label}: ${t.value ?? 0}. View matching tickets.`}
            >
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
                <Badge tone={t.tone}>view</Badge>
              </div>
              <div className="mt-4 text-2xs uppercase tracking-wider text-ink-muted">{t.label}</div>
              {isLoading ? (
                <Skeleton className="h-8 w-20 mt-1.5" />
              ) : (
                <div className="text-4xl font-semibold tracking-tight text-ink mt-1 tabular-nums">
                  {t.value ?? 0}
                </div>
              )}
              <div className="mt-3 -mx-1">
                <Sparkline values={t.series} stroke={t.sparkColor} fill={`${t.sparkColor}1F`} height={28} />
              </div>
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
            {isLoading && Array.from({ length: 5 }).map((_, i) => (
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
        <Badge tone="brass">live</Badge>
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

/* ─────────────────────────── ANALYTICS CARDS ─────────────────────────── */

function DailyVolumeCard({
  analytics,
  loading,
}: {
  analytics: DashboardAnalytics | undefined;
  loading: boolean;
}) {
  const series = analytics?.daily_volume ?? [];
  const max = Math.max(1, ...series.map((d) => d.total));
  return (
    <Card className="xl:col-span-2">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="h-section">Daily ticket volume</h2>
          <p className="text-xs text-ink-muted mt-0.5">Last 14 days · critical highlighted</p>
        </div>
        <div className="flex items-center gap-3 text-2xs text-ink-muted">
          <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-pill bg-brand-600" /> total</span>
          <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-pill bg-danger" /> critical</span>
        </div>
      </div>

      {loading ? (
        <div className="mt-6 grid grid-cols-14 gap-1.5">
          {Array.from({ length: 14 }).map((_, i) => (
            <Skeleton key={i} className="h-32 w-full" rounded="md" />
          ))}
        </div>
      ) : (
        <div className="mt-6 flex items-end gap-1.5" style={{ height: 160 }}>
          {series.map((d) => {
            const h = (d.total / max) * 140;
            const ch = (d.critical / max) * 140;
            const day = new Date(d.date).toLocaleDateString(undefined, { weekday: 'short' });
            return (
              <div key={d.date} className="flex-1 flex flex-col items-center gap-1.5 group">
                <div className="relative w-full max-w-[28px] rounded-md overflow-hidden" style={{ height: 140 }}>
                  <motion.div
                    initial={{ height: 0 }}
                    animate={{ height: h }}
                    transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
                    className="absolute bottom-0 left-0 right-0 bg-brand-600/85 group-hover:bg-brand-700 rounded-md"
                  />
                  <motion.div
                    initial={{ height: 0 }}
                    animate={{ height: ch }}
                    transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1], delay: 0.08 }}
                    className="absolute bottom-0 left-0 right-0 bg-danger rounded-md"
                  />
                  {d.total > 0 && (
                    <span className="absolute -top-5 left-1/2 -translate-x-1/2 text-2xs text-ink-muted opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none">
                      {d.total} · {d.critical}c
                    </span>
                  )}
                </div>
                <div className="text-2xs text-ink-muted">{day[0]}</div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

function PriorityMixCard({
  analytics,
  loading,
}: {
  analytics: DashboardAnalytics | undefined;
  loading: boolean;
}) {
  const order = ['critical', 'high', 'medium', 'low'] as const;
  const slices = order.map((p) => ({
    label: p,
    value: analytics?.by_priority[p] ?? 0,
    color: PRIORITY_COLORS[p],
  }));
  return (
    <Card>
      <h2 className="h-section">By priority</h2>
      <p className="text-xs text-ink-muted mt-0.5">Open tickets, current state</p>
      {loading ? (
        <Skeleton className="h-48 w-full mt-4" rounded="2xl" />
      ) : (
        <div className="mt-5">
          <Donut slices={slices} size={170} stroke={20} centerLabel="open" />
        </div>
      )}
    </Card>
  );
}

function StatusBreakdownCard({
  analytics,
  loading,
}: {
  analytics: DashboardAnalytics | undefined;
  loading: boolean;
}) {
  const data = analytics?.by_status ?? {};
  const order = [
    'new', 'acknowledged', 'assigned', 'in_progress', 'on_hold',
    'escalated', 'resolved', 'closed', 'reopened',
  ];
  const rows = order
    .filter((s) => (data[s] ?? 0) > 0)
    .map((s) => ({
      label: s.replace('_', ' '),
      value: data[s] ?? 0,
      tone: 'brand' as const,
    }));

  return (
    <Card>
      <h2 className="h-section">By status</h2>
      <p className="text-xs text-ink-muted mt-0.5">All tickets, all time</p>
      {loading ? (
        <Skeleton className="h-40 w-full mt-4" rounded="2xl" />
      ) : (
        <div className="mt-5">
          {rows.length === 0 ? (
            <p className="text-sm text-ink-muted">No tickets yet.</p>
          ) : (
            <BarChart rows={rows} />
          )}
        </div>
      )}
    </Card>
  );
}

function ResolutionTimeCard({
  analytics,
  loading,
}: {
  analytics: DashboardAnalytics | undefined;
  loading: boolean;
}) {
  const rows = analytics?.avg_resolution_minutes ?? [];
  return (
    <Card>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="h-section">Avg time to resolve</h2>
          <p className="text-xs text-ink-muted mt-0.5">Last 30 days · by priority</p>
        </div>
        <Timer className="h-5 w-5 text-brass-500" />
      </div>
      {loading ? (
        <Skeleton className="h-32 w-full mt-4" rounded="2xl" />
      ) : rows.length === 0 ? (
        <p className="text-sm text-ink-muted mt-4">No resolved tickets in window.</p>
      ) : (
        <div className="mt-5 space-y-3">
          {rows.map((r) => (
            <div key={r.priority} className="flex items-center justify-between">
              <PriorityBadge priority={r.priority as Priority} />
              <div className="text-right">
                <div className="text-md font-semibold tabular-nums text-ink">
                  {r.minutes != null ? formatMinutes(r.minutes) : '—'}
                </div>
                <div className="text-2xs text-ink-muted">{r.n} resolved</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function TopBranchesCard({
  analytics,
  loading,
}: {
  analytics: DashboardAnalytics | undefined;
  loading: boolean;
}) {
  const rows = (analytics?.top_branches ?? []).map((b) => ({
    label: `${b.code} · ${b.name}`,
    value: b.count,
    tone: 'brass' as const,
  }));
  return (
    <Card>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="h-section">Top branches</h2>
          <p className="text-xs text-ink-muted mt-0.5">Last 30 days · ticket volume</p>
        </div>
        <Building2 className="h-5 w-5 text-brass-500" />
      </div>
      {loading ? (
        <Skeleton className="h-32 w-full mt-4" rounded="2xl" />
      ) : rows.length === 0 ? (
        <p className="text-sm text-ink-muted mt-4">No data (branch users see their own branch only).</p>
      ) : (
        <div className="mt-5">
          <BarChart rows={rows} />
        </div>
      )}
    </Card>
  );
}

function formatMinutes(m: number): string {
  if (m < 60) return `${m.toFixed(0)}m`;
  if (m < 1440) return `${(m / 60).toFixed(1)}h`;
  return `${(m / 1440).toFixed(1)}d`;
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
