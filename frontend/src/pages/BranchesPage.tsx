import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { motion } from 'framer-motion';
import {
  Plus,
  Building2,
  ChevronLeft,
  ChevronRight,
  Pencil,
  Trash2,
  RotateCcw,
} from 'lucide-react';

import { api, extractError } from '@/lib/api';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Modal } from '@/components/Modal';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Skeleton } from '@/components/Skeleton';
import { useToasts } from '@/components/Toast';
import { listBranches } from '@/features/tickets/api';
import { formatDateTime } from '@/lib/format';

const schema = z.object({
  code: z.string().min(2).max(20),
  name: z.string().min(2).max(150),
  region: z.string().max(100).optional(),
  address: z.string().max(255).optional(),
  ifsc: z.string().max(20).optional(),
  contact_email: z.string().email().or(z.literal('')).optional(),
  contact_phone: z.string().max(40).optional(),
});
type Form = z.infer<typeof schema>;

interface BranchRow {
  id: string;
  code: string;
  name: string;
  region: string;
  address: string;
  ifsc: string;
  contact_email: string;
  contact_phone: string;
  is_active: boolean;
  created_at: string;
}

export function BranchesPage() {
  const qc = useQueryClient();
  const toast = useToasts((s) => s.push);

  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<BranchRow | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<BranchRow | null>(null);
  const [page, setPage] = useState(1);
  const [includeInactive, setIncludeInactive] = useState(false);
  const size = 20;

  const { data, isLoading } = useQuery({
    queryKey: ['branches', page, size, includeInactive],
    queryFn: () => listBranches(page, size, includeInactive),
  });

  const create = useMutation({
    mutationFn: async (input: Form) => (await api.post('/branches', input)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['branches'] });
      setCreateOpen(false);
      toast({ tone: 'success', message: 'Branch created.' });
    },
    onError: (e) => toast({ tone: 'danger', message: extractError(e).message }),
  });

  const update = useMutation({
    mutationFn: async (vars: { id: string; body: Partial<Form> }) =>
      (await api.patch(`/branches/${vars.id}`, vars.body)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['branches'] });
      setEditTarget(null);
      toast({ tone: 'success', message: 'Branch updated.' });
    },
    onError: (e) => toast({ tone: 'danger', message: extractError(e).message }),
  });

  const deactivate = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/branches/${id}`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['branches'] });
      toast({ tone: 'success', message: 'Branch deactivated.' });
    },
    onError: (e) => toast({ tone: 'danger', message: extractError(e).message }),
  });

  const restore = useMutation({
    mutationFn: async (id: string) => (await api.post(`/branches/${id}/restore`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['branches'] });
      toast({ tone: 'success', message: 'Branch restored.' });
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
          <span className="label">Network</span>
          <h1 className="text-4xl font-semibold tracking-tight text-ink mt-1">Branches</h1>
          <p className="text-sm text-ink-muted mt-1">Manage the bank's branch directory.</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="text-sm text-ink-muted flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(e) => {
                setPage(1);
                setIncludeInactive(e.target.checked);
              }}
              className="rounded"
            />
            Show inactive
          </label>
          <button onClick={() => setCreateOpen(true)} className="btn-primary">
            <Plus className="h-4 w-4" /> New branch
          </button>
        </div>
      </motion.header>

      <Card padded={false} className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Name</th>
                <th>Region</th>
                <th>IFSC</th>
                <th>Status</th>
                <th>Created</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {isLoading &&
                Array.from({ length: 6 }).map((_, i) => (
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
                    No branches yet.
                  </td>
                </tr>
              )}
              {data?.items.map((b) => (
                <tr key={b.id}>
                  <td className="font-mono text-2xs">{b.code}</td>
                  <td className="font-medium text-ink">
                    <span className="inline-flex items-center gap-2">
                      <Building2 className="h-4 w-4 text-brand-600" />
                      {b.name}
                    </span>
                  </td>
                  <td className="text-ink-muted">{b.region || '—'}</td>
                  <td className="text-ink-muted">{b.ifsc || '—'}</td>
                  <td>
                    <Badge tone={b.is_active ? 'success' : 'neutral'}>
                      {b.is_active ? 'active' : 'inactive'}
                    </Badge>
                  </td>
                  <td className="text-ink-muted whitespace-nowrap">{formatDateTime(b.created_at)}</td>
                  <td>
                    <div className="flex items-center justify-end gap-1">
                      <IconButton title="Edit" onClick={() => setEditTarget(b)}>
                        <Pencil className="h-3.5 w-3.5" />
                      </IconButton>
                      {b.is_active ? (
                        <IconButton
                          title="Deactivate"
                          tone="danger"
                          onClick={() => setConfirmTarget(b)}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </IconButton>
                      ) : (
                        <IconButton title="Restore" tone="success" onClick={() => restore.mutate(b.id)}>
                          <RotateCcw className="h-3.5 w-3.5" />
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

      <BranchFormModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Create branch"
        description="Add a new branch to the directory."
        submitting={create.isPending}
        onSubmit={(v) => create.mutate(v)}
      />

      <BranchFormModal
        open={!!editTarget}
        onClose={() => setEditTarget(null)}
        title={editTarget ? `Edit ${editTarget.code} — ${editTarget.name}` : 'Edit branch'}
        description="Update branch details. Code can't be changed once created."
        defaults={editTarget ?? undefined}
        submitting={update.isPending}
        onSubmit={(v) => editTarget && update.mutate({ id: editTarget.id, body: { ...v, code: undefined } })}
        codeReadOnly
      />

      <ConfirmDialog
        open={!!confirmTarget}
        onClose={() => setConfirmTarget(null)}
        title={confirmTarget ? `Deactivate ${confirmTarget.code} — ${confirmTarget.name}?` : ''}
        description="Branches with active tickets keep their references intact; the branch just disappears from the active directory until you restore it."
        confirmLabel="Deactivate branch"
        tone="danger"
        pending={deactivate.isPending}
        onConfirm={() => {
          if (confirmTarget) {
            deactivate.mutate(confirmTarget.id);
            setConfirmTarget(null);
          }
        }}
      />
    </div>
  );
}

function IconButton({
  children,
  onClick,
  title,
  tone = 'neutral',
}: {
  children: React.ReactNode;
  onClick: () => void;
  title: string;
  tone?: 'neutral' | 'danger' | 'success';
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
      className={`h-8 w-8 rounded-pill grid place-items-center transition-colors ${toneClass}`}
    >
      {children}
    </button>
  );
}

function BranchFormModal({
  open,
  onClose,
  title,
  description,
  defaults,
  codeReadOnly,
  submitting,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  defaults?: Partial<Form>;
  codeReadOnly?: boolean;
  submitting: boolean;
  onSubmit: (v: Form) => void;
}) {
  const { register, handleSubmit, reset } = useForm<Form>({
    values: defaults
      ? {
          code: defaults.code ?? '',
          name: defaults.name ?? '',
          region: defaults.region ?? '',
          address: defaults.address ?? '',
          ifsc: defaults.ifsc ?? '',
          contact_email: defaults.contact_email ?? '',
          contact_phone: defaults.contact_phone ?? '',
        }
      : undefined,
    defaultValues: defaults
      ? undefined
      : { code: '', name: '', region: '', address: '', ifsc: '', contact_email: '', contact_phone: '' },
  });

  return (
    <Modal
      open={open}
      onClose={() => { reset(); onClose(); }}
      title={title}
      description={description}
    >
      <form
        className="grid grid-cols-1 md:grid-cols-2 gap-4"
        onSubmit={handleSubmit((v) => onSubmit(v))}
      >
        <Field label="Code">
          <input className="input" disabled={codeReadOnly} {...register('code')} />
        </Field>
        <Field label="Name">
          <input className="input" {...register('name')} />
        </Field>
        <Field label="Region">
          <input className="input" {...register('region')} />
        </Field>
        <Field label="IFSC">
          <input className="input" {...register('ifsc')} />
        </Field>
        <Field label="Contact email">
          <input className="input" type="email" {...register('contact_email')} />
        </Field>
        <Field label="Contact phone">
          <input className="input" {...register('contact_phone')} />
        </Field>
        <div className="md:col-span-2">
          <Field label="Address">
            <input className="input" {...register('address')} />
          </Field>
        </div>
        <div className="md:col-span-2 flex justify-end gap-2 mt-2">
          <button type="button" className="btn-secondary" onClick={() => { reset(); onClose(); }}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? 'Saving…' : 'Save'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="label">{label}</span>
      {children}
    </label>
  );
}
