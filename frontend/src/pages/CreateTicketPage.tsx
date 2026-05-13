import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { cn } from '@/lib/cn';
import { createTicket, getCategories } from '@/features/tickets/api';
import { categorizeText } from '@/features/ai/api';
import type { TicketPriority, Category } from '@/features/tickets/api';
import type { CategorizeResponse } from '@/features/ai/api';

// ---------- Schema ----------

const schema = z.object({
  title: z.string().min(5, 'Title must be at least 5 characters').max(200, 'Title too long'),
  description: z.string().min(20, 'Description must be at least 20 characters').max(10000, 'Description too long'),
  priority: z.enum(['critical', 'high', 'medium', 'low'] as const),
  category_id: z.string().optional(),
  tags: z.array(z.string()),
});

type FormValues = z.infer<typeof schema>;

// ---------- Tag input ----------

function TagInput({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const [tagInput, setTagInput] = useState('');

  const addTag = (tag: string) => {
    const trimmed = tag.trim().toLowerCase().replace(/\s+/g, '-');
    if (trimmed && !value.includes(trimmed) && value.length < 10) {
      onChange([...value, trimmed]);
    }
    setTagInput('');
  };

  const removeTag = (tag: string) => {
    onChange(value.filter((t) => t !== tag));
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2 min-h-[36px]">
        {value.map((tag) => (
          <span
            key={tag}
            className="pill bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300 gap-1.5"
          >
            {tag}
            <button
              type="button"
              onClick={() => removeTag(tag)}
              className="hover:text-brand-900 dark:hover:text-brand-100"
            >
              <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          className="input flex-1"
          placeholder="Add tag and press Enter…"
          value={tagInput}
          onChange={(e) => setTagInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              addTag(tagInput);
            }
            if (e.key === 'Backspace' && !tagInput && value.length > 0) {
              removeTag(value[value.length - 1]);
            }
          }}
        />
        <Button
          type="button"
          variant="ghost"
          disabled={!tagInput.trim()}
          onClick={() => addTag(tagInput)}
        >
          Add
        </Button>
      </div>
    </div>
  );
}

// ---------- AI Suggestion panel ----------

interface AISuggestionProps {
  suggestion: CategorizeResponse;
  categories: Category[];
  onAccept: (priority: TicketPriority, categoryId?: string) => void;
  onDismiss: () => void;
}

function AISuggestion({ suggestion, categories, onAccept, onDismiss }: AISuggestionProps) {
  const matchedCategory = categories.find(
    (c) => c.code === suggestion.category || c.name.toLowerCase() === suggestion.category.toLowerCase(),
  );

  return (
    <div className="p-4 rounded-xl border-2 border-accent-300 dark:border-accent-500/50 bg-accent-50 dark:bg-accent-500/10">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <div className="h-7 w-7 rounded-lg bg-accent-200 dark:bg-accent-500/30 flex items-center justify-center">
            <svg className="h-4 w-4 text-accent-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a10 10 0 0 1 0 20M12 2a10 10 0 0 0 0 20M12 8v4M12 16h.01" />
            </svg>
          </div>
          <span className="text-sm font-semibold text-accent-700 dark:text-accent-400">AI Suggestion</span>
          <span className={cn('pill text-xs',
            suggestion.confidence >= 0.8 ? 'bg-emerald-100 text-emerald-700' :
            suggestion.confidence >= 0.5 ? 'bg-amber-100 text-amber-700' :
            'bg-red-100 text-red-700'
          )}>
            {(suggestion.confidence * 100).toFixed(0)}% confidence
          </span>
        </div>
        <button onClick={onDismiss} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300">
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div>
          <p className="text-xs text-slate-500 mb-1">Suggested Category</p>
          <p className="text-sm font-medium text-slate-800 dark:text-slate-200">
            {suggestion.category}
            {suggestion.subcategory && <span className="text-slate-500"> / {suggestion.subcategory}</span>}
          </p>
        </div>
        <div>
          <p className="text-xs text-slate-500 mb-1">Suggested Priority</p>
          <p className="text-sm font-medium capitalize text-slate-800 dark:text-slate-200">{suggestion.priority}</p>
        </div>
        {suggestion.department && (
          <div>
            <p className="text-xs text-slate-500 mb-1">Department</p>
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200">{suggestion.department}</p>
          </div>
        )}
        {suggestion.tags.length > 0 && (
          <div>
            <p className="text-xs text-slate-500 mb-1">Suggested Tags</p>
            <div className="flex flex-wrap gap-1">
              {suggestion.tags.map((t) => (
                <span key={t} className="pill bg-accent-100 text-accent-700 dark:bg-accent-500/20 dark:text-accent-400 text-[10px]">{t}</span>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <Button
          type="button"
          onClick={() =>
            onAccept(suggestion.priority as TicketPriority, matchedCategory?.id)
          }
        >
          Accept Suggestion
        </Button>
        <Button type="button" variant="ghost" onClick={onDismiss}>
          Dismiss
        </Button>
      </div>
    </div>
  );
}

// ---------- Main page ----------

export function CreateTicketPage() {
  const navigate = useNavigate();
  const [aiSuggestion, setAISuggestion] = useState<CategorizeResponse | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const categoriesQuery = useQuery({
    queryKey: ['categories'],
    queryFn: getCategories,
    staleTime: 5 * 60_000,
  });

  const categories: Category[] = categoriesQuery.data ?? [];

  const {
    register,
    handleSubmit,
    control,
    setValue,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      priority: 'medium',
      tags: [],
    },
  });

  const aiAssistMutation = useMutation({
    mutationFn: async () => {
      const title = watch('title');
      const description = watch('description');
      return categorizeText(`${description}`, title);
    },
    onSuccess: (result) => setAISuggestion(result),
  });

  const acceptSuggestion = (priority: TicketPriority, categoryId?: string) => {
    setValue('priority', priority);
    if (categoryId) setValue('category_id', categoryId);
    if (aiSuggestion?.tags?.length) {
      setValue('tags', aiSuggestion.tags);
    }
    setAISuggestion(null);
  };

  const createMutation = useMutation({
    mutationFn: createTicket,
    onSuccess: (ticket) => navigate(`/tickets/${ticket.id}`),
    onError: () => setSubmitError('Failed to create ticket. Please try again.'),
  });

  const onSubmit = (values: FormValues) => {
    setSubmitError(null);
    createMutation.mutate({
      title: values.title,
      description: values.description,
      priority: values.priority,
      ...(values.category_id ? { category_id: values.category_id } : {}),
      ...(values.tags.length > 0 ? { tags: values.tags } : {}),
    });
  };

  const titleValue = watch('title');
  const descriptionValue = watch('description');
  const canAIAssist = titleValue?.length >= 5 && descriptionValue?.length >= 20;

  return (
    <div className="flex flex-col gap-6 max-w-3xl">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button
          onClick={() => navigate('/tickets')}
          className="h-9 w-9 rounded-xl border border-slate-200 dark:border-slate-700 flex items-center justify-center hover:bg-surface-subtle dark:hover:bg-slate-800 transition-colors"
        >
          <svg className="h-4 w-4 text-slate-600 dark:text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 12H5M12 5l-7 7 7 7" />
          </svg>
        </button>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Create Ticket</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Submit a new support ticket for resolution</p>
        </div>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-6">
        {/* Main form card */}
        <Card>
          <div className="flex flex-col gap-5">
            {/* Title */}
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
                Title <span className="text-red-500">*</span>
              </label>
              <input
                {...register('title')}
                className={cn('input', errors.title && 'border-red-500 focus:ring-red-200')}
                placeholder="Brief summary of the issue…"
              />
              {errors.title && (
                <p className="text-xs text-red-600">{errors.title.message}</p>
              )}
            </div>

            {/* Description */}
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
                Description <span className="text-red-500">*</span>
              </label>
              <textarea
                {...register('description')}
                rows={8}
                className={cn('input resize-none', errors.description && 'border-red-500 focus:ring-red-200')}
                placeholder="Describe the issue in detail. Include steps to reproduce, expected vs actual behavior, affected accounts/branches, etc."
              />
              {errors.description && (
                <p className="text-xs text-red-600">{errors.description.message}</p>
              )}
            </div>

            {/* AI Assist button */}
            <div className="flex items-center gap-3">
              <Button
                type="button"
                variant="ghost"
                disabled={!canAIAssist || aiAssistMutation.isPending}
                onClick={() => aiAssistMutation.mutate()}
                className="border border-accent-300 dark:border-accent-500/40 text-accent-600 dark:text-accent-400 hover:bg-accent-50 dark:hover:bg-accent-500/10"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2a10 10 0 0 1 0 20M12 2a10 10 0 0 0 0 20M12 8v4M12 16h.01" />
                </svg>
                {aiAssistMutation.isPending ? 'Analyzing…' : 'AI Assist'}
              </Button>
              {!canAIAssist && (
                <p className="text-xs text-slate-400">Fill in title and description to use AI Assist</p>
              )}
              {aiAssistMutation.isError && (
                <p className="text-xs text-red-600">AI analysis failed. Try again or fill in manually.</p>
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
        </Card>

        {/* Settings card */}
        <Card>
          <h2 className="text-base font-semibold mb-4">Classification</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            {/* Priority */}
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
                Priority <span className="text-red-500">*</span>
              </label>
              <select {...register('priority')} className="input">
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
              {errors.priority && (
                <p className="text-xs text-red-600">{errors.priority.message}</p>
              )}
            </div>

            {/* Category */}
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
                Category
              </label>
              <select
                {...register('category_id')}
                className="input"
                disabled={categoriesQuery.isLoading}
              >
                <option value="">Select category…</option>
                {categories.map((cat) => (
                  <option key={cat.id} value={cat.id}>
                    {cat.name} ({cat.banking_domain})
                  </option>
                ))}
              </select>
            </div>

            {/* Tags — span full width */}
            <div className="sm:col-span-2 flex flex-col gap-1.5">
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
                Tags
              </label>
              <Controller
                control={control}
                name="tags"
                render={({ field }) => (
                  <TagInput value={field.value} onChange={field.onChange} />
                )}
              />
              <p className="text-xs text-slate-400">Press Enter to add a tag. Maximum 10 tags.</p>
            </div>
          </div>
        </Card>

        {/* Submit error */}
        {submitError && (
          <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 text-sm">
            <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" />
            </svg>
            {submitError}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-3 justify-end">
          <Button type="button" variant="ghost" onClick={() => navigate('/tickets')}>
            Cancel
          </Button>
          <Button
            type="submit"
            disabled={isSubmitting || createMutation.isPending}
          >
            {createMutation.isPending ? 'Creating…' : 'Create Ticket'}
          </Button>
        </div>
      </form>
    </div>
  );
}
