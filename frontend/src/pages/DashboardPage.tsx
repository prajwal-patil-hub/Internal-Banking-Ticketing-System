import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { TicketCard } from '@/components/TicketCard';
import { useAuth } from '@/store/auth';
import { cn } from '@/lib/cn';
import {
  getDashboardKPIs,
  getSLAStatus,
  getCategoryDistribution,
  getDepartmentLoad,
  getRecentTickets,
  getAIMetrics,
} from '@/features/dashboard/api';
import type { KPIData, SLAStatus, AIMetrics } from '@/features/dashboard/api';
import type { TicketSummary } from '@/features/tickets/api';

const STALE = 30_000;

// ---------- Skeleton ----------

function Skeleton({ className }: { className?: string }) {
  return (
    <div className={cn('animate-pulse rounded-xl bg-slate-200 dark:bg-slate-800', className)} />
  );
}

function KPISkeleton() {
  return (
    <Card className="flex flex-col gap-2">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-8 w-16 mt-1" />
    </Card>
  );
}

// ---------- KPI Card ----------

interface KPICardProps {
  label: string;
  value: number | string;
  suffix?: string;
  tone?: 'default' | 'danger' | 'success' | 'warning';
  icon: string;
}

function KPICard({ label, value, suffix, tone = 'default', icon }: KPICardProps) {
  const valueClass = {
    default: 'text-slate-900 dark:text-slate-100',
    danger: 'text-red-600',
    success: 'text-emerald-600',
    warning: 'text-amber-600',
  }[tone];

  return (
    <Card className="flex flex-col gap-1 relative overflow-hidden">
      <div className="flex items-start justify-between">
        <span className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400 font-medium">
          {label}
        </span>
        <div className="h-8 w-8 rounded-lg bg-brand-50 dark:bg-brand-900/30 flex items-center justify-center shrink-0">
          <svg className="h-4 w-4 text-brand-600 dark:text-brand-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d={icon} />
          </svg>
        </div>
      </div>
      <div className="flex items-end gap-1 mt-1">
        <span className={cn('text-3xl font-semibold tabular-nums', valueClass)}>
          {value}
        </span>
        {suffix && (
          <span className="text-sm text-slate-500 mb-1">{suffix}</span>
        )}
      </div>
    </Card>
  );
}

// ---------- SLA Health Bar ----------

function SLAHealthBar({ sla }: { sla: SLAStatus }) {
  const total = sla.on_time + sla.at_risk + sla.breached;
  const onTimePct = total > 0 ? (sla.on_time / total) * 100 : 0;
  const atRiskPct = total > 0 ? (sla.at_risk / total) * 100 : 0;
  const breachedPct = total > 0 ? (sla.breached / total) * 100 : 0;

  return (
    <Card>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-base font-semibold">SLA Health</h2>
        <span className={cn(
          'pill text-sm font-semibold',
          sla.compliance_rate >= 90 ? 'bg-emerald-100 text-emerald-700' :
          sla.compliance_rate >= 75 ? 'bg-amber-100 text-amber-700' :
          'bg-red-100 text-red-700',
        )}>
          {sla.compliance_rate.toFixed(1)}% compliant
        </span>
      </div>

      {/* Segmented bar */}
      <div className="flex rounded-full overflow-hidden h-4 gap-0.5">
        {onTimePct > 0 && (
          <div
            className="bg-emerald-500 transition-all duration-700"
            style={{ width: `${onTimePct}%` }}
            title={`On time: ${sla.on_time}`}
          />
        )}
        {atRiskPct > 0 && (
          <div
            className="bg-amber-400 transition-all duration-700"
            style={{ width: `${atRiskPct}%` }}
            title={`At risk: ${sla.at_risk}`}
          />
        )}
        {breachedPct > 0 && (
          <div
            className="bg-red-500 transition-all duration-700"
            style={{ width: `${breachedPct}%` }}
            title={`Breached: ${sla.breached}`}
          />
        )}
      </div>

      <div className="flex items-center gap-4 mt-3 text-xs text-slate-600 dark:text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500 inline-block" />
          On Time: {sla.on_time}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-amber-400 inline-block" />
          At Risk: {sla.at_risk}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-red-500 inline-block" />
          Breached: {sla.breached}
        </span>
      </div>
    </Card>
  );
}

