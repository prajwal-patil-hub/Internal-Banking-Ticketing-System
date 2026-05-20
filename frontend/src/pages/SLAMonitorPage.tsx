import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';

import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { listTickets } from '@/features/tickets/api';
import { api } from '@/lib/api';
import { cn } from '@/lib/cn';

const STALE = 30_000;

interface SLAStatusRaw {
  total_tracked: number;
  response_sla_breached: number;
  resolution_sla_breached: number;
  at_risk_next_60min: number;
  sla_compliance_rate: number;
  health_by_priority: Record<string, { total: number; breached: number; compliance_rate: number }>;
  as_of: string;
}

async function getSLAStatusRaw(): Promise<SLAStatusRaw> {
  const { data } = await api.get('/dashboard/sla-status');
  return data.data ?? {};
}

function KPI({ label, value, tone = 'default' }: { label: string; value: string | number; tone?: 'default' | 'danger' | 'warning' | 'good' }) {
  const toneClass = {
    default: 'text-ink-900 dark:text-ink-50',
    danger:  'text-oxblood',
    warning: 'text-accent-500',
    good:    'text-brand-500',
  }[tone];
  return (
    <Card>
      <p className="text-xs uppercase tracking-wide text-ink-500 font-medium">{label}</p>
      <p className={cn('mt-1 text-3xl font-semibold tabular-nums', toneClass)}>{value}</p>
    </Card>
  );
}

export function SLAMonitorPage() {
  const navigate = useNavigate();

  const sla = useQuery({
    queryKey: ['sla-monitor', 'status'],
    queryFn: getSLAStatusRaw,
    staleTime: STALE,
    refetchInterval: STALE,
  });

  const breachedTickets = useQuery({
    queryKey: ['sla-monitor', 'breached-tickets'],
    queryFn: () => listTickets({ page: 1, page_size: 20 }),
    staleTime: STALE,
  });

  const s = sla.data;
  const breachedAll = (breachedTickets.data?.items ?? []).filter((t) => t.sla_breached);
  const compliance = s?.sla_compliance_rate ?? 100;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="font-display text-2xl tracking-tight text-ink-900 dark:text-ink-50">SLA Monitor</h1>
          <p className="text-sm text-ink-500 mt-1">
            Live response & resolution-time compliance across all open tickets.
            {s?.as_of && <> Updated {new Date(s.as_of).toLocaleTimeString()}.</>}
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={() => sla.refetch()}>Refresh</Button>
      </header>

      {sla.isError ? (
        <Card className="flex flex-col items-center gap-3 py-8">
          <p className="text-sm text-oxblood">Failed to load SLA data.</p>
          <Button variant="ghost" onClick={() => sla.refetch()}>Retry</Button>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
            <KPI label="Total tracked" value={s?.total_tracked ?? '—'} />
            <KPI
              label="Compliance"
              value={`${compliance.toFixed(1)}%`}
              tone={compliance >= 95 ? 'good' : compliance >= 85 ? 'warning' : 'danger'}
            />
            <KPI
              label="Resolution breached"
              value={s?.resolution_sla_breached ?? 0}
              tone={(s?.resolution_sla_breached ?? 0) > 0 ? 'danger' : 'default'}
            />
            <KPI
              label="At risk (next 60m)"
              value={s?.at_risk_next_60min ?? 0}
              tone={(s?.at_risk_next_60min ?? 0) > 0 ? 'warning' : 'default'}
            />
          </div>

          <Card>
            <h2 className="font-display text-lg text-ink-900 dark:text-ink-50 mb-4">Compliance by priority</h2>
            <div className="flex flex-col gap-3">
              {Object.entries(s?.health_by_priority ?? {}).length === 0 ? (
                <p className="text-sm text-ink-300">No tracked tickets in any priority bucket.</p>
              ) : (
                Object.entries(s?.health_by_priority ?? {}).map(([priority, h]) => (
                  <div key={priority} className="flex items-center gap-3">
                    <span className="capitalize w-24 text-sm text-ink-700">{priority}</span>
                    <div className="flex-1 h-3 bg-cream-200 rounded-full overflow-hidden">
                      <div
                        className={cn(
                          'h-full transition-all duration-500',
                          h.compliance_rate >= 95 ? 'bg-brand-500'
                            : h.compliance_rate >= 85 ? 'bg-accent-400'
                            : 'bg-oxblood',
                        )}
                        style={{ width: `${Math.max(h.compliance_rate, 1)}%` }}
                      />
                    </div>
                    <span className="w-16 text-right text-xs text-ink-700 tabular-nums">
                      {h.compliance_rate.toFixed(1)}%
                    </span>
                    <span className="w-28 text-right text-xs text-ink-500 tabular-nums">
                      {h.breached}/{h.total} breached
                    </span>
                  </div>
                ))
              )}
            </div>
          </Card>

          <Card>
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-lg text-ink-900 dark:text-ink-50">Breached tickets</h2>
              <Button variant="ghost" size="sm" onClick={() => navigate('/tickets')}>View all tickets</Button>
            </div>
            {breachedTickets.isLoading ? (
              <p className="text-sm text-ink-300">Loading…</p>
            ) : breachedAll.length === 0 ? (
              <p className="text-sm text-ink-300">No breached tickets in the current page. Keep it up.</p>
            ) : (
              <ul className="flex flex-col divide-y divide-cream-200">
                {breachedAll.slice(0, 10).map((t) => (
                  <li
                    key={t.id}
                    className="py-3 flex items-center justify-between cursor-pointer hover:bg-cream-50 -mx-2 px-2 rounded"
                    onClick={() => navigate(`/tickets/${t.id}`)}
                  >
                    <div>
                      <p className="text-sm font-medium text-ink-900 dark:text-ink-50">{t.title}</p>
                      <p className="text-xs text-ink-500">{t.ticket_number} · {t.priority} · {t.status}</p>
                    </div>
                    <span className="pill bg-oxblood-50 text-oxblood">Breached</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
