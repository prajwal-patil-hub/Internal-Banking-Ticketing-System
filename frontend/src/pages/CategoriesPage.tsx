import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { motion } from 'framer-motion';
import {
  Plus,
  Tag,
  Pencil,
  Trash2,
  RotateCcw,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

import { api, extractError } from '@/lib/api';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Modal } from '@/components/Modal';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Skeleton } from '@/components/Skeleton';
import { useToasts } from '@/components/Toast';

interface CategoryRow {
  id: string;
  name: string;
  description: string;
  default_priority: 'critical' | 'high' | 'medium' | 'low';
  is_active: boolean;
}

interface ListEnvelope {
  data: CategoryRow[];
  meta: { pagination: { page: number; size: number; total: number; pages: number } };
}

const schema = z.object({
  name: z.string().min(2).max(100),
  description: z.string().max(255).optional(),
  default_priority: z.enum(['critical', 'high', 'medium', 'low']),
});
type Form = z.infer<typeof schema>;

async function listCategories(page: number, size: number, includeInactive: boolean) {
  const params = new URLSearchParams({ page: String(page), size: String(size) });
  if (includeInactive) params.set('include_inactive', 'true');
  const { data } = await api.get<ListEnvelope>(`/categories?${params.toString()}`);
  return { items: data.data, meta: data.meta.pagination };
}

export function CategoriesPage() {
  const qc = useQueryClient();
  const toast = useToasts((s) => s.push);

  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<CategoryRow | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<CategoryRow | null>(null);
  const [page, setPage] = useState(1);
  const [includeInactive, setIncludeInactive] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['categories', page, includeInactive],
    queryFn: () => listCategories(page, 20, includeInactive),
  });

  const create = useMutation({
    mutationFn: async (input: Form) => (await api.post('/categories', input)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['categories'] });
      setCreateOpen(false);
      toast({ tone: 'success', message: 'Category created.' });
    },
    onError: (e) => toast({ tone: 'danger', message: extractError(e).message }),
  });

  const update = useMutation({
    mutationFn: async (vars: { id: string; body: Partial<Form> }) =>
      (await api.patch(`/categories/${vars.id}`, vars.body)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['categories'] });
      setEditTarget(null);
      toast({ tone: 'success', message: 'Category updated.' });
    },
    onError: (e) => toast({ tone: 'danger', message: extractError(e).message }),
  });

  const deactivate = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/categories/${id}`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['categories'] });
      toast({ tone: 'success', message: 'Category deactivated.' });
    },
    onError: (e) => toast({ tone: 'danger', message: extractError(e).message }),
  });

  const restore = useMutation({
    mutationFn: async (id: string) => (await api.post(`/categories/${id}/restore`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['categories'] });
      toast({ tone: 'success', message: 'Category restored.' });
    },
    onError: (e) => toast({ tone: 'danger', message: extractError(e).message }),
  });

  return (
    <div className="flex flex-col gap-6">
      <motion.header
        initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}
        className="flex items-end justify-between gap-4 flex-wrap"
      >
        <div>
          <span className="label">Taxonomy</span>
          <h1 className="text-4xl font-semibold tracking-tight text-ink mt-1">Categories</h1>
          <p className="text-sm text-ink-muted mt-1">Issue categories that branches choose when raising a ticket.</p>
          <div className="hairline-brass mt-3 max-w-xs" />
        </div>
        <div className="flex items-center gap-3">
          <label className="text-sm text-ink-muted flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(e) => { setPage(1); setIncludeInactive(e.target.checked); }}
              className="rounded"
            />
            Show inactive
          </label>
          <button onClick={() => setCreateOpen(true)} className="btn-primary">
            <Plus className="h-4 w-4" /> New category
          </button>
        </div>
      </motion.header>

      <Card padded={false} className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Description</th>
                <th>Default priority</th>
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
                <tr><td colSpan={5} className="py-12 text-center text-ink-muted">No categories yet.</td></tr>
              )}
              {data?.items.map((c) => (
                <tr key={c.id}>
                  <td className="font-medium text-ink">
                    <span className="inline-flex items-center gap-2">
                      <Tag className="h-4 w-4 text-brass-500" />
                      {c.name}
                    </span>
                  </td>
                  <td className="text-ink-muted max-w-[420px] truncate">{c.description || '—'}</td>
                  <td>
                    <Badge tone={c.default_priority === 'critical' ? 'danger' : c.default_priority === 'high' ? 'warning' : c.default_priority === 'medium' ? 'info' : 'neutral'}>
                      {c.default_priority}
                    </Badge>
                  </td>
                  <td>
                    <Badge tone={c.is_active ? 'success' : 'neutral'}>
                      {c.is_active ? 'active' : 'inactive'}
                    </Badge>
                  </td>
                  <td>
                    <div className="flex items-center justify-end gap-1">
                      <IconButton title="Edit" onClick={() => setEditTarget(c)}>
                        <Pencil className="h-3.5 w-3.5" />
                      </IconButton>
                      {c.is_active ? (
                        <IconButton title="Deactivate" tone="danger" onClick={() => setConfirmTarget(c)}>
                          <Trash2 className="h-3.5 w-3.5" />
                        </IconButton>
                      ) : (
                        <IconButton title="Restore" tone="success" onClick={() => restore.mutate(c.id)}>
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

      <CategoryFormModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Create category"
        description="Categories drive ticket routing and default priorities."
        submitting={create.isPending}
        onSubmit={(v) => create.mutate(v)}
      />
      <CategoryFormModal
        open={!!editTarget}
        onClose={() => setEditTarget(null)}
        title={editTarget ? `Edit ${editTarget.name}` : 'Edit category'}
        defaults={editTarget ?? undefined}
        submitting={update.isPending}
        onSubmit={(v) => editTarget && update.mutate({ id: editTarget.id, body: v })}
      />

      <ConfirmDialog
        open={!!confirmTarget}
        onClose={() => setConfirmTarget(null)}
        title={confirmTarget ? `Deactivate ${confirmTarget.name}?` : ''}
        description="Branches won't be able to pick this category for new tickets. Existing tickets keep their reference."
        confirmLabel="Deactivate"
        tone="danger"
        pending={deactivate.isPending}
        onConfirm={() => {
          if (confirmTarget) { deactivate.mutate(confirmTarget.id); setConfirmTarget(null); }
        }}
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

function CategoryFormModal({
  open, onClose, title, description, defaults, submitting, onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  defaults?: Partial<CategoryRow>;
  submitting: boolean;
  onSubmit: (v: Form) => void;
}) {
  const { register, handleSubmit, reset } = useForm<Form>({
    values: defaults
      ? {
          name: defaults.name ?? '',
          description: defaults.description ?? '',
          default_priority: (defaults.default_priority ?? 'medium') as Form['default_priority'],
        }
      : undefined,
    defaultValues: defaults ? undefined : { name: '', description: '', default_priority: 'medium' },
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
          <span className="label">Default priority</span>
          <select className="input" {...register('default_priority')}>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
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
