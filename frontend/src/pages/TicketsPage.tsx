import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Plus,
  RefreshCw,
  Download,
  Search,
  ChevronLeft,
  ChevronRight,
  Filter,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
  Rows3,
  LayoutGrid,
  Hourglass,
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

const SORTABLE_COLS = ['ticket_no', 'priority', 'status', 'sla_due_at', 'created_at'] as const;
type SortCol = (typeof SORTABLE_COLS)[number];

function parseSort(sort: string | null): { col: SortCol | null; desc: boolean } {
  if (!sort) return { col: null, desc: false };
  const desc = sort.startsWith('-');
  const col = sort.replace(/^-/, '') as SortCol;
  if (!SORTABLE_COLS.includes(col)) return { col: null, desc: false };
  return { col, desc };
}

function ageFor(iso: string): { label: string; tone: 'neutral' | 'warning' | 'danger' } {
  const ms = Date.now() - new Date(iso).getTime();
  const hrs = ms / (1000 * 60 * 60);
  if (hrs >= 72) return { label: '>3d', tone: 'danger' };
  if (hrs >= 24) return { label: '>1d', tone: 'warning' };
  return { label: 'new', tone: 'neutral' };
}

export function TicketsPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const [page, setPage] = useState(1);
  const [size] = useState(20);
  const [q, setQ] = useState(() => searchParams.get('q') ?? '');
  const [status, setStatus] = useState<TicketFilters['status']>(
    () => (searchParams.getAll('status') as TicketFilters['status']) ?? [],
  );
  const [priority, setPriority] = useState<TicketFilters['priority']>(
    () => (searchParams.getAll('priority') as TicketFilters['priority']) ?? [],
  );
  const [breached, setBreached] = useState<boolean | undefined>(() => {
    const v = searchParams.get('breached');
    if (v === 'true') return true;
    if (v === 'false') return false;
    return undefined;
  });
  const [sort, setSort] = useState<string | undefined>(() => searchParams.get('sort') ?? undefined);
  const [density, setDensity] = useState<'comfortable' | 'compact'>(
    () => (localStorage.getItem('tickets:density') as 'comfortable' | 'compact') ?? 'comfortable',
  );
  const [openCreate, setOpenCreate] = useState(false);

  const { hasRole } = useAuth();
  const canCreate = hasRole('branch_user', 'admin', 'supervisor', 'agent');

  useEffect(() => {
    const next = new URLSearchParams();
    if (q) next.set('q', q);
    status?.forEach((s) => next.append('status', s));
    priority?.forEach((p) => next.append('priority', p));
    if (breached === true) next.set('breached', 'true');
    if (breached === false) next.set('breached', 'false');
    if (sort) next.set('sort', sort);
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, status, priority, breached, sort]);

  useEffect(() => {
    localStorage.setItem('tickets:density', density);
  }, [density]);

  const filters = useMemo<TicketFilters>(
    () => ({ page, size, q: q || undefined, status, priority, breached, sort }),
    [page, size, q, status, priority, breached, sort],
  );

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['tickets', filters],
    queryFn: () => listTickets(filters),
  });

  const toggleArr = <T extends string>(arr: T[] | undefined, v: T) =>
    arr?.includes(v) ? arr.filter((x) => x !== v) : [...(arr ?? []), v];

  const cycleSort = (col: SortCol) => {
    const { col: cur, desc } = parseSort(sort ?? null);
    if (cur !== col) { setSort(`-${col}`); return; }
    if (cur === col && desc) { setSort(col); return; }
    setSort(undefined);
  };

  const downloadCsv = async () => {
    const params = new URLSearchParams();
    status?.forEach((s) => params.append('status', s));
    priority?.forEach((p) => params.append('priority', p));
    if (breached != null) params.set('breached', String(breached));
    if (q) params.set('q', q);
    if (sort) params.set('sort', sort);
    const resp = await api.get(`/tickets/export.csv?${params.toString()}`, { responseType: 'blob' });
    const url = URL.createObjectURL(resp.data as Blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'tickets.csv'; a.click();
    URL.revokeObjectURL(url);
  };

  const parsed = parseSort(sort ?? null);

  return (
    <div className="flex flex-col gap-6">
      <motion.header
        initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}
        className="flex items-end justify-between gap-4 flex-wrap"
      >
        <div>
          <span className="label">Operations</span>
          <h1 className="text-4xl font-semibold tracking-tight text-ink mt-1">Tickets</h1>
          <p className="text-sm text-ink-muted mt-1">All tickets visible to your role.</p>
          <div className="hairline-brass mt-3 max-w-xs" />
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2 min-w-0">
          <button
            onClick={() => setDensity((d) => d === 'compact' ? 'comfortable' : 'compact')}
            className="btn-secondary"
            title={`Density: ${density}`}
          >
            {density === 'compact' ? <LayoutGrid className="h-4 w-4" /> : <Rows3 className="h-4 w-4" />}
            <span className="hidden sm:inline">{density === 'compact' ? 'Comfortable' : 'Compact'}</span>
          </button>
          <button onClick={() => refetch()} className="btn-secondary" title="Refresh">
            <RefreshCw className="h-4 w-4" /> <span className="hidden sm:inline">Refresh</span>
          </button>
          <button onClick={downloadCsv} className="btn-secondary" title="Export CSV">
            <Download className="h-4 w-4" /> <span className="hidden sm:inline">CSV</span>
          </button>
          {canCreate && (
            <button onClick={() => setOpenCreate(true)} className="btn-primary order-first sm:order-none">
              <Plus className="h-4 w-4" /> New ticket
            </button>
          )}
        </div>
      </motion.header>

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
              tone="claret"
            />
          ))}
        </div>
      </Card>

      <Card padded={false} className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className={cn('data-table', density === 'compact' && 'compact')}>
            <thead>
              <tr>
                <Th label="Ticket"   col="ticket_no"   parsed={parsed} onClick={cycleSort} />
                <th>Title</th>
                <Th label="Status"   col="status"      parsed={parsed} onClick={cycleSort} />
                <Th label="Priority" col="priority"    parsed={parsed} onClick={cycleSort} />
                <Th label="SLA"      col="sla_due_at"  parsed={parsed} onClick={cycleSort} />
                <Th label="Age"      col="created_at"  parsed={parsed} onClick={cycleSort} />
              </tr>
            </thead>
            <tbody>
              {isLoading && Array.from({ length: 8 }).map((_, i) => (
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
              {data?.items.map((t) => {
                const age = ageFor(t.created_at);
                return (
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
                    <td className="text-ink-muted whitespace-nowrap">
                      <span className="inline-flex items-center gap-1.5">
                        <Hourglass className={cn(
                          'h-3.5 w-3.5',
                          age.tone === 'danger'  && 'text-danger',
                          age.tone === 'warning' && 'text-warning-deep',
                          age.tone === 'neutral' && 'text-ink-subtle',
                        )} />
                        {formatRelative(t.created_at)}
                      </span>
                    </td>
                  </tr>
                );
              })}
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

function Th({
  label,
  col,
  parsed,
  onClick,
}: {
  label: string;
  col: SortCol;
  parsed: { col: SortCol | null; desc: boolean };
  onClick: (c: SortCol) => void;
}) {
  const active = parsed.col === col;
  return (
    <th>
      <button
        onClick={() => onClick(col)}
        className="inline-flex items-center gap-1.5 hover:text-ink transition-colors"
        title={`Sort by ${label}`}
      >
        <span>{label}</span>
        {!active && <ArrowUpDown className="h-3 w-3 opacity-50" />}
        {active && parsed.desc && <ArrowDown className="h-3 w-3 text-brand-600" />}
        {active && !parsed.desc && <ArrowUp className="h-3 w-3 text-brand-600" />}
      </button>
    </th>
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
  tone?: 'brand' | 'claret';
}) {
  const activeClass = tone === 'claret'
    ? 'bg-accent-500 text-white border-accent-500 shadow-soft'
    : 'bg-brand-600 text-white border-brand-600 shadow-soft';
  return (
    <button
      onClick={onClick}
      className={cn(
        'pill border transition-all duration-150 capitalize',
        active ? activeClass : 'bg-canvas-raised text-ink-muted border-white/60 hover:border-brand-200 hover:text-ink',
      )}
    >
      {label}
    </button>
  );
}