// ---------- Category Distribution ----------

interface CategoryItem {
  category: string;
  count: number;
  percentage: number;
}

function CategoryDistribution({ items }: { items: CategoryItem[] }) {
  const maxCount = Math.max(...items.map((i) => i.count), 1);

  return (
    <Card>
      <h2 className="text-base font-semibold mb-4">Category Distribution</h2>
      <div className="flex flex-col gap-2.5">
        {items.slice(0, 8).map((item) => (
          <div key={item.category} className="flex items-center gap-3">
            <span className="text-xs text-slate-600 dark:text-slate-400 w-32 truncate shrink-0" title={item.category}>
              {item.category}
            </span>
            <div className="flex-1 h-5 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-brand-500 rounded-full transition-all duration-700"
                style={{ width: `${(item.count / maxCount) * 100}%` }}
              />
            </div>
            <span className="text-xs font-medium text-slate-700 dark:text-slate-300 w-10 text-right shrink-0">
              {item.count}
            </span>
            <span className="text-xs text-slate-400 w-10 text-right shrink-0">
              {item.percentage.toFixed(0)}%
            </span>
          </div>
        ))}
        {items.length === 0 && (
          <p className="text-sm text-slate-400 text-center py-4">No data available</p>
        )}
      </div>
    </Card>
  );
}

// ---------- Department Load Table ----------

interface DeptLoad {
  department: string;
  open_count: number;
  breached_count: number;
  avg_age_hours: number;
}

