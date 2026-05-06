import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Badge } from '@/components/Badge';
import { formatDateTime } from '@/lib/format';

interface AuditRow {
  id: string;
  actor_user_id: string | null;
  actor_role: string;
  entity_type: string;
  entity_id: string | null;
  action: string;
  old_value: Record<string, unknown>;
  new_value: Record<string, unknown>;
  ip_address: string;
  user_agent: string;
  request_id: string;
  created_at: string;
}

interface ListEnvelope<T> {
  data: T[];
  meta: { pagination: { page: number; size: number; total: number; pages: number } };
}

interface Filters {
  entity_type?: string;
  action?: string;
  actor_user_id?: string;
  date_from?: string;
  date_to?: string;
}

async function listAudit(page: number, size: number, f: Filters) {
  const params = new URLSearchParams({ page: String(page), size: String(size) });
  if (f.entity_type) params.set('entity_type', f.entity_type);
  if (f.action) params.set('action', f.action);
  if (f.actor_user_id) params.set('actor_user_id', f.actor_user_id);
  if (f.date_from) params.set('date_from', f.date_from);
  if (f.date_to) params.set('date_to', f.date_to);
  const { data } = await api.get<ListEnvelope<AuditRow>>(`/audit-logs?${params.toString()}`);
  return { items: data.data, meta: data.meta.pagination };
}

const ACTION_TONE: Record<string, Parameters<typeof Badge>[0]['tone']> = {
  'ticket.created': 'info',
  'ticket.acknowledged': 'ack',
  'ticket.assigned': 'assigned',
  'ticket.started': 'progress',
  'ticket.held': 'hold',
  'ticket.escalated': 'escalated',
  'ticket.resolved': 'resolved',
  'ticket.closed': 'closed',
  'ticket.reopened': 'reopened',
  'comment.posted': 'neutral',
  'auth.login': 'success',
};

export function AuditPage() {
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<Filters>({});
  const [draft, setDraft] = useState<Filters>({});

  const { data, isLoading } = useQuery({
    queryKey: ['audit', page, filters],
    queryFn: () => listAudit(page, 25, filters),
  });

  const apply = () => { setPage(1); setFilters(draft); };
  const reset = () => { setDraft({}); setPage(1); setFilters({}); };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Audit Log</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Append-only record of every state change, secured by a database trigger.
        </p>
      </div>

      <Card>
        <div className="grid gap-3 md:grid-cols-[1fr_1fr_1fr_1fr_auto_auto]">
          <input
            className="input"
            placeholder="Entity type (e.g. ticket)"
            value={draft.entity_type ?? ''}
            onChange={(e) => setDraft({ ...draft, entity_type: e.target.value || undefined })}
          />
          <input
            className="input"
            placeholder="Action (e.g. ticket.assigned)"
            value={draft.action ?? ''}
            onChange={(e) => setDraft({ ...draft, action: e.target.value || undefined })}
          />
          <input
            className="input"
            placeholder="Actor user id"
            value={draft.actor_user_id ?? ''}
            onChange={(e) => setDraft({ ...draft, actor_user_id: e.target.value || undefined })}
          />
          <input
            className="input"
            type="datetime-local"
            value={draft.date_from ?? ''}
            onChange={(e) => setDraft({ ...draft, date_from: e.target.value || undefined })}
          />
          <Button onClick={apply}>Apply</Button>
          <Button variant="ghost" onClick={reset}>Reset</Button>
          <Button
            variant="ghost"
            onClick={async () => {
              const params = new URLSearchParams();
              if (filters.entity_type) params.set('entity_type', filters.entity_type);
              if (filters.action) params.set('action', filters.action);
              if (filters.actor_user_id) params.set('actor_user_id', filters.actor_user_id);
              if (filters.date_from) params.set('date_from', filters.date_from);
              if (filters.date_to) params.set('date_to', filters.date_to);
              const resp = await api.get(`/audit-logs/export.csv?${params.toString()}`, { responseType: 'blob' });
              const url = URL.createObjectURL(resp.data as Blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = 'audit.csv';
              a.click();
              URL.revokeObjectURL(url);
            }}
          >
            ⬇ CSV
          </Button>
        </div>
      </Card>

      <Card padded={false} className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-surface-muted dark:bg-slate-800/50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">When</th>
              <th className="px-4 py-3">Actor</th>
              <th className="px-4 py-3">Action</th>
              <th className="px-4 py-3">Entity</th>
              <th className="px-4 py-3">Diff</th>
              <th className="px-4 py-3">IP</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {isLoading && <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-400">Loading…</td></tr>}
            {!isLoading && (data?.items.length ?? 0) === 0 && (
              <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-400">No audit entries.</td></tr>
            )}
            {data?.items.map((a) => (
              <tr key={a.id} className="hover:bg-surface-muted/60 dark:hover:bg-slate-800/40 align-top">
                <td className="px-4 py-3 text-slate-500 whitespace-nowrap">{formatDateTime(a.created_at)}</td>
                <td className="px-4 py-3">
                  <div className="text-xs">
                    {a.actor_user_id ? (
                      <code>{a.actor_user_id.slice(0, 8)}</code>
                    ) : <span className="text-slate-400">system</span>}
                  </div>
                  <div className="text-[11px] text-slate-500 capitalize">{a.actor_role.replace('_', ' ') || '—'}</div>
                </td>
                <td className="px-4 py-3"><Badge tone={ACTION_TONE[a.action] ?? 'neutral'}>{a.action}</Badge></td>
                <td className="px-4 py-3">
                  <div className="text-xs">{a.entity_type}</div>
                  <code className="text-[11px] text-slate-500">{a.entity_id ? a.entity_id.slice(0, 8) + '…' : '—'}</code>
                </td>
                <td className="px-4 py-3 max-w-[420px]">
                  <details>
                    <summary className="cursor-pointer text-xs text-brand-700">view</summary>
                    <pre className="mt-1 text-[11px] whitespace-pre-wrap break-all bg-surface-muted dark:bg-slate-800/50 p-2 rounded">
{JSON.stringify({ old: a.old_value, new: a.new_value }, null, 2)}
                    </pre>
                  </details>
                </td>
                <td className="px-4 py-3 text-xs text-slate-500">{a.ip_address || '—'}</td>
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
