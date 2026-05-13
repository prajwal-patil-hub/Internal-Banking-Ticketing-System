import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { Lock } from 'lucide-react';

import { Modal } from '@/components/Modal';
import { Badge } from '@/components/Badge';
import { Skeleton } from '@/components/Skeleton';
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

  const { register, handleSubmit, formState: { isSubmitting }, reset, setValue } = useForm<FormValues>({
    defaultValues: {
      branch_id: user?.branch_id ?? '',
      category_id: '',
      title: '',
      description: '',
      priority: 'medium',
    },
  });

  // Branch users are pinned to their assigned branch (backend enforces this
  // too — a mismatch causes a 422). Other roles pick freely.
  const isLockedBranch = user?.role === 'branch_user' && !!user.branch_id;
  const userBranch = user?.branch_id
    ? branches.data?.items.find((b) => b.id === user.branch_id)
    : undefined;

  // Re-sync the form whenever the modal opens so a stale value from a prior
  // session can't slip through (e.g. user was reassigned to a new branch).
  useEffect(() => {
    if (open && user?.branch_id) {
      setValue('branch_id', user.branch_id);
    }
  }, [open, user?.branch_id, setValue]);

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
    <Modal
      open={open}
      onClose={onClose}
      title="Raise a ticket"
      description="Fill in the basics. The SLA clock starts the moment you submit."
    >
      {error && <Badge tone="danger" className="mb-4">{error}</Badge>}
      <form className="flex flex-col gap-4" onSubmit={handleSubmit(submit)}>
        <Field label="Branch">
          {isLockedBranch ? (
            <>
              {branches.isLoading ? (
                <Skeleton className="h-10 w-full" />
              ) : userBranch ? (
                <div
                  className="input flex items-center justify-between bg-canvas-raised/60 cursor-not-allowed select-none"
                  aria-readonly="true"
                  title="Branch users can only raise tickets for their own branch"
                >
                  <span className="text-ink">
                    <span className="font-mono text-2xs text-ink-muted mr-2">{userBranch.code}</span>
                    {userBranch.name}
                  </span>
                  <span className="inline-flex items-center gap-1 text-2xs uppercase tracking-wider text-ink-muted">
                    <Lock className="h-3 w-3" />
                    Your branch
                  </span>
                </div>
              ) : (
                <Badge tone="danger">Your branch is no longer active. Contact an admin.</Badge>
              )}
              <input type="hidden" {...register('branch_id')} />
            </>
          ) : (
            <select className="input" {...register('branch_id')}>
              <option value="">Select branch…</option>
              {branches.data?.items.map((b) => (
                <option key={b.id} value={b.id}>{b.code} — {b.name}</option>
              ))}
            </select>
          )}
        </Field>

        <Field label="Category">
          <select className="input" {...register('category_id')}>
            <option value="">Select category…</option>
            {categories.data?.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </Field>

        <Field label="Priority">
          <select className="input" {...register('priority')}>
            <option value="critical">Critical · 2h SLA</option>
            <option value="high">High · 6h SLA</option>
            <option value="medium">Medium · 24h SLA</option>
            <option value="low">Low · 72h SLA</option>
          </select>
        </Field>

        <Field label="Title">
          <input className="input" placeholder="Short summary" {...register('title')} />
        </Field>

        <Field label="Description">
          <textarea
            className="input min-h-[140px] resize-y"
            placeholder="What's happening, when did it start, what have you tried?"
            {...register('description')}
          />
        </Field>

        <div className="flex justify-end gap-2 mt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button
            type="submit"
            className="btn-primary"
            disabled={isSubmitting || (isLockedBranch && branches.isLoading)}
          >
            {isSubmitting ? 'Creating…' : 'Create ticket'}
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
