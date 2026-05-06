import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

import { api, extractError } from '@/lib/api';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Badge } from '@/components/Badge';
import { Modal } from '@/components/Modal';
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
      reset();
      setOpen(false);
    },
    onError: (e) => setError(extractError(e).message),
  });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Branches</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Manage branch directory.</p>
        </div>
        <Button onClick={() => { setError(null); setOpen(true); }}>+ New branch</Button>
      </div>

      <Card padded={false} className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-surface-muted dark:bg-slate-800/50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Code</th>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Region</th>
              <th className="px-4 py-3">IFSC</th>
              <th className="px-4 py-3">Active</th>
              <th className="px-4 py-3">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {isLoading && <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-400">Loading…</td></tr>}
            {!isLoading && data?.items.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-400">No branches yet.</td></tr>
            )}
            {data?.items.map((b) => (
              <tr key={b.id} className="hover:bg-surface-muted/60 dark:hover:bg-slate-800/40">
                <td className="px-4 py-3 font-mono text-xs">{b.code}</td>
                <td className="px-4 py-3">{b.name}</td>
                <td className="px-4 py-3 text-slate-500">{b.region || '—'}</td>
                <td className="px-4 py-3 text-slate-500">{b.ifsc || '—'}</td>
                <td className="px-4 py-3">
                  <Badge tone={b.is_active ? 'success' : 'neutral'}>
                    {b.is_active ? 'active' : 'inactive'}
                  </Badge>
                </td>
                <td className="px-4 py-3 text-slate-500">{formatDateTime(b.created_at)}</td>
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

      <Modal open={open} onClose={() => setOpen(false)} title="Create branch">
        {error && <Badge tone="danger" className="mb-3">{error}</Badge>}
        <form
          className="grid grid-cols-1 md:grid-cols-2 gap-3"
          onSubmit={handleSubmit((v) => create.mutate(v))}
        >
          <Input label="Code"          {...register('code')} />
          <Input label="Name"          {...register('name')} />
          <Input label="Region"        {...register('region')} />
          <Input label="IFSC"          {...register('ifsc')} />
          <Input label="Contact email" type="email" {...register('contact_email')} />
          <Input label="Contact phone" {...register('contact_phone')} />
          <label className="text-sm md:col-span-2">
            <span className="block mb-1 font-medium">Address</span>
            <input className="input" {...register('address')} />
          </label>
          <div className="md:col-span-2 flex justify-end gap-2 mt-2">
            <Button variant="ghost" type="button" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={isSubmitting}>{isSubmitting ? 'Saving…' : 'Save branch'}</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

const Input = ({ label, ...rest }: React.InputHTMLAttributes<HTMLInputElement> & { label: string }) => (
  <label className="text-sm">
    <span className="block mb-1 font-medium">{label}</span>
    <input className="input" {...rest} />
  </label>
);
