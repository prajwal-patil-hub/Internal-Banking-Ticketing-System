import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { motion } from 'framer-motion';
import {
  Plus,
  Users as UsersIcon,
  Pencil,
  Trash2,
  RotateCcw,
  ChevronLeft,
  ChevronRight,
  UserPlus,
  UserMinus,
} from 'lucide-react';

import { api, extractError } from '@/lib/api';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Modal } from '@/components/Modal';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Skeleton } from '@/components/Skeleton';
import { useToasts } from '@/components/Toast';

interface TeamRow {
  id: string;
  name: string;
  description: string;
  supervisor_id: string | null;
  is_active: boolean;
}

interface UserRow {
  id: string;
  email: string;
  full_name: string;
  role: string;
}

interface MemberRow {
  user_id: string;
  email: string;
  full_name: string;
  role: string;
}

interface ListEnvelope<T> {
  data: T[];
  meta: { pagination: { page: number; size: number; total: number; pages: number } };
}

const schema = z.object({
  name: z.string().min(2).max(100),
  description: z.string().max(255).optional(),
  supervisor_id: z.string().uuid().optional().or(z.literal('').transform(() => undefined)),
});
type Form = z.infer<typeof schema>;

async function listTeams(page: number, size: number) {
  const { data } = await api.get<ListEnvelope<TeamRow>>(`/teams?page=${page}&size=${size}`);
  return { items: data.data, meta: data.meta.pagination };
}
async function listUsers() {
  const { data } = await api.get<ListEnvelope<UserRow>>('/users?page=1&size=100');
  return data.data;
}
async function listMembers(teamId: string) {
  const { data } = await api.get<{ data: MemberRow[] }>(`/teams/${teamId}/members`);
  return data.data;
}

function userInitials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join('') || '?';
}

