import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { motion } from 'framer-motion';
import { Plus, Building2, ChevronLeft, ChevronRight } from 'lucide-react';

import { api, extractError } from '@/lib/api';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Modal } from '@/components/Modal';
import { Skeleton } from '@/components/Skeleton';
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

export function BranchesPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(1);
  const size = 20;
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['branches', page, size],
    queryFn: () => listBranches(page, size),
  });

  const { register, handleSubmit, reset, formState: { isSubmitting } } = useForm<Form>({
    defaultValues: { code: '', name: '', region: '', address: '', ifsc: '', contact_email: '', contact_phone: '' },
  });

  const create = useMutation({
    mutationFn: async (input: Form) => (await api.post('/branches', input)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['branches'] });
      reset(); setOpen(false);
    },
    onError: (e) => setError(extractError(e).message),
  });

  return (
    <div className="flex flex-col gap-6">
      <motion.header
        initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}
        className="flex items-end justify-between gap-4 flex-wrap"
      >
        <div>
          <span className="label">Network</span>
          <h1 className="text-4xl font-semibold tracking-tight text-ink mt-1">Branches</h1>
          <p className="text-sm text-ink-muted mt-1">Manage the bank's branch directory.</p>
        </div>
        <button onClick={() => { setError(null); setOpen(true); }} className="btn-primary">
          <Plus className="h-4 w-4" /> New branch
        </button>
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
              </tr>
            </thead>
            <tbody>
              {isLoading && Array.from({ length: 6 }).map((_, i) => (
                <tr key={i}>{Array.from({ length: 6 }).map((__, j) => (
                  <td key={j}><Skeleton className="h-4 w-full max-w-[160px]" /></td>
                ))}</tr>
              ))}
              {!isLoading && data?.items.length === 0 && (
                <tr><td colSpan={6} className="py-12 text-center text-ink-muted">No branches yet.</td></tr>
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

      <Modal open={open} onClose={() => setOpen(false)} title="Create branch" description="Add a new branch to the directory.">
        {error && <Badge tone="danger" className="mb-4">{error}</Badge>}
        <form className="grid grid-cols-1 md:grid-cols-2 gap-4" onSubmit={handleSubmit((v) => create.mutate(v))}>
          <Field label="Code"          input={<input className="input" {...register('code')} />} />
          <Field label="Name"          input={<input className="input" {...register('name')} />} />
          <Field label="Region"        input={<input className="input" {...register('region')} />} />
          <Field label="IFSC"          input={<input className="input" {...register('ifsc')} />} />
          <Field label="Contact email" input={<input className="input" type="email" {...register('contact_email')} />} />
          <Field label="Contact phone" input={<input className="input" {...register('contact_phone')} />} />
          <div className="md:col-span-2">
            <Field label="Address" input={<input className="input" {...register('address')} />} />
          </div>
          <div className="md:col-span-2 flex justify-end gap-2 mt-2">
            <button type="button" className="btn-secondary" onClick={() => setOpen(false)}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={isSubmitting}>
              {isSubmitting ? 'Saving…' : 'Save branch'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

function Field({ label, input }: { label: string; input: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="label">{label}</span>
      {input}
    </label>
  );
}
