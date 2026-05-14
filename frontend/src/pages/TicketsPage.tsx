import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/Button';
import { TicketCard } from '@/components/TicketCard';
import { useAuth } from '@/store/auth';
import { cn } from '@/lib/cn';
import { listTickets } from '@/features/tickets/api';
import type { TicketStatus, TicketPriority } from '@/features/tickets/api';

const STALE = 30_000;
const PAGE_SIZE = 20;

const STATUS_OPTIONS: { value: TicketStatus | ''; label: string }[] = [
  { value: '', label: 'All Statuses' },
  { value: 'new', label: 'New' },
  { value: 'acknowledged', label: 'Acknowledged' },
  { value: 'assigned', label: 'Assigned' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'on_hold', label: 'On Hold' },
  { value: 'escalated', label: 'Escalated' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'closed', label: 'Closed' },
  { value: 'reopened', label: 'Reopened' },
];

const PRIORITY_OPTIONS: { value: TicketPriority | ''; label: string }[] = [
  { value: '', label: 'All Priorities' },
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
];

// ── Skeleton ──────────────────────────────────────────────────────────────────

function Sk({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-lg bg-slate-200 dark:bg-slate-800', className)} />;
}

function TicketSkeleton() {
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-3.5">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <Sk className="h-4 w-20 rounded" />
          <Sk className="h-4 w-16 rounded-full" />
          <Sk className="h-4 w-14 rounded-full" />
        </div>
        <Sk className="h-3.5 w-full rounded" />
        <Sk className="h-3 w-2/3 rounded" />
        <div className="flex items-center gap-2">
          <Sk className="h-4 w-16 rounded-full" />
          <Sk className="h-3 w-20 rounded" />
        </div>
      </div>
    </div>
  );
}

// ── Active filter chip ────────────────────────────────────────────────────────

