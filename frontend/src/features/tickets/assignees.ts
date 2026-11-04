import type { WorkloadEntry } from '@/features/tickets/api';

/**
 * How the assign list is ordered and labelled.
 *
 * Kept out of the component file so it can be unit-tested directly, and so
 * that file exports components only — mixing the two breaks fast refresh.
 */

export function leaveLabel(e: WorkloadEntry): string | null {
  if (!e.on_leave) return null;
  return e.leave_to ? `on leave until ${e.leave_to}` : 'on leave';
}

/**
 * Available people first, then lightest queue first.
 *
 * The order matters more than it looks: the top of this list is what a
 * supervisor will click without reading, so it has to be the person the
 * router itself would have chosen. Somebody on leave with an empty queue
 * must never sit there.
 */
export function rankCandidates(entries: WorkloadEntry[]): WorkloadEntry[] {
  return [...entries].sort(
    (a, b) => Number(a.on_leave) - Number(b.on_leave) || a.open_count - b.open_count,
  );
}
