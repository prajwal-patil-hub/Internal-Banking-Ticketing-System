import { useRef, useState, type DragEvent } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { cn } from '@/lib/cn';
import { extractError } from '@/lib/api';
import { useAuth } from '@/store/auth';
import {
  listAttachments,
  uploadAttachment,
  downloadAttachment,
  deleteAttachment,
  MAX_ATTACHMENT_BYTES,
  type Attachment,
} from '@/features/tickets/api';

/** 1.4 MB rather than 1468006 bytes. */
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** A glyph per family, so the list is scannable without reading extensions. */
function fileGlyph(contentType: string): { path: string; tone: string } {
  if (contentType.startsWith('image/')) {
    return { path: 'M4 5h16v14H4zM8.5 11a1.5 1.5 0 100-3 1.5 1.5 0 000 3zM4 16l4.5-4.5L14 17', tone: 'text-[var(--brand)]' };
  }
  if (contentType === 'application/pdf') {
    return { path: 'M6 2h8l4 4v16H6zM14 2v4h4M9 13h6M9 17h4', tone: 'text-[var(--err)]' };
  }
  if (contentType.includes('sheet') || contentType.includes('excel') || contentType === 'text/csv') {
    return { path: 'M6 2h8l4 4v16H6zM14 2v4h4M9 12h6M9 16h6M12 12v4', tone: 'text-[var(--ok)]' };
  }
  return { path: 'M6 2h8l4 4v16H6zM14 2v4h4M9 13h6M9 17h4', tone: 'text-[var(--tx-3)]' };
}

export function TicketAttachments({
  ticketId, canModify,
}: { ticketId: string; canModify: boolean }) {
  const queryClient = useQueryClient();
  const userId = useAuth((s) => s.user?.id);
  const role = useAuth((s) => s.user?.role);
  const isAgentLike = role === 'agent' || role === 'supervisor' || role === 'admin';

  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: files = [], isLoading } = useQuery({
    queryKey: ['attachments', ticketId],
    queryFn: () => listAttachments(ticketId),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['attachments', ticketId] });

  const upload = useMutation({
    mutationFn: (file: File) => uploadAttachment(ticketId, file),
    onSuccess: () => { setError(null); refresh(); },
    onError: (e) => setError(extractError(e).message),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteAttachment(ticketId, id),
    onSuccess: refresh,
    onError: (e) => setError(extractError(e).message),
  });

  const handleFiles = (list: FileList | null) => {
    if (!list?.length) return;
    setError(null);
    for (const file of Array.from(list)) {
      // Checked here purely to fail fast — the server enforces it for real.
      if (file.size > MAX_ATTACHMENT_BYTES) {
        setError(
          `${file.name} is ${formatSize(file.size)} — the limit is ` +
          `${formatSize(MAX_ATTACHMENT_BYTES)}.`,
        );
        continue;
      }
      upload.mutate(file);
    }
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    if (canModify) handleFiles(e.dataTransfer.files);
  };

  const canDelete = (a: Attachment) =>
    canModify && (isAgentLike || a.uploader?.id === userId);

  return (
    <div className="card-sm flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[var(--tx)]">
          Attachments {files.length > 0 && (
            <span className="text-[var(--tx-3)] font-normal">({files.length})</span>
          )}
        </h2>
        {upload.isPending && (
          <span className="text-xs text-[var(--tx-3)]">Uploading…</span>
        )}
      </div>

      {error && <p className="text-xs text-[var(--err)]">{error}</p>}

      {isLoading ? (
        <div className="animate-pulse h-10 rounded-lg bg-[var(--inset)]" />
      ) : files.length === 0 ? (
        <p className="text-xs text-[var(--tx-3)]">No files attached yet.</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {files.map((a) => {
            const glyph = fileGlyph(a.content_type);
            return (
              <li
                key={a.id}
                className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg bg-[var(--inset)] group"
              >
                <svg className={cn('h-4 w-4 shrink-0', glyph.tone)} viewBox="0 0 24 24"
                     fill="none" stroke="currentColor" strokeWidth="2"
                     strokeLinecap="round" strokeLinejoin="round">
                  <path d={glyph.path} />
                </svg>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-[var(--tx)] truncate" title={a.filename}>
                    {a.filename}
                  </p>
                  <p className="text-[10px] text-[var(--tx-3)]">
                    {formatSize(a.size_bytes)}
                    {a.uploader && ` · ${a.uploader.full_name}`}
                  </p>
                </div>
                <button
                  onClick={() => downloadAttachment(ticketId, a).catch((e) => setError(extractError(e).message))}
                  className="text-[var(--tx-3)] hover:text-[var(--brand)] transition-colors p-1"
                  title={`Download ${a.filename}`}
                  aria-label={`Download ${a.filename}`}
                >
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                       strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" />
                  </svg>
                </button>
                {canDelete(a) && (
                  <button
                    onClick={() => remove.mutate(a.id)}
                    disabled={remove.isPending}
                    className="text-[var(--tx-3)] hover:text-[var(--err)] transition-colors p-1 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                    title={`Remove ${a.filename}`}
                    aria-label={`Remove ${a.filename}`}
                  >
                    <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" />
                    </svg>
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {canModify && (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            'rounded-lg border border-dashed p-3 text-center transition-colors',
            dragging
              ? 'border-[var(--brand)] bg-[var(--brand-xs)]'
              : 'border-[var(--line)]',
          )}
        >
          <input
            ref={inputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => { handleFiles(e.target.files); e.target.value = ''; }}
            accept="image/*,.pdf,.txt,.csv,.xlsx,.xls,.doc,.docx"
          />
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={upload.isPending}
            className="text-xs text-[var(--brand)] hover:underline disabled:opacity-50"
          >
            Choose a file
          </button>
          <span className="text-xs text-[var(--tx-3)]"> or drag it here</span>
          <p className="text-[10px] text-[var(--tx-3)] mt-1">
            Images, PDF, text, CSV and Office documents · up to {formatSize(MAX_ATTACHMENT_BYTES)}
          </p>
        </div>
      )}
    </div>
  );
}
