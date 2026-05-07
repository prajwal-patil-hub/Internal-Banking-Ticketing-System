import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Paperclip, Upload, FileText } from 'lucide-react';

import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Skeleton } from '@/components/Skeleton';
import { extractError } from '@/lib/api';
import { listAttachments, uploadAttachment } from '../workflow';
import { formatRelative } from '@/lib/format';

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
        <h3 className="h-card flex items-center gap-2">
          <Paperclip className="h-4 w-4 text-brand-600" />
          Attachments
        </h3>
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) { setError(null); upload.mutate(f); }
          }}
        />
        <button
          className="btn-secondary"
          onClick={() => inputRef.current?.click()}
          disabled={upload.isPending}
        >
          <Upload className="h-4 w-4" />
          {upload.isPending ? 'Uploading…' : 'Upload'}
        </button>
      </div>

      {error && <Badge tone="danger" className="mt-3">{error}</Badge>}

      <div className="mt-4 space-y-2">
        {isLoading && Array.from({ length: 2 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" rounded="2xl" />
        ))}
        {!isLoading && (data?.length ?? 0) === 0 && (
          <p className="text-sm text-ink-muted py-2">No attachments yet.</p>
        )}
        {data?.map((a) => (
          <div
            key={a.id}
            className="flex items-center gap-3 rounded-2xl bg-white/60 border border-white/50 p-3"
          >
            <span className="h-9 w-9 rounded-2xl grid place-items-center bg-brand-50 text-brand-700">
              <FileText className="h-4 w-4" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="font-medium text-sm text-ink truncate">{a.file_name}</div>
              <div className="text-2xs text-ink-muted truncate">
                {a.mime_type} · {humanSize(a.size_bytes)} · {formatRelative(a.created_at)}
              </div>
            </div>
            <code className="text-2xs text-ink-subtle hidden sm:inline">{a.checksum_sha256.slice(0, 10)}…</code>
          </div>
        ))}
      </div>
    </Card>
  );
}
