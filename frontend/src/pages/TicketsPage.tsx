import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/Button';
import { TicketCard } from '@/components/TicketCard';
import { useAuth } from '@/store/auth';
import { canRaiseTicket } from '@/lib/permissions';
import { cn } from '@/lib/cn';
import { listTickets } from '@/features/tickets/api';
import type { TicketSource, TicketStatus, TicketPriority } from '@/features/tickets/api';
import { PageHeader, PageShell, RefreshingDot } from '@/components/PageHeader';

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
  return <div className={cn('animate-pulse rounded-lg bg-[var(--inset)]', className)} />;
}

function TicketSkeleton() {
  return (
    <div className="rounded-xl border border-[var(--sh-dark)] p-3.5">
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
  // An auditor is read-only: offering a New Ticket button leads to a form
  // whose submit the server rejects.
  const canRaise = canRaiseTicket(user);
  const [searchParams, setSearchParams] = useSearchParams();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const filterDrawerRef = useRef<HTMLDivElement>(null);

  // Parse filters from URL
  const status   = (searchParams.get('status') ?? '') as TicketStatus | '';
  const priority = (searchParams.get('priority') ?? '') as TicketPriority | '';
  const search   = searchParams.get('q') ?? '';
  const myTickets = searchParams.get('mine') === '1';
  const page     = parseInt(searchParams.get('page') ?? '1', 10);

  // Drill-down filters. These arrive from the dashboard KPI cards rather than
  // the filter drawer, so they are read straight from the URL and surfaced as
  // removable chips — otherwise a card would land the user on a list that
  // silently disagrees with the number they just clicked.
  const slaBreached  = searchParams.get('sla_breached') === '1';
  const statusGroup  = searchParams.get('status_group') as 'open' | 'closed' | null;
  const source       = (searchParams.get('source') ?? '') as TicketSource | '';
  const aiCategorized = searchParams.get('ai_categorized') === '1';
  const createdFrom  = searchParams.get('created_from') ?? '';
  const resolvedFrom = searchParams.get('resolved_from') ?? '';

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
        if (searchInput) next.set('q', searchInput);
        else next.delete('q');
        next.delete('page');
        return next;
      });
    }, 400);
    return () => clearTimeout(t);
  }, [searchInput, setSearchParams]);

  const applyFilters = () => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (draftStatus) next.set('status', draftStatus);
      else next.delete('status');
      if (draftPriority) next.set('priority', draftPriority);
      else next.delete('priority');
      if (draftMyTickets) next.set('mine', '1');
      else next.delete('mine');
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
    setSearchParams({});   // also clears any drill-down the URL carried
    setFiltersOpen(false);
  };

  type FilterKey =
    | 'status' | 'priority' | 'mine' | 'q'
    | 'sla_breached' | 'status_group' | 'source' | 'ai_categorized'
    | 'created_from' | 'resolved_from';

  const removeFilter = (key: FilterKey) => {
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
  const activeCount = [
    status, priority, myTickets ? '1' : '', search,
    slaBreached ? '1' : '', statusGroup ?? '', source,
    aiCategorized ? '1' : '', createdFrom, resolvedFrom,
  ].filter(Boolean).length;

  const queryParams = {
    ...(status    ? { status }             : {}),
    ...(priority  ? { priority }           : {}),
    ...(search    ? { search }             : {}),
    ...(myTickets && user ? { assignee_id: user.id } : {}),
    ...(slaBreached    ? { sla_breached: true }        : {}),
    ...(statusGroup    ? { status_group: statusGroup } : {}),
    ...(source         ? { source }                    : {}),
    ...(aiCategorized  ? { ai_categorized: true }      : {}),
    ...(createdFrom    ? { created_from: createdFrom } : {}),
    ...(resolvedFrom   ? { resolved_from: resolvedFrom } : {}),
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
    <PageShell>

      <PageHeader
        title="Tickets"
        subtitle={
          isFetching && !isLoading
            ? <RefreshingDot />
            : `${total.toLocaleString()} ticket${total !== 1 ? 's' : ''}`
        }
        actions={canRaise && (
          <Button onClick={() => navigate('/tickets/new')}>
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
            New Ticket
          </Button>
        )}
      />

      {/* ── Search bar + filter trigger ──────────────────────────────── */}
      <div className="flex items-center gap-2">
        {/* Search */}
        <div className="relative flex-1">
          <svg
            className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--tx-3)] pointer-events-none"
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
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[var(--tx-3)] hover:text-[var(--tx)]"
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
            className="text-xs text-[var(--tx-3)] hover:text-[var(--tx)] whitespace-nowrap shrink-0 transition-colors"
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
          <div className="rounded-xl border border-[var(--sh-dark)] bg-white p-4">
            <div className="flex flex-wrap items-end gap-4 mb-4">
              {/* Status */}
              <div className="flex flex-col gap-1">
                <label className="text-[10px] font-semibold uppercase tracking-wider text-[var(--tx-3)]">Status</label>
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
                <label className="text-[10px] font-semibold uppercase tracking-wider text-[var(--tx-3)]">Priority</label>
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
                <label className="text-[10px] font-semibold uppercase tracking-wider text-[var(--tx-3)]">Assigned To</label>
                <label className="flex items-center gap-2 h-8 cursor-pointer select-none text-sm font-medium text-[var(--tx-2)]">
                  <input
                    type="checkbox"
                    className="rounded border-[var(--sh-dark)] text-brand-600 focus:ring-brand-500"
                    checked={draftMyTickets}
                    onChange={(e) => setDraftMine(e.target.checked)}
                  />
                  My tickets only
                </label>
              </div>
            </div>

            <div className="flex items-center gap-2 pt-3 border-t border-[var(--sh-dark)]">
              <Button onClick={applyFilters}>Apply Filters</Button>
              <button
                onClick={() => { setDraftStatus(''); setDraftPriority(''); setDraftMine(false); }}
                className="text-xs text-[var(--tx-3)] hover:text-[var(--tx)] transition-colors"
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
          <span className="text-[10px] uppercase tracking-wider text-[var(--tx-3)] font-semibold">Active:</span>
          {search    && <FilterChip label={`Search: "${search}"`}                onRemove={() => removeFilter('q')} />}
          {status    && <FilterChip label={`Status: ${status.replace('_', ' ')}`} onRemove={() => removeFilter('status')} />}
          {priority  && <FilterChip label={`Priority: ${priority}`}              onRemove={() => removeFilter('priority')} />}
          {myTickets && <FilterChip label="My tickets"                           onRemove={() => removeFilter('mine')} />}
          {/* Drill-downs arriving from a dashboard card. Naming them here is
              what makes a filtered count legible instead of mysterious. */}
          {statusGroup   && <FilterChip label={statusGroup === 'open' ? 'Open tickets' : 'Closed tickets'} onRemove={() => removeFilter('status_group')} />}
          {slaBreached   && <FilterChip label="SLA breached"                      onRemove={() => removeFilter('sla_breached')} />}
          {source        && <FilterChip label={`Source: ${source}`}               onRemove={() => removeFilter('source')} />}
          {aiCategorized && <FilterChip label="AI categorised"                    onRemove={() => removeFilter('ai_categorized')} />}
          {createdFrom   && <FilterChip label={`Created since ${createdFrom.slice(0, 10)}`}  onRemove={() => removeFilter('created_from')} />}
          {resolvedFrom  && <FilterChip label={`Resolved since ${resolvedFrom.slice(0, 10)}`} onRemove={() => removeFilter('resolved_from')} />}
        </div>
      )}

      {/* ── Error ───────────────────────────────────────────────────── */}
      {isError && (
        <div className="flex items-center gap-3 rounded-xl border border-red-100 dark:border-red-900/40 bg-white p-4">
          <svg className="h-5 w-5 text-red-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" />
          </svg>
          <p className="text-sm text-[var(--tx-2)] flex-1">Failed to load tickets. Please try again.</p>
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
            <div className="flex flex-col items-center gap-3 py-16 text-center bg-white rounded-xl border border-[var(--sh-dark)]">
              <svg className="h-10 w-10 text-[var(--tx-3)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 12h6M9 16h6M13 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-5-5z" />
              </svg>
              <div>
                <p className="text-sm font-medium text-[var(--tx-2)]">No tickets found</p>
                <p className="text-xs text-[var(--tx-3)] mt-1">
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
              <p className="text-xs text-[var(--tx-3)]">
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
                            : 'text-[var(--tx-3)] hover:bg-[var(--inset)]',
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
    </PageShell>
  );
}
