import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { motion } from 'framer-motion';
import {
  ChevronLeft,
  ChevronRight,
  Plus,
  Pencil,
  KeyRound,
  ShieldCheck,
  Shield,
  UserMinus,
  UserCheck,
  Copy as CopyIcon,
} from 'lucide-react';

import { api, extractError } from '@/lib/api';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Modal } from '@/components/Modal';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Skeleton } from '@/components/Skeleton';
import { useToasts } from '@/components/Toast';
import { listBranches } from '@/features/tickets/api';
import { useAuth } from '@/store/auth';
import type { AuthUser, Role } from '@/store/auth';

interface UserRow extends AuthUser {
  is_active: boolean;
}

interface ListEnvelope {
  success: boolean;
  data: UserRow[];
  meta: { pagination: { page: number; size: number; total: number; pages: number } };
}

const ROLE_TONE: Record<string, Parameters<typeof Badge>[0]['tone']> = {
  admin: 'danger',
  supervisor: 'warning',
  agent: 'info',
  auditor: 'assigned',
  branch_user: 'neutral',
};

const ROLES: Role[] = ['admin', 'supervisor', 'agent', 'auditor', 'branch_user'];

function userInitials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join('') || '?';
}

async function listUsers(page: number, size: number) {
  const { data } = await api.get<ListEnvelope>(`/users?page=${page}&size=${size}`);
  return { items: data.data, meta: data.meta.pagination };
}

interface CreateForm {
  email: string;
  full_name: string;
  role: Role;
  branch_id?: string;
  password?: string;
}

interface EditForm {
  full_name: string;
  role: Role;
  branch_id?: string;
  is_active: boolean;
}

const createSchema = z.object({
  email: z.string().min(3),
  full_name: z.string().min(2).max(150),
  role: z.enum(['admin', 'supervisor', 'agent', 'auditor', 'branch_user']),
  branch_id: z.string().uuid().optional().or(z.literal('').transform(() => undefined)),
  password: z.string().min(8).optional().or(z.literal('').transform(() => undefined)),
});

