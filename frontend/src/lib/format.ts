/** Time helpers tuned for SLA UI: "in 1h 12m" / "12m ago" / "—". */

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

export function formatRelative(iso: string | null | undefined, now = new Date()): string {
  if (!iso) return '—';
  const t = new Date(iso).getTime();
  const diffMs = t - now.getTime();
  const sign = diffMs >= 0 ? '' : '-';
  const abs = Math.abs(diffMs);
  const min = Math.floor(abs / 60_000);
  if (min < 1) return 'now';
  const d = Math.floor(min / 1440);
  const h = Math.floor((min - d * 1440) / 60);
  const m = min - d * 1440 - h * 60;
  const parts: string[] = [];
  if (d) parts.push(`${d}d`);
  if (h) parts.push(`${h}h`);
  if (!d && m) parts.push(`${m}m`);
  const text = parts.join(' ');
  return diffMs >= 0 ? `in ${text}` : `${sign}${text} ago`.replace('-', '');
}

export function isBreached(iso: string | null | undefined, now = new Date()): boolean {
  if (!iso) return false;
  return new Date(iso).getTime() < now.getTime();
}
