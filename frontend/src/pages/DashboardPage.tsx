import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';

/**
 * Phase P0 placeholder dashboard. Real KPIs / SLA gauge / breach list arrive in P7
 * once the data endpoints (`/dashboard/kpis`, `/sla/breaches`) are live.
 */
export function DashboardPage() {
  const kpis = [
    { label: 'Open tickets',      value: '—', tone: 'info' as const },
    { label: 'SLA breached',      value: '—', tone: 'danger' as const },
    { label: 'Resolved today',    value: '—', tone: 'success' as const },
    { label: 'Avg. resolution',   value: '—', tone: 'neutral' as const },
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
              <span className="text-3xl font-semibold">{k.value}</span>
              <Badge tone={k.tone}>live</Badge>
            </div>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <Card className="xl:col-span-2">
          <h2 className="text-base font-semibold">Recent tickets</h2>
          <p className="mt-2 text-sm text-slate-500">
            Ticket list lands in Phase P2 with filters, pagination and SLA indicators.
          </p>
        </Card>

        <Card>
          <h2 className="text-base font-semibold">SLA health</h2>
          <p className="mt-2 text-sm text-slate-500">
            Live breach feed and gauge land in Phase P4 / P7.
          </p>
        </Card>
      </div>
    </div>
  );
}