function FilterChip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="filter-chip">
      {label}
      <button
        onClick={onRemove}
        className="ml-0.5 hover:text-red-500 transition-colors"
        aria-label={`Remove ${label} filter`}
      >
        <svg className="h-2.5 w-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 6 6 18M6 6l12 12" />
        </svg>
      </button>
    </span>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function TicketsPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const filterDrawerRef = useRef<HTMLDivElement>(null);

  // Parse filters from URL
  const status   = (searchParams.get('status') ?? '') as TicketStatus | '';
  const priority = (searchParams.get('priority') ?? '') as TicketPriority | '';
  const search   = searchParams.get('q') ?? '';
  const myTickets = searchParams.get('mine') === '1';
  const page     = parseInt(searchParams.get('page') ?? '1', 10);

  // Local draft state for filter panel (applied on button click)
  const [draftStatus,    setDraftStatus]   = useState(status);
  const [draftPriority,  setDraftPriority] = useState(priority);
  const [draftMyTickets, setDraftMine]     = useState(myTickets);
  const [searchInput,    setSearchInput]   = useState(search);

  // Sync draft with URL when URL changes externally
  useEffect(() => { setDraftStatus(status); }, [status]);
  useEffect(() => { setDraftPriority(priority); }, [priority]);
  useEffect(() => { setDraftMine(myTickets); }, [myTickets]);
  useEffect(() => { setSearchInput(search); }, [search]);

  // Debounced search
  useEffect(() => {
    const t = setTimeout(() => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        searchInput ? next.set('q', searchInput) : next.delete('q');
        next.delete('page');
        return next;
      });
    }, 400);
    return () => clearTimeout(t);
  }, [searchInput, setSearchParams]);

  const applyFilters = () => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      draftStatus   ? next.set('status',   draftStatus)   : next.delete('status');
      draftPriority ? next.set('priority', draftPriority) : next.delete('priority');
      draftMyTickets ? next.set('mine', '1')              : next.delete('mine');
      next.delete('page');
      return next;
    });
    setFiltersOpen(false);
  };

  const clearFilters = () => {
    setDraftStatus('');
    setDraftPriority('');
    setDraftMine(false);
    setSearchInput('');
    setSearchParams({});
    setFiltersOpen(false);
  };

  const removeFilter = (key: 'status' | 'priority' | 'mine' | 'q') => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete(key);
      next.delete('page');
      return next;
    });
    if (key === 'status')   setDraftStatus('');
    if (key === 'priority') setDraftPriority('');
    if (key === 'mine')     setDraftMine(false);
    if (key === 'q')        setSearchInput('');
  };

  const setPage = (p: number) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set('page', String(p));
      return next;
    });
  };

  // Active filter count (for badge)
  const activeCount = [status, priority, myTickets ? '1' : '', search].filter(Boolean).length;

  const queryParams = {
    ...(status    ? { status }             : {}),
    ...(priority  ? { priority }           : {}),
    ...(search    ? { search }             : {}),
    ...(myTickets && user ? { assignee_id: user.id } : {}),
    page,
    page_size: PAGE_SIZE,
  };

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['tickets', 'list', queryParams],
    queryFn: () => listTickets(queryParams),
    staleTime: STALE,
    refetchInterval: STALE,
  });

  const totalPages = data?.total_pages ?? 1;
  const total      = data?.total ?? 0;

  return (
    <div className="flex flex-col gap-4">

      {/* ── Page header ─────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">Tickets</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            {isFetching && !isLoading ? (
              <span className="flex items-center gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse inline-block" />
                Refreshing…
              </span>
            ) : (
              `${total.toLocaleString()} ticket${total !== 1 ? 's' : ''}`
            )}
          </p>
        </div>
        <Button onClick={() => navigate('/tickets/new')}>
          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
          New Ticket
        </Button>
      </div>

      {/* ── Search bar + filter trigger ──────────────────────────────── */}
      <div className="flex items-center gap-2">
        {/* Search */}
        <div className="relative flex-1">
          <svg
            className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400 pointer-events-none"
            viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="M21 21l-4.35-4.35" />
          </svg>
          <input
            className="input pl-8 h-9"
            placeholder="Search by title, keyword, ticket number…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
          {searchInput && (
            <button
              onClick={() => { setSearchInput(''); removeFilter('q'); }}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
            >
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>

        {/* Filters button */}
        <button
          onClick={() => setFiltersOpen((p) => !p)}
          aria-expanded={filtersOpen}
          className={cn(
            'btn-outline h-9 gap-1.5 shrink-0 relative',
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

        {/* Clear all (only when filters active) */}
        {activeCount > 0 && (
          <button
            onClick={clearFilters}
            className="text-xs text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 whitespace-nowrap shrink-0 transition-colors"
          >
            Clear all
          </button>
        )}
      </div>

      {/* ── Collapsible filter drawer ────────────────────────────────── */}
      <div
        className={cn('filter-drawer', filtersOpen && 'open')}
        aria-hidden={!filtersOpen}
      >
        <div ref={filterDrawerRef}>
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
            <div className="flex flex-wrap items-end gap-4 mb-4">
              {/* Status */}
              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Status</label>
                <select
                  className="input w-40 h-8 text-xs"
                  value={draftStatus}
                  onChange={(e) => setDraftStatus(e.target.value as TicketStatus | '')}
                >
                  {STATUS_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>

              {/* Priority */}
              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Priority</label>
                <select
                  className="input w-36 h-8 text-xs"
                  value={draftPriority}
                  onChange={(e) => setDraftPriority(e.target.value as TicketPriority | '')}
                >
                  {PRIORITY_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>

              {/* My Tickets */}
              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Assigned To</label>
                <label className="flex items-center gap-2 h-8 cursor-pointer select-none text-sm font-medium text-slate-700 dark:text-slate-300">
                  <input
                    type="checkbox"
                    className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                    checked={draftMyTickets}
                    onChange={(e) => setDraftMine(e.target.checked)}
                  />
                  My tickets only
                </label>
              </div>
            </div>

            <div className="flex items-center gap-2 pt-3 border-t border-slate-100 dark:border-slate-800">
              <Button onClick={applyFilters}>Apply Filters</Button>
              <button
                onClick={() => { setDraftStatus(''); setDraftPriority(''); setDraftMine(false); }}
                className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
              >
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
          {search    && <FilterChip label={`Search: "${search}"`}                onRemove={() => removeFilter('q')} />}
          {status    && <FilterChip label={`Status: ${status.replace('_', ' ')}`} onRemove={() => removeFilter('status')} />}
          {priority  && <FilterChip label={`Priority: ${priority}`}              onRemove={() => removeFilter('priority')} />}
          {myTickets && <FilterChip label="My tickets"                           onRemove={() => removeFilter('mine')} />}
        </div>
      )}

      {/* ── Error ───────────────────────────────────────────────────── */}
      {isError && (
        <div className="flex items-center gap-3 rounded-xl border border-red-100 dark:border-red-900/40 bg-white dark:bg-slate-900 p-4">
          <svg className="h-5 w-5 text-red-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" />
          </svg>
          <p className="text-sm text-slate-600 dark:text-slate-400 flex-1">Failed to load tickets. Please try again.</p>
          <Button variant="ghost" onClick={() => refetch()}>Retry</Button>
        </div>
      )}

      {/* ── Loading ──────────────────────────────────────────────────── */}
      {isLoading && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
          {Array.from({ length: 10 }).map((_, i) => <TicketSkeleton key={i} />)}
        </div>
      )}

      {/* ── Ticket grid ─────────────────────────────────────────────── */}
      {!isLoading && !isError && data && (
        <>
          {data.items.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-16 text-center bg-white dark:bg-slate-900 rounded-xl border border-slate-200/80 dark:border-slate-800">
              <svg className="h-10 w-10 text-slate-300 dark:text-slate-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 12h6M9 16h6M13 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-5-5z" />
              </svg>
              <div>
                <p className="text-sm font-medium text-slate-700 dark:text-slate-300">No tickets found</p>
                <p className="text-xs text-slate-400 mt-1">
                  {activeCount > 0 ? 'Try adjusting your filters.' : 'Create your first ticket to get started.'}
                </p>
              </div>
              {activeCount === 0 && (
                <Button onClick={() => navigate('/tickets/new')}>Create Ticket</Button>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
              {data.items.map((ticket) => (
                <TicketCard key={ticket.id} ticket={ticket} />
              ))}
            </div>
          )}

          {/* ── Pagination ───────────────────────────────────────────── */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-1">
              <p className="text-xs text-slate-400">
                Page {page} of {totalPages} · {total.toLocaleString()} tickets
              </p>
              <div className="flex items-center gap-1.5">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                  className="btn-outline h-7 w-7 p-0 text-xs disabled:opacity-40"
                  aria-label="Previous page"
                >
                  <svg className="h-3.5 w-3.5 mx-auto" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M15 18l-6-6 6-6" />
                  </svg>
                </button>

                <div className="flex items-center gap-1">
                  {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                    let p: number;
                    if (totalPages <= 7)          p = i + 1;
                    else if (page <= 4)           p = i + 1;
                    else if (page >= totalPages - 3) p = totalPages - 6 + i;
                    else                          p = page - 3 + i;
                    return (
                      <button
                        key={p}
                        onClick={() => setPage(p)}
                        className={cn(
                          'h-7 w-7 rounded-lg text-xs font-medium transition-colors',
                          p === page
                            ? 'bg-brand-600 text-white'
                            : 'text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800',
                        )}
                      >
                        {p}
                      </button>
                    );
                  })}
                </div>

                <button
                  disabled={page >= totalPages}
                  onClick={() => setPage(page + 1)}
                  className="btn-outline h-7 w-7 p-0 text-xs disabled:opacity-40"
                  aria-label="Next page"
                >
                  <svg className="h-3.5 w-3.5 mx-auto" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M9 18l6-6-6-6" />
                  </svg>
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
