import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { ChevronLeft, ChevronRight, Download, Filter, Lock } from 'lucide-react';

import { api } from '@/lib/api';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Skeleton } from '@/components/Skeleton';
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

  const downloadCsv = async () => {
    const params = new URLSearchParams();
    if (filters.entity_type) params.set('entity_type', filters.entity_type);
    if (filters.action) params.set('action', filters.action);
    if (filters.actor_user_id) params.set('actor_user_id', filters.actor_user_id);
    if (filters.date_from) params.set('date_from', filters.date_from);
    if (filters.date_to) params.set('date_to', filters.date_to);
    const resp = await api.get(`/audit-logs/export.csv?${params.toString()}`, { responseType: 'blob' });
    const url = URL.createObjectURL(resp.data as Blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'audit.csv'; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col gap-6">
      <motion.header
        initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}
        className="flex items-end justify-between gap-4 flex-wrap"
      >
        <div>
          <span className="label flex items-center gap-1.5"><Lock className="h-3 w-3" /> Append-only</span>
          <h1 className="text-4xl font-semibold tracking-tight text-ink mt-1">Audit log</h1>
          <p className="text-sm text-ink-muted mt-1">
            Append-only record of every state change. Protected by a database trigger.
          </p>
        </div>
      </motion.header>

      <Card>
        <div className="grid gap-3 md:grid-cols-[1fr_1fr_1fr_1fr_auto_auto]">
          <input className="input" placeholder="Entity type (e.g. ticket)"
                 value={draft.entity_type ?? ''}
                 onChange={(e) => setDraft({ ...draft, entity_type: e.target.value || undefined })} />
          <input className="input" placeholder="Action (e.g. ticket.assigned)"
                 value={draft.action ?? ''}
                 onChange={(e) => setDraft({ ...draft, action: e.target.value || undefined })} />
          <input className="input" placeholder="Actor user id"
                 value={draft.actor_user_id ?? ''}
                 onChange={(e) => setDraft({ ...draft, actor_user_id: e.target.value || undefined })} />
          <input className="input" type="datetime-local"
                 value={draft.date_from ?? ''}
                 onChange={(e) => setDraft({ ...draft, date_from: e.target.value || undefined })} />
          <button onClick={apply} className="btn-primary"><Filter className="h-4 w-4" /> Apply</button>
          <button onClick={reset} className="btn-secondary">Reset</button>
        </div>
        <div className="mt-3 flex justify-end">
          <button onClick={downloadCsv} className="btn-secondary">
            <Download className="h-4 w-4" /> Export CSV
          </button>
        </div>
      </Card>

      <Card padded={false} className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>When</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Entity</th>
                <th>Diff</th>
                <th>IP</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && Array.from({ length: 8 }).map((_, i) => (
                <tr key={i}>{Array.from({ length: 6 }).map((__, j) => (
                  <td key={j}><Skeleton className="h-4 w-full max-w-[160px]" /></td>
                ))}</tr>
              ))}
              {!isLoading && (data?.items.length ?? 0) === 0 && (
                <tr><td colSpan={6} className="py-12 text-center text-ink-muted">No audit entries.</td></tr>
              )}
              {data?.items.map((a) => (
                <tr key={a.id}>
                  <td className="text-ink-muted whitespace-nowrap text-2xs">{formatDateTime(a.created_at)}</td>
                  <td>
                    <div className="text-2xs">
                      {a.actor_user_id
                        ? <code className="text-ink">{a.actor_user_id.slice(0, 8)}</code>
                        : <span className="text-ink-subtle">system</span>}
                    </div>
                    <div className="text-2xs text-ink-muted capitalize">{a.actor_role.replace('_', ' ') || '—'}</div>
                  </td>
                  <td><Badge tone={ACTION_TONE[a.action] ?? 'neutral'}>{a.action}</Badge></td>
                  <td>
                    <div className="text-2xs text-ink">{a.entity_type}</div>
                    <code className="text-2xs text-ink-subtle">{a.entity_id ? a.entity_id.slice(0, 8) + '…' : '—'}</code>
                  </td>
                  <td className="max-w-[420px]">
                    <details>
                      <summary className="cursor-pointer text-2xs text-brand-700 hover:text-brand-800">view diff</summary>
                      <pre className="mt-1.5 text-2xs whitespace-pre-wrap break-all bg-white/70 border border-white/50 p-2.5 rounded-2xl">
{JSON.stringify({ old: a.old_value, new: a.new_value }, null, 2)}
                      </pre>
                    </details>
                  </td>
                  <td className="text-2xs text-ink-muted">{a.ip_address || '—'}</td>
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