function DepartmentTable({ rows }: { rows: DeptLoad[] }) {
  return (
    <Card padded={false}>
      <div className="p-6 pb-2">
        <h2 className="text-base font-semibold">Department Load</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100 dark:border-slate-800">
              <th className="text-left px-6 py-2 text-xs uppercase tracking-wide text-slate-500 font-medium">Department</th>
              <th className="text-right px-4 py-2 text-xs uppercase tracking-wide text-slate-500 font-medium">Open</th>
              <th className="text-right px-4 py-2 text-xs uppercase tracking-wide text-slate-500 font-medium">Breached</th>
              <th className="text-right px-6 py-2 text-xs uppercase tracking-wide text-slate-500 font-medium">Avg Age</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr
                key={row.department}
                className={cn(
                  'border-b border-slate-50 dark:border-slate-800/50 hover:bg-surface-subtle dark:hover:bg-slate-800/30 transition-colors',
                  idx === rows.length - 1 && 'border-b-0',
                )}
              >
                <td className="px-6 py-3 font-medium text-slate-800 dark:text-slate-200">{row.department}</td>
                <td className="px-4 py-3 text-right tabular-nums">{row.open_count}</td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {row.breached_count > 0 ? (
                    <span className="text-red-600 font-medium">{row.breached_count}</span>
                  ) : (
                    <span className="text-slate-400">0</span>
                  )}
                </td>
                <td className="px-6 py-3 text-right tabular-nums text-slate-500">
                  {row.avg_age_hours < 24
                    ? `${row.avg_age_hours.toFixed(1)}h`
                    : `${(row.avg_age_hours / 24).toFixed(1)}d`}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={4} className="px-6 py-8 text-center text-slate-400 text-sm">No department data</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

// ---------- AI Metrics Card ----------

function AIMetricsCard({ metrics }: { metrics: AIMetrics }) {
  return (
    <Card>
      <div className="flex items-center gap-2 mb-4">
        <div className="h-7 w-7 rounded-lg bg-accent-100 dark:bg-accent-500/20 flex items-center justify-center">
          <svg className="h-4 w-4 text-accent-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2a10 10 0 0 1 0 20M12 2a10 10 0 0 0 0 20M12 8v4M12 16h.01" />
          </svg>
        </div>
        <h2 className="text-base font-semibold">AI Metrics</h2>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-0.5">
          <span className="text-xs text-slate-500">Categorized</span>
          <span className="text-xl font-semibold tabular-nums">{metrics.total_categorized}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-xs text-slate-500">Avg Confidence</span>
          <span className="text-xl font-semibold tabular-nums">{(metrics.avg_confidence * 100).toFixed(0)}%</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-xs text-slate-500">High Risk</span>
          <span className="text-xl font-semibold tabular-nums text-red-600">{metrics.high_risk_tickets}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-xs text-slate-500">Avg Latency</span>
          <span className="text-xl font-semibold tabular-nums">{metrics.avg_latency_ms.toFixed(0)}ms</span>
        </div>
      </div>
    </Card>
  );
}

// ---------- Error state ----------

function ErrorCard({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Card className="flex flex-col items-center gap-3 py-8">
      <svg className="h-10 w-10 text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <path d="M12 8v4M12 16h.01" />
      </svg>
      <p className="text-sm text-slate-600 dark:text-slate-400">{message}</p>
      <Button variant="ghost" onClick={onRetry}>Retry</Button>
    </Card>
  );
}

// ---------- Main Dashboard ----------

export function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const kpiQuery = useQuery({
    queryKey: ['dashboard', 'kpis'],
    queryFn: getDashboardKPIs,
    staleTime: STALE,
    refetchInterval: STALE,
  });

  const slaQuery = useQuery({
    queryKey: ['dashboard', 'sla'],
    queryFn: getSLAStatus,
    staleTime: STALE,
    refetchInterval: STALE,
  });

  const categoryQuery = useQuery({
    queryKey: ['dashboard', 'categories'],
    queryFn: getCategoryDistribution,
    staleTime: STALE,
    refetchInterval: STALE,
  });

  const deptQuery = useQuery({
    queryKey: ['dashboard', 'departments'],
    queryFn: getDepartmentLoad,
    staleTime: STALE,
    refetchInterval: STALE,
  });

  const recentQuery = useQuery({
    queryKey: ['dashboard', 'recent'],
    queryFn: getRecentTickets,
    staleTime: STALE,
    refetchInterval: STALE,
  });

  const aiMetricsQuery = useQuery({
    queryKey: ['dashboard', 'ai-metrics'],
    queryFn: getAIMetrics,
    staleTime: STALE,
    refetchInterval: STALE,
  });

  const kpis: KPIData | undefined = kpiQuery.data;
  const recentTickets = (recentQuery.data ?? []) as TicketSummary[];

  return (
    <div className="flex flex-col gap-6">
      {/* Page header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Welcome back, {user?.full_name?.split(' ')[0] ?? 'User'}
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            SUCCESS Bank · Internal Ticketing Platform · Operational overview
          </p>
        </div>
        <div className="flex items-center gap-3">
          {kpiQuery.isFetching && (
            <span className="text-xs text-slate-400 flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse inline-block" />
              Refreshing…
            </span>
          )}
          <Button onClick={() => navigate('/tickets/new')}>
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
            New Ticket
          </Button>
        </div>
      </div>

      {/* Primary KPIs row 1 */}
      {kpiQuery.isLoading ? (
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => <KPISkeleton key={i} />)}
        </div>
      ) : kpiQuery.isError ? (
        <ErrorCard message="Failed to load KPI data" onRetry={() => kpiQuery.refetch()} />
      ) : kpis ? (
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          <KPICard
            label="Open Tickets"
            value={kpis.open_tickets}
            tone="default"
            icon="M9 12h6M9 16h6M13 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-5-5z"
          />
          <KPICard
            label="SLA Breached"
            value={kpis.sla_breached}
            tone="danger"
            icon="M12 9v4M12 17h.01M4.93 19h14.14L12 5z"
          />
          <KPICard
            label="Resolved Today"
            value={kpis.resolved_today}
            tone="success"
            icon="M5 13l4 4L19 7"
          />
          <KPICard
            label="Critical Open"
            value={kpis.critical_open}
            tone={kpis.critical_open > 0 ? 'danger' : 'default'}
            icon="M12 8v4M12 16h.01M4.93 19h14.14L12 5z"
          />
        </div>
      ) : null}

      {/* Secondary KPIs row 2 */}
      {kpis && (
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          <KPICard
            label="AI Categorized"
            value={kpis.ai_auto_categorized}
            tone="default"
            icon="M12 2a10 10 0 0 1 0 20M12 2a10 10 0 0 0 0 20M12 8v4M12 16h.01"
          />
          <KPICard
            label="Email Tickets Today"
            value={kpis.email_tickets_today}
            tone="default"
            icon="M4 4h16v16H4V4zm0 0l8 9 8-9"
          />
          <KPICard
            label="Escalations Active"
            value={kpis.escalations_active}
            tone={kpis.escalations_active > 0 ? 'warning' : 'default'}
            icon="M12 9v4M12 17h.01M4.93 19h14.14L12 5z"
          />
          <KPICard
            label="Avg Resolution"
            value={kpis.avg_resolution_hours < 24
              ? kpis.avg_resolution_hours.toFixed(1)
              : (kpis.avg_resolution_hours / 24).toFixed(1)}
            suffix={kpis.avg_resolution_hours < 24 ? 'hrs' : 'days'}
            tone="default"
            icon="M12 8v4l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z"
          />
        </div>
      )}

      {/* Middle row: SLA + Category */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {slaQuery.isLoading ? (
          <Card><Skeleton className="h-32" /></Card>
        ) : slaQuery.isError ? (
          <ErrorCard message="Failed to load SLA data" onRetry={() => slaQuery.refetch()} />
        ) : slaQuery.data ? (
          <SLAHealthBar sla={slaQuery.data} />
        ) : null}

        {categoryQuery.isLoading ? (
          <Card><Skeleton className="h-32" /></Card>
        ) : categoryQuery.isError ? (
          <ErrorCard message="Failed to load category data" onRetry={() => categoryQuery.refetch()} />
        ) : categoryQuery.data ? (
          <CategoryDistribution items={categoryQuery.data} />
        ) : null}
      </div>

      {/* Bottom row: dept table + AI metrics */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2">
          {deptQuery.isLoading ? (
            <Card><Skeleton className="h-40" /></Card>
          ) : deptQuery.isError ? (
            <ErrorCard message="Failed to load department data" onRetry={() => deptQuery.refetch()} />
          ) : deptQuery.data ? (
            <DepartmentTable rows={deptQuery.data} />
          ) : null}
        </div>

        <div>
          {aiMetricsQuery.isLoading ? (
            <Card><Skeleton className="h-40" /></Card>
          ) : aiMetricsQuery.isError ? (
            <Card className="text-sm text-slate-400 text-center py-8">AI metrics unavailable</Card>
          ) : aiMetricsQuery.data ? (
            <AIMetricsCard metrics={aiMetricsQuery.data} />
          ) : null}
        </div>
      </div>

      {/* Recent Tickets */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold">Recent Tickets</h2>
          <Button variant="ghost" onClick={() => navigate('/tickets')}>
            View all tickets
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </Button>
        </div>

        {recentQuery.isLoading ? (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Card key={i} padded={false} className="p-4">
                <div className="flex flex-col gap-2">
                  <Skeleton className="h-3 w-20" />
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-3 w-3/4" />
                </div>
              </Card>
            ))}
          </div>
        ) : recentQuery.isError ? (
          <ErrorCard message="Failed to load recent tickets" onRetry={() => recentQuery.refetch()} />
        ) : recentTickets.length === 0 ? (
          <Card className="flex flex-col items-center gap-2 py-10 text-center">
            <svg className="h-10 w-10 text-slate-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M9 12h6M9 16h6M13 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-5-5z" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <p className="text-sm text-slate-500">No recent tickets</p>
          </Card>
        ) : (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            {recentTickets.slice(0, 10).map((ticket) => (
              <TicketCard key={ticket.id} ticket={ticket} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
