import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Badge } from '@/components/Badge';
import type { AuthUser } from '@/store/auth';

interface ListEnvelope {
  success: boolean;
  data: AuthUser[];
  meta: { pagination: { page: number; size: number; total: number; pages: number } };
}

async function listUsers(page = 1, size = 20) {
  const { data } = await api.get<ListEnvelope>(`/users?page=${page}&size=${size}`);
  return { items: data.data, meta: data.meta.pagination };
}

const ROLE_TONE: Record<string, Parameters<typeof Badge>[0]['tone']> = {
  admin: 'danger',
  supervisor: 'warning',
  agent: 'info',
  auditor: 'assigned',
  branch_user: 'neutral',
};

export function UsersPage() {
  const [page, setPage] = useState(1);
  const size = 20;
  const { data, isLoading } = useQuery({ queryKey: ['users', page], queryFn: () => listUsers(page, size) });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Users & Roles</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Read-only listing in P2. Invite/edit flows arrive in a later phase.
        </p>
      </div>

      <Card padded={false} className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-surface-muted dark:bg-slate-800/50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Role</th>
              <th className="px-4 py-3">Branch</th>
              <th className="px-4 py-3">MFA</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {isLoading && <tr><td colSpan={5} className="px-4 py-8 text-center text-slate-400">Loading…</td></tr>}
            {!isLoading && data?.items.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-10 text-center text-slate-400">No users found.</td></tr>
            )}
            {data?.items.map((u) => (
              <tr key={u.id} className="hover:bg-surface-muted/60 dark:hover:bg-slate-800/40">
                <td className="px-4 py-3">{u.email}</td>
                <td className="px-4 py-3">{u.full_name}</td>
                <td className="px-4 py-3">
                  <Badge tone={ROLE_TONE[u.role] ?? 'neutral'}>{u.role.replace('_', ' ')}</Badge>
                </td>
                <td className="px-4 py-3 text-slate-500">
                  {u.branch_id ? <code className="text-xs">{u.branch_id.slice(0, 8)}…</code> : '—'}
                </td>
                <td className="px-4 py-3">
                  <Badge tone={u.mfa_enabled ? 'success' : 'neutral'}>
                    {u.mfa_enabled ? 'enabled' : 'off'}
                  </Badge>
                </td>
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
              <Button variant="ghost" disabled={page >= (data.meta.pages || 1)} onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
