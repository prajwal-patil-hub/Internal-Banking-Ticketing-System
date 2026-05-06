import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { api } from '@/lib/api';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { formatDateTime, formatRelative } from '@/lib/format';

interface PolicyRow {
  id: string;
  priority: 'critical' | 'high' | 'medium' | 'low';
  response_minutes: number;
  resolution_minutes: number;
}

interface BreachRow {
  id: string;
  ticket_id: string;
  policy_priority: 'critical' | 'high' | 'medium' | 'low';
  due_at: string;
  breached: boolean;
  breach_at: string | null;
  paused_at: string | null;
  total_paused_seconds: number;
}

interface BreachEnvelope {
  data: { items: BreachRow[]; total: number };
}

async function listPolicies() {
  const { data } = await api.get<{ data: PolicyRow[] }>('/sla/policies');
  return data.data;
}

async function listBreaches() {
  const { data } = await api.get<BreachEnvelope>('/sla/breaches');
  return data.data;
}

const PRIORITY_TONE = {
  critical: 'danger',
  high:     'warning',
  medium:   'info',
  low:      'neutral',
} as const;

export function SlaPage() {
  const policies = useQuery({ queryKey: ['sla', 'policies'], queryFn: listPolicies });
  const breaches = useQuery({ queryKey: ['sla', 'breaches'], queryFn: listBreaches, refetchInterval: 60_000 });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">SLA Monitor</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Live view of breached tickets. The breach detector ticks every 60 seconds.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {policies.data?.map((p) => (
          <Card key={p.id} className="kpi">
            <span className="text-xs uppercase tracking-wide text-slate-500">{p.priority} SLA</span>
            <div className="flex items-end justify-between">
              <div className="text-2xl font-semibold leading-tight">
                {p.resolution_minutes >= 60
                  ? `${(p.resolution_minutes / 60).toFixed(0)}h`
                  : `${p.resolution_minutes}m`}
              </div>
              <Badge tone={PRIORITY_TONE[p.priority]}>resolve</Badge>
            </div>
            <div className="text-xs text-slate-500 mt-1">
              First response: {p.response_minutes}m
            </div>
          </Card>
        ))}
      </div>

      <Card padded={false} className="overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <h2 className="font-semibold">Breached tickets</h2>
          <Badge tone="danger">{breaches.data?.total ?? 0} total</Badge>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-surface-muted dark:bg-slate-800/50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Ticket</th>
              <th className="px-4 py-3">Priority</th>
              <th className="px-4 py-3">Was due</th>
              <th className="px-4 py-3">Breach detected</th>
              <th className="px-4 py-3">Pause time</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {breaches.isLoading && <tr><td colSpan={5} className="px-4 py-8 text-center text-slate-400">Loading…</td></tr>}
            {!breaches.isLoading && (breaches.data?.items.length ?? 0) === 0 && (
              <tr><td colSpan={5} className="px-4 py-10 text-center text-slate-400">No breaches. 🎉</td></tr>
            )}
            {breaches.data?.items.map((b) => (
              <tr key={b.id} className="hover:bg-surface-muted/60 dark:hover:bg-slate-800/40">
                <td className="px-4 py-3">
                  <Link to={`/tickets/${b.ticket_id}`} className="text-brand-700 hover:underline font-mono text-xs">
                    {b.ticket_id.slice(0, 8)}…
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <Badge tone={PRIORITY_TONE[b.policy_priority]}>{b.policy_priority}</Badge>
                </td>
                <td className="px-4 py-3 text-slate-500">{formatRelative(b.due_at)}</td>
                <td className="px-4 py-3 text-slate-500">{formatDateTime(b.breach_at)}</td>
                <td className="px-4 py-3 text-slate-500">
                  {b.total_paused_seconds > 0
                    ? `${Math.round(b.total_paused_seconds / 60)} min`
                    : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
