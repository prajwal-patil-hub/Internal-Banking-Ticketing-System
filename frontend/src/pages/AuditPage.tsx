import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/Button';
import { cn } from '@/lib/cn';
import { getAuditLog } from '@/features/tickets/api';
import type { AuditEntry } from '@/features/tickets/api';

const STALE = 30_000;
const PAGE_SIZE = 25;

const ENTITY_TYPES = ['', 'ticket', 'user', 'comment', 'category', 'branch', 'sla'];
const ACTIONS = ['', 'create', 'update', 'delete', 'status_change', 'assign', 'login', 'logout', 'escalate'];

function Sk({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-lg bg-slate-200 dark:bg-slate-800', className)} />;
}

const ACTION_CLS: Record<string, string> = {
  create:        'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  update:        'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  delete:        'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  status_change: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  assign:        'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400',
  login:         'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
  logout:        'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
  escalate:      'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
};

// ── Diff viewer ───────────────────────────────────────────────────────────────

function DiffViewer({ oldValues, newValues }: { oldValues: Record<string, unknown> | null; newValues: Record<string, unknown> | null }) {
  const allKeys = new Set([...Object.keys(oldValues ?? {}), ...Object.keys(newValues ?? {})]);
  if (allKeys.size === 0) return <p className="text-xs text-slate-400 italic">No details</p>;

  const changedKeys = [...allKeys].filter(
    (k) => JSON.stringify((oldValues ?? {})[k]) !== JSON.stringify((newValues ?? {})[k]),
  );

  if (changedKeys.length === 0) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
        {oldValues && <div>
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1.5">Before</p>
          <pre className="bg-slate-50 dark:bg-slate-900 rounded-lg p-2.5 overflow-x-auto text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-800 text-[10px] leading-relaxed">{JSON.stringify(oldValues, null, 2)}</pre>
        </div>}
        {newValues && <div>
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1.5">After</p>
          <pre className="bg-slate-50 dark:bg-slate-900 rounded-lg p-2.5 overflow-x-auto text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-800 text-[10px] leading-relaxed">{JSON.stringify(newValues, null, 2)}</pre>
        </div>}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 text-xs">
      {changedKeys.map((key) => {
        const oldVal = (oldValues ?? {})[key];
        const newVal = (newValues ?? {})[key];
        return (
          <div key={key}>
            <span className="font-mono font-semibold text-[10px] text-slate-500 dark:text-slate-400 block mb-1">{key}</span>
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-red-50 dark:bg-red-900/20 rounded-lg px-2 py-1.5 border border-red-100 dark:border-red-900/40">
                <span className="text-[9px] text-red-500 font-semibold uppercase tracking-wide block mb-0.5">Before</span>
                <code className="text-red-700 dark:text-red-400 break-all text-[10px]">{oldVal === undefined ? '—' : JSON.stringify(oldVal)}</code>
              </div>
              <div className="bg-emerald-50 dark:bg-emerald-900/20 rounded-lg px-2 py-1.5 border border-emerald-100 dark:border-emerald-900/40">
                <span className="text-[9px] text-emerald-500 font-semibold uppercase tracking-wide block mb-0.5">After</span>
                <code className="text-emerald-700 dark:text-emerald-400 break-all text-[10px]">{newVal === undefined ? '—' : JSON.stringify(newVal)}</code>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Table row ─────────────────────────────────────────────────────────────────

function AuditRow({ entry }: { entry: AuditEntry }) {
  const [expanded, setExpanded] = useState(false);
  const hasDiff = entry.old_values !== null || entry.new_values !== null;
  const date = new Date(entry.created_at);
  const dateStr = date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: '2-digit' });
  const timeStr = date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  return (
    <>
      <tr
        className={cn(
          'border-b border-slate-100 dark:border-slate-800 transition-colors',
          hasDiff ? 'cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/30' : '',
          expanded && 'bg-slate-50 dark:bg-slate-800/20',
        )}
        onClick={() => hasDiff && setExpanded((p) => !p)}
      >
        <td className="px-4 py-2.5 whitespace-nowrap">
          <div className="text-xs font-medium text-slate-700 dark:text-slate-300">{dateStr}</div>
          <div className="text-[10px] text-slate-400 font-mono">{timeStr}</div>
        </td>
        <td className="px-4 py-2.5">
          <div className="text-xs text-slate-700 dark:text-slate-300 font-medium">{entry.actor_email ?? 'System'}</div>
          {entry.actor_id && (
            <div className="text-[10px] text-slate-400 font-mono">{entry.actor_id.slice(0, 8)}…</div>
          )}
        </td>
        <td className="px-4 py-2.5">
          <span className={cn('pill text-[10px]', ACTION_CLS[entry.action] ?? 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400')}>
            {entry.action}
          </span>
        </td>
        <td className="px-4 py-2.5">
          <div className="text-xs text-slate-600 dark:text-slate-400 font-medium capitalize">{entry.entity_type}</div>
          <div className="text-[10px] text-slate-400 font-mono">{entry.entity_id.slice(0, 8)}…</div>
        </td>
        <td className="px-4 py-2.5 text-xs text-slate-400 font-mono">{entry.ip_address ?? '—'}</td>
        <td className="px-4 py-2.5 text-right w-8">
          {hasDiff && (
            <svg className={cn('h-3.5 w-3.5 text-slate-400 inline-block transition-transform duration-150', expanded && 'rotate-180')} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M6 9l6 6 6-6" />
            </svg>
          )}
        </td>
      </tr>
      {expanded && hasDiff && (
        <tr className="bg-slate-50 dark:bg-slate-900/50">
          <td colSpan={6} className="px-5 py-3.5">
            <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-2.5">Change Details</p>
            <DiffViewer oldValues={entry.old_values} newValues={entry.new_values} />
          </td>
        </tr>
      )}
    </>
  );
}

// ── Filter chip ───────────────────────────────────────────────────────────────

function FilterChip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="filter-chip">
      {label}
      <button onClick={onRemove} className="ml-0.5 hover:text-red-500 transition-colors" aria-label={`Remove ${label}`}>
        <svg className="h-2.5 w-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 6 6 18M6 6l12 12" />
        </svg>
      </button>
    </span>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function AuditPage() {
  const [entityType, setEntityType] = useState('');
  const [action,     setAction]     = useState('');
  const [fromDate,   setFromDate]   = useState('');
  const [toDate,     setToDate]     = useState('');
  const [page,       setPage]       = useState(1);
  const [filtersOpen, setFiltersOpen] = useState(false);

  // Draft state
  const [draftEntity,   setDraftEntity]   = useState('');
  const [draftAction,   setDraftAction]   = useState('');
  const [draftFromDate, setDraftFromDate] = useState('');
  const [draftToDate,   setDraftToDate]   = useState('');

  const queryParams = {
    ...(entityType ? { entity_type: entityType } : {}),
    ...(action     ? { action }                  : {}),
    ...(fromDate   ? { from_date: fromDate }     : {}),
    ...(toDate     ? { to_date: toDate }         : {}),
    page,
    page_size: PAGE_SIZE,
  };

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['audit', queryParams],
    queryFn: () => getAuditLog(queryParams),
    staleTime: STALE,
    refetchInterval: STALE,
  });

  const applyFilters = () => {
    setEntityType(draftEntity);
    setAction(draftAction);
    setFromDate(draftFromDate);
    setToDate(draftToDate);
    setPage(1);
    setFiltersOpen(false);
  };

  const clearFilters = () => {
    setEntityType(''); setAction(''); setFromDate(''); setToDate('');
    setDraftEntity(''); setDraftAction(''); setDraftFromDate(''); setDraftToDate('');
    setPage(1);
    setFiltersOpen(false);
  };

  const removeFilter = (key: 'entityType' | 'action' | 'fromDate' | 'toDate') => {
    if (key === 'entityType') { setEntityType(''); setDraftEntity(''); }
    if (key === 'action')     { setAction('');     setDraftAction(''); }
    if (key === 'fromDate')   { setFromDate('');   setDraftFromDate(''); }
    if (key === 'toDate')     { setToDate('');     setDraftToDate(''); }
    setPage(1);
  };

  const activeCount = [entityType, action, fromDate, toDate].filter(Boolean).length;
  const total      = data?.total ?? 0;
  const totalPages = data?.total_pages ?? 1;

  return (
    <div className="flex flex-col gap-4">

      {/* ── Header ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">Audit Log</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            {isFetching && !isLoading ? (
              <span className="flex items-center gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse inline-block" />
                Refreshing…
              </span>
            ) : (
              `${total.toLocaleString()} audit entr${total !== 1 ? 'ies' : 'y'}`
            )}
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="btn-outline h-8 text-xs gap-1.5"
          title="Refresh"
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M1 4v6h6M23 20v-6h-6M20.49 9A9 9 0 0 0 5.64 5.64L1 10M23 14l-4.64 4.36A9 9 0 0 1 3.51 15" />
          </svg>
          Refresh
        </button>
      </div>

      {/* ── Filter trigger bar ───────────────────────────────────────── */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => setFiltersOpen((p) => !p)}
          aria-expanded={filtersOpen}
          className={cn(
            'btn-outline h-9 gap-1.5 text-sm',
            filtersOpen && 'border-brand-400 dark:border-brand-600 bg-brand-50 dark:bg-brand-900/20 text-brand-700 dark:text-brand-400',
          )}
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 6h18M7 12h10M11 18h2" />
          </svg>
          Filters
          {activeCount > 0 && (
            <span className="h-4 min-w-4 px-1 rounded-full bg-brand-600 text-white text-[10px] font-bold flex items-center justify-center">
              {activeCount}
            </span>
          )}
          <svg
            className={cn('h-3 w-3 transition-transform duration-200', filtersOpen && 'rotate-180')}
            viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
          >
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>

        {activeCount > 0 && (
          <button onClick={clearFilters} className="text-xs text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 transition-colors">
            Clear all
          </button>
        )}
      </div>

      {/* ── Collapsible filter drawer ─────────────────────────────────── */}
      <div className={cn('filter-drawer', filtersOpen && 'open')} aria-hidden={!filtersOpen}>
        <div>
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Entity Type</label>
                <select className="input h-8 text-xs" value={draftEntity} onChange={(e) => setDraftEntity(e.target.value)}>
                  {ENTITY_TYPES.map((et) => <option key={et} value={et}>{et || 'All Types'}</option>)}
                </select>
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Action</label>
                <select className="input h-8 text-xs" value={draftAction} onChange={(e) => setDraftAction(e.target.value)}>
                  {ACTIONS.map((a) => <option key={a} value={a}>{a || 'All Actions'}</option>)}
                </select>
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">From Date</label>
                <input type="date" className="input h-8 text-xs" value={draftFromDate} onChange={(e) => setDraftFromDate(e.target.value)} />
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">To Date</label>
                <input type="date" className="input h-8 text-xs" value={draftToDate} onChange={(e) => setDraftToDate(e.target.value)} />
              </div>
            </div>

            <div className="flex items-center gap-2 pt-3 border-t border-slate-100 dark:border-slate-800">
              <Button onClick={applyFilters}>Apply Filters</Button>
              <button onClick={() => { setDraftEntity(''); setDraftAction(''); setDraftFromDate(''); setDraftToDate(''); }} className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors">
                Reset
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Active filter chips ──────────────────────────────────────── */}
      {activeCount > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Active:</span>
          {entityType && <FilterChip label={`Type: ${entityType}`} onRemove={() => removeFilter('entityType')} />}
          {action     && <FilterChip label={`Action: ${action}`}   onRemove={() => removeFilter('action')} />}
          {fromDate   && <FilterChip label={`From: ${fromDate}`}   onRemove={() => removeFilter('fromDate')} />}
          {toDate     && <FilterChip label={`To: ${toDate}`}       onRemove={() => removeFilter('toDate')} />}
        </div>
      )}

      {/* ── Table ───────────────────────────────────────────────────── */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800 overflow-hidden">
        {isError ? (
          <div className="flex flex-col items-center gap-3 py-12">
            <svg className="h-9 w-9 text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" />
            </svg>
            <p className="text-sm text-slate-500">Failed to load audit log.</p>
            <Button variant="ghost" onClick={() => refetch()}>Retry</Button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800">
                  <th className="text-left px-4 py-2.5 text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Timestamp</th>
                  <th className="text-left px-4 py-2.5 text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Actor</th>
                  <th className="text-left px-4 py-2.5 text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Action</th>
                  <th className="text-left px-4 py-2.5 text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Entity</th>
                  <th className="text-left px-4 py-2.5 text-[10px] uppercase tracking-wider text-slate-400 font-semibold">IP</th>
                  <th className="px-4 py-2.5 w-8" />
                </tr>
              </thead>
              <tbody>
                {isLoading
                  ? Array.from({ length: 10 }).map((_, i) => (
                      <tr key={i} className="border-b border-slate-50 dark:border-slate-800">
                        {[...Array(5)].map((__, j) => (
                          <td key={j} className="px-4 py-2.5"><Sk className="h-3.5 w-full" /></td>
                        ))}
                        <td className="px-4 py-2.5" />
                      </tr>
                    ))
                  : data?.items.length === 0
                  ? (
                      <tr>
                        <td colSpan={6} className="px-4 py-12 text-center text-sm text-slate-400">
                          No audit entries{activeCount > 0 ? ' for these filters' : ''}.
                        </td>
                      </tr>
                    )
                  : (data?.items ?? []).map((entry) => <AuditRow key={entry.id} entry={entry} />)
                }
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Pagination ──────────────────────────────────────────────── */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-slate-400">
            Page {page} of {totalPages} · {total.toLocaleString()} entries
          </p>
          <div className="flex items-center gap-1.5">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="btn-outline h-7 w-7 p-0 disabled:opacity-40"
              aria-label="Previous"
            >
              <svg className="h-3.5 w-3.5 mx-auto" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M15 18l-6-6 6-6" />
              </svg>
            </button>

            <div className="flex items-center gap-1">
              {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                let pg: number;
                if (totalPages <= 5)          pg = i + 1;
                else if (page <= 3)           pg = i + 1;
                else if (page >= totalPages - 2) pg = totalPages - 4 + i;
                else                          pg = page - 2 + i;
                return (
                  <button
                    key={pg}
                    onClick={() => setPage(pg)}
                    className={cn(
                      'h-7 w-7 rounded-lg text-xs font-medium transition-colors',
                      pg === page
                        ? 'bg-brand-600 text-white'
                        : 'text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800',
                    )}
                  >
                    {pg}
                  </button>
                );
              })}
            </div>

            <button
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="btn-outline h-7 w-7 p-0 disabled:opacity-40"
              aria-label="Next"
            >
              <svg className="h-3.5 w-3.5 mx-auto" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 18l6-6-6-6" />
              </svg>
            </button>
          </div>
        </div>
      )}

      <p className="text-[10px] text-slate-400 text-center">
        Click any row with a ↓ indicator to view field-level changes.
      </p>
    </div>
  );
}
