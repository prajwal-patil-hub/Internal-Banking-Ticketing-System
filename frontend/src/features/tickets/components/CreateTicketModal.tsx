import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

import { Modal } from '@/components/Modal';
import { Button } from '@/components/Button';
import { Badge } from '@/components/Badge';
import { createTicket, listBranches, listCategories, type CreateTicketInput } from '../api';
import { extractError } from '@/lib/api';
import { useAuth } from '@/store/auth';

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

const schema = z.object({
  branch_id: z.string().uuid(),
  category_id: z.string().uuid(),
  title: z.string().min(3).max(200),
  description: z.string().min(3).max(10_000),
  priority: z.enum(['critical', 'high', 'medium', 'low']),
});

type FormValues = z.infer<typeof schema>;

export function CreateTicketModal({ open, onClose, onCreated }: Props) {
  const [error, setError] = useState<string | null>(null);
  const user = useAuth((s) => s.user);

  const branches = useQuery({ queryKey: ['branches'], queryFn: () => listBranches(1, 100), enabled: open });
  const categories = useQuery({ queryKey: ['categories'], queryFn: () => listCategories(), enabled: open });

  const { register, handleSubmit, formState: { isSubmitting }, reset } = useForm<FormValues>({
    defaultValues: {
      branch_id: user?.branch_id ?? '',
      category_id: '',
      title: '',
      description: '',
      priority: 'medium',
    },
  });

  const submit = async (values: FormValues) => {
    setError(null);
    const parsed = schema.safeParse(values);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? 'Invalid input.');
      return;
    }
    try {
      await createTicket(parsed.data as CreateTicketInput);
      reset();
      onCreated();
    } catch (e) {
      setError(extractError(e).message);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Raise a ticket">
      {error && <Badge tone="danger" className="mb-3">{error}</Badge>}
      <form className="flex flex-col gap-3" onSubmit={handleSubmit(submit)}>
        <label className="text-sm">
          <span className="block mb-1 font-medium">Branch</span>
          <select className="input" {...register('branch_id')}>
            <option value="">Select branch…</option>
            {branches.data?.items.map((b) => (
              <option key={b.id} value={b.id}>{b.code} — {b.name}</option>
            ))}
          </select>
        </label>

        <label className="text-sm">
          <span className="block mb-1 font-medium">Category</span>
          <select className="input" {...register('category_id')}>
            <option value="">Select category…</option>
            {categories.data?.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </label>

        <label className="text-sm">
          <span className="block mb-1 font-medium">Priority</span>
          <select className="input" {...register('priority')}>
            <option value="critical">Critical (2h SLA)</option>
            <option value="high">High (6h SLA)</option>
            <option value="medium">Medium (24h SLA)</option>
            <option value="low">Low (72h SLA)</option>
          </select>
        </label>

        <label className="text-sm">
          <span className="block mb-1 font-medium">Title</span>
          <input className="input" placeholder="Short summary" {...register('title')} />
        </label>

        <label className="text-sm">
          <span className="block mb-1 font-medium">Description</span>
          <textarea
            className="input min-h-[120px]"
            placeholder="What's happening, when did it start, what have you tried?"
            {...register('description')}
          />
        </label>

        <div className="flex justify-end gap-2 mt-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Creating…' : 'Create ticket'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
