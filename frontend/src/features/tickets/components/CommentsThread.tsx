import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Send, Lock, MessageCircle } from 'lucide-react';

import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Skeleton } from '@/components/Skeleton';
import { useAuth } from '@/store/auth';
import { extractError } from '@/lib/api';
import { listComments, postComment } from '../workflow';
import { formatRelative } from '@/lib/format';
import { cn } from '@/lib/cn';

export function CommentsThread({ ticketId }: { ticketId: string }) {
  const qc = useQueryClient();
  const { hasRole } = useAuth();
  const canInternal = hasRole('agent', 'supervisor', 'admin');

  const [body, setBody] = useState('');
  const [isInternal, setIsInternal] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['comments', ticketId],
    queryFn: () => listComments(ticketId),
  });

  const send = useMutation({
    mutationFn: () => postComment(ticketId, body, isInternal),
    onSuccess: () => {
      setBody(''); setIsInternal(false);
      qc.invalidateQueries({ queryKey: ['comments', ticketId] });
      qc.invalidateQueries({ queryKey: ['ticket', ticketId] });
    },
    onError: (e) => setError(extractError(e).message),
  });

  return (
    <Card padded={false} className="overflow-hidden">
      <div className="px-6 pt-5 pb-4 flex items-center justify-between">
        <div>
          <h3 className="h-card flex items-center gap-2">
            <MessageCircle className="h-4 w-4 text-brand-600" />
            Discussion
          </h3>
          <p className="text-xs text-ink-muted mt-0.5">Comments and internal notes for this ticket.</p>
        </div>
        <Badge tone="neutral">{data?.length ?? 0} comments</Badge>
      </div>

      <div className="px-6 pb-4">
        <div className="space-y-3 max-h-[460px] overflow-auto pr-1">
          {isLoading && Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" rounded="2xl" />
          ))}
          {!isLoading && (data?.length ?? 0) === 0 && (
            <div className="py-8 text-center text-sm text-ink-muted">
              No comments yet — start the conversation below.
            </div>
          )}
          {data?.map((c) => (
            <article
              key={c.id}
              className={cn(
                'rounded-2xl p-4 text-sm',
                c.is_internal
                  ? 'bg-warning-soft border-l-[3px] border-warning'
                  : 'bg-white/70 border border-white/50',
              )}
            >
              <div className="flex items-center justify-between text-2xs text-ink-muted">
                <div className="flex items-center gap-2">
                  <span className="h-7 w-7 rounded-pill grid place-items-center bg-brand-50 text-brand-700 font-semibold text-xs">
                    {c.author_id.slice(0, 2).toUpperCase()}
                  </span>
                  <code className="text-ink">{c.author_id.slice(0, 8)}</code>
                </div>
                <div className="flex items-center gap-2">
                  {c.is_internal && (
                    <span className="inline-flex items-center gap-1 pill bg-warning-soft text-warning-deep">
                      <Lock className="h-3 w-3" /> Internal
                    </span>
                  )}
                  <span>{formatRelative(c.created_at)}</span>
                </div>
              </div>
              <p className="mt-2.5 text-ink whitespace-pre-wrap leading-relaxed">{c.body}</p>
            </article>
          ))}
        </div>
      </div>

      <div className="border-t border-white/40 px-6 py-4 bg-white/40">
        {error && <Badge tone="danger" className="mb-2">{error}</Badge>}
        <textarea
          className="input min-h-[88px] resize-y"
          placeholder="Write a comment…"
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
        <div className="mt-3 flex items-center justify-between">
          {canInternal ? (
            <label className="text-xs text-ink-muted inline-flex items-center gap-2 select-none cursor-pointer">
              <input
                type="checkbox"
                checked={isInternal}
                onChange={(e) => setIsInternal(e.target.checked)}
                className="rounded"
              />
              <Lock className="h-3.5 w-3.5" /> Internal note (hidden from branch user)
            </label>
          ) : <span />}
          <button
            disabled={!body.trim() || send.isPending}
            onClick={() => { setError(null); send.mutate(); }}
            className="btn-primary"
          >
            <Send className="h-4 w-4" />
            {send.isPending ? 'Posting…' : 'Post comment'}
          </button>
        </div>
      </div>
    </Card>
  );
}
