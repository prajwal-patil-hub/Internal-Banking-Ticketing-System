/**
 * File presentation helpers, shared by everything that shows an attachment.
 *
 * These lived inside the ticket attachment list until a second and third place
 * needed them — the picker on the create page and the one in the reply box. A
 * file rendered three ways in three places is how "1.4 MB" becomes "1468006"
 * on one screen and nowhere else.
 */

/** 1.4 MB rather than 1468006 bytes. */
export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** A glyph per family, so a list is scannable without reading extensions. */
export function fileGlyph(contentType: string): { path: string; tone: string } {
  if (contentType.startsWith('image/')) {
    return {
      path: 'M4 5h16v14H4zM8.5 11a1.5 1.5 0 100-3 1.5 1.5 0 000 3zM4 16l4.5-4.5L14 17',
      tone: 'text-[var(--brand)]',
    };
  }
  if (contentType === 'application/pdf') {
    return { path: 'M6 2h8l4 4v16H6zM14 2v4h4M9 13h6M9 17h4', tone: 'text-[var(--err)]' };
  }
  if (
    contentType.includes('sheet') ||
    contentType.includes('excel') ||
    contentType === 'text/csv'
  ) {
    return {
      path: 'M6 2h8l4 4v16H6zM14 2v4h4M9 12h6M9 16h6M12 12v4',
      tone: 'text-[var(--ok)]',
    };
  }
  return { path: 'M6 2h8l4 4v16H6zM14 2v4h4M9 13h6M9 17h4', tone: 'text-[var(--tx-3)]' };
}

/**
 * A browser does not always know a file's type — `file.type` is empty for
 * plenty of ordinary uploads. Fall back to the extension so a .csv picked on a
 * machine with no matching MIME registration is not rejected as "unknown".
 */
const EXTENSION_TYPES: Record<string, string> = {
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  gif: 'image/gif',
  webp: 'image/webp',
  pdf: 'application/pdf',
  txt: 'text/plain',
  csv: 'text/csv',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  xls: 'application/vnd.ms-excel',
  doc: 'application/msword',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
};

export function guessContentType(file: File): string {
  if (file.type) return file.type;
  const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
  return EXTENSION_TYPES[ext] ?? '';
}
