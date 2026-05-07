import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Plus,
  RefreshCw,
  Download,
  Search,
  ChevronLeft,
  ChevronRight,
  Filter,
} from 'lucide-react';

import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Skeleton } from '@/components/Skeleton';
import { listTickets, type TicketFilters } from '@/features/tickets/api';
import { api } from '@/lib/api';
import { PriorityBadge, StatusBadge } from '@/features/tickets/components/StatusBadge';
import { formatRelative, isBreached } from '@/lib/format';
import { useAuth } from '@/store/auth';
import { CreateTicketModal } from '@/features/tickets/components/CreateTicketModal';
import { cn } from '@/lib/cn';

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

  const downloadCsv = async () => {
    const params = new URLSearchParams();
    status?.forEach((s) => params.append('status', s));
    priority?.forEach((p) => params.append('priority', p));
    if (breached != null) params.set('breached', String(breached));
    if (q) params.set('q', q);
    const resp = await api.get(`/tickets/export.csv?${params.toString()}`, { responseType: 'blob' });
    const url = URL.createObjectURL(resp.data as Blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'tickets.csv'; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Page header */}
      <motion.header
        initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}
        className="flex items-end justify-between gap-4 flex-wrap"
      >
        <div>
          <span className="label">Operations</span>
          <h1 className="text-4xl font-semibold tracking-tight text-ink mt-1">Tickets</h1>
          <p className="text-sm text-ink-muted mt-1">
            All tickets visible to your role.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => refetch()} className="btn-secondary">
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
          <button onClick={downloadCsv} className="btn-secondary">
            <Download className="h-4 w-4" /> CSV
          </button>
          {canCreate && (
            <button onClick={() => setOpenCreate(true)} className="btn-primary">
              <Plus className="h-4 w-4" /> New ticket
            </button>
          )}
        </div>
      </motion.header>

      {/* Filters */}
      <Card className="p-5">
        <div className="grid gap-3 md:grid-cols-[1fr_auto] items-center">
          <div className="relative">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-ink-subtle" />
            <input
              className="input pl-10"
              placeholder="Search by ticket number or title…"
              value={q}
              onChange={(e) => { setPage(1); setQ(e.target.value); }}
            />
          </div>
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-ink-subtle" />
            <select
              className="input py-2 px-3 w-auto"
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
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-1.5">
          <span className="text-2xs uppercase tracking-wider text-ink-muted mr-1.5">Status</span>
          {STATUSES!.map((s) => (
            <FilterChip
              key={s}
              active={!!status?.includes(s)}
              onClick={() => { setPage(1); setStatus(toggleArr(status, s)); }}
              label={s.replace('_', ' ')}
            />
          ))}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-2xs uppercase tracking-wider text-ink-muted mr-1.5">Priority</span>
          {PRIORITIES!.map((p) => (
            <FilterChip
              key={p}
              active={!!priority?.includes(p)}
              onClick={() => { setPage(1); setPriority(toggleArr(priority, p)); }}
              label={p}
              tone="accent"
            />
          ))}
        </div>
      </Card>

      {/* Table */}
      <Card padded={false} className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Ticket</th>
                <th>Title</th>
                <th>Status</th>
                <th>Priority</th>
                <th>SLA</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {isLoading &&
                Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i}>
                    {Array.from({ length: 6 }).map((__, j) => (
                      <td key={j}><Skeleton className="h-4 w-full max-w-[180px]" /></td>
                    ))}
                  </tr>
                ))}
              {isError && (
                <tr><td colSpan={6} className="py-10 text-center text-danger-deep">Failed to load tickets.</td></tr>
              )}
              {!isLoading && data?.items.length === 0 && (
                <tr><td colSpan={6} className="py-12 text-center text-ink-muted">No tickets match these filters.</td></tr>
              )}
              {data?.items.map((t) => (
                <tr key={t.id}>
                  <td className="font-mono text-2xs">
                    <Link to={`/tickets/${t.id}`} className="text-brand-700 hover:text-brand-800 hover:underline">
                      {t.ticket_no}
                    </Link>
                  </td>
                  <td className="text-ink">{t.title}</td>
                  <td><StatusBadge status={t.status} /></td>
                  <td><PriorityBadge priority={t.priority} /></td>
                  <td>
                    {t.sla_due_at ? (
                      <Badge tone={isBreached(t.sla_due_at) ? 'danger' : 'success'}>
                        {formatRelative(t.sla_due_at)}
                      </Badge>
                    ) : <span className="text-ink-subtle">—</span>}
                  </td>
                  <td className="text-ink-muted whitespace-nowrap">{formatRelative(t.created_at)}</td>
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

      <CreateTicketModal
        open={openCreate}
        onClose={() => setOpenCreate(false)}
        onCreated={() => { setOpenCreate(false); refetch(); }}
      />
    </div>
  );
}

function FilterChip({
  active,
  onClick,
  label,
  tone = 'brand',
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  tone?: 'brand' | 'accent';
}) {
  const activeClass = tone === 'accent'
    ? 'bg-accent-500 text-white border-accent-500 shadow-soft'
    : 'bg-brand-600 text-white border-brand-600 shadow-soft';
  return (
    <button
      onClick={onClick}
      className={cn(
        'pill border transition-all duration-150 capitalize',
        active
          ? activeClass
          : 'bg-white/60 text-ink-muted border-white/60 hover:border-brand-200 hover:text-ink',
      )}
    >
      {label}
    </button>
  );
}
