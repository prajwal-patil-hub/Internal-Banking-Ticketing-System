import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { listBranches } from '@/features/admin/api';
import type { Branch } from '@/features/admin/api';

const STALE = 60_000;

export function BranchesPage() {
  const [search, setSearch] = useState('');
  const [activeOnly, setActiveOnly] = useState(true);
  const [page, setPage] = useState(1);

  const branchesQuery = useQuery({
    queryKey: ['admin', 'branches', { search, activeOnly, page }],
    queryFn: () =>
      listBranches({
        page,
        per_page: 50,
        ...(search ? { search } : {}),
        ...(activeOnly ? { is_active: true } : {}),
      }),
    staleTime: STALE,
  });

  const branches: Branch[] = branchesQuery.data?.items ?? [];
  const total = branchesQuery.data?.total ?? 0;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="font-display text-2xl tracking-tight text-ink-900 dark:text-ink-50">Branches</h1>
        <p className="text-sm text-ink-500 mt-1">
          {total} branch{total !== 1 ? 'es' : ''}
        </p>
      </header>

      <Card padded={false}>
        <div className="p-4 flex flex-wrap items-center gap-3">
          <input
            className="input flex-1 min-w-[220px]"
            placeholder="Search by code, name, region or IFSC…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          />
          <label className="flex items-center gap-2 text-sm text-ink-700 dark:text-ink-100">
            <input
              type="checkbox"
              className="rounded border-cream-300 text-brand-600 focus:ring-accent-400"
              checked={activeOnly}
              onChange={(e) => { setActiveOnly(e.target.checked); setPage(1); }}
            />
            Active only
          </label>
        </div>
      </Card>

      {branchesQuery.isError && (
        <Card className="flex flex-col items-center gap-3 py-8">
          <p className="text-sm text-oxblood">Failed to load branches.</p>
          <Button variant="ghost" onClick={() => branchesQuery.refetch()}>Retry</Button>
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {branchesQuery.isLoading ? (
          Array.from({ length: 6 }).map((_, i) => (
            <Card key={i}>
              <div className="h-4 w-32 rounded bg-cream-200 animate-pulse mb-2" />
              <div className="h-3 w-48 rounded bg-cream-200 animate-pulse" />
            </Card>
          ))
        ) : branches.length === 0 ? (
          <Card className="md:col-span-2 xl:col-span-3 text-center py-12">
            <p className="text-sm text-ink-300">No branches match this filter.</p>
          </Card>
        ) : (
          branches.map((b) => (
            <Card key={b.id} className="flex flex-col gap-2">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-medium text-ink-900 dark:text-ink-50">{b.name}</h3>
                  <p className="text-xs text-ink-500 mt-0.5">
                    {b.code} {b.region && `· ${b.region}`}
                  </p>
                </div>
                {b.is_active ? (
                  <span className="pill bg-brand-50 text-brand-700">Active</span>
                ) : (
                  <span className="pill bg-oxblood-50 text-oxblood">Inactive</span>
                )}
              </div>
              {b.address && <p className="text-xs text-ink-700">{b.address}</p>}
              <div className="text-xs text-ink-500 flex flex-col gap-0.5 mt-1">
                {b.ifsc && <span>IFSC: <span className="font-mono">{b.ifsc}</span></span>}
                {b.contact_email && <span>{b.contact_email}</span>}
                {b.contact_phone && <span>{b.contact_phone}</span>}
              </div>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