export function UsersPage() {
  const qc = useQueryClient();
  const { user: me } = useAuth();
  const toast = useToasts((s) => s.push);

  const [page, setPage] = useState(1);
  const size = 20;

  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<UserRow | null>(null);
  const [confirmAction, setConfirmAction] = useState<
    | { kind: 'deactivate' | 'reset'; user: UserRow }
    | null
  >(null);
  const [issued, setIssued] = useState<{ user: UserRow; password: string } | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['users', page],
    queryFn: () => listUsers(page, size),
  });

  const branches = useQuery({
    queryKey: ['branches'],
    queryFn: () => listBranches(1, 100),
    enabled: createOpen || !!editTarget,
  });

  const create = useMutation({
    mutationFn: async (input: CreateForm) => {
      const body = {
        email: input.email,
        full_name: input.full_name,
        role: input.role,
        branch_id: input.branch_id || undefined,
        password: input.password || undefined,
      };
      const { data } = await api.post('/users', body);
      return data.data as { user: UserRow; initial_password: string };
    },
    onSuccess: (resp) => {
      qc.invalidateQueries({ queryKey: ['users'] });
      setCreateOpen(false);
      setIssued({ user: resp.user, password: resp.initial_password });
    },
    onError: (e) => toast({ tone: 'danger', message: extractError(e).message }),
  });

  const update = useMutation({
    mutationFn: async (vars: { id: string; body: Partial<EditForm> }) => {
      const { data } = await api.patch(`/users/${vars.id}`, vars.body);
      return data.data as UserRow;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['users'] });
      setEditTarget(null);
      toast({ tone: 'success', message: 'User updated.' });
    },
    onError: (e) => toast({ tone: 'danger', message: extractError(e).message }),
  });

  const deactivate = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/users/${id}`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['users'] });
      toast({ tone: 'success', message: 'User deactivated.' });
    },
    onError: (e) => toast({ tone: 'danger', message: extractError(e).message }),
  });

  const restore = useMutation({
    mutationFn: async (id: string) => (await api.post(`/users/${id}/restore`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['users'] });
      toast({ tone: 'success', message: 'User restored.' });
    },
    onError: (e) => toast({ tone: 'danger', message: extractError(e).message }),
  });

  const resetPwd = useMutation({
    mutationFn: async (id: string) => {
      const { data } = await api.post(`/users/${id}/reset-password`);
      return data.data as { user: UserRow; new_password: string };
    },
    onSuccess: (resp) => {
      qc.invalidateQueries({ queryKey: ['users'] });
      setIssued({ user: resp.user, password: resp.new_password });
    },
    onError: (e) => toast({ tone: 'danger', message: extractError(e).message }),
  });

  return (
    <div className="flex flex-col gap-6">
      <motion.header
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="flex items-end justify-between gap-4 flex-wrap"
      >
        <div>
          <span className="label">Identity</span>
          <h1 className="text-4xl font-semibold tracking-tight text-ink mt-1">Users &amp; roles</h1>
          <p className="text-sm text-ink-muted mt-1">
            All accounts that can access the platform.
          </p>
        </div>
        <button onClick={() => setCreateOpen(true)} className="btn-primary">
          <Plus className="h-4 w-4" /> New user
        </button>
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
                <th>Status</th>
                <th>MFA</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {isLoading &&
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}>
                    {Array.from({ length: 7 }).map((__, j) => (
                      <td key={j}>
                        <Skeleton className="h-4 w-full max-w-[160px]" />
                      </td>
                    ))}
                  </tr>
                ))}
              {!isLoading && data?.items.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-ink-muted">
                    No users found.
                  </td>
                </tr>
              )}
              {data?.items.map((u) => (
                <tr key={u.id}>
                  <td>
                    <div className="flex items-center gap-3">
                      <span
                        className="h-9 w-9 rounded-pill grid place-items-center text-white font-semibold text-xs"
                        style={{
                          background: 'linear-gradient(135deg, #1F3A5F 0%, #182D49 60%, #0B1929 100%)',
                        }}
                      >
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
                    {u.branch_id ? (
                      <code className="text-2xs">{u.branch_id.slice(0, 8)}…</code>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>
                    <Badge tone={u.is_active ? 'success' : 'neutral'}>
                      {u.is_active ? 'active' : 'inactive'}
                    </Badge>
                  </td>
                  <td>
                    {u.mfa_enabled ? (
                      <span className="pill bg-success-soft text-success-deep">
                        <ShieldCheck className="h-3.5 w-3.5" /> on
                      </span>
                    ) : (
                      <span className="pill bg-slate-100 text-ink-muted">
                        <Shield className="h-3.5 w-3.5" /> off
                      </span>
                    )}
                  </td>
                  <td>
                    <div className="flex items-center justify-end gap-1">
                      <IconButton
                        title="Edit"
                        onClick={() => setEditTarget(u)}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </IconButton>
                      <IconButton
                        title="Reset password"
                        onClick={() => setConfirmAction({ kind: 'reset', user: u })}
                      >
                        <KeyRound className="h-3.5 w-3.5" />
                      </IconButton>
                      {u.is_active ? (
                        <IconButton
                          title="Deactivate"
                          tone="danger"
                          disabled={u.id === me?.id}
                          onClick={() => setConfirmAction({ kind: 'deactivate', user: u })}
                        >
                          <UserMinus className="h-3.5 w-3.5" />
                        </IconButton>
                      ) : (
                        <IconButton
                          title="Restore"
                          tone="success"
                          onClick={() => restore.mutate(u.id)}
                        >
                          <UserCheck className="h-3.5 w-3.5" />
                        </IconButton>
                      )}
                    </div>
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
              <button
                onClick={() => setPage((p) => p - 1)}
                disabled={page <= 1}
                className="btn-secondary"
              >
                <ChevronLeft className="h-4 w-4" /> Prev
              </button>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page >= (data.meta.pages || 1)}
                className="btn-secondary"
              >
                Next <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </Card>

      {/* Create */}
      <CreateUserModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        branches={branches.data?.items ?? []}
        submitting={create.isPending}
        onSubmit={(v) => create.mutate(v)}
      />

      {/* Edit */}
      <EditUserModal
        target={editTarget}
        onClose={() => setEditTarget(null)}
        branches={branches.data?.items ?? []}
        submitting={update.isPending}
        onSubmit={(body) => editTarget && update.mutate({ id: editTarget.id, body })}
      />

      <ConfirmDialog
        open={!!confirmAction}
        onClose={() => setConfirmAction(null)}
        title={
          confirmAction?.kind === 'reset'
            ? `Reset password for ${confirmAction.user.email}?`
            : confirmAction?.kind === 'deactivate'
              ? `Deactivate ${confirmAction.user.email}?`
              : ''
        }
        description={
          confirmAction?.kind === 'reset'
            ? "We'll generate a new one-time password and revoke all of this user's open sessions. You'll need to share the new password with them via a side channel."
            : "The user won't be able to sign in. Existing audit history is preserved. You can restore them later."
        }
        confirmLabel={confirmAction?.kind === 'reset' ? 'Reset password' : 'Deactivate user'}
        tone="danger"
        pending={resetPwd.isPending || deactivate.isPending}
        onConfirm={() => {
          if (!confirmAction) return;
          if (confirmAction.kind === 'reset') resetPwd.mutate(confirmAction.user.id);
          else deactivate.mutate(confirmAction.user.id);
          setConfirmAction(null);
        }}
      />

      {/* Issued password */}
      <Modal
        open={!!issued}
        onClose={() => setIssued(null)}
        title="Password issued"
        description="Save this password now — it won't be shown again. Share it with the user via a side channel."
      >
        {issued && (
          <div className="space-y-3">
            <div className="flex items-center gap-3 rounded-2xl bg-warning-soft p-4">
              <div className="text-warning-deep text-xs font-semibold uppercase tracking-wider">
                One-time password
              </div>
            </div>
            <div className="rounded-2xl bg-white/80 border border-white/60 px-4 py-3 flex items-center justify-between gap-3">
              <code className="text-ink font-mono text-sm break-all">{issued.password}</code>
              <button
                onClick={() => navigator.clipboard.writeText(issued.password)}
                className="btn-secondary"
                title="Copy"
              >
                <CopyIcon className="h-4 w-4" /> Copy
              </button>
            </div>
            <p className="text-xs text-ink-muted">
              For: <strong>{issued.user.email}</strong>. They should change this on first sign-in
              from their profile.
            </p>
            <div className="flex justify-end">
              <button onClick={() => setIssued(null)} className="btn-primary">Done</button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}

/* ──────────────────────────── Sub-components ──────────────────────────── */

function IconButton({
  children,
  onClick,
  title,
  tone = 'neutral',
  disabled,
}: {
  children: React.ReactNode;
  onClick: () => void;
  title: string;
  tone?: 'neutral' | 'danger' | 'success';
  disabled?: boolean;
}) {
  const toneClass = {
    neutral: 'text-ink-muted hover:text-ink hover:bg-white/70',
    danger: 'text-danger-deep hover:text-danger-deep hover:bg-danger-soft',
    success: 'text-success-deep hover:text-success-deep hover:bg-success-soft',
  }[tone];
  return (
    <button
      onClick={onClick}
      title={title}
      aria-label={title}
      disabled={disabled}
      className={`h-8 w-8 rounded-pill grid place-items-center transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${toneClass}`}
    >
      {children}
    </button>
  );
}

function CreateUserModal({
  open,
  onClose,
  branches,
  submitting,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  branches: { id: string; code: string; name: string }[];
  submitting: boolean;
  onSubmit: (v: CreateForm) => void;
}) {
  const { register, handleSubmit, reset, formState: { errors } } = useForm<CreateForm>({
    defaultValues: { email: '', full_name: '', role: 'agent', branch_id: '', password: '' },
  });

  return (
    <Modal
      open={open}
      onClose={() => { reset(); onClose(); }}
      title="Add user"
      description="Create a new account. Leave the password blank to auto-generate one."
    >
      <form
        className="grid grid-cols-1 md:grid-cols-2 gap-4"
        onSubmit={handleSubmit((v) => {
          const parsed = createSchema.safeParse(v);
          if (!parsed.success) return;
          onSubmit(parsed.data);
        })}
      >
        <Field label="Work email" error={errors.email?.message}>
          <input className="input" type="email" placeholder="user@successbank.local" {...register('email')} />
        </Field>
        <Field label="Full name" error={errors.full_name?.message}>
          <input className="input" placeholder="Jane Doe" {...register('full_name')} />
        </Field>
        <Field label="Role" error={errors.role?.message}>
          <select className="input" {...register('role')}>
            {ROLES.map((r) => (
              <option key={r} value={r}>{r.replace('_', ' ')}</option>
            ))}
          </select>
        </Field>
        <Field label="Branch (optional)">
          <select className="input" {...register('branch_id')}>
            <option value="">— none —</option>
            {branches.map((b) => (
              <option key={b.id} value={b.id}>{b.code} — {b.name}</option>
            ))}
          </select>
        </Field>
        <div className="md:col-span-2">
          <Field
            label="Initial password (leave blank to auto-generate)"
            error={errors.password?.message}
          >
            <input className="input" type="text" placeholder="auto-generate" {...register('password')} />
          </Field>
        </div>
        <div className="md:col-span-2 flex justify-end gap-2 mt-2">
          <button type="button" className="btn-secondary" onClick={() => { reset(); onClose(); }}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? 'Creating…' : 'Create user'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function EditUserModal({
  target,
  onClose,
  branches,
  submitting,
  onSubmit,
}: {
  target: UserRow | null;
  onClose: () => void;
  branches: { id: string; code: string; name: string }[];
  submitting: boolean;
  onSubmit: (v: Partial<EditForm>) => void;
}) {
  const { register, handleSubmit, reset } = useForm<EditForm>({
    values: target
      ? {
          full_name: target.full_name,
          role: target.role,
          branch_id: target.branch_id ?? '',
          is_active: target.is_active,
        }
      : undefined,
  });

  if (!target) return null;

  return (
    <Modal
      open={!!target}
      onClose={() => { reset(); onClose(); }}
      title={`Edit ${target.email}`}
      description="Change the user's name, role, or branch. Email is immutable."
    >
      <form
        className="grid grid-cols-1 md:grid-cols-2 gap-4"
        onSubmit={handleSubmit((v) => {
          onSubmit({
            full_name: v.full_name,
            role: v.role,
            branch_id: v.branch_id || undefined,
            is_active: v.is_active,
          });
        })}
      >
        <Field label="Full name">
          <input className="input" {...register('full_name')} />
        </Field>
        <Field label="Role">
          <select className="input" {...register('role')}>
            {ROLES.map((r) => (
              <option key={r} value={r}>{r.replace('_', ' ')}</option>
            ))}
          </select>
        </Field>
        <Field label="Branch">
          <select className="input" {...register('branch_id')}>
            <option value="">— none —</option>
            {branches.map((b) => (
              <option key={b.id} value={b.id}>{b.code} — {b.name}</option>
            ))}
          </select>
        </Field>
        <Field label="Status">
          <label className="text-sm flex items-center gap-2 mt-3 cursor-pointer">
            <input type="checkbox" className="rounded" {...register('is_active')} />
            Active
          </label>
        </Field>
        <div className="md:col-span-2 flex justify-end gap-2 mt-2">
          <button type="button" className="btn-secondary" onClick={() => { reset(); onClose(); }}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="label">{label}</span>
      {children}
      {error && <span className="text-2xs text-danger-deep">{error}</span>}
    </label>
  );
}