export function TeamsPage() {
  const qc = useQueryClient();
  const toast = useToasts((s) => s.push);

  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<TeamRow | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<TeamRow | null>(null);
  const [membersOf, setMembersOf] = useState<TeamRow | null>(null);
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ['teams', page],
    queryFn: () => listTeams(page, 20),
  });

  const users = useQuery({
    queryKey: ['users-all'],
    queryFn: listUsers,
    enabled: createOpen || !!editTarget || !!membersOf,
  });

  const create = useMutation({
    mutationFn: async (input: Form) => (await api.post('/teams', input)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['teams'] });
      setCreateOpen(false);
      toast({ tone: 'success', message: 'Team created.' });
    },
    onError: (e) => toast({ tone: 'danger', message: extractError(e).message }),
  });

  const update = useMutation({
    mutationFn: async (vars: { id: string; body: Partial<Form> }) =>
      (await api.patch(`/teams/${vars.id}`, vars.body)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['teams'] });
      setEditTarget(null);
      toast({ tone: 'success', message: 'Team updated.' });
    },
    onError: (e) => toast({ tone: 'danger', message: extractError(e).message }),
  });

  const deactivate = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/teams/${id}`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['teams'] });
      toast({ tone: 'success', message: 'Team deactivated.' });
    },
    onError: (e) => toast({ tone: 'danger', message: extractError(e).message }),
  });
  const restore = useMutation({
    mutationFn: async (id: string) => (await api.post(`/teams/${id}/restore`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['teams'] });
      toast({ tone: 'success', message: 'Team restored.' });
    },
    onError: (e) => toast({ tone: 'danger', message: extractError(e).message }),
  });

  const supervisors = (users.data ?? []).filter((u) => u.role === 'supervisor' || u.role === 'admin');

  return (
    <div className="flex flex-col gap-6">
      <motion.header
        initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}
        className="flex items-end justify-between gap-4 flex-wrap"
      >
        <div>
          <span className="label">Support</span>
          <h1 className="text-4xl font-semibold tracking-tight text-ink mt-1">Teams</h1>
          <p className="text-sm text-ink-muted mt-1">Groups of agents that admins can assign tickets to.</p>
          <div className="hairline-brass mt-3 max-w-xs" />
        </div>
        <button onClick={() => setCreateOpen(true)} className="btn-primary">
          <Plus className="h-4 w-4" /> New team
        </button>
      </motion.header>

      <Card padded={false} className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Description</th>
                <th>Supervisor</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {isLoading && Array.from({ length: 5 }).map((_, i) => (
                <tr key={i}>{Array.from({ length: 5 }).map((__, j) => (
                  <td key={j}><Skeleton className="h-4 w-full max-w-[160px]" /></td>
                ))}</tr>
              ))}
              {!isLoading && data?.items.length === 0 && (
                <tr><td colSpan={5} className="py-12 text-center text-ink-muted">No teams yet.</td></tr>
              )}
              {data?.items.map((t) => {
                const sup = users.data?.find((u) => u.id === t.supervisor_id);
                return (
                  <tr key={t.id}>
                    <td className="font-medium text-ink">
                      <button onClick={() => setMembersOf(t)} className="inline-flex items-center gap-2 hover:underline">
                        <UsersIcon className="h-4 w-4 text-brass-500" />
                        {t.name}
                      </button>
                    </td>
                    <td className="text-ink-muted max-w-[420px] truncate">{t.description || '—'}</td>
                    <td className="text-ink-muted">{sup ? sup.full_name : '—'}</td>
                    <td>
                      <Badge tone={t.is_active ? 'success' : 'neutral'}>
                        {t.is_active ? 'active' : 'inactive'}
                      </Badge>
                    </td>
                    <td>
                      <div className="flex items-center justify-end gap-1">
                        <IconButton title="Members" onClick={() => setMembersOf(t)}>
                          <UsersIcon className="h-3.5 w-3.5" />
                        </IconButton>
                        <IconButton title="Edit" onClick={() => setEditTarget(t)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </IconButton>
                        {t.is_active ? (
                          <IconButton title="Deactivate" tone="danger" onClick={() => setConfirmTarget(t)}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </IconButton>
                        ) : (
                          <IconButton title="Restore" tone="success" onClick={() => restore.mutate(t.id)}>
                            <RotateCcw className="h-3.5 w-3.5" />
                          </IconButton>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
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

      <TeamFormModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Create team"
        description="Pick a supervisor and add members after."
        supervisors={supervisors}
        submitting={create.isPending}
        onSubmit={(v) => create.mutate(v)}
      />
      <TeamFormModal
        open={!!editTarget}
        onClose={() => setEditTarget(null)}
        title={editTarget ? `Edit ${editTarget.name}` : 'Edit team'}
        supervisors={supervisors}
        defaults={editTarget ?? undefined}
        submitting={update.isPending}
        onSubmit={(v) => editTarget && update.mutate({ id: editTarget.id, body: v })}
      />

      <ConfirmDialog
        open={!!confirmTarget}
        onClose={() => setConfirmTarget(null)}
        title={confirmTarget ? `Deactivate ${confirmTarget.name}?` : ''}
        description="Tickets keep their assignment reference. The team disappears from active selectors until you restore it."
        confirmLabel="Deactivate"
        tone="danger"
        pending={deactivate.isPending}
        onConfirm={() => {
          if (confirmTarget) { deactivate.mutate(confirmTarget.id); setConfirmTarget(null); }
        }}
      />

      <MembersModal
        team={membersOf}
        onClose={() => setMembersOf(null)}
        users={users.data ?? []}
      />
    </div>
  );
}

function IconButton({
  children, onClick, title, tone = 'neutral',
}: {
  children: React.ReactNode; onClick: () => void; title: string;
  tone?: 'neutral' | 'danger' | 'success';
}) {
  const toneClass = {
    neutral: 'text-ink-muted hover:text-ink hover:bg-white/70',
    danger: 'text-danger-deep hover:bg-danger-soft',
    success: 'text-success-deep hover:bg-success-soft',
  }[tone];
  return (
    <button onClick={onClick} title={title} aria-label={title}
      className={`h-8 w-8 rounded-pill grid place-items-center transition-colors ${toneClass}`}>
      {children}
    </button>
  );
}

function TeamFormModal({
  open, onClose, title, description, defaults, supervisors, submitting, onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  defaults?: Partial<TeamRow>;
  supervisors: UserRow[];
  submitting: boolean;
  onSubmit: (v: Form) => void;
}) {
  const { register, handleSubmit, reset } = useForm<Form>({
    values: defaults
      ? {
          name: defaults.name ?? '',
          description: defaults.description ?? '',
          supervisor_id: (defaults.supervisor_id ?? '') as Form['supervisor_id'],
        }
      : undefined,
    defaultValues: defaults ? undefined : { name: '', description: '', supervisor_id: '' as Form['supervisor_id'] },
  });
  return (
    <Modal open={open} onClose={() => { reset(); onClose(); }} title={title} description={description}>
      <form
        className="flex flex-col gap-4"
        onSubmit={handleSubmit((v) => {
          const parsed = schema.safeParse(v);
          if (!parsed.success) return;
          onSubmit(parsed.data);
        })}
      >
        <label className="flex flex-col gap-1.5">
          <span className="label">Name</span>
          <input className="input" {...register('name')} />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="label">Description</span>
          <input className="input" {...register('description')} />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="label">Supervisor</span>
          <select className="input" {...register('supervisor_id')}>
            <option value="">— none —</option>
            {supervisors.map((u) => (
              <option key={u.id} value={u.id}>{u.full_name} ({u.role})</option>
            ))}
          </select>
        </label>
        <div className="flex justify-end gap-2 mt-2">
          <button type="button" className="btn-secondary" onClick={() => { reset(); onClose(); }}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? 'Saving…' : 'Save'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function MembersModal({
  team, onClose, users,
}: {
  team: TeamRow | null;
  onClose: () => void;
  users: UserRow[];
}) {
  const qc = useQueryClient();
  const toast = useToasts((s) => s.push);
  const [pickUserId, setPickUserId] = useState<string>('');

  const members = useQuery({
    queryKey: ['team-members', team?.id],
    queryFn: () => listMembers(team!.id),
    enabled: !!team,
  });

  const add = useMutation({
    mutationFn: async (userId: string) =>
      (await api.post(`/teams/${team!.id}/members/${userId}`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['team-members', team!.id] });
      setPickUserId('');
      toast({ tone: 'success', message: 'Member added.' });
    },
    onError: (e) => toast({ tone: 'danger', message: extractError(e).message }),
  });
  const remove = useMutation({
    mutationFn: async (userId: string) =>
      (await api.delete(`/teams/${team!.id}/members/${userId}`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['team-members', team!.id] });
      toast({ tone: 'success', message: 'Member removed.' });
    },
    onError: (e) => toast({ tone: 'danger', message: extractError(e).message }),
  });

  if (!team) return null;
  const memberIds = new Set((members.data ?? []).map((m) => m.user_id));
  const addable = users.filter((u) => !memberIds.has(u.id) && ['agent', 'supervisor'].includes(u.role));

  return (
    <Modal
      open={!!team}
      onClose={onClose}
      title={`${team.name} · members`}
      description="Agents and supervisors who handle tickets routed to this team."
    >
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
          <div className="flex-1">
            <span className="label">Add member</span>
            <select
              className="input mt-1.5"
              value={pickUserId}
              onChange={(e) => setPickUserId(e.target.value)}
            >
              <option value="">Pick a user…</option>
              {addable.map((u) => (
                <option key={u.id} value={u.id}>{u.full_name} ({u.role})</option>
              ))}
            </select>
          </div>
          <button
            onClick={() => pickUserId && add.mutate(pickUserId)}
            className="btn-primary"
            disabled={!pickUserId || add.isPending}
          >
            <UserPlus className="h-4 w-4" /> Add
          </button>
        </div>

        <div className="hairline" />

        <div className="space-y-2 max-h-[40vh] overflow-auto">
          {members.isLoading && Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" rounded="2xl" />
          ))}
          {!members.isLoading && (members.data?.length ?? 0) === 0 && (
            <p className="text-sm text-ink-muted py-3">No members yet.</p>
          )}
          {members.data?.map((m) => (
            <div key={m.user_id} className="flex items-center gap-3 rounded-2xl bg-white/60 border border-white/50 p-3">
              <span
                className="h-9 w-9 rounded-pill grid place-items-center text-white font-semibold text-xs"
                style={{ background: 'linear-gradient(135deg, #1F3A5F 0%, #182D49 60%, #0B1929 100%)' }}
              >
                {userInitials(m.full_name)}
              </span>
              <div className="min-w-0 flex-1">
                <div className="font-medium text-sm text-ink truncate">{m.full_name}</div>
                <div className="text-2xs text-ink-muted truncate">{m.email} · {m.role}</div>
              </div>
              <button
                onClick={() => remove.mutate(m.user_id)}
                className="btn-ghost px-2 py-1.5"
                title="Remove"
              >
                <UserMinus className="h-4 w-4 text-danger-deep" />
              </button>
            </div>
          ))}
        </div>
      </div>
    </Modal>
  );
}
