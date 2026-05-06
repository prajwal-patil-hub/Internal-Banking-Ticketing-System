import { Badge } from '@/components/Badge';
import type { Priority, TicketStatus } from '../types';

const STATUS_TONE: Record<TicketStatus, Parameters<typeof Badge>[0]['tone']> = {
  new: 'new',
  acknowledged: 'ack',
  assigned: 'assigned',
  in_progress: 'progress',
  on_hold: 'hold',
  escalated: 'escalated',
  resolved: 'resolved',
  closed: 'closed',
  reopened: 'reopened',
};

const PRIORITY_TONE: Record<Priority, Parameters<typeof Badge>[0]['tone']> = {
  critical: 'danger',
  high: 'warning',
  medium: 'info',
  low: 'neutral',
};

export function StatusBadge({ status }: { status: TicketStatus }) {
  return <Badge tone={STATUS_TONE[status]}>{status.replace('_', ' ')}</Badge>;
}

export function PriorityBadge({ priority }: { priority: Priority }) {
  return <Badge tone={PRIORITY_TONE[priority]}>{priority}</Badge>;
}
