import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ChevronLeft, ChevronRight, Zap } from 'lucide-react';

import { api, extractError } from '@/lib/api';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Skeleton } from '@/components/Skeleton';
import { formatDateTime, formatRelative } from '@/lib/format';

interface Escalation {
  id: string;
  ticket_id: string;
  level: number;
  escalated_to_user_id: string | null;
  reason: string;
  triggered_by_user_id: string | null;
  is_automatic: boolean;
  escalated_at: string;
  resolved_at: string | null;
}
interface ListEnvelope<T> {
  data: T[];
  meta: { pagination: { page: number; size: number; total: number; pages: number } };
}

async function listEscalations(openOnly: boolean, page = 1, size = 25) {
  const params = new URLSearchParams({ page: String(page), size: String(size) });
  if (openOnly) params.set('open_only', 'true');
  const { data } = await api.get<ListEnvelope<Escalation>>(`/escalations?${params.toString()}`);
  return { items: data.data, meta: data.meta.pagination };
}
async function resolveEscalation(id: string) {
  const { data } = await api.post<{ data: Escalation }>(`/escalations/${id}/resolve`);
  return data.data;
}

export function EscalationsPage() {
  const qc = useQueryClient();
  const [openOnly, setOpenOnly] = useState(true);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['escalations', openOnly, page],
    queryFn: () => listEscalations(openOnly, page),
    refetchInterval: 60_000,
  });

  const resolve = useMutation({
    mutationFn: (id: string) => resolveEscalation(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['escalations'] }),
    onError: (e) => setError(extractError(e).message),
  });

  return (
    <div className="flex flex-col gap-6">
      <motion.header
        initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}
        className="flex items-end justify-between gap-4 flex-wrap"
      >
        <div>
          <span className="label">Incidents</span>
          <h1 className="text-4xl font-semibold tracking-tight text-ink mt-1">Escalations</h1>
          <p className="text-sm text-ink-muted mt-1">Manual and automatic SLA-breach escalations.</p>
        </div>
        <label className="text-sm text-ink-muted flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={openOnly}
            onChange={(e) => { setPage(1); setOpenOnly(e.target.checked); }}
            className="rounded"
          />
          Show open only
        </label>
      </motion.header>

      {error && <Badge tone="danger">{error}</Badge>}

      <Card padded={false} className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Ticket</th>
                <th>Level</th>
                <th>Source</th>
                <th>Reason</th>
                <th>Raised</th>
                <th>Resolved</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {isLoading && Array.from({ length: 5 }).map((_, i) => (
                <tr key={i}>{Array.from({ length: 7 }).map((__, j) => (
                  <td key={j}><Skeleton className="h-4 w-full max-w-[160px]" /></td>
                ))}</tr>
              ))}
              {!isLoading && (data?.items.length ?? 0) === 0 && (
                <tr><td colSpan={7} className="py-12 text-center text-ink-muted">No escalations.</td></tr>
              )}
              {data?.items.map((e) => (
                <tr key={e.id}>
                  <td className="font-mono text-2xs">
                    <Link to={`/tickets/${e.ticket_id}`} className="text-brand-700 hover:text-brand-800 hover:underline">
                      {e.ticket_id.slice(0, 8)}…
                    </Link>
                  </td>
                  <td>
                    <Badge tone={e.level >= 2 ? 'danger' : 'warning'}>
                      <Zap className="h-3 w-3" /> L{e.level}
                    </Badge>
                  </td>
                  <td>
                    <Badge tone={e.is_automatic ? 'info' : 'assigned'}>
                      {e.is_automatic ? 'auto' : 'manual'}
                    </Badge>
                  </td>
                  <td className="text-ink max-w-[420px] truncate">{e.reason || '—'}</td>
                  <td className="text-ink-muted whitespace-nowrap">{formatRelative(e.escalated_at)}</td>
                  <td className="text-ink-muted whitespace-nowrap">{formatDateTime(e.resolved_at)}</td>
                  <td className="text-right">
                    {e.resolved_at == null && (
                      <button
                        className="btn-secondary"
                        onClick={() => { setError(null); resolve.mutate(e.id); }}
                      >
                        Resolve
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {data && (
          <div className="flex items-center justify-between p-4 border-t border-white/40">
            <span className="text-2xs uppercase tracking-wider text-ink-muted">
              Page {data.meta.page} of {data.meta.pages || 1} · {data.meta.total} total
            </span>
            <div className="flex gap-2">
              <button onClick={() => setPage((p) => p - 1)} disabled={page <= 1} className="btn-secondary">
                <ChevronLeft className="h-4 w-4" /> Prev
              </button>
              <button onClick={() => setPage((p) => p + 1)} disabled={page >= (data.meta.pages || 1)} className="btn-secondary">
                Next <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
