import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
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

// ── Skeleton ─────────────────────────────────────────────────────────────────

function Sk({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-lg bg-slate-200 dark:bg-slate-800', className)} />;
}

// ── KPI Card ─────────────────────────────────────────────────────────────────

interface KPICardProps {
  label: string;
  value: number | string;
  suffix?: string;
  tone?: 'default' | 'danger' | 'success' | 'warning';
  icon: string;
  delta?: { value: number; label: string };
}

function KPICard({ label, value, suffix, tone = 'default', icon, delta }: KPICardProps) {
  const toneClasses = {
    default: { value: 'text-slate-900 dark:text-slate-100', icon: 'bg-brand-50 dark:bg-brand-900/30 text-brand-600 dark:text-brand-400' },
    danger:  { value: 'text-red-600 dark:text-red-400',     icon: 'bg-red-50 dark:bg-red-900/30 text-red-500' },
    success: { value: 'text-emerald-600 dark:text-emerald-400', icon: 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-500' },
    warning: { value: 'text-amber-600 dark:text-amber-400', icon: 'bg-amber-50 dark:bg-amber-900/30 text-amber-500' },
  }[tone];

  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800 p-4 flex flex-col gap-2.5">
      <div className="flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-widest text-slate-400 dark:text-slate-500 font-semibold truncate pr-2">
          {label}
        </span>
        <div className={cn('h-7 w-7 rounded-lg flex items-center justify-center shrink-0', toneClasses.icon)}>
          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d={icon} />
          </svg>
        </div>
      </div>
      <div className="flex items-end gap-1.5">
        <span className={cn('text-2xl font-bold tabular-nums leading-none', toneClasses.value)}>
          {value}
        </span>
        {suffix && (
          <span className="text-xs text-slate-400 mb-0.5 font-medium">{suffix}</span>
        )}
      </div>
      {delta && (
        <div className="flex items-center gap-1">
          <span className={cn('text-[10px] font-medium', delta.value >= 0 ? 'text-emerald-600' : 'text-red-500')}>
            {delta.value >= 0 ? '↑' : '↓'} {Math.abs(delta.value)}
          </span>
          <span className="text-[10px] text-slate-400">{delta.label}</span>
        </div>
      )}
    </div>
  );
}

// ── SLA Health ────────────────────────────────────────────────────────────────

function SLAHealthCard({ sla }: { sla: SLAStatus }) {
  const total = sla.on_time + sla.at_risk + sla.breached;
  const pct = (n: number) => (total > 0 ? (n / total) * 100 : 0);

  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800 p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">SLA Health</span>
        <span className={cn(
          'pill text-xs font-semibold',
          sla.compliance_rate >= 90 ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400' :
          sla.compliance_rate >= 75 ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' :
          'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
        )}>
          {sla.compliance_rate.toFixed(1)}% SLO
        </span>
      </div>

      {/* Segmented bar */}
      <div className="flex rounded-full overflow-hidden h-2.5 gap-px mb-3">
        {pct(sla.on_time) > 0 && (
          <div className="bg-emerald-500 transition-all duration-700" style={{ width: `${pct(sla.on_time)}%` }} title={`On time: ${sla.on_time}`} />
        )}
        {pct(sla.at_risk) > 0 && (
          <div className="bg-amber-400 transition-all duration-700" style={{ width: `${pct(sla.at_risk)}%` }} title={`At risk: ${sla.at_risk}`} />
        )}
        {pct(sla.breached) > 0 && (
          <div className="bg-red-500 transition-all duration-700" style={{ width: `${pct(sla.breached)}%` }} title={`Breached: ${sla.breached}`} />
        )}
        {total === 0 && <div className="bg-slate-200 dark:bg-slate-700 w-full" />}
      </div>

      <div className="grid grid-cols-3 gap-2 text-center">
        {[
          { label: 'On Time',  count: sla.on_time,  color: 'bg-emerald-500' },
          { label: 'At Risk',  count: sla.at_risk,  color: 'bg-amber-400' },
          { label: 'Breached', count: sla.breached, color: 'bg-red-500' },
        ].map(({ label, count, color }) => (
          <div key={label} className="flex flex-col items-center gap-0.5">
            <div className="flex items-center gap-1">
              <span className={cn('h-2 w-2 rounded-full inline-block', color)} />
              <span className="text-xs font-bold tabular-nums text-slate-800 dark:text-slate-200">{count}</span>
            </div>
            <span className="text-[10px] text-slate-400">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Category Distribution ─────────────────────────────────────────────────────

interface CategoryItem { category: string; count: number; percentage: number }

function CategoryChart({ items }: { items: CategoryItem[] }) {
  const maxCount = Math.max(...items.map((i) => i.count), 1);
  const shown = items.slice(0, 7);

  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800 p-4">
      <span className="text-sm font-semibold text-slate-800 dark:text-slate-200 block mb-3">Category Breakdown</span>
      <div className="flex flex-col gap-1.5">
        {shown.map((item) => (
          <div key={item.category} className="flex items-center gap-2">
            <span className="text-xs text-slate-500 dark:text-slate-400 w-28 truncate shrink-0" title={item.category}>
              {item.category}
            </span>
            <div className="flex-1 h-1.5 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-brand-500 rounded-full transition-all duration-700"
                style={{ width: `${(item.count / maxCount) * 100}%` }}
              />
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <span className="text-xs font-semibold tabular-nums text-slate-700 dark:text-slate-300 w-7 text-right">{item.count}</span>
              <span className="text-[10px] text-slate-400 w-7 text-right">{item.percentage.toFixed(0)}%</span>
            </div>
          </div>
        ))}
        {items.length === 0 && (
          <p className="text-xs text-slate-400 text-center py-3">No data yet</p>
        )}
      </div>
    </div>
  );
}

// ── Department Table ─────────────────────────────────────────────────────────

interface DeptLoad { department: string; open_count: number; breached_count: number; avg_age_hours: number }

function DeptTable({ rows }: { rows: DeptLoad[] }) {
  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800 overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800">
        <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">Department Load</span>
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-slate-100 dark:border-slate-800">
            <th className="text-left px-4 py-2 text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Department</th>
            <th className="text-right px-3 py-2 text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Open</th>
            <th className="text-right px-3 py-2 text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Breached</th>
            <th className="text-right px-4 py-2 text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Avg Age</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr
              key={row.department}
              className={cn(
                'transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40',
                idx < rows.length - 1 && 'border-b border-slate-50 dark:border-slate-800/60',
              )}
            >
              <td className="px-4 py-2.5 font-medium text-slate-700 dark:text-slate-300">{row.department}</td>
              <td className="px-3 py-2.5 text-right tabular-nums text-slate-600 dark:text-slate-400">{row.open_count}</td>
              <td className="px-3 py-2.5 text-right tabular-nums">
                {row.breached_count > 0
                  ? <span className="text-red-600 dark:text-red-400 font-semibold">{row.breached_count}</span>
                  : <span className="text-slate-300 dark:text-slate-600">—</span>}
              </td>
              <td className="px-4 py-2.5 text-right tabular-nums text-slate-500">
                {row.avg_age_hours < 24 ? `${row.avg_age_hours.toFixed(1)}h` : `${(row.avg_age_hours / 24).toFixed(1)}d`}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={4} className="px-4 py-6 text-center text-slate-400">No department data</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

// ── AI Metrics ────────────────────────────────────────────────────────────────

function AIMetricsPanel({ metrics }: { metrics: AIMetrics }) {
  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800 p-4">
      <div className="flex items-center gap-2 mb-3">
        <div className="h-6 w-6 rounded-lg bg-accent-100 dark:bg-accent-500/20 flex items-center justify-center">
          <svg className="h-3.5 w-3.5 text-accent-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2a10 10 0 0 1 0 20M12 2a10 10 0 0 0 0 20M12 8v4M12 16h.01" />
          </svg>
        </div>
        <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">AI Metrics</span>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-3">
        {[
          { label: 'Categorized',    value: metrics.total_categorized, className: '' },
          { label: 'Avg Confidence', value: `${(metrics.avg_confidence * 100).toFixed(0)}%`, className: '' },
          { label: 'High Risk',      value: metrics.high_risk_tickets, className: metrics.high_risk_tickets > 0 ? 'text-red-600 dark:text-red-400' : '' },
          { label: 'Avg Latency',    value: `${metrics.avg_latency_ms.toFixed(0)}ms`, className: '' },
        ].map(({ label, value, className }) => (
          <div key={label} className="flex flex-col gap-0.5">
            <span className="text-[10px] text-slate-400 uppercase tracking-wide font-medium">{label}</span>
            <span className={cn('text-xl font-bold tabular-nums text-slate-800 dark:text-slate-200', className)}>{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Error Card ────────────────────────────────────────────────────────────────

function ErrorCard({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-red-100 dark:border-red-900/40 p-4 flex items-center gap-3">
      <svg className="h-5 w-5 text-red-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" />
      </svg>
      <p className="text-sm text-slate-600 dark:text-slate-400 flex-1">{message}</p>
      <button onClick={onRetry} className="text-xs text-brand-600 dark:text-brand-400 hover:underline font-medium">Retry</button>
    </div>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────────

export function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const kpiQuery      = useQuery({ queryKey: ['dashboard', 'kpis'],        queryFn: getDashboardKPIs,       staleTime: STALE, refetchInterval: STALE });
  const slaQuery      = useQuery({ queryKey: ['dashboard', 'sla'],         queryFn: getSLAStatus,           staleTime: STALE, refetchInterval: STALE });
  const categoryQuery = useQuery({ queryKey: ['dashboard', 'categories'],  queryFn: getCategoryDistribution, staleTime: STALE, refetchInterval: STALE });
  const deptQuery     = useQuery({ queryKey: ['dashboard', 'departments'], queryFn: getDepartmentLoad,      staleTime: STALE, refetchInterval: STALE });
  const recentQuery   = useQuery({ queryKey: ['dashboard', 'recent'],      queryFn: getRecentTickets,       staleTime: STALE, refetchInterval: STALE });
  const aiQuery       = useQuery({ queryKey: ['dashboard', 'ai-metrics'],  queryFn: getAIMetrics,           staleTime: STALE, refetchInterval: STALE });

  const kpis = kpiQuery.data as KPIData | undefined;
  const recentTickets = (recentQuery.data ?? []) as TicketSummary[];
  const isRefreshing = kpiQuery.isFetching || slaQuery.isFetching;

  return (
    <div className="flex flex-col gap-5">

      {/* ── Page header ──────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
            Welcome, <span className="text-brand-600 dark:text-brand-400">{user?.full_name?.split(' ')[0] ?? 'User'}</span>
          </h1>
          <p className="text-xs text-slate-400 mt-0.5">Operational overview · SUCCESS Bank Internal Ticketing</p>
        </div>
        <div className="flex items-center gap-2">
          {isRefreshing && (
            <span className="text-[11px] text-slate-400 flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse inline-block" />
              Live
            </span>
          )}
          <Button onClick={() => navigate('/tickets/new')}>
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
            New Ticket
          </Button>
        </div>
      </div>

      {/* ── 8-column KPI strip ───────────────────────────────────────── */}
      {kpiQuery.isLoading ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-8 gap-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="rounded-xl border border-slate-200 dark:border-slate-800 p-4 flex flex-col gap-2">
              <Sk className="h-2.5 w-20 rounded" />
              <Sk className="h-7 w-12 rounded-lg" />
            </div>
          ))}
        </div>
      ) : kpiQuery.isError ? (
        <ErrorCard message="Failed to load KPI data" onRetry={() => kpiQuery.refetch()} />
      ) : kpis ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-8 gap-3">
          <KPICard label="Open"         value={kpis.open_tickets}       tone="default"                                           icon="M9 12h6M9 16h6M13 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-5-5z" />
          <KPICard label="SLA Breached" value={kpis.sla_breached}       tone="danger"                                            icon="M12 9v4M12 17h.01M4.93 19h14.14L12 5z" />
          <KPICard label="Resolved"     value={kpis.resolved_today}     tone="success"                                           icon="M5 13l4 4L19 7" />
          <KPICard label="Critical"     value={kpis.critical_open}      tone={kpis.critical_open > 0 ? 'danger' : 'default'}    icon="M12 8v4M12 16h.01M4.93 19h14.14L12 5z" />
          <KPICard label="AI Sorted"    value={kpis.ai_auto_categorized} tone="default"                                          icon="M12 2a10 10 0 0 1 0 20M12 2a10 10 0 0 0 0 20M12 8v4M12 16h.01" />
          <KPICard label="Via Email"    value={kpis.email_tickets_today} tone="default"                                          icon="M4 4h16v16H4V4zm0 0l8 9 8-9" />
          <KPICard label="Escalated"    value={kpis.escalations_active} tone={kpis.escalations_active > 0 ? 'warning' : 'default'} icon="M12 9v4M12 17h.01M4.93 19h14.14L12 5z" />
          <KPICard
            label="Avg Resolve"
            value={kpis.avg_resolution_hours < 24
              ? kpis.avg_resolution_hours.toFixed(1)
              : (kpis.avg_resolution_hours / 24).toFixed(1)}
            suffix={kpis.avg_resolution_hours < 24 ? 'h' : 'd'}
            tone="default"
            icon="M12 8v4l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z"
          />
        </div>
      ) : null}

      {/* ── Middle row: SLA + Categories + AI ───────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* SLA */}
        <div>
          {slaQuery.isLoading ? (
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800 p-4">
              <Sk className="h-32" />
            </div>
          ) : slaQuery.isError ? (
            <ErrorCard message="Failed to load SLA data" onRetry={() => slaQuery.refetch()} />
          ) : slaQuery.data ? (
            <SLAHealthCard sla={slaQuery.data} />
          ) : null}
        </div>

        {/* Categories */}
        <div>
          {categoryQuery.isLoading ? (
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800 p-4">
              <Sk className="h-32" />
            </div>
          ) : categoryQuery.isError ? (
            <ErrorCard message="Failed to load category data" onRetry={() => categoryQuery.refetch()} />
          ) : categoryQuery.data ? (
            <CategoryChart items={categoryQuery.data} />
          ) : null}
        </div>

        {/* AI metrics */}
        <div>
          {aiQuery.isLoading ? (
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800 p-4">
              <Sk className="h-32" />
            </div>
          ) : aiQuery.isError ? (
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800 p-4 text-xs text-slate-400 text-center py-8">AI metrics unavailable</div>
          ) : aiQuery.data ? (
            <AIMetricsPanel metrics={aiQuery.data} />
          ) : null}
        </div>
      </div>

      {/* ── Bottom row: dept table + recent tickets ──────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
        {/* Dept table — takes 2 of 5 cols */}
        <div className="xl:col-span-2">
          {deptQuery.isLoading ? (
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800 p-4">
              <Sk className="h-40" />
            </div>
          ) : deptQuery.isError ? (
            <ErrorCard message="Failed to load department data" onRetry={() => deptQuery.refetch()} />
          ) : deptQuery.data ? (
            <DeptTable rows={deptQuery.data} />
          ) : null}
        </div>

        {/* Recent tickets — takes 3 of 5 cols */}
        <div className="xl:col-span-3">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">Recent Tickets</span>
            <button
              onClick={() => navigate('/tickets')}
              className="text-xs text-brand-600 dark:text-brand-400 hover:underline font-medium flex items-center gap-1"
            >
              View all
              <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </button>
          </div>

          {recentQuery.isLoading ? (
            <div className="flex flex-col gap-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="rounded-xl border border-slate-200 dark:border-slate-800 p-3">
                  <div className="flex flex-col gap-2">
                    <Sk className="h-3 w-24" />
                    <Sk className="h-4 w-full" />
                    <Sk className="h-2.5 w-1/2" />
                  </div>
                </div>
              ))}
            </div>
          ) : recentQuery.isError ? (
            <ErrorCard message="Failed to load recent tickets" onRetry={() => recentQuery.refetch()} />
          ) : recentTickets.length === 0 ? (
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800 p-8 flex flex-col items-center gap-2 text-center">
              <svg className="h-8 w-8 text-slate-300 dark:text-slate-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M9 12h6M9 16h6M13 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-5-5z" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <p className="text-sm text-slate-400">No recent tickets</p>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {recentTickets.slice(0, 8).map((ticket) => (
                <TicketCard key={ticket.id} ticket={ticket} compact />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
