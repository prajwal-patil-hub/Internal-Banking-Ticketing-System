import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/Button';
import { cn } from '@/lib/cn';
import { extractError } from '@/lib/api';
import {
  listUsers, createUser, updateUser, deactivateUser,
  getLevels, listOrgUnits, listOrgRoles,
  type OrgUser,
} from '@/features/org/api';

const SYSTEM_ROLES = ['admin', 'agent', 'supervisor', 'auditor', 'branch_user'];

function UserFormModal({
  editing,
  onClose,
}: {
  editing: OrgUser | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const { data: levels = [] } = useQuery({ queryKey: ['org-levels'], queryFn: getLevels });
  const [selectedLevelId, setSelectedLevelId] = useState('');
  const { data: orgUnitsRes } = useQuery({
    queryKey: ['org-units', selectedLevelId],
    queryFn: () => listOrgUnits({ hierarchy_level_id: selectedLevelId || undefined, per_page: 200 }),
  });
  const { data: orgRoles = [] } = useQuery({
    queryKey: ['org-roles', selectedLevelId],
    queryFn: () => listOrgRoles(selectedLevelId || undefined),
  });
  const orgUnits = orgUnitsRes?.data ?? [];

  const [form, setForm] = useState({
    email: editing?.email ?? '',
    full_name: editing?.full_name ?? '',
    password: '',
    role: editing?.role ?? 'branch_user',
    org_unit_id: editing?.org_unit_id ?? '',
    org_role_id: editing?.org_role_id ?? '',
    is_active: editing?.is_active ?? true,
    is_super_admin: editing?.is_super_admin ?? false,
  });
  const [error, setError] = useState<string | null>(null);

  const createMut = useMutation({
    mutationFn: () => createUser({
      email: form.email,
      full_name: form.full_name,
      password: form.password,
      role: form.role,
      org_unit_id: form.org_unit_id || undefined,
      org_role_id: form.org_role_id || undefined,
      is_super_admin: form.is_super_admin,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); onClose(); },
    // `.detail` is FastAPI's default error shape; this API returns
    // `{error: {message}}`, so the real reason — "Only a super admin can grant
    // super admin privileges", for one — was never reaching the screen.
    onError: (e) => setError(extractError(e).message),
  });

  const updateMut = useMutation({
    mutationFn: () => updateUser(editing!.id, {
      full_name: form.full_name,
      role: form.role,
      org_unit_id: form.org_unit_id || null,
      org_role_id: form.org_role_id || null,
      is_active: form.is_active,
      is_super_admin: form.is_super_admin,
      ...(form.password ? { password: form.password } : {}),
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); onClose(); },
    onError: (e) => setError(extractError(e).message),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="card w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-[var(--tx)]">{editing ? 'Edit User' : 'Create User'}</h2>
          <button onClick={onClose} className="btn-ghost !p-1.5 rounded-lg">
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {error && <div className="mb-3 text-xs text-[var(--err)] card-sm !p-2" style={{ borderLeft: '3px solid var(--err)' }}>{error}</div>}

        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
              Full Name *
              <input className="input" value={form.full_name} onChange={e => setForm(p => ({ ...p, full_name: e.target.value }))} />
            </label>
            <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
              Email *
              <input type="email" className="input" value={form.email} disabled={!!editing} onChange={e => setForm(p => ({ ...p, email: e.target.value }))} />
            </label>
          </div>

          <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
            {editing ? 'New Password (leave blank to keep)' : 'Password *'}
            <input type="password" className="input" value={form.password} onChange={e => setForm(p => ({ ...p, password: e.target.value }))} placeholder="Min 8 characters" />
          </label>

          <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
            System Role
            <select className="input" value={form.role} onChange={e => setForm(p => ({ ...p, role: e.target.value }))}>
              {SYSTEM_ROLES.map(r => <option key={r} value={r}>{r.replace('_', ' ')}</option>)}
            </select>
          </label>

          <div>
            <p className="text-xs font-semibold text-[var(--tx-3)] uppercase tracking-wide mb-2">Org Assignment</p>
            <div className="grid grid-cols-1 gap-3">
              <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
                Filter by Level
                <select className="input h-8 text-xs" value={selectedLevelId} onChange={e => setSelectedLevelId(e.target.value)}>
                  <option value="">All levels</option>
                  {levels.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
                Org Unit
                <select className="input" value={form.org_unit_id} onChange={e => setForm(p => ({ ...p, org_unit_id: e.target.value, org_role_id: '' }))}>
                  <option value="">None</option>
                  {orgUnits.map(u => <option key={u.id} value={u.id}>{u.name} ({u.code}) — {u.hierarchy_level}</option>)}
                </select>
              </label>
              {form.org_unit_id && (
                <label className="flex flex-col gap-1 text-sm font-medium text-[var(--tx-2)]">
                  Org Role
                  <select className="input" value={form.org_role_id} onChange={e => setForm(p => ({ ...p, org_role_id: e.target.value }))}>
                    <option value="">None</option>
                    {orgRoles.filter(r => orgUnits.find(u => u.id === form.org_unit_id)?.hierarchy_level_id === r.hierarchy_level_id).map(r => (
                      <option key={r.id} value={r.id}>{r.name}{r.can_manage_subtree ? ' (Subtree Admin)' : r.can_manage_unit ? ' (Unit Admin)' : ''}</option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          </div>

          <div className="flex gap-6">
            <label className="flex items-center gap-2 text-sm text-[var(--tx-2)]">
              <input type="checkbox" checked={form.is_active} onChange={e => setForm(p => ({ ...p, is_active: e.target.checked }))} className="h-4 w-4" />
              Active
            </label>
            <label className="flex items-center gap-2 text-sm text-[var(--tx-2)]">
              <input type="checkbox" checked={form.is_super_admin} onChange={e => setForm(p => ({ ...p, is_super_admin: e.target.checked }))} className="h-4 w-4" />
              Super Admin
            </label>
          </div>

          <div className="flex gap-2 justify-end pt-2">
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
            <Button
              onClick={() => editing ? updateMut.mutate() : createMut.mutate()}
              disabled={!form.full_name.trim() || (!editing && (!form.email.trim() || !form.password))}
            >
              {editing ? 'Save Changes' : 'Create User'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function UsersPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<OrgUser | null>(null);
  const [creating, setCreating] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['users', search, roleFilter, page],
    queryFn: () => listUsers({ search: search || undefined, role: roleFilter || undefined, page, per_page: 20 }),
  });
  const users = data?.data ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / 20);

  const deactivateMut = useMutation({
    mutationFn: (id: string) => deactivateUser(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  });

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-[var(--tx)]">Users</h1>
          <p className="text-xs text-[var(--tx-3)] mt-0.5">Manage user accounts and org assignments.</p>
        </div>
        <Button onClick={() => setCreating(true)} className="h-8 text-xs">+ Add User</Button>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <input className="input h-8 text-xs w-56" placeholder="Search name or email…" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} />
        <select className="input h-8 text-xs w-40" value={roleFilter} onChange={e => { setRoleFilter(e.target.value); setPage(1); }}>
          <option value="">All roles</option>
          {SYSTEM_ROLES.map(r => <option key={r} value={r}>{r.replace('_', ' ')}</option>)}
        </select>
        <span className="text-xs text-[var(--tx-3)] ml-auto">{total} user{total !== 1 ? 's' : ''}</span>
      </div>

      <div className="card-sm !p-0 overflow-hidden">
        <table className="data-table w-full">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>System Role</th>
              <th>Org Unit</th>
              <th>Org Role</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={7} className="text-center py-8">
                <div className="flex justify-center">
                  <div className="h-5 w-5 rounded-full border-2 border-[var(--brand)] border-t-transparent animate-spin" />
                </div>
              </td></tr>
            )}
            {!isLoading && users.map(user => (
              <tr key={user.id}>
                <td>
                  <div className="flex items-center gap-2">
                    <div className="h-7 w-7 rounded-full bg-[var(--brand-xs)] flex items-center justify-center text-xs font-semibold text-[var(--brand)] shrink-0">
                      {user.full_name[0]?.toUpperCase()}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-[var(--tx)]">{user.full_name}</p>
                      {user.is_super_admin && <span className="pill pill-err text-[9px]">Super Admin</span>}
                    </div>
                  </div>
                </td>
                <td className="text-xs text-[var(--tx-2)]">{user.email}</td>
                <td><span className="pill pill-neu text-xs">{user.role.replace('_', ' ')}</span></td>
                <td className="text-xs">
                  {user.org_unit ? (
                    <div>
                      <p className="font-medium text-[var(--tx)]">{user.org_unit.name}</p>
                      <p className="text-[var(--tx-3)]">{user.org_unit.code} · {user.org_unit.level}</p>
                    </div>
                  ) : <span className="text-[var(--tx-3)]">—</span>}
                </td>
                <td className="text-xs text-[var(--tx-2)]">{user.org_role?.name ?? '—'}</td>
                <td>
                  <span className={cn('pill', user.is_active ? 'pill-ok' : 'pill-err')}>
                    {user.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td className="text-right">
                  <button onClick={() => setEditing(user)} className="btn-ghost !py-1 !px-2 text-xs mr-1">Edit</button>
                  {user.is_active && (
                    <button onClick={() => { if (confirm(`Deactivate ${user.full_name}?`)) deactivateMut.mutate(user.id); }} className="btn-ghost !py-1 !px-2 text-xs text-[var(--err)]">
                      Deactivate
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {!isLoading && users.length === 0 && (
              <tr><td colSpan={7} className="text-center text-sm text-[var(--tx-3)] py-8">No users found</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center gap-2 justify-center">
          <button disabled={page <= 1} onClick={() => setPage(p => p - 1)} className="btn-ghost !py-1 !px-3 text-xs disabled:opacity-40">← Prev</button>
          <span className="text-xs text-[var(--tx-2)]">Page {page} of {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)} className="btn-ghost !py-1 !px-3 text-xs disabled:opacity-40">Next →</button>
        </div>
      )}

      {(creating || editing) && (
        <UserFormModal
          editing={editing}
          onClose={() => { setEditing(null); setCreating(false); }}
        />
      )}
    </div>
  );
}
