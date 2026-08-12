import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Button } from '@/components/Button';
import { FileStager } from '@/components/FileStager';
import { cn } from '@/lib/cn';
import { createTicket, getCategories, uploadAttachments } from '@/features/tickets/api';
import { categorizeText } from '@/features/ai/api';
import type { TicketPriority, Category } from '@/features/tickets/api';
import type { CategorizeResponse } from '@/features/ai/api';

// ── Schema ───────────────────────────────────────────────────────────────────

const schema = z.object({
  title:       z.string().min(5, 'Minimum 5 characters').max(200, 'Title too long'),
  description: z.string().min(20, 'Minimum 20 characters').max(10000, 'Description too long'),
  priority:    z.enum(['critical', 'high', 'medium', 'low'] as const),
  category_id: z.string().optional(),
  tags:        z.array(z.string()),
});

type FormValues = z.infer<typeof schema>;

// ── Tag input ─────────────────────────────────────────────────────────────────

function TagInput({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const [tagInput, setTagInput] = useState('');

  const addTag = (tag: string) => {
    const t = tag.trim().toLowerCase().replace(/\s+/g, '-');
    if (t && !value.includes(t) && value.length < 10) onChange([...value, t]);
    setTagInput('');
  };

  return (
    <div className="flex flex-col gap-2">
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {value.map((tag) => (
            <span key={tag} className="pill bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300 gap-1">
              {tag}
              <button type="button" onClick={() => onChange(value.filter((t) => t !== tag))} className="hover:text-red-600 dark:hover:text-red-400 transition-colors">
                <svg className="h-2.5 w-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="flex gap-2">
        <input
          className="input flex-1 h-8 text-xs"
          placeholder="Type a tag and press Enter…"
          value={tagInput}
          onChange={(e) => setTagInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') { e.preventDefault(); addTag(tagInput); }
            if (e.key === 'Backspace' && !tagInput && value.length > 0) onChange(value.slice(0, -1));
          }}
        />
        <button type="button" disabled={!tagInput.trim()} onClick={() => addTag(tagInput)}
          className="btn-outline h-8 text-xs disabled:opacity-40">
          Add
        </button>
      </div>
      <p className="text-[10px] text-[var(--tx-3)]">Press Enter to add · max 10 tags</p>
    </div>
  );
}

// ── AI suggestion panel ───────────────────────────────────────────────────────

interface AISuggestionProps {
  suggestion: CategorizeResponse;
  categories: Category[];
  onAccept: (priority: TicketPriority, categoryId?: string) => void;
  onDismiss: () => void;
}

function AISuggestion({ suggestion, categories, onAccept, onDismiss }: AISuggestionProps) {
  const matched = categories.find(
    (c) => c.code === suggestion.category || c.name.toLowerCase() === suggestion.category.toLowerCase(),
  );

  return (
    <div className="card-sm !p-3.5" style={{ borderLeft: '2px solid var(--brand-sm)' }}>
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <div className="h-6 w-6 rounded-lg bg-[var(--brand-xs)] flex items-center justify-center">
            <svg className="h-3.5 w-3.5 text-[var(--brand)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a10 10 0 0 1 0 20M12 2a10 10 0 0 0 0 20M12 8v4M12 16h.01" />
            </svg>
          </div>
          <span className="text-sm font-semibold text-[var(--brand-dk)] dark:text-[var(--brand-lt)]">AI Suggestion</span>
          <span className={cn('pill',
            suggestion.confidence >= 0.8 ? 'pill-ok' :
            suggestion.confidence >= 0.5 ? 'pill-warn' :
            'pill-err'
          )}>
            {(suggestion.confidence * 100).toFixed(0)}% confidence
          </span>
        </div>
        <button onClick={onDismiss} className="text-[var(--tx-3)] hover:text-[var(--tx)] transition-colors">
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <p className="text-[10px] text-[var(--tx-3)] uppercase tracking-wide font-semibold mb-0.5">Category</p>
          <p className="text-xs font-medium text-[var(--tx)]">
            {suggestion.category}
            {suggestion.subcategory && <span className="text-[var(--tx-3)]"> / {suggestion.subcategory}</span>}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-[var(--tx-3)] uppercase tracking-wide font-semibold mb-0.5">Priority</p>
          <p className="text-xs font-medium capitalize text-[var(--tx)]">{suggestion.priority}</p>
        </div>
        {suggestion.department && (
          <div>
            <p className="text-[10px] text-[var(--tx-3)] uppercase tracking-wide font-semibold mb-0.5">Department</p>
            <p className="text-xs font-medium text-[var(--tx)]">{suggestion.department}</p>
          </div>
        )}
        {suggestion.tags.length > 0 && (
          <div>
            <p className="text-[10px] text-[var(--tx-3)] uppercase tracking-wide font-semibold mb-0.5">Tags</p>
            <div className="flex flex-wrap gap-1">
              {suggestion.tags.map((t) => (
                <span key={t} className="pill bg-[var(--brand-xs)] text-[var(--brand)] text-[9px]">{t}</span>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <Button type="button" onClick={() => onAccept(suggestion.priority as TicketPriority, matched?.id)}>
          Accept
        </Button>
        <Button type="button" variant="ghost" onClick={onDismiss}>
          Dismiss
        </Button>
      </div>
    </div>
  );
}

// ── Form field wrapper ────────────────────────────────────────────────────────

function Field({ label, required, error, children }: { label: string; required?: boolean; error?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-sm font-medium text-[var(--tx-2)]">
        {label} {required && <span className="text-[var(--err)]">*</span>}
      </label>
      {children}
      {error && <p className="text-xs text-[var(--err)]">{error}</p>}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function CreateTicketPage() {
  const navigate = useNavigate();
  const [aiSuggestion, setAISuggestion] = useState<CategorizeResponse | null>(null);
  const [submitError,  setSubmitError]  = useState<string | null>(null);
  const [files,        setFiles]        = useState<File[]>([]);
  const [uploadNote,   setUploadNote]   = useState<string | null>(null);

  const categoriesQuery = useQuery({ queryKey: ['categories'], queryFn: getCategories, staleTime: 5 * 60_000 });
  const categories: Category[] = categoriesQuery.data ?? [];

  const { register, handleSubmit, control, setValue, watch, formState: { errors, isSubmitting } } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { priority: 'medium', tags: [] },
  });

  const aiMutation = useMutation({
    mutationFn: async () => categorizeText(watch('description'), watch('title')),
    onSuccess: (r) => setAISuggestion(r),
  });

  // Files can only be uploaded once the ticket has an id, so this is two
  // phases rather than one multipart request. The ticket is what matters: if
  // an upload fails the ticket still exists, the user lands on it, and the
  // page says which files to re-attach — rather than losing a written-out
  // problem report because a screenshot did not go through.
  const createMutation = useMutation({
    mutationFn: async (input: Parameters<typeof createTicket>[0]) => {
      const ticket = await createTicket(input);
      if (files.length === 0) return { ticket, failed: [] as string[] };

      setUploadNote(`Uploading ${files.length} file${files.length > 1 ? 's' : ''}…`);
      const outcomes = await uploadAttachments(ticket.id, files, {
        onProgress: (done, total) => setUploadNote(`Uploading file ${done} of ${total}…`),
      });
      return { ticket, failed: outcomes.filter((o) => !o.ok).map((o) => o.file.name) };
    },
    onSuccess: ({ ticket, failed }) => {
      setUploadNote(null);
      navigate(`/tickets/${ticket.id}`, {
        state: failed.length
          ? { attachmentWarning: `These files did not upload: ${failed.join(', ')}. You can attach them from this page.` }
          : undefined,
      });
    },
    onError: () => {
      setUploadNote(null);
      setSubmitError('Failed to create ticket. Please try again.');
    },
  });

  const acceptSuggestion = (priority: TicketPriority, categoryId?: string) => {
    setValue('priority', priority);
    if (categoryId) setValue('category_id', categoryId);
    if (aiSuggestion?.tags?.length) setValue('tags', aiSuggestion.tags);
    setAISuggestion(null);
  };

  const onSubmit = (values: FormValues) => {
    setSubmitError(null);
    createMutation.mutate({
      title:       values.title,
      description: values.description,
      priority:    values.priority,
      ...(values.category_id     ? { category_id: values.category_id } : {}),
      ...(values.tags.length > 0 ? { tags: values.tags }               : {}),
    });
  };

  const title       = watch('title');
  const description = watch('description');
  const canAI       = (title?.length ?? 0) >= 5 && (description?.length ?? 0) >= 20;

  return (
    <div className="flex flex-col gap-5 max-w-2xl">

      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate('/tickets')}
          className="btn-ghost !p-1.5 rounded-lg shrink-0"
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 12H5M12 5l-7 7 7 7" />
          </svg>
        </button>
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-[var(--tx)]">Create Ticket</h1>
          <p className="text-xs text-[var(--tx-3)]">Submit a new support request</p>
        </div>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">

        {/* Main content card */}
        <div className="card-sm !p-5 flex flex-col gap-4">

          <Field label="Title" required error={errors.title?.message}>
            <input
              {...register('title')}
              className={cn('input', errors.title && 'border-red-400 focus:ring-red-200')}
              placeholder="Brief summary of the issue…"
            />
          </Field>

          <Field label="Description" required error={errors.description?.message}>
            <textarea
              {...register('description')}
              rows={5}
              className={cn('input resize-y', errors.description && 'border-red-400 focus:ring-red-200')}
              placeholder="Describe the issue in detail: steps to reproduce, expected vs actual behavior, affected accounts, branch, etc."
            />
          </Field>

          {/* AI Assist */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              disabled={!canAI || aiMutation.isPending}
              onClick={() => aiMutation.mutate()}
              className={cn(
                'btn-outline h-8 text-xs gap-1.5 text-accent-600 dark:text-accent-400',
                'border-accent-300 dark:border-accent-500/40 hover:bg-accent-50 dark:hover:bg-accent-500/10',
                'disabled:opacity-40',
              )}
            >
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2a10 10 0 0 1 0 20M12 2a10 10 0 0 0 0 20M12 8v4M12 16h.01" />
              </svg>
              {aiMutation.isPending ? 'Analyzing…' : 'AI Assist'}
            </button>
            {!canAI && (
              <p className="text-xs text-[var(--tx-3)]">Add title + description to enable AI Assist</p>
            )}
            {aiMutation.isError && (
              <p className="text-xs text-[var(--err)]">AI analysis failed. Fill in manually.</p>
            )}
          </div>

          {/* AI suggestion panel */}
          {aiSuggestion && (
            <AISuggestion
              suggestion={aiSuggestion}
              categories={categories}
              onAccept={acceptSuggestion}
              onDismiss={() => setAISuggestion(null)}
            />
          )}
        </div>

        {/* Classification card */}
        <div className="card-sm !p-5">
          <h2 className="text-sm font-semibold text-[var(--tx-2)] mb-4">Classification</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Priority" required error={errors.priority?.message}>
              <select {...register('priority')} className="input">
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </Field>

            <Field label="Category">
              <select {...register('category_id')} className="input" disabled={categoriesQuery.isLoading}>
                <option value="">Select category…</option>
                {categories.map((cat) => (
                  <option key={cat.id} value={cat.id}>{cat.name} ({cat.banking_domain})</option>
                ))}
              </select>
            </Field>

            <div className="sm:col-span-2">
              <Field label="Tags">
                <Controller
                  control={control}
                  name="tags"
                  render={({ field }) => <TagInput value={field.value} onChange={field.onChange} />}
                />
              </Field>
            </div>
          </div>
        </div>

        {/* Attachments card */}
        <div className="card-sm !p-5">
          <h2 className="text-sm font-semibold text-[var(--tx-2)] mb-1">Attachments</h2>
          <p className="text-xs text-[var(--tx-3)] mb-4">
            A screenshot of the error, the statement in question, or a spreadsheet of
            the affected transactions — anything that shows the problem is usually
            faster than describing it.
          </p>
          <FileStager
            files={files}
            onChange={setFiles}
            disabled={createMutation.isPending}
            compact
          />
        </div>

        {/* Submit error */}
        {submitError && (
          <div className="card-sm flex items-center gap-2 text-sm text-[var(--err)]" style={{ borderLeft: '3px solid var(--err)' }}>
            <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" />
            </svg>
            {submitError}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-3 justify-end">
          {uploadNote && (
            <span className="text-xs text-[var(--tx-3)] mr-auto">{uploadNote}</span>
          )}
          <Button type="button" variant="ghost" onClick={() => navigate('/tickets')}>Cancel</Button>
          <Button type="submit" disabled={isSubmitting || createMutation.isPending}>
            {createMutation.isPending ? 'Creating…' : 'Create Ticket'}
          </Button>
        </div>
      </form>
    </div>
  );
}
