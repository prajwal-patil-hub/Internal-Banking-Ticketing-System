import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Badge } from '@/components/Badge';
import { useAuth } from '@/store/auth';
import { extractError } from '@/lib/api';
import { listComments, postComment } from '../workflow';
import { formatDateTime } from '@/lib/format';

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
      setBody('');
      setIsInternal(false);
      qc.invalidateQueries({ queryKey: ['comments', ticketId] });
      qc.invalidateQueries({ queryKey: ['ticket', ticketId] });
    },
    onError: (e) => setError(extractError(e).message),
  });

  return (
    <Card>
      <h3 className="font-semibold">Discussion</h3>

      <div className="mt-4 space-y-3 max-h-[420px] overflow-auto pr-1">
        {isLoading && <p className="text-sm text-slate-400">Loading…</p>}
        {!isLoading && (data?.length ?? 0) === 0 && (
          <p className="text-sm text-slate-400">No comments yet.</p>
        )}
        {data?.map((c) => (
          <div
            key={c.id}
            className={
              'rounded-xl px-4 py-3 text-sm border ' +
              (c.is_internal
                ? 'bg-amber-50 border-amber-200 dark:bg-amber-900/20 dark:border-amber-700/40'
                : 'bg-surface-muted border-slate-200 dark:bg-slate-800/40 dark:border-slate-700')
            }
          >
            <div className="flex items-center justify-between text-xs text-slate-500">
              <span><code>{c.author_id.slice(0, 8)}</code></span>
              <div className="flex items-center gap-2">
                {c.is_internal && <Badge tone="warning">internal</Badge>}
                <span>{formatDateTime(c.created_at)}</span>
              </div>
            </div>
            <p className="mt-2 whitespace-pre-wrap text-slate-800 dark:text-slate-100">{c.body}</p>
          </div>
        ))}
      </div>

      <div className="mt-4 border-t pt-4 dark:border-slate-800">
        {error && <Badge tone="danger" className="mb-2">{error}</Badge>}
        <textarea
          className="input min-h-[90px]"
          placeholder="Write a comment…"
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
        <div className="mt-2 flex items-center justify-between">
          {canInternal ? (
            <label className="text-xs text-slate-600 inline-flex items-center gap-2">
              <input
                type="checkbox"
                checked={isInternal}
                onChange={(e) => setIsInternal(e.target.checked)}
              />
              Internal note (hidden from branch user)
            </label>
          ) : <span />}

          <Button
            disabled={!body.trim() || send.isPending}
            onClick={() => { setError(null); send.mutate(); }}
          >
            {send.isPending ? 'Posting…' : 'Post comment'}
          </Button>
        </div>
      </div>
    </Card>
  );
}
