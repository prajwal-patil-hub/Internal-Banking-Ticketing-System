import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { listUsers, listRoles } from '@/features/admin/api';
import type { AdminUser } from '@/features/admin/api';

const STALE = 30_000;

function fmt(d: string | null) {
  if (!d) return '—';
  return new Date(d).toLocaleString();
}

function RoleBadge({ role }: { role: string }) {
  return (
    <span className="pill bg-cream-200 text-ink-700">{role.replace('_', ' ')}</span>
  );
}

export function UsersPage() {
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [page, setPage] = useState(1);

  const usersQuery = useQuery({
    queryKey: ['admin', 'users', { search, role: roleFilter, page }],
    queryFn: () =>
      listUsers({
        page,
        per_page: 20,
        ...(search ? { search } : {}),
        ...(roleFilter ? { role: roleFilter } : {}),
      }),
    staleTime: STALE,
  });

  const rolesQuery = useQuery({
    queryKey: ['admin', 'roles'],
    queryFn: listRoles,
    staleTime: 5 * 60_000,
  });

  const users: AdminUser[] = usersQuery.data?.items ?? [];
  const total = usersQuery.data?.total ?? 0;
  const totalPages = usersQuery.data?.total_pages ?? 1;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="font-display text-2xl tracking-tight text-ink-900 dark:text-ink-50">Users & Roles</h1>
        <p className="text-sm text-ink-500 mt-1">{total} user{total !== 1 ? 's' : ''}</p>
      </header>

      <Card padded={false}>
        <div className="p-4 flex flex-wrap items-center gap-3">
          <input
            className="input flex-1 min-w-[220px]"
            placeholder="Search by name or email…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          />
          <select
            className="input w-48"
            value={roleFilter}
            onChange={(e) => { setRoleFilter(e.target.value); setPage(1); }}
          >
            <option value="">All roles</option>
            {(rolesQuery.data ?? []).map((r) => (
              <option key={r.id} value={r.name}>{r.name}</option>
            ))}
          </select>
        </div>
      </Card>

      {usersQuery.isError && (
        <Card className="flex flex-col items-center gap-3 py-8">
          <p className="text-sm text-oxblood">Failed to load users.</p>
          <Button variant="ghost" onClick={() => usersQuery.refetch()}>Retry</Button>
        </Card>
      )}

      <Card padded={false}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-cream-200 text-xs uppercase tracking-wide text-ink-500">
                <th className="text-left px-5 py-3 font-medium">Name</th>
                <th className="text-left px-4 py-3 font-medium">Email</th>
                <th className="text-left px-4 py-3 font-medium">Role</th>
                <th className="text-left px-4 py-3 font-medium">Status</th>
                <th className="text-left px-4 py-3 font-medium">Last login</th>
              </tr>
            </thead>
            <tbody>
              {usersQuery.isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} className="border-b border-cream-200/40">
                    {Array.from({ length: 5 }).map((__, j) => (
                      <td key={j} className="px-4 py-3">
                        <div className="h-4 w-full max-w-[160px] rounded bg-cream-200 animate-pulse" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-5 py-12 text-center text-ink-300 text-sm">
                    No users match this filter.
                  </td>
                </tr>
              ) : (
                users.map((u) => (
                  <tr key={u.id} className="border-b border-cream-200/40 hover:bg-cream-50">
                    <td className="px-5 py-3 font-medium text-ink-900 dark:text-ink-50">{u.full_name}</td>
                    <td className="px-4 py-3 text-ink-700">{u.email}</td>
                    <td className="px-4 py-3"><RoleBadge role={u.role} /></td>
                    <td className="px-4 py-3">
                      {u.is_active ? (
                        <span className="pill bg-brand-50 text-brand-700">Active</span>
                      ) : (
                        <span className="pill bg-oxblood-50 text-oxblood">Inactive</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-ink-500 text-xs">{fmt(u.last_login_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-xs text-ink-500">Page {page} of {totalPages}</span>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <Button variant="ghost" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
          </div>
        </div>
      )}

      {/* Role / permission card */}
      <Card>
        <h2 className="font-display text-lg text-ink-900 dark:text-ink-50 mb-3">Roles & Permissions</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {(rolesQuery.data ?? []).map((r) => (
            <div key={r.id} className="border border-cream-200 rounded-md p-4">
              <div className="flex items-center justify-between mb-1">
                <span className="font-medium text-ink-900 dark:text-ink-50 capitalize">{r.name.replace('_', ' ')}</span>
                <span className="text-xs text-ink-500">{r.permissions.length} permissions</span>
              </div>
              {r.description && <p className="text-xs text-ink-500 mb-2">{r.description}</p>}
              <div className="flex flex-wrap gap-1">
                {r.permissions.slice(0, 8).map((p) => (
                  <span key={p} className="pill bg-cream-200 text-ink-700 normal-case tracking-normal">{p}</span>
                ))}
                {r.permissions.length > 8 && (
                  <span className="pill bg-cream-200 text-ink-500 normal-case tracking-normal">+{r.permissions.length - 8} more</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
