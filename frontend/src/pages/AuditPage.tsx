import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { cn } from '@/lib/cn';
import { getAuditLog } from '@/features/tickets/api';
import type { AuditEntry } from '@/features/tickets/api';

const STALE = 30_000;
const PAGE_SIZE = 25;

const ENTITY_TYPES = ['', 'ticket', 'user', 'comment', 'category', 'branch', 'sla'];
const ACTIONS = ['', 'create', 'update', 'delete', 'status_change', 'assign', 'login', 'logout', 'escalate'];

function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-xl bg-slate-200 dark:bg-slate-800', className)} />;
}

const ACTION_CLASS: Record<string, string> = {
  create:        'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  update:        'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  delete:        'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  status_change: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  assign:        'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400',
  login:         'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
  logout:        'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
  escalate:      'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
};

function actionClass(action: string): string {
  return ACTION_CLASS[action] ?? 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400';
}

// ---------- Diff viewer ----------

interface DiffProps {
  oldValues: Record<string, unknown> | null;
  newValues: Record<string, unknown> | null;
}

function DiffViewer({ oldValues, newValues }: DiffProps) {
  const allKeys = new Set([
    ...Object.keys(oldValues ?? {}),
    ...Object.keys(newValues ?? {}),
  ]);

  if (allKeys.size === 0) return <p className="text-xs text-slate-400 italic">No details available</p>;

  // Find changed keys
  const changedKeys = [...allKeys].filter(
    (k) => JSON.stringify((oldValues ?? {})[k]) !== JSON.stringify((newValues ?? {})[k]),
  );

  if (changedKeys.length === 0 && (oldValues || newValues)) {
    // Just show raw
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
        {oldValues && (
          <div>
            <p className="font-medium text-slate-500 mb-1.5">Before</p>
            <pre className="bg-slate-50 dark:bg-slate-900 rounded-lg p-3 overflow-x-auto text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-800 leading-relaxed">
              {JSON.stringify(oldValues, null, 2)}
            </pre>
          </div>
        )}
        {newValues && (
          <div>
            <p className="font-medium text-slate-500 mb-1.5">After</p>
            <pre className="bg-slate-50 dark:bg-slate-900 rounded-lg p-3 overflow-x-auto text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-800 leading-relaxed">
              {JSON.stringify(newValues, null, 2)}
            </pre>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 text-xs">
      {changedKeys.map((key) => {
        const oldVal = (oldValues ?? {})[key];
        const newVal = (newValues ?? {})[key];
        return (
          <div key={key} className="flex flex-col gap-1">
            <span className="font-mono font-medium text-slate-600 dark:text-slate-400">{key}</span>
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-red-50 dark:bg-red-900/20 rounded-lg px-2 py-1.5 border border-red-100 dark:border-red-900/40">
                <span className="text-[10px] text-red-500 font-medium uppercase tracking-wide block mb-0.5">Before</span>
                <code className="text-red-700 dark:text-red-400 break-all">
                  {oldVal === undefined ? <em className="not-italic opacity-50">—</em> : JSON.stringify(oldVal)}
                </code>
              </div>
              <div className="bg-emerald-50 dark:bg-emerald-900/20 rounded-lg px-2 py-1.5 border border-emerald-100 dark:border-emerald-900/40">
                <span className="text-[10px] text-emerald-500 font-medium uppercase tracking-wide block mb-0.5">After</span>
                <code className="text-emerald-700 dark:text-emerald-400 break-all">
                  {newVal === undefined ? <em className="not-italic opacity-50">—</em> : JSON.stringify(newVal)}
                </code>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------- Row ----------

function AuditRow({ entry }: { entry: AuditEntry }) {
  const [expanded, setExpanded] = useState(false);
  const hasDiff = entry.old_values !== null || entry.new_values !== null;

  const date = new Date(entry.created_at);
  const dateStr = date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  const timeStr = date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  return (
    <>
      <tr
        className={cn(
          'border-b border-slate-100 dark:border-slate-800 transition-colors',
          hasDiff ? 'cursor-pointer hover:bg-surface-subtle dark:hover:bg-slate-800/30' : '',
          expanded && 'bg-surface-subtle dark:bg-slate-800/20',
        )}
        onClick={() => hasDiff && setExpanded((p) => !p)}
      >
        <td className="px-4 py-3 whitespace-nowrap">
          <div className="text-xs font-medium text-slate-700 dark:text-slate-300">{dateStr}</div>
          <div className="text-[10px] text-slate-400 font-mono">{timeStr}</div>
        </td>
        <td className="px-4 py-3">
          <div className="text-xs text-slate-700 dark:text-slate-300 font-medium">
            {entry.actor_email ?? 'System'}
          </div>
          {entry.actor_id && (
            <div className="text-[10px] text-slate-400 font-mono">{entry.actor_id.slice(0, 8)}…</div>
          )}
        </td>
        <td className="px-4 py-3">
          <span className={cn('pill text-xs', actionClass(entry.action))}>
            {entry.action}
          </span>
        </td>
        <td className="px-4 py-3">
          <div className="text-xs text-slate-600 dark:text-slate-400 font-medium capitalize">
            {entry.entity_type}
          </div>
          <div className="text-[10px] text-slate-400 font-mono">{entry.entity_id.slice(0, 8)}…</div>
        </td>
        <td className="px-4 py-3 text-xs text-slate-500 dark:text-slate-400">
          {entry.ip_address ?? '—'}
        </td>
        <td className="px-4 py-3 text-right">
          {hasDiff && (
            <svg
              className={cn('h-4 w-4 text-slate-400 inline-block transition-transform duration-150', expanded && 'rotate-180')}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M6 9l6 6 6-6" />
            </svg>
          )}
        </td>
      </tr>
      {expanded && hasDiff && (
        <tr className="bg-slate-50 dark:bg-slate-900/50">
          <td colSpan={6} className="px-6 py-4">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Change Details</p>
            <DiffViewer oldValues={entry.old_values} newValues={entry.new_values} />
          </td>
        </tr>
      )}
    </>
  );
}

// ---------- Main page ----------

export function AuditPage() {
  const [entityType, setEntityType] = useState('');
  const [action, setAction] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [page, setPage] = useState(1);

  const queryParams = {
    ...(entityType ? { entity_type: entityType } : {}),
    ...(action ? { action } : {}),
    ...(fromDate ? { from_date: fromDate } : {}),
    ...(toDate ? { to_date: toDate } : {}),
    page,
    page_size: PAGE_SIZE,
  };

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['audit', queryParams],
    queryFn: () => getAuditLog(queryParams),
    staleTime: STALE,
    refetchInterval: STALE,
  });

  const clearFilters = () => {
    setEntityType('');
    setAction('');
    setFromDate('');
    setToDate('');
    setPage(1);
  };

  const hasFilters = entityType || action || fromDate || toDate;
  const totalPages = data?.total_pages ?? 1;
  const total = data?.total ?? 0;

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Audit Log</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            {isFetching && !isLoading ? (
              <span className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse inline-block" />
                Refreshing…
              </span>
            ) : (
              `${total.toLocaleString()} audit entr${total !== 1 ? 'ies' : 'y'}`
            )}
          </p>
        </div>
        <Button variant="ghost" onClick={() => refetch()}>
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M1 4v6h6M23 20v-6h-6M20.49 9A9 9 0 0 0 5.64 5.64L1 10M23 14l-4.64 4.36A9 9 0 0 1 3.51 15" />
          </svg>
          Refresh
        </Button>
      </div>

      {/* Filters */}
      <Card padded={false}>
        <div className="p-4 flex flex-wrap items-end gap-3">
          {/* Entity type */}
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-500 font-medium">Entity Type</label>
            <select
              className="input w-36"
              value={entityType}
              onChange={(e) => { setEntityType(e.target.value); setPage(1); }}
            >
              {ENTITY_TYPES.map((et) => (
                <option key={et} value={et}>{et || 'All Types'}</option>
              ))}
            </select>
          </div>

          {/* Action */}
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-500 font-medium">Action</label>
            <select
              className="input w-40"
              value={action}
              onChange={(e) => { setAction(e.target.value); setPage(1); }}
            >
              {ACTIONS.map((a) => (
                <option key={a} value={a}>{a || 'All Actions'}</option>
              ))}
            </select>
          </div>

          {/* From date */}
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-500 font-medium">From Date</label>
            <input
              type="date"
              className="input w-40"
              value={fromDate}
              onChange={(e) => { setFromDate(e.target.value); setPage(1); }}
            />
          </div>

          {/* To date */}
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-500 font-medium">To Date</label>
            <input
              type="date"
              className="input w-40"
              value={toDate}
              onChange={(e) => { setToDate(e.target.value); setPage(1); }}
            />
          </div>

          {hasFilters && (
            <button
              onClick={clearFilters}
              className="text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 underline underline-offset-2 self-end pb-2"
            >
              Clear filters
            </button>
          )}
        </div>
      </Card>

      {/* Legend */}
      <div className="flex items-center gap-3 flex-wrap">
        {Object.entries(ACTION_CLASS).map(([a, cls]) => (
          <span key={a} className={cn('pill text-xs', cls)}>{a}</span>
        ))}
      </div>

      {/* Table */}
      <Card padded={false}>
        {isError ? (
          <div className="flex flex-col items-center gap-3 py-12">
            <svg className="h-10 w-10 text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" />
            </svg>
            <p className="text-sm text-slate-600">Failed to load audit log.</p>
            <Button variant="ghost" onClick={() => refetch()}>Retry</Button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800">
                  <th className="text-left px-4 py-3 text-xs uppercase tracking-wide text-slate-500 font-medium">Timestamp</th>
                  <th className="text-left px-4 py-3 text-xs uppercase tracking-wide text-slate-500 font-medium">Actor</th>
                  <th className="text-left px-4 py-3 text-xs uppercase tracking-wide text-slate-500 font-medium">Action</th>
                  <th className="text-left px-4 py-3 text-xs uppercase tracking-wide text-slate-500 font-medium">Entity</th>
                  <th className="text-left px-4 py-3 text-xs uppercase tracking-wide text-slate-500 font-medium">IP Address</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  Array.from({ length: 10 }).map((_, i) => (
                    <tr key={i} className="border-b border-slate-50 dark:border-slate-800">
                      {Array.from({ length: 5 }).map((_, j) => (
                        <td key={j} className="px-4 py-3">
                          <Skeleton className="h-4 w-full" />
                        </td>
                      ))}
                      <td className="px-4 py-3" />
                    </tr>
                  ))
                ) : data?.items.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-12 text-center text-sm text-slate-400">
                      No audit entries found{hasFilters ? ' for these filters' : ''}.
                    </td>
                  </tr>
                ) : (
                  (data?.items ?? []).map((entry) => (
                    <AuditRow key={entry.id} entry={entry} />
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-slate-500">
            Page {page} of {totalPages} · {total} entries
          </p>
          <div className="flex items-center gap-2">
            <Button variant="ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M15 18l-6-6 6-6" />
              </svg>
              Previous
            </Button>

            <div className="flex items-center gap-1">
              {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                let pg: number;
                if (totalPages <= 5) {
                  pg = i + 1;
                } else if (page <= 3) {
                  pg = i + 1;
                } else if (page >= totalPages - 2) {
                  pg = totalPages - 4 + i;
                } else {
                  pg = page - 2 + i;
                }
                return (
                  <button
                    key={pg}
                    onClick={() => setPage(pg)}
                    className={cn(
                      'h-8 w-8 rounded-lg text-sm font-medium transition-colors',
                      pg === page
                        ? 'bg-brand-600 text-white'
                        : 'text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800',
                    )}
                  >
                    {pg}
                  </button>
                );
              })}
            </div>

            <Button variant="ghost" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
              Next
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 18l6-6-6-6" />
              </svg>
            </Button>
          </div>
        </div>
      )}

      <p className="text-xs text-slate-400 text-center">
        Click any row with a diff indicator to view field-level changes.
      </p>
    </div>
  );
}
