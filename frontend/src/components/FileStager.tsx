import { useRef, useState, type DragEvent } from 'react';
import { cn } from '@/lib/cn';
import { formatSize, fileGlyph } from '@/lib/files';
import { MAX_ATTACHMENT_BYTES, ATTACHMENT_ACCEPT } from '@/features/tickets/api';

/**
 * Collects files *before* anything exists to attach them to.
 *
 * A ticket cannot own a file until it has an id, and neither can a reply. So
 * both flows hold the files here while the user is still writing, and upload
 * once the thing they belong to has been created. That is why this component
 * owns no network code at all — it hands `files` back and the page decides
 * when to send them.
 */
export function FileStager({
  files,
  onChange,
  disabled = false,
  label = 'Attachments',
  hint,
  compact = false,
}: {
  files: File[];
  onChange: (files: File[]) => void;
  disabled?: boolean;
  label?: string;
  hint?: string;
  compact?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const add = (list: FileList | null) => {
    if (!list?.length) return;
    setError(null);

    const accepted: File[] = [];
    const rejected: string[] = [];

    for (const file of Array.from(list)) {
      // The server enforces this for real; checking here just avoids spending
      // a minute uploading something that will be refused on arrival.
      if (file.size > MAX_ATTACHMENT_BYTES) {
        rejected.push(`${file.name} (${formatSize(file.size)})`);
        continue;
      }
      // Same name and size twice is a double-click, not two files.
      const duplicate = files.some((f) => f.name === file.name && f.size === file.size);
      if (!duplicate) accepted.push(file);
    }

    if (rejected.length) {
      setError(
        `Too large — the limit is ${formatSize(MAX_ATTACHMENT_BYTES)}: ${rejected.join(', ')}`,
      );
    }
    if (accepted.length) onChange([...files, ...accepted]);
  };

  const removeAt = (index: number) => {
    setError(null);
    onChange(files.filter((_, i) => i !== index));
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    if (!disabled) add(e.dataTransfer.files);
  };

  return (
    <div className="flex flex-col gap-2">
      {!compact && (
        <label className="text-xs font-medium text-[var(--tx-2)]">
          {label}
          <span className="text-[var(--tx-3)] font-normal"> (optional)</span>
        </label>
      )}

      {files.length > 0 && (
        <ul className="flex flex-col gap-1.5">
          {files.map((file, index) => {
            const glyph = fileGlyph(file.type);
            return (
              <li
                key={`${file.name}-${file.size}-${index}`}
                className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg bg-[var(--inset)]"
              >
                <svg className={cn('h-4 w-4 shrink-0', glyph.tone)} viewBox="0 0 24 24"
                     fill="none" stroke="currentColor" strokeWidth="2"
                     strokeLinecap="round" strokeLinejoin="round">
                  <path d={glyph.path} />
                </svg>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-[var(--tx)] truncate" title={file.name}>
                    {file.name}
                  </p>
                  <p className="text-[10px] text-[var(--tx-3)]">{formatSize(file.size)}</p>
                </div>
                <button
                  type="button"
                  onClick={() => removeAt(index)}
                  disabled={disabled}
                  className="text-[var(--tx-3)] hover:text-[var(--err)] transition-colors p-1 disabled:opacity-40"
                  title={`Remove ${file.name}`}
                  aria-label={`Remove ${file.name}`}
                >
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                       strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M18 6L6 18M6 6l12 12" />
                  </svg>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {error && <p className="text-xs text-[var(--err)]">{error}</p>}

      <div
        onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          'rounded-lg border border-dashed text-center transition-colors',
          compact ? 'p-2' : 'p-3',
          dragging ? 'border-[var(--brand)] bg-[var(--brand-xs)]' : 'border-[var(--line)]',
          disabled && 'opacity-50',
        )}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          disabled={disabled}
          onChange={(e) => { add(e.target.files); e.target.value = ''; }}
          accept={ATTACHMENT_ACCEPT}
        />
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={disabled}
          className="text-xs text-[var(--brand)] hover:underline disabled:opacity-50"
        >
          {compact ? 'Attach a file' : 'Choose files'}
        </button>
        <span className="text-xs text-[var(--tx-3)]"> or drag them here</span>
        {!compact && (
          <p className="text-[10px] text-[var(--tx-3)] mt-1">
            {hint ??
              `Screenshots, PDF, Word, Excel, text and CSV · up to ${formatSize(MAX_ATTACHMENT_BYTES)} each`}
          </p>
        )}
      </div>
    </div>
  );
}
