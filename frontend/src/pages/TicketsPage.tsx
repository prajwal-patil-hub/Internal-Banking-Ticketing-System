import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { listTickets, type TicketFilters } from '@/features/tickets/api';
import { api } from '@/lib/api';
import { PriorityBadge, StatusBadge } from '@/features/tickets/components/StatusBadge';
import { formatRelative, isBreached } from '@/lib/format';
import { useAuth } from '@/store/auth';
import { CreateTicketModal } from '@/features/tickets/components/CreateTicketModal';

const STATUSES: TicketFilters['status'] = [
  'new', 'acknowledged', 'assigned', 'in_progress', 'on_hold',
  'escalated', 'resolved', 'closed', 'reopened',
];

const PRIORITIES: TicketFilters['priority'] = ['critical', 'high', 'medium', 'low'];

export function TicketsPage() {
  const [page, setPage] = useState(1);
  const [size] = useState(20);
  const [q, setQ] = useState('');
  const [status, setStatus] = useState<TicketFilters['status']>([]);
  const [priority, setPriority] = useState<TicketFilters['priority']>([]);
  const [breached, setBreached] = useState<boolean | undefined>(undefined);
  const [openCreate, setOpenCreate] = useState(false);

  const { hasRole } = useAuth();
  const canCreate = hasRole('branch_user');

  const filters = useMemo<TicketFilters>(
    () => ({ page, size, q: q || undefined, status, priority, breached }),
    [page, size, q, status, priority, breached],
  );

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['tickets', filters],
    queryFn: () => listTickets(filters),
  });

  const toggleArr = <T extends string>(arr: T[] | undefined, v: T) =>
    arr?.includes(v) ? arr.filter((x) => x !== v) : [...(arr ?? []), v];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Tickets</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            All tickets visible to your role.
          </p>
        </div>
        {canCreate && (
          <Button onClick={() => setOpenCreate(true)}>+ New ticket</Button>
        )}
      </div>

      <Card>
        <div className="grid gap-3 md:grid-cols-[1fr_auto_auto_auto]">
          <input
            className="input"
            placeholder="Search by ticket number or title…"
            value={q}
            onChange={(e) => { setPage(1); setQ(e.target.value); }}
          />
          <select
            className="input"
            value={breached === undefined ? '' : String(breached)}
            onChange={(e) => {
              const v = e.target.value;
              setPage(1);
              setBreached(v === '' ? undefined : v === 'true');
            }}
          >
            <option value="">SLA: any</option>
            <option value="true">Breached</option>
            <option value="false">On time</option>
          </select>
          <Button variant="ghost" onClick={() => refetch()}>Refresh</Button>
          <Button
            variant="ghost"
            onClick={async () => {
              const params = new URLSearchParams();
              status?.forEach((s) => params.append('status', s));
              priority?.forEach((p) => params.append('priority', p));
              if (breached != null) params.set('breached', String(breached));
              if (q) params.set('q', q);
              const resp = await api.get(`/tickets/export.csv?${params.toString()}`, { responseType: 'blob' });
              const url = URL.createObjectURL(resp.data as Blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = 'tickets.csv';
              a.click();
              URL.revokeObjectURL(url);
            }}
          >
            ⬇ CSV
          </Button>
        </div>

        <div className="mt-3 flex flex-wrap gap-1.5">
          <span className="text-xs text-slate-500 mr-1">Status:</span>
          {STATUSES!.map((s) => (
            <button
              key={s}
              onClick={() => { setPage(1); setStatus(toggleArr(status, s)); }}
              className={`pill border ${
                status?.includes(s)
                  ? 'bg-brand-600 text-white border-brand-600'
                  : 'bg-white text-slate-600 border-slate-200 hover:border-brand-300'
              }`}
            >
              {s.replace('_', ' ')}
            </button>
          ))}
        </div>

        <div className="mt-2 flex flex-wrap gap-1.5">
          <span className="text-xs text-slate-500 mr-1">Priority:</span>
          {PRIORITIES!.map((p) => (
            <button
              key={p}
              onClick={() => { setPage(1); setPriority(toggleArr(priority, p)); }}
              className={`pill border ${
                priority?.includes(p)
                  ? 'bg-accent-500 text-white border-accent-500'
                  : 'bg-white text-slate-600 border-slate-200 hover:border-accent-300'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </Card>

      <Card padded={false} className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-surface-muted dark:bg-slate-800/50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Ticket</th>
              <th className="px-4 py-3">Title</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Priority</th>
              <th className="px-4 py-3">SLA</th>
              <th className="px-4 py-3">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {isLoading && <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-400">Loading…</td></tr>}
            {isError && <tr><td colSpan={6} className="px-4 py-8 text-center text-red-500">Failed to load tickets.</td></tr>}
            {!isLoading && data?.items.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-400">No tickets match these filters.</td></tr>
            )}
            {data?.items.map((t) => (
              <tr key={t.id} className="hover:bg-surface-muted/60 dark:hover:bg-slate-800/40">
                <td className="px-4 py-3 font-mono text-xs">
                  <Link className="text-brand-700 hover:underline" to={`/tickets/${t.id}`}>{t.ticket_no}</Link>
                </td>
                <td className="px-4 py-3">{t.title}</td>
                <td className="px-4 py-3"><StatusBadge status={t.status} /></td>
                <td className="px-4 py-3"><PriorityBadge priority={t.priority} /></td>
                <td className="px-4 py-3">
                  {t.sla_due_at ? (
                    <Badge tone={isBreached(t.sla_due_at) ? 'danger' : 'success'}>
                      {formatRelative(t.sla_due_at)}
                    </Badge>
                  ) : '—'}
                </td>
                <td className="px-4 py-3 text-slate-500">{formatRelative(t.created_at)}</td>
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
              <Button
                variant="ghost"
                disabled={page >= (data.meta.pages || 1)}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </Card>

      <CreateTicketModal
        open={openCreate}
        onClose={() => setOpenCreate(false)}
        onCreated={() => { setOpenCreate(false); refetch(); }}
      />
    </div>
  );
}
