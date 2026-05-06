import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { api, extractError } from '@/lib/api';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Badge } from '@/components/Badge';
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
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Escalations</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Manual and automatic SLA-breach escalations.
          </p>
        </div>
        <label className="text-sm flex items-center gap-2">
          <input
            type="checkbox"
            checked={openOnly}
            onChange={(e) => { setPage(1); setOpenOnly(e.target.checked); }}
          />
          Show open only
        </label>
      </div>

      {error && <Badge tone="danger">{error}</Badge>}

      <Card padded={false} className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-surface-muted dark:bg-slate-800/50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Ticket</th>
              <th className="px-4 py-3">Level</th>
              <th className="px-4 py-3">Source</th>
              <th className="px-4 py-3">Reason</th>
              <th className="px-4 py-3">Raised</th>
              <th className="px-4 py-3">Resolved</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {isLoading && <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-400">Loading…</td></tr>}
            {!isLoading && (data?.items.length ?? 0) === 0 && (
              <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-400">No escalations.</td></tr>
            )}
            {data?.items.map((e) => (
              <tr key={e.id} className="hover:bg-surface-muted/60 dark:hover:bg-slate-800/40">
                <td className="px-4 py-3">
                  <Link to={`/tickets/${e.ticket_id}`} className="text-brand-700 hover:underline font-mono text-xs">
                    {e.ticket_id.slice(0, 8)}…
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <Badge tone={e.level >= 2 ? 'danger' : 'warning'}>L{e.level}</Badge>
                </td>
                <td className="px-4 py-3">
                  <Badge tone={e.is_automatic ? 'info' : 'assigned'}>
                    {e.is_automatic ? 'auto' : 'manual'}
                  </Badge>
                </td>
                <td className="px-4 py-3 text-slate-600 dark:text-slate-300 max-w-[420px] truncate">
                  {e.reason || '—'}
                </td>
                <td className="px-4 py-3 text-slate-500">{formatRelative(e.escalated_at)}</td>
                <td className="px-4 py-3 text-slate-500">{formatDateTime(e.resolved_at)}</td>
                <td className="px-4 py-3 text-right">
                  {e.resolved_at == null && (
                    <Button variant="ghost" onClick={() => { setError(null); resolve.mutate(e.id); }}>
                      Resolve
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {data && (
          <div className="flex items-center justify-between p-4 border-t border-slate-100 dark:border-slate-800">
            <span className="text-xs text-slate-500">
              Page {data.meta.page} of {data.meta.pages || 1} · {data.meta.total} total
            </span>
            <div className="flex gap-2">
              <Button variant="ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Prev</Button>
              <Button variant="ghost" disabled={page >= (data.meta.pages || 1)} onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
