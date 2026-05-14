import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Card } from '@/components/Card';
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

function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-xl bg-slate-200 dark:bg-slate-800', className)} />;
}

function TicketSkeleton() {
  return (
    <Card padded={false} className="p-4">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <Skeleton className="h-5 w-20 rounded-lg" />
          <Skeleton className="h-5 w-16 rounded-full" />
          <Skeleton className="h-5 w-14 rounded-full" />
        </div>
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-3 w-2/3" />
        <div className="flex items-center gap-2 mt-1">
          <Skeleton className="h-5 w-16 rounded-full" />
          <Skeleton className="h-3 w-20" />
        </div>
      </div>
    </Card>
  );
}

export function TicketsPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  // Parse filters from URL
  const status = (searchParams.get('status') ?? '') as TicketStatus | '';
  const priority = (searchParams.get('priority') ?? '') as TicketPriority | '';
  const search = searchParams.get('q') ?? '';
  const myTickets = searchParams.get('mine') === '1';
  const page = parseInt(searchParams.get('page') ?? '1', 10);

  // Local search input state (debounced)
  const [searchInput, setSearchInput] = useState(search);

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (searchInput) {
          next.set('q', searchInput);
        } else {
          next.delete('q');
        }
        next.delete('page');
        return next;
      });
    }, 400);
    return () => clearTimeout(timer);
  }, [searchInput, setSearchParams]);

  const queryParams = {
    ...(status ? { status } : {}),
    ...(priority ? { priority } : {}),
    ...(search ? { search } : {}),
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

  const setFilter = (key: string, value: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) {
        next.set(key, value);
      } else {
        next.delete(key);
      }
      next.delete('page');
      return next;
    });
  };

  const setPage = (p: number) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set('page', String(p));
      return next;
    });
  };

  const clearFilters = () => {
    setSearchInput('');
    setSearchParams({});
  };

  const hasFilters = status || priority || search || myTickets;
  const totalPages = data?.total_pages ?? 1;
  const total = data?.total ?? 0;

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Tickets</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            {isFetching && !isLoading ? (
              <span className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse inline-block" />
                Refreshing…
              </span>
            ) : (
              `${total.toLocaleString()} ticket${total !== 1 ? 's' : ''} found`
            )}
          </p>
        </div>
        <Button onClick={() => navigate('/tickets/new')}>
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
          Create Ticket
        </Button>
      </div>

      {/* Filters */}
      <Card padded={false}>
        <div className="p-4 flex flex-wrap items-center gap-3">
          {/* Search */}
          <div className="relative flex-1 min-w-[200px]">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 pointer-events-none" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" />
              <path d="M21 21l-4.35-4.35" />
            </svg>
            <input
              className="input pl-9 w-full"
              placeholder="Search tickets, keywords…"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
          </div>

          {/* Status */}
          <select
            className="input w-44"
            value={status}
            onChange={(e) => setFilter('status', e.target.value)}
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>

          {/* Priority */}
          <select
            className="input w-40"
            value={priority}
            onChange={(e) => setFilter('priority', e.target.value)}
          >
            {PRIORITY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>

          {/* My Tickets */}
          <label className="flex items-center gap-2 cursor-pointer select-none text-sm font-medium text-slate-700 dark:text-slate-300">
            <input
              type="checkbox"
              className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
              checked={myTickets}
              onChange={(e) => setFilter('mine', e.target.checked ? '1' : '')}
            />
            My Tickets
          </label>

          {hasFilters && (
            <button
              onClick={clearFilters}
              className="text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 underline underline-offset-2 whitespace-nowrap"
            >
              Clear filters
            </button>
          )}
        </div>
      </Card>

      {/* Error state */}
      {isError && (
        <Card className="flex flex-col items-center gap-3 py-8">
          <svg className="h-10 w-10 text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 8v4M12 16h.01" />
          </svg>
          <p className="text-sm text-slate-600 dark:text-slate-400">Failed to load tickets. Please try again.</p>
          <Button variant="ghost" onClick={() => refetch()}>Retry</Button>
        </Card>
      )}

      {/* Loading skeletons */}
      {isLoading && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
          {Array.from({ length: 10 }).map((_, i) => <TicketSkeleton key={i} />)}
        </div>
      )}

      {/* Tickets grid */}
      {!isLoading && !isError && data && (
        <>
          {data.items.length === 0 ? (
            <Card className="flex flex-col items-center gap-3 py-12 text-center">
              <svg className="h-12 w-12 text-slate-300 dark:text-slate-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 12h6M9 16h6M13 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-5-5z" />
              </svg>
              <div>
                <p className="text-base font-medium text-slate-700 dark:text-slate-300">No tickets found</p>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                  {hasFilters ? 'Try adjusting your filters.' : 'Create your first ticket to get started.'}
                </p>
              </div>
              {!hasFilters && (
                <Button onClick={() => navigate('/tickets/new')}>Create Ticket</Button>
              )}
            </Card>
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
              {data.items.map((ticket) => (
                <TicketCard key={ticket.id} ticket={ticket} />
              ))}
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-slate-500">
                Page {page} of {totalPages} · {total} tickets
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M15 18l-6-6 6-6" />
                  </svg>
                  Previous
                </Button>

                {/* Page numbers */}
                <div className="flex items-center gap-1">
                  {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                    let p: number;
                    if (totalPages <= 7) {
                      p = i + 1;
                    } else if (page <= 4) {
                      p = i + 1;
                    } else if (page >= totalPages - 3) {
                      p = totalPages - 6 + i;
                    } else {
                      p = page - 3 + i;
                    }
                    return (
                      <button
                        key={p}
                        onClick={() => setPage(p)}
                        className={cn(
                          'h-8 w-8 rounded-lg text-sm font-medium transition-colors',
                          p === page
                            ? 'bg-brand-600 text-white'
                            : 'text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800',
                        )}
                      >
                        {p}
                      </button>
                    );
                  })}
                </div>

                <Button
                  variant="ghost"
                  disabled={page >= totalPages}
                  onClick={() => setPage(page + 1)}
                >
                  Next
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M9 18l6-6-6-6" />
                  </svg>
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
