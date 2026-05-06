import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Badge } from '@/components/Badge';
import { extractError } from '@/lib/api';
import { listAttachments, uploadAttachment } from '../workflow';
import { formatDateTime } from '@/lib/format';

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function Attachments({ ticketId }: { ticketId: string }) {
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['attachments', ticketId],
    queryFn: () => listAttachments(ticketId),
  });

  const upload = useMutation({
    mutationFn: (file: File) => uploadAttachment(ticketId, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['attachments', ticketId] });
      if (inputRef.current) inputRef.current.value = '';
    },
    onError: (e) => setError(extractError(e).message),
  });

  return (
    <Card>
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">Attachments</h3>
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) { setError(null); upload.mutate(f); }
          }}
        />
        <Button variant="ghost" onClick={() => inputRef.current?.click()} disabled={upload.isPending}>
          {upload.isPending ? 'Uploading…' : '+ Upload'}
        </Button>
      </div>

      {error && <Badge tone="danger" className="mt-3">{error}</Badge>}

      <div className="mt-4 space-y-2">
        {isLoading && <p className="text-sm text-slate-400">Loading…</p>}
        {!isLoading && (data?.length ?? 0) === 0 && (
          <p className="text-sm text-slate-400">No attachments yet.</p>
        )}
        {data?.map((a) => (
          <div
            key={a.id}
            className="flex items-center justify-between rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm"
          >
            <div className="min-w-0">
              <div className="font-medium truncate">{a.file_name}</div>
              <div className="text-xs text-slate-500">
                {a.mime_type} · {humanSize(a.size_bytes)} · {formatDateTime(a.created_at)}
              </div>
            </div>
            <code className="text-xs text-slate-400">{a.checksum_sha256.slice(0, 10)}…</code>
          </div>
        ))}
      </div>
    </Card>
  );
}
