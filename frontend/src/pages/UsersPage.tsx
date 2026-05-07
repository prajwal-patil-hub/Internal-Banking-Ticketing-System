import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { ChevronLeft, ChevronRight, ShieldCheck, Shield } from 'lucide-react';

import { api } from '@/lib/api';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Skeleton } from '@/components/Skeleton';
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

function userInitials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join('') || '?';
}

export function UsersPage() {
  const [page, setPage] = useState(1);
  const size = 20;
  const { data, isLoading } = useQuery({
    queryKey: ['users', page],
    queryFn: () => listUsers(page, size),
  });

  return (
    <div className="flex flex-col gap-6">
      <motion.header
        initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}
      >
        <span className="label">Identity</span>
        <h1 className="text-4xl font-semibold tracking-tight text-ink mt-1">Users &amp; roles</h1>
        <p className="text-sm text-ink-muted mt-1">All accounts that can access the platform.</p>
      </motion.header>

      <Card padded={false} className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>User</th>
                <th>Email</th>
                <th>Role</th>
                <th>Branch</th>
                <th>MFA</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && Array.from({ length: 5 }).map((_, i) => (
                <tr key={i}>{Array.from({ length: 5 }).map((__, j) => (
                  <td key={j}><Skeleton className="h-4 w-full max-w-[160px]" /></td>
                ))}</tr>
              ))}
              {!isLoading && data?.items.length === 0 && (
                <tr><td colSpan={5} className="py-12 text-center text-ink-muted">No users found.</td></tr>
              )}
              {data?.items.map((u) => (
                <tr key={u.id}>
                  <td>
                    <div className="flex items-center gap-3">
                      <span className="h-9 w-9 rounded-pill grid place-items-center text-white font-semibold text-xs"
                            style={{ background: 'linear-gradient(135deg, #4F46E5, #8B5CF6)' }}>
                        {userInitials(u.full_name)}
                      </span>
                      <span className="text-ink font-medium">{u.full_name}</span>
                    </div>
                  </td>
                  <td className="text-ink-muted">{u.email}</td>
                  <td>
                    <Badge tone={ROLE_TONE[u.role] ?? 'neutral'}>
                      {u.role.replace('_', ' ')}
                    </Badge>
                  </td>
                  <td className="text-ink-muted">
                    {u.branch_id ? <code className="text-2xs">{u.branch_id.slice(0, 8)}…</code> : '—'}
                  </td>
                  <td>
                    {u.mfa_enabled
                      ? <span className="pill bg-success-soft text-success-deep"><ShieldCheck className="h-3.5 w-3.5" /> on</span>
                      : <span className="pill bg-slate-100 text-ink-muted"><Shield className="h-3.5 w-3.5" /> off</span>}
                  </td>
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
    </div>
  );
}
