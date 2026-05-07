import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Activity, Clock4, AlertTriangle } from 'lucide-react';

import { api } from '@/lib/api';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Skeleton } from '@/components/Skeleton';
import { formatDateTime, formatRelative } from '@/lib/format';
import { cn } from '@/lib/cn';

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
interface BreachEnvelope { data: { items: BreachRow[]; total: number } }

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

const PRIORITY_RING: Record<string, string> = {
  critical: 'from-danger to-rose-400',
  high:     'from-warning to-amber-300',
  medium:   'from-info to-sky-300',
  low:      'from-slate-300 to-slate-200',
};

export function SlaPage() {
  const policies = useQuery({ queryKey: ['sla', 'policies'], queryFn: listPolicies });
  const breaches = useQuery({ queryKey: ['sla', 'breaches'], queryFn: listBreaches, refetchInterval: 60_000 });

  return (
    <div className="flex flex-col gap-6">
      <motion.header
        initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}
      >
        <span className="label">Service levels</span>
        <h1 className="text-4xl font-semibold tracking-tight text-ink mt-1">SLA Monitor</h1>
        <p className="text-sm text-ink-muted mt-1">
          Live view of breached tickets. The breach detector ticks every 60 seconds.
        </p>
      </motion.header>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {policies.isLoading && Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-32 w-full" rounded="3xl" />
        ))}
        {policies.data?.map((p) => (
          <motion.div
            key={p.id}
            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}
            className="glass rounded-4xl p-5 relative overflow-hidden"
          >
            <div className={cn('absolute -top-16 -right-16 h-40 w-40 rounded-full bg-gradient-to-br opacity-30', PRIORITY_RING[p.priority])} />
            <div className="relative z-10">
              <div className="flex items-start justify-between">
                <span className="h-9 w-9 rounded-2xl grid place-items-center bg-white/70">
                  <Activity className="h-[18px] w-[18px] text-brand-600" />
                </span>
                <Badge tone={PRIORITY_TONE[p.priority]}>{p.priority}</Badge>
              </div>
              <div className="mt-4 text-2xs uppercase tracking-wider text-ink-muted">Resolution SLA</div>
              <div className="text-4xl font-semibold tracking-tight text-ink mt-0.5">
                {p.resolution_minutes >= 60
                  ? `${(p.resolution_minutes / 60).toFixed(0)}h`
                  : `${p.resolution_minutes}m`}
              </div>
              <div className="mt-2 inline-flex items-center gap-1.5 text-2xs text-ink-muted">
                <Clock4 className="h-3 w-3" />
                First response: {p.response_minutes}m
              </div>
            </div>
          </motion.div>
        ))}
      </div>

      <Card padded={false} className="overflow-hidden">
        <div className="px-6 py-4 flex items-center justify-between border-b border-white/40">
          <div>
            <h2 className="h-section flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-danger" />
              Breached tickets
            </h2>
            <p className="text-xs text-ink-muted mt-0.5">Currently past their resolution SLA.</p>
          </div>
          <Badge tone="danger">{breaches.data?.total ?? 0} total</Badge>
        </div>
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Ticket</th>
                <th>Priority</th>
                <th>Was due</th>
                <th>Breach detected</th>
                <th>Pause time</th>
              </tr>
            </thead>
            <tbody>
              {breaches.isLoading && Array.from({ length: 4 }).map((_, i) => (
                <tr key={i}>{Array.from({ length: 5 }).map((__, j) => (
                  <td key={j}><Skeleton className="h-4 w-full max-w-[160px]" /></td>
                ))}</tr>
              ))}
              {!breaches.isLoading && (breaches.data?.items.length ?? 0) === 0 && (
                <tr><td colSpan={5} className="py-12 text-center text-ink-muted">No breaches. 🎉</td></tr>
              )}
              {breaches.data?.items.map((b) => (
                <tr key={b.id}>
                  <td className="font-mono text-2xs">
                    <Link to={`/tickets/${b.ticket_id}`} className="text-brand-700 hover:text-brand-800 hover:underline">
                      {b.ticket_id.slice(0, 8)}…
                    </Link>
                  </td>
                  <td><Badge tone={PRIORITY_TONE[b.policy_priority]}>{b.policy_priority}</Badge></td>
                  <td className="text-ink-muted">{formatRelative(b.due_at)}</td>
                  <td className="text-ink-muted">{formatDateTime(b.breach_at)}</td>
                  <td className="text-ink-muted">
                    {b.total_paused_seconds > 0 ? `${Math.round(b.total_paused_seconds / 60)} min` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
